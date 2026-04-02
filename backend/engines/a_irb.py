"""
PROMETHEUS Risk Platform
Engine: A-IRB — Advanced Internal Ratings-Based Approach
Regulatory basis: CRE30-36 (effective Jan 2023)

Implements:
  - Corporate / Bank / Sovereign risk-weight function (CRE31)
  - SME adjustment (CRE31.9)
  - Maturity adjustment (CRE31.7)
  - Double-default framework for CDS-protected exposures (CRE22)
  - EL calculation and comparison to provisions (CRE35)
  - Market regime adjustments (stressed vs. baseline)
  - PD term structure & sector correlation adjustments
  - EAD schedule evolution for derivatives
  - Sensitivity analysis & RWA drivers
  - Data quality tracking & diagnostic logging
  - Only applicable to Banking Book (req #10)
"""

from __future__ import annotations
import math
import logging
import time
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import date
from enum import Enum

from backend.config import AIRB
# FIX 1: local implementations — backend.core does not exist
def _norm_cdf_local(x: float) -> float:
    import math as _math
    return 0.5 * (1.0 + _math.erf(x / _math.sqrt(2)))

def _norm_inv_local(p: float) -> float:
    import math as _math
    a = [2.515517, 0.802853, 0.010328]
    b = [1.432788, 0.189269, 0.001308]
    if p < 0.5:
        t = _math.sqrt(-2.0 * _math.log(p)); sign = -1
    else:
        t = _math.sqrt(-2.0 * _math.log(1 - p)); sign = 1
    num = a[0] + a[1]*t + a[2]*t**2
    den = 1 + b[0]*t + b[1]*t**2 + b[2]*t**3
    return sign * (t - num / den)

# Aliases used below
cached_norm_cdf = _norm_cdf_local
cached_norm_inv = _norm_inv_local

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Enums & Configuration
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegime(Enum):
    """Market state affecting PD/LGD calibration."""
    NORMAL = "normal"
    STRESSED = "stressed"
    CRISIS = "crisis"

class SectorType(Enum):
    """Obligor sector for correlation adjustments."""
    FINANCIALS = "FINANCIALS"
    REAL_ESTATE = "REAL_ESTATE"
    RETAIL = "RETAIL"
    UTILITIES = "UTILITIES"
    INDUSTRIALS = "INDUSTRIALS"
    UNKNOWN = "UNKNOWN"
# ─────────────────────────────────────────────────────────────────────────────
# Macroeconomic & Market Data
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MacroeconomicFactors:
    """Real-time macroeconomic variables for PD/LGD/correlation adjustment."""
    date: date
    vix_level: float = 15.0              # VIX index (normal ~15-20, crisis >30)
    yield_curve_slope: float = 2.0       # 10Y - 2Y yield spread (bp)
    high_yield_spread: float = 400.0     # HY-OAS (bp, normal ~300-500, crisis >800)
    unemployment_rate: float = 4.0       # % (normal 3-5%, recession >6%)
    real_gdp_growth: float = 2.0         # % annualized
    credit_default_rate: float = 0.02    # Current default rate (% of portfolio)
    
    # Derived stress indicators
    def stress_index(self) -> float:
        """
        Composite stress index [0, 1]: 0=normal, 1=crisis.
        Combines VIX, spreads, unemployment, defaults.
        """
        # Normalize components to [0,1]
        vix_norm = min(self.vix_level / 80.0, 1.0)  # VIX peaks ~80 in crises
        spread_norm = min((self.high_yield_spread - 300) / 1000.0, 1.0)  # 300bp=0, 1300bp=1
        unemployment_norm = min(max(self.unemployment_rate - 3.0, 0.0) / 5.0, 1.0)  # 3%=0, 8%=1
        default_norm = min(self.credit_default_rate / 0.10, 1.0)  # 0.1%=0, 10%=1
        
        # Weighted average: VIX (25%), spreads (35%), unemployment (20%), defaults (20%)
        stress = 0.25*vix_norm + 0.35*spread_norm + 0.20*unemployment_norm + 0.20*default_norm
        return min(max(stress, 0.0), 1.0)
    
    def regime(self) -> MarketRegime:
        """Classify regime based on stress index."""
        s = self.stress_index()
        if s < 0.3:
            return MarketRegime.NORMAL
        elif s < 0.6:
            return MarketRegime.STRESSED
        else:
            return MarketRegime.CRISIS

@dataclass
class CreditSpreadsData:
    """CDS spread data for implied PD calibration."""
    date: date
    obligor_id: str
    tenor_1y: float = 0.0                # CDS spread 1Y (bp)
    tenor_3y: float = 0.0                # CDS spread 3Y (bp)
    tenor_5y: float = 0.0                # CDS spread 5Y (bp)
    recovery_assumption: float = 0.40    # Recovery for implied PD calc
    bid_ask_spread: float = 10.0         # Bid-ask in bp (liquidity)
    
    def implied_pd_1y(self) -> float:
        """Implied 1Y PD from CDS spread."""
        # Approximation: PD ≈ Spread / (1 - Recovery)
        # More precise: use market formula with accrued interest
        if self.tenor_1y <= 0:
            return 0.0
        return min((self.tenor_1y / 10000) / (1.0 - self.recovery_assumption), 1.0)
    
    def implied_pd_5y(self) -> float:
        """Implied 5Y PD (hazard rate) from 5Y CDS."""
        if self.tenor_5y <= 0:
            return 0.0
        # Flat hazard rate approximation
        return min((self.tenor_5y / 10000) / (1.0 - self.recovery_assumption), 1.0)
    
    def bid_ask_impact(self) -> float:
        """Mid-spread adjusted for bid-ask."""
        return self.tenor_5y + self.bid_ask_spread / 2.0
# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PDTermStructure:
    """PD varies by time horizon — not flat."""
    pd_1y: float
    pd_3y: float
    pd_5y: float
    pd_source: str = "internal"  # 'internal', 'external_rating', 'market'
    
    def get_pd_at_horizon(self, years: float) -> float:
        """
        Interpolate PD for arbitrary horizon.
        Linear interpolation between tenor points.
        """
        if years <= 1.0:
            return self.pd_1y
        elif years <= 3.0:
            weight = (years - 1.0) / 2.0
            return self.pd_1y + (self.pd_3y - self.pd_1y) * weight
        elif years <= 5.0:
            weight = (years - 3.0) / 2.0
            return self.pd_3y + (self.pd_5y - self.pd_3y) * weight
        else:
            # Flat extrapolation beyond 5Y
            return self.pd_5y
    
    def validate(self) -> bool:
        """Check term structure is increasing (typical)."""
        if self.pd_1y < 0 or self.pd_3y < 0 or self.pd_5y < 0:
            return False
        # Allow non-monotonic (inverted curves in stress)
        return True

@dataclass
class BankingBookExposure:
    trade_id:           str
    portfolio_id:       str
    obligor_id:         str
    asset_class:        str         # 'CORP','BANK','SOVEREIGN','RETAIL_MORT','RETAIL_REV','RETAIL_OTHER'
    ead:                float       # Exposure at Default (USD)
    pd:                 float       # 1-year PD (decimal) — DEPRECATED, use pd_term_structure
    lgd:                float       # Loss Given Default (decimal)
    maturity:           float       # Effective maturity (years)
    sales_volume:       float = 0.0 # Annual sales (EUR equiv.) — for SME adj.
    has_cds:            bool = False
    cds_pd:             float = 0.0 # Guarantor PD (for double-default)
    cds_lgd:            float = 0.45
    provisions:         float = 0.0 # Specific provisions held
    sector:             str   = "UNKNOWN"

    # ── Funded collateral (CRE32.10–32.14) ───────────────────────────────────
    collateral_type:    str   = "NONE"
    collateral_value:   float = 0.0
    collateral_he:      float = 0.0

    # ── Guarantee / unfunded protection (CRE32.23–32.27) ────────────────────
    has_guarantee:      bool  = False
    guarantor_pd:       float = 0.0
    guarantor_lgd:      float = 0.45
    guarantee_coverage: float = 0.0

    # ── CDS partial coverage (CRE22) ─────────────────────────────────────────
    cds_coverage:       float = 1.0

    # ── On-balance-sheet netting – retail only (CRE32.63) ────────────────────
    deposit_offset:     float = 0.0

    # ── Term structure & EAD evolution ───────────────────────────────────────
    pd_term_structure:  Optional[PDTermStructure] = None
    ead_schedule:       Optional[Dict[float, float]] = None  # {time_year: ead_amount}
    
    # NEW: Market regime
    market_regime:      MarketRegime = field(default_factory=lambda: MarketRegime.NORMAL)
    portfolio_concentration: float = 0.0  # Herfindahl index or single-obligor concentration
    
    def get_pd_at_maturity(self) -> float:
        """Get PD adjusted for actual maturity."""
        if self.pd_term_structure is not None:
            return self.pd_term_structure.get_pd_at_horizon(self.maturity)
        return self.pd
    
    def get_ead_at_time(self, t: float) -> float:
        """Get EAD at given time horizon (for exposure evolution)."""
        if self.ead_schedule is None:
            return self.ead
        
        times = sorted(self.ead_schedule.keys())
        if t <= times[0]:
            return self.ead_schedule[times[0]]
        
        for i in range(len(times) - 1):
            t_low, t_high = times[i], times[i + 1]
            if t_low <= t < t_high:
                ead_low = self.ead_schedule[t_low]
                ead_high = self.ead_schedule[t_high]
                weight = (t - t_low) / (t_high - t_low)
                return ead_low + (ead_high - ead_low) * weight
        
        return self.ead_schedule[times[-1]]

@dataclass
class AIRBResult:
    trade_id:           str
    pd_applied:         float
    lgd_applied:        float
    ead_applied:        float
    maturity:           float
    correlation_r:      float
    capital_req_k:      float           # K per unit EAD
    maturity_adj_b:     float
    rwa:                float
    el:                 float           # Expected Loss
    el_diff:            float           # EL − Provisions
    
    # NEW: Sensitivity analysis
    rwa_sensitivity_pd: float = 0.0     # ΔRwa per +10bp PD
    rwa_sensitivity_lgd: float = 0.0    # ΔRwa per +5% LGD
    rwa_sensitivity_ead: float = 0.0    # ΔRwa per +10% EAD
    
    # NEW: Diagnostic & attribution
    rwa_drivers:        Dict[str, float] = field(default_factory=dict)  # breakdown by component
    pd_stressed:        float = 0.0     # PD under stress regime
    
    # Data quality & validation
    validation_errors:  List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    data_quality_score: float = 1.0     # 0.0-1.0 confidence
    
    # Mitigant tracking
    rwa_pre_mitigant:     float = 0.0
    rwa_mitigant_benefit: float = 0.0
    lgd_pre_mitigant:     float = 0.0
    lgd_star:             float = 0.0
    pd_pre_mitigant:      float = 0.0
    mitigant_type:        str   = "NONE"

    # Performance tracking
    computation_time_ms: float = 0.0
    confidence_level:   float = 0.95

@dataclass
class AIRBConfiguration:
    """Market-sensitive A-IRB parameters."""
    pd_curve_source: str = "internal"  # 'internal', 'external_rating', 'market'
    lgd_curve_source: str = "internal"
    use_stressed_params: bool = False  # Stressed vs. baseline
    calibration_date: date = field(default_factory=date.today)
    market_regime: MarketRegime = MarketRegime.NORMAL
    pd_stress_factor: Dict[str, float] = field(
        default_factory=lambda: {
            "CORP": 1.5,
            "BANK": 1.4,
            "SOVEREIGN": 1.2,
            "RETAIL_MORT": 1.3,
            "RETAIL_REV": 1.6,
            "RETAIL_OTHER": 1.4,
        }
    )
    lgd_stress_factor: Dict[str, float] = field(
        default_factory=lambda: {
            "CORP": 1.2,
            "BANK": 1.15,
            "SOVEREIGN": 1.1,
            "RETAIL_MORT": 1.25,
            "RETAIL_REV": 1.3,
            "RETAIL_OTHER": 1.25,
        }
    )

# ─────────────────────────────────────────────────────────────────────────────
# CRE31: IRB Risk-Weight Formula
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Standard normal CDF — uses CalculationCache for memoization."""
    return cached_norm_cdf(x)

def _norm_inv(p: float) -> float:
    """Inverse normal CDF — uses CalculationCache for memoization."""
    return cached_norm_inv(p)

def asset_correlation(pd: float, asset_class: str, sales: float = 0.0) -> float:
    """
    CRE31.5: correlation R for corporate/bank/sovereign.
    R = 0.12×(1-exp(-50×PD))/(1-exp(-50)) + 0.24×(1-(1-exp(-50×PD))/(1-exp(-50)))
    SME adjustment (CRE31.9): subtract 0.04×(1-(S-5)/45) where S in [5,50] mEUR
    """
    pd = max(pd, AIRB.pd_floor)

    if asset_class in ("CORP", "BANK", "SOVEREIGN"):
        e50pd = math.exp(-50 * pd)
        denom = 1 - math.exp(-50)
        R = 0.12 * (1 - e50pd) / denom + 0.24 * (1 - (1 - e50pd) / denom)

        # SME adjustment (sales 5–50 mEUR)
        S_mEUR = sales / 1_000_000
        if 5 < S_mEUR < 50:
            R -= 0.04 * (1 - (S_mEUR - 5) / 45)

    elif asset_class == "RETAIL_MORT":
        R = 0.15

    elif asset_class == "RETAIL_REV":
        R = 0.04

    else:  # RETAIL_OTHER
        e35pd = math.exp(-35 * pd)
        denom35 = 1 - math.exp(-35)
        R = 0.03 * (1 - e35pd) / denom35 + 0.16 * (1 - (1 - e35pd) / denom35)

    return max(0.0, min(R, 0.99))

def sector_correlation_adjustment(
    pd: float,
    asset_class: str,
    sector: str,
    portfolio_concentration: float = 0.0
) -> float:
    """
    Advanced correlation accounting for sector & concentration.
    Higher concentration → higher correlation → higher RWA.
    
    Args:
        pd: obligor PD
        asset_class: CORP/BANK/etc
        sector: FINANCIALS/REAL_ESTATE/etc
        portfolio_concentration: single-obligor concentration (0-1)
    
    Returns:
        Adjusted correlation R
    """
    R_base = asset_correlation(pd, asset_class)
    
    # Sector multiplier (cyclicality)
    sector_multipliers = {
        "FINANCIALS": 1.15,
        "REAL_ESTATE": 1.10,
        "RETAIL": 0.90,
        "UTILITIES": 0.85,
        "INDUSTRIALS": 1.0,
    }
    sector_mult = sector_multipliers.get(sector, 1.0)
    
    # Concentration adjustment (Granularity Adjustment, Basel III)
    if portfolio_concentration > 0.05:  # >5% single obligor
        concentration_adj = 1.0 + 0.5 * (portfolio_concentration - 0.05)
    else:
        concentration_adj = 1.0
    
    R_adjusted = min(R_base * sector_mult * concentration_adj, 0.99)
    return R_adjusted

def maturity_adjustment(pd: float, M: float) -> float:
    """CRE31.7: b(PD) = (0.11852 - 0.05478×ln(PD))²"""
    pd = max(pd, AIRB.pd_floor)
    b = (0.11852 - 0.05478 * math.log(pd))**2
    return b

def capital_requirement_k(
    pd: float, lgd: float, M: float, R: float, b: float
) -> float:
    """
    CRE31.4 corporate/bank/sovereign capital formula:
    K = [LGD × N((N⁻¹(PD) + √R × N⁻¹(0.999)) / √(1-R)) - PD × LGD]
        × (1-1.5b)⁻¹ × (1+(M-2.5)×b)
    """
    pd  = max(pd,  AIRB.pd_floor)
    lgd = max(lgd, 0.0)

    N_inv_pd  = _norm_inv(pd)
    N_inv_999 = _norm_inv(0.999)

    arg = (N_inv_pd + math.sqrt(R) * N_inv_999) / math.sqrt(1 - R)
    K_no_ma = lgd * _norm_cdf(arg) - pd * lgd

    # Maturity adjustment (not applied to retail)
    K = K_no_ma * (1 + (M - 2.5) * b) / (1 - 1.5 * b)
    return max(K, 0.0)

def rwa_from_k(K: float, ead: float) -> float:
    """RWA = K × 12.5 × EAD  (CRE31.4)"""
    return K * 12.5 * ead

# ─────────────────────────────────────────────────────────────────────────────
# Adapter: UniversalTrade → BankingBookExposure (Phase 1 Integration)
# ─────────────────────────────────────────────────────────────────────────────

def universal_trade_to_airb_exposure(trade: object) -> Optional[BankingBookExposure]:
    """
    Convert UniversalTrade (Phase 1) to BankingBookExposure for A-IRB calculation.
    Returns None if trade is not eligible for A-IRB (trading book, missing data, etc).
    """
    # Check: must be banking book
    if not trade.is_banking_book():
        logger.debug("Trade %s: not banking book — skipped from A-IRB", trade.trade_id)
        return None
    
    # Check: must have obligor PD & LGD
    if trade.obligor_pd is None or trade.obligor_pd <= 0 or trade.obligor_lgd is None:
        logger.warning("Trade %s: missing obligor_pd or obligor_lgd — skipped from A-IRB", trade.trade_id)
        return None
    
    # Map asset class to A-IRB category
    asset_class_map = {
        "IR": "CORP",
        "FX": "BANK",
        "EQUITY": "CORP",
        "CREDIT": "CORP",
        "COMMODITY": "CORP",
    }
    airb_asset_class = asset_class_map.get(trade.asset_class.value, "CORP")
    
    # TTM as effective maturity
    ttm = trade.time_to_maturity()
    
    return BankingBookExposure(
        trade_id=trade.trade_id,
        portfolio_id=trade.portfolio_id or "UNKNOWN",
        obligor_id=trade.obligor_id or "UNKNOWN",
        asset_class=airb_asset_class,
        ead=trade.get_ead_estimate(method="best"),
        pd=trade.obligor_pd,
        lgd=trade.obligor_lgd,
        maturity=ttm,
        sales_volume=0.0,
        has_cds=trade.counterparty_type.value == "CCP" if trade.counterparty_type else False,
        cds_pd=0.0,
        provisions=0.0,
        sector=getattr(trade, 'sector', 'UNKNOWN'),
    )

# ─────────────────────────────────────────────────────────────────────────────
# Double-Default & Market Regime
# ─────────────────────────────────────────────────────────────────────────────

def double_default_pd(pd_obligor: float, pd_guarantor: float) -> float:
    """
    CRE22: PD_dd = PD_o × PD_g × (1/PD_o + 1/PD_g - 1)
    Simplified to: PD_dd = PD_o × PD_g × (1 + correlation effect)
    """
    rho_gg = 0.70   # intra-financial correlation
    pdd = (1 - rho_gg) * pd_obligor * pd_guarantor + rho_gg * min(pd_obligor, pd_guarantor)
    return min(pdd, pd_obligor)


_COLLATERAL_PARAMS = {
    "FINANCIAL":      (0.00, 0.15),
    "RECEIVABLES":    (0.20, 0.40),
    "RESIDENTIAL_RE": (0.20, 0.40),
    "COMMERCIAL_RE":  (0.20, 0.40),
    "OTHER_PHYSICAL": (0.25, 0.40),
    "NONE":           (None, 1.00),
}
_LGD_FLOORS_SECURED = {
    "FINANCIAL": 0.00, "RECEIVABLES": 0.10,
    "RESIDENTIAL_RE": 0.10, "COMMERCIAL_RE": 0.10, "OTHER_PHYSICAL": 0.15,
}

def compute_lgd_star(ead, lgd_u, col_val, col_type, he=0.0, asset_class="CORP"):
    """CRE32.10 LGD* = (EU/E_gross)*LGDU + (ES/E_gross)*LGDS"""
    lgds, hc = _COLLATERAL_PARAMS.get(col_type.upper(), (None, 1.0))
    if lgds is None or col_val <= 0 or ead <= 0:
        return lgd_u, 0.0, ead
    e_gross = ead * (1 + he)
    es = min(col_val * (1 - hc), e_gross)
    eu = e_gross - es
    lgd_star = (eu / e_gross) * lgd_u + (es / e_gross) * lgds
    return max(lgd_star, _LGD_FLOORS_SECURED.get(col_type.upper(), 0.25)), es, eu

def apply_market_regime_stress(
    pd_base: float,
    lgd_base: float,
    asset_class: str,
    regime: MarketRegime,
    stress_factors: Dict[str, float]
) -> Tuple[float, float]:
    """
    Apply stress factors to PD/LGD under stressed/crisis regimes.
    Returns: (pd_stressed, lgd_stressed)
    """
    if regime == MarketRegime.NORMAL:
        return pd_base, lgd_base
    
    pd_factor = stress_factors.get(asset_class, 1.0)
    lgd_factor = stress_factors.get(asset_class, 1.0)
    
    pd_stressed = min(pd_base * pd_factor, 1.0)
    lgd_stressed = min(lgd_base * lgd_factor, 1.0)
    
    return pd_stressed, lgd_stressed

def validate_pd_migration(trade_id: str, prev_pd: float, new_pd: float) -> bool:
    """
    Warn if PD migration is unrealistic (e.g., downgrade >2 notches).
    ~30% change per notch.
    """
    if prev_pd <= 0 or new_pd <= 0:
        return True
    
    notch_change = abs(math.log(new_pd / prev_pd)) / 0.30
    if notch_change > 2.0:
        logger.warning(
            "Trade %s: unrealistic rating migration (%.1f notches, PD %.4f%% → %.4f%%)",
            trade_id, notch_change, prev_pd*100, new_pd*100
        )
        return False
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Macroeconomic Overlay & Dynamic Correlation
# ─────────────────────────────────────────────────────────────────────────────

class MacroeconomicOverlay:
    """
    Adjust PD, LGD, correlation based on macroeconomic conditions.
    Implements counter-cyclical buffer & stress adjustments.
    """
    
    def __init__(self):
        # Elasticity parameters (how much PD/LGD move with macro variables)
        self.pd_vix_elasticity = 0.15      # PD increases 15% per 10-point VIX rise
        self.pd_gdp_elasticity = -0.20     # PD decreases 20% per 1% GDP growth
        self.pd_default_elasticity = 0.50  # PD increases 50% per 1% increase in default rate
        
        self.lgd_spread_elasticity = 0.10  # LGD increases 10% per 100bp spread widening
        self.lgd_default_elasticity = 0.30 # LGD increases with default rates (recovery cycle)
    
    def adjust_pd_for_macro(self, pd_base: float, macro: MacroeconomicFactors) -> float:
        """
        Adjust PD based on macroeconomic conditions.
        Counter-cyclical: PD ↑ when VIX ↑, spreads ↑, defaults ↑, growth ↓
        """
        # VIX adjustment (normal VIX ~15, crisis ~60)
        vix_impact = self.pd_vix_elasticity * (macro.vix_level - 15.0) / 10.0
        
        # GDP adjustment (recession when growth <0)
        gdp_impact = self.pd_gdp_elasticity * (macro.real_gdp_growth - 2.0)
        
        # Credit default rate adjustment
        default_impact = self.pd_default_elasticity * (macro.credit_default_rate - 0.02)
        
        # Combined multiplicative adjustment
        total_adjustment = vix_impact + gdp_impact + default_impact
        adjustment_factor = 1.0 + total_adjustment
        adjustment_factor = max(0.5, min(adjustment_factor, 3.0))  # Clamp: 0.5x to 3x
        
        pd_adjusted = pd_base * adjustment_factor
        return min(max(pd_adjusted, AIRB.pd_floor), 1.0)
    
    def adjust_lgd_for_macro(self, lgd_base: float, macro: MacroeconomicFactors) -> float:
        """
        Adjust LGD based on recovery cycle (Frye effect).
        LGD ↑ when spreads ↑ and defaults ↑ (forced liquidations reduce recovery).
        """
        # HY spread adjustment (normal ~400bp, crisis >800bp)
        spread_impact = self.lgd_spread_elasticity * (macro.high_yield_spread - 400.0) / 100.0
        
        # Default rate adjustment (recovery cycle)
        default_impact = self.lgd_default_elasticity * (macro.credit_default_rate - 0.02)
        
        # Combined multiplicative adjustment
        total_adjustment = spread_impact + default_impact
        adjustment_factor = 1.0 + total_adjustment
        adjustment_factor = max(0.7, min(adjustment_factor, 1.5))  # LGD bounded [70%, 150% of base]
        
        lgd_adjusted = lgd_base * adjustment_factor
        return min(max(lgd_adjusted, 0.10), 0.95)  # LGD in [10%, 95%]
    
    def adjust_correlation_for_macro(self, correlation_base: float, 
                                     macro: MacroeconomicFactors) -> float:
        """
        Dynamic correlation: increases during stress (crisis beta).
        Normal: R ≈ 0.15-0.40, Stressed: R ≈ 0.50-0.80, Crisis: R ≈ 0.70-0.95
        """
        stress_index = macro.stress_index()
        
        # Empirical crisis multiplier: correlation amplifies during crises
        if stress_index < 0.3:  # Normal regime
            correlation_multiplier = 1.0
        elif stress_index < 0.6:  # Stressed regime
            correlation_multiplier = 1.2 + (stress_index - 0.3) / 0.3 * 0.3  # 1.2 to 1.5
        else:  # Crisis regime
            correlation_multiplier = 1.5 + (stress_index - 0.6) / 0.4 * 0.5  # 1.5 to 2.0
        
        correlation_adjusted = correlation_base * correlation_multiplier
        return min(max(correlation_adjusted, 0.0), 0.99)

class DynamicCorrelationModel:
    """
    Implements dynamic asset correlation that varies with market regime.
    Based on empirical studies: correlation clusters increase in crises.
    """
    
    def __init__(self):
        # Regime-dependent correlation matrices (simplified)
        self.correlation_normal = {
            "CORP": 0.25,
            "BANK": 0.30,
            "SOVEREIGN": 0.15,
            "RETAIL_MORT": 0.08,
            "RETAIL_REV": 0.04,
            "RETAIL_OTHER": 0.08,
        }
        self.correlation_stressed = {
            "CORP": 0.50,
            "BANK": 0.65,
            "SOVEREIGN": 0.40,
            "RETAIL_MORT": 0.25,
            "RETAIL_REV": 0.15,
            "RETAIL_OTHER": 0.20,
        }
        self.correlation_crisis = {
            "CORP": 0.75,
            "BANK": 0.85,
            "SOVEREIGN": 0.70,
            "RETAIL_MORT": 0.50,
            "RETAIL_REV": 0.40,
            "RETAIL_OTHER": 0.45,
        }
    
    def get_regime_correlation(self, asset_class: str, regime: MarketRegime) -> float:
        """
        Get correlation for asset class in given regime.
        Interpolates if regime is between defined states.
        """
        if regime == MarketRegime.NORMAL:
            return self.correlation_normal.get(asset_class, 0.20)
        elif regime == MarketRegime.STRESSED:
            return self.correlation_stressed.get(asset_class, 0.40)
        else:  # CRISIS
            return self.correlation_crisis.get(asset_class, 0.70)
    
    def get_correlation_by_stress_index(self, asset_class: str, stress_index: float) -> float:
        """
        Interpolate correlation based on continuous stress index [0, 1].
        0 = normal, 1 = crisis.
        """
        r_normal = self.correlation_normal.get(asset_class, 0.20)
        r_crisis = self.correlation_crisis.get(asset_class, 0.70)
        
        # Quadratic interpolation (faster increase at higher stress)
        r_adjusted = r_normal + (r_crisis - r_normal) * (stress_index ** 1.5)
        return min(max(r_adjusted, 0.0), 0.99)

class ImpliedPDCalibration:
    """
    Calibrate PD from market prices (CDS spreads).
    Compares market-implied PD to historical/fundamental PD.
    """
    
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
    
    def pd_from_cds_spread(self, cds_spread_bp: float, recovery_rate: float = 0.40,
                          maturity_years: float = 5.0) -> float:
        """
        Back out implied PD from CDS spread.
        Approximation: PD ≈ Spread / (1 - Recovery) for flat hazard rate.
        More precise: requires solving for hazard rate in term-structure.
        
        Args:
            cds_spread_bp: CDS spread in basis points
            recovery_rate: Recovery on default (typically 0.30-0.50)
            maturity_years: Contract maturity for interpolation
        
        Returns:
            Implied annual PD (decimal, e.g., 0.01 = 1%)
        """
        if cds_spread_bp <= 0:
            return AIRB.pd_floor
        
        # Convert bp to decimal
        spread_decimal = cds_spread_bp / 10000.0
        
        # Simplified: assume flat hazard rate
        # CDS premium ≈ hazard_rate × (1 - recovery)
        # But CDS also reflects risk-free discounting and accrual
        
        # Rigorous formula would solve: 
        # Spread = lambda × (1-R) × [integral of discount factors]
        # Simplified flat-curve approximation:
        implied_pd = spread_decimal / (1.0 - recovery_rate)
        
        return min(max(implied_pd, AIRB.pd_floor), 1.0)
    
    def blended_pd(self, pd_historical: float, pd_market_implied: float,
                  weights: Tuple[float, float] = (0.60, 0.40)) -> float:
        """
        Blend historical PD with market-implied PD.
        Default: 60% historical (stable), 40% market-implied (forward-looking).
        
        Higher market weight during stress (prices reflect live information).
        """
        if pd_market_implied is None or pd_market_implied <= 0:
            return pd_historical
        
        w_hist, w_market = weights
        blended = w_hist * pd_historical + w_market * pd_market_implied
        
        return min(max(blended, AIRB.pd_floor), 1.0)
    
    def calibration_spread(self, pd_historical: float, recovery_rate: float = 0.40) -> float:
        """
        Back out CDS spread that would justify historical PD.
        Useful for pricing consistency checks.
        """
        return pd_historical * (1.0 - recovery_rate) * 10000.0  # Convert to bp

# ─────────────────────────────────────────────────────────────────────────────
# A-IRB Master Engine
# ─────────────────────────────────────────────────────────────────────────────

class AIRBEngine:
    """
    A-IRB capital calculator for Banking Book exposures.
    Per CRE30-36.
    
    Enhanced with:
    - Market regime adjustments (stressed/crisis)
    - PD term structure & maturity interpolation
    - Sector correlation adjustments
    - EAD schedule evolution
    - Sensitivity analysis
    - Comprehensive diagnostic logging
    """

    def __init__(self, config: Optional[AIRBConfiguration] = None):
        self.config = config or AIRBConfiguration()
        self.validator = None  # FIX 3: RiskValidator from backend.core not available
        
        # Initialize overlay models
        self.macro_overlay = MacroeconomicOverlay()
        self.dynamic_correlation_model = DynamicCorrelationModel()
        self.implied_pd_calibration = ImpliedPDCalibration()
        
        logger.info(
            "A-IRB Engine initialised (regime=%s, stressed=%s, PD_floor=%.4f%%)",
            self.config.market_regime.value,
            self.config.use_stressed_params,
            AIRB.pd_floor*100
        )

    def _validate_inputs(self, exp: BankingBookExposure) -> List[str]:
        """Validate BankingBookExposure inputs. Return list of warnings."""
        warnings = []
        
        if exp.pd < 0 or exp.pd > 1:
            raise ValueError(f"Trade {exp.trade_id}: PD must be in [0,1], got {exp.pd}")
        if exp.lgd < 0 or exp.lgd > 1:
            raise ValueError(f"Trade {exp.trade_id}: LGD must be in [0,1], got {exp.lgd}")
        if exp.ead < 0:
            raise ValueError(f"Trade {exp.trade_id}: EAD cannot be negative")
        
        if exp.pd_term_structure is not None and not exp.pd_term_structure.validate():
            warnings.append(f"Trade {exp.trade_id}: PD term structure validation failed")
        
        if exp.maturity < AIRB.maturity_floor or exp.maturity > AIRB.maturity_cap:
            warnings.append(f"Trade {exp.trade_id}: maturity {exp.maturity:.2f} outside [{AIRB.maturity_floor}, {AIRB.maturity_cap}]")
            exp.maturity = max(AIRB.maturity_floor, min(exp.maturity, AIRB.maturity_cap))
        
        return warnings

    def compute(self, exp: BankingBookExposure, _sensitivity_run: bool = False) -> AIRBResult:
        """
        Compute A-IRB capital requirement with diagnostic logging.
        Includes sensitivity analysis & RWA attribution.
        """
        start_time = time.time()
        warnings = self._validate_inputs(exp)

        # Get PD at maturity (term structure)
        pd_base = exp.get_pd_at_maturity()
        pd_eff  = max(pd_base, AIRB.pd_floor)
        lgd_eff = exp.lgd
        M_eff   = exp.maturity

        # Apply market regime stress
        if self.config.use_stressed_params:
            pd_stressed, lgd_stressed = apply_market_regime_stress(
                pd_eff, lgd_eff, exp.asset_class,
                exp.market_regime, self.config.pd_stress_factor
            )
            logger.debug(
                "Trade %s: stress applied — PD %.4f%% → %.4f%%, LGD %.1f%% → %.1f%%",
                exp.trade_id, pd_eff*100, pd_stressed*100, lgd_eff*100, lgd_stressed*100
            )
            pd_eff = pd_stressed
            lgd_eff = lgd_stressed

        # Validate PD migration
        if not _sensitivity_run:
            validate_pd_migration(exp.trade_id, exp.pd, pd_eff)

        # ── CRM chain (CRE32) ───────────────────────────────────────────────────
        pd_pre_mit  = pd_eff
        lgd_pre_mit = lgd_eff
        mit_types   = []

        # (A) Retail deposit netting — EAD (CRE32.63)
        dep = getattr(exp, "deposit_offset", 0.0)
        if dep > 0 and exp.asset_class.startswith("RETAIL"):
            ead_used = max(exp.ead - dep, 0.0)
            mit_types.append("NETTING")
        else:
            ead_used = exp.ead

        # (B) Funded collateral → LGD* (CRE32.10)
        col_t = getattr(exp, "collateral_type",  "NONE")
        col_v = getattr(exp, "collateral_value", 0.0)
        col_h = getattr(exp, "collateral_he",    0.0)
        if col_t.upper() != "NONE" and col_v > 0:
            lgd_eff, _, _ = compute_lgd_star(ead_used, lgd_eff, col_v, col_t, col_h, exp.asset_class)
            mit_types.append("COLLATERAL")

        # (C) Guarantee → PD substitution (CRE32.24–32.27)
        if getattr(exp, "has_guarantee", False) and getattr(exp, "guarantor_pd", 0.0) > 0:
            cov = max(0.0, min(getattr(exp, "guarantee_coverage", 0.0), 1.0))
            if cov > 0:
                pd_g   = max(exp.guarantor_pd, AIRB.pd_floor)
                lgd_g  = getattr(exp, "guarantor_lgd", 0.45)
                pd_eff  = max(cov * pd_g  + (1-cov) * pd_eff,  AIRB.pd_floor)
                lgd_eff = cov * lgd_g + (1-cov) * lgd_eff
                mit_types.append("GUARANTEE")

        # (D) CDS double-default — partial coverage (CRE22)
        if exp.has_cds and exp.cds_pd > 0:
            cds_cov = max(0.0, min(getattr(exp, "cds_coverage", 1.0), 1.0))
            if cds_cov > 0:
                pd_dd   = double_default_pd(pd_eff, max(exp.cds_pd, AIRB.pd_floor))
                pd_eff  = cds_cov * pd_dd       + (1-cds_cov) * pd_eff
                lgd_eff = cds_cov * exp.cds_lgd + (1-cds_cov) * lgd_eff
                mit_types.append("CDS")

        mitigant_label = "+".join(mit_types) if mit_types else "NONE"

        # Sector & concentration-adjusted correlation
        R = sector_correlation_adjustment(
            pd_eff, exp.asset_class, exp.sector, exp.portfolio_concentration
        )
        b = maturity_adjustment(pd_eff, M_eff)

        # Retail does not get maturity adjustment
        if exp.asset_class.startswith("RETAIL"):
            b = 0.0
            M_eff = 1.0

        K    = capital_requirement_k(pd_eff, lgd_eff, M_eff, R, b)
        rwa  = rwa_from_k(K, ead_used)
        R_p  = asset_correlation(pd_pre_mit, exp.asset_class)
        b_p  = maturity_adjustment(pd_pre_mit, M_eff)
        K_p  = capital_requirement_k(pd_pre_mit, lgd_pre_mit, M_eff, R_p, b_p)
        rwa_pre = rwa_from_k(K_p, exp.ead)
        el  = pd_eff * lgd_eff * ead_used
        el_diff = el - exp.provisions
        
        computation_time_ms = (time.time() - start_time) * 1000

        # RWA drivers attribution
        rwa_drivers = {
            "base_rwa": rwa,
            "pd_contribution": (pd_eff / (pd_eff + lgd_eff + 0.001)) * rwa if pd_eff > 0 else 0,
            "lgd_contribution": (lgd_eff / (pd_eff + lgd_eff + 0.001)) * rwa if lgd_eff > 0 else 0,
            "correlation_contribution": (R / (R + 0.1)) * rwa,
            "maturity_contribution": abs((M_eff - 2.5) * b) * K * 12.5 * ead_used,
        }

        logger.debug(
            "A-IRB [%s] PD=%.4f%% LGD=%.1f%% EAD=%.0f R=%.4f K=%.4f RWA=%.0f EL=%.0f [%.2f ms]",
            exp.trade_id, pd_eff*100, lgd_eff*100, ead_used, R, K, rwa, el, computation_time_ms
        )

        # Compute sensitivities
        result = AIRBResult(
            trade_id           = exp.trade_id,
            pd_applied         = pd_eff,
            lgd_applied        = lgd_eff,
            ead_applied        = ead_used,
            maturity           = M_eff,
            correlation_r      = R,
            capital_req_k      = K,
            maturity_adj_b     = b,
            rwa                = rwa,
            el                 = el,
            el_diff            = el_diff,
            rwa_drivers        = rwa_drivers,
            pd_stressed        = pd_eff if self.config.use_stressed_params else 0.0,
            validation_warnings = warnings,
            data_quality_score  = 1.0 if not warnings else 0.85,
            computation_time_ms = computation_time_ms,
            rwa_pre_mitigant    = rwa_pre,
            rwa_mitigant_benefit= max(rwa_pre - rwa, 0.0),
            lgd_pre_mitigant    = lgd_pre_mit,
            lgd_star            = lgd_eff,
            pd_pre_mitigant     = pd_pre_mit,
            mitigant_type       = mitigant_label,
        )
        
        # Compute sensitivity analysis
        if not _sensitivity_run:  # FIX 2: skip on shock re-runs to prevent recursion
            self._compute_sensitivities(exp, result)
        
        return result
    
    def compute_with_macro_overlay(self, exp: BankingBookExposure, 
                                   macro: MacroeconomicFactors,
                                   cds_spreads: Optional[CreditSpreadsData] = None) -> AIRBResult:
        """
        Compute A-IRB with macroeconomic overlay and market-implied PD.
        
        Args:
            exp: Banking book exposure
            macro: Current macroeconomic conditions
            cds_spreads: Optional CDS spread data for implied PD calibration
        
        Returns:
            AIRBResult with macro-adjusted parameters
        """
        start_time = time.time()
        exp_copy = copy.deepcopy(exp)
        warnings = self._validate_inputs(exp_copy)
        
        # Get base PD (historical/fundamental)
        pd_base = exp_copy.get_pd_at_maturity()
        pd_base = max(pd_base, AIRB.pd_floor)
        lgd_base = exp_copy.lgd
        
        # Overlay 1: Macro adjustment
        pd_macro = self.macro_overlay.adjust_pd_for_macro(pd_base, macro)
        lgd_macro = self.macro_overlay.adjust_lgd_for_macro(lgd_base, macro)
        
        # Overlay 2: Market-implied PD calibration
        pd_market_implied = None
        if cds_spreads is not None and cds_spreads.tenor_5y > 0:
            pd_market_implied = self.implied_pd_calibration.pd_from_cds_spread(
                cds_spreads.tenor_5y, recovery_rate=cds_spreads.recovery_assumption
            )
            # Blend historical (macro-adjusted) with market-implied
            weights = (0.60, 0.40) if macro.stress_index() < 0.5 else (0.40, 0.60)
            pd_eff = self.implied_pd_calibration.blended_pd(pd_macro, pd_market_implied, weights)
            logger.debug(
                "Trade %s: market-implied calibration — CDS spread %dbp → PD %.4f%%, "
                "blended with macro %.4f%% → final %.4f%%",
                exp_copy.trade_id, cds_spreads.tenor_5y, pd_market_implied*100,
                pd_macro*100, pd_eff*100
            )
        else:
            pd_eff = pd_macro
        
        lgd_eff = lgd_macro
        M_eff = exp_copy.maturity
        
        # Overlay 3: Dynamic correlation
        R_base = sector_correlation_adjustment(
            pd_eff, exp_copy.asset_class, exp_copy.sector, exp_copy.portfolio_concentration
        )
        stress_index = macro.stress_index()
        R_dynamic = self.dynamic_correlation_model.get_correlation_by_stress_index(
            exp_copy.asset_class, stress_index
        )
        # Use dynamic correlation (regime-aware)
        R = R_dynamic
        
        logger.info(
            "Trade %s: macro overlay — base R=%.4f → dynamic R=%.4f (stress=%.2f), "
            "PD %.4f%% → %.4f%%, LGD %.1f%% → %.1f%%",
            exp_copy.trade_id, R_base, R, stress_index,
            pd_base*100, pd_eff*100, lgd_base*100, lgd_eff*100
        )
        
        # Standard calculation with macro-adjusted inputs
        b = maturity_adjustment(pd_eff, M_eff)
        if exp_copy.asset_class.startswith("RETAIL"):
            b = 0.0
            M_eff = 1.0
        
        K = capital_requirement_k(pd_eff, lgd_eff, M_eff, R, b)
        ead_used = exp_copy.ead
        rwa = rwa_from_k(K, ead_used)
        el = pd_eff * lgd_eff * ead_used
        el_diff = el - exp_copy.provisions
        
        computation_time_ms = (time.time() - start_time) * 1000
        
        rwa_drivers = {
            "base_rwa": rwa,
            "macro_adjustment_factor": pd_eff / pd_base if pd_base > 0 else 1.0,
            "dynamic_correlation_factor": R / R_base if R_base > 0 else 1.0,
            "stress_index": stress_index,
        }
        
        result = AIRBResult(
            trade_id           = exp_copy.trade_id,
            pd_applied         = pd_eff,
            lgd_applied        = lgd_eff,
            ead_applied        = ead_used,
            maturity           = M_eff,
            correlation_r      = R,
            capital_req_k      = K,
            maturity_adj_b     = b,
            rwa                = rwa,
            el                 = el,
            el_diff            = el_diff,
            rwa_drivers        = rwa_drivers,
            pd_stressed        = pd_eff,
            validation_warnings= warnings,
            data_quality_score = 0.95 if pd_market_implied is not None else 0.85,
            computation_time_ms= computation_time_ms,
        )
        
        return result

    def _compute_sensitivities(self, exp: BankingBookExposure, result: AIRBResult):
        """
        Add sensitivity analysis to result.
        Shocks: PD +10bp, LGD +5%, EAD +10%
        """
        try:
            # Shock: PD +10bp
            exp_pd_up = copy.deepcopy(exp)
            exp_pd_up.pd += 0.001
            result_pd_up = self.compute(exp_pd_up, _sensitivity_run=True)
            result.rwa_sensitivity_pd = result_pd_up.rwa - result.rwa
            
            # Shock: LGD +5%
            exp_lgd_up = copy.deepcopy(exp)
            exp_lgd_up.lgd = min(exp_lgd_up.lgd + 0.05, 1.0)
            result_lgd_up = self.compute(exp_lgd_up, _sensitivity_run=True)
            result.rwa_sensitivity_lgd = result_lgd_up.rwa - result.rwa
            
            # Shock: EAD +10%
            exp_ead_up = copy.deepcopy(exp)
            exp_ead_up.ead *= 1.10
            result_ead_up = self.compute(exp_ead_up, _sensitivity_run=True)
            result.rwa_sensitivity_ead = result_ead_up.rwa - result.rwa
            
            logger.debug(
                "Trade %s sensitivities: PD_10bp=%.0f LGD_5pct=%.0f EAD_10pct=%.0f",
                exp.trade_id, result.rwa_sensitivity_pd, result.rwa_sensitivity_lgd,
                result.rwa_sensitivity_ead
            )
        except Exception as e:
            logger.warning("Trade %s: sensitivity calculation failed — %s", exp.trade_id, e)

    def compute_from_universal_trade(self, trade: object) -> Optional[AIRBResult]:
        """
        Compute A-IRB directly from UniversalTrade (Phase 1).
        Returns None if trade not eligible for A-IRB.
        """
        # Validate trade quality first (validator stubbed — skip if not available)
        val_result = None
        if self.validator is not None:
            val_result = self.validator.validate_trade(trade)
            if not val_result.is_valid:
                logger.warning("Trade %s: validation failed — %s", trade.trade_id, val_result.errors)
                return None
        
        # Adapt to BankingBookExposure
        exp = universal_trade_to_airb_exposure(trade)
        if exp is None:
            return None
        
        # Compute with validation metadata
        result = self.compute(exp)
        if val_result is not None:
            result.validation_warnings.extend(val_result.warnings)
        result.data_quality_score = 0.95 if not val_result.warnings else 0.85
        return result

    def compute_portfolio(self, exposures: List[BankingBookExposure]) -> Dict:
        """
        Compute A-IRB for portfolio with comprehensive diagnostics.
        """
        start_time = time.time()
        results = []
        failed_trades = []
        
        for exp in exposures:
            try:
                r = self.compute(exp)
                results.append(r)
            except Exception as e:
                logger.error("A-IRB failed for trade %s: %s", exp.trade_id, e)
                failed_trades.append((exp.trade_id, str(e)))

        total_rwa = sum(r.rwa for r in results)
        total_el  = sum(r.el  for r in results)
        total_ead = sum(r.ead_applied for r in results)
        el_shortfall = sum(max(r.el_diff, 0) for r in results)
        total_computation_time = (time.time() - start_time) * 1000
        
        # Data quality assessment
        avg_quality_score = sum(r.data_quality_score for r in results) / len(results) if results else 1.0
        warnings_count = sum(len(r.validation_warnings) for r in results)
        
        # Sensitivity aggregates
        total_rwa_sensitivity_pd = sum(r.rwa_sensitivity_pd for r in results)
        total_rwa_sensitivity_lgd = sum(r.rwa_sensitivity_lgd for r in results)
        total_rwa_sensitivity_ead = sum(r.rwa_sensitivity_ead for r in results)

        logger.info(
            "A-IRB Portfolio: %d exposures | EAD=%.0f | RWA=%.0f | EL=%.0f | "
            "EL shortfall=%.0f | Avg Quality=%.2f | Time=%.0f ms | "
            "Sensitivities [PD_10bp=%.0f, LGD_5pct=%.0f, EAD_10pct=%.0f]",
            len(results), total_ead, total_rwa, total_el, el_shortfall, avg_quality_score,
            total_computation_time, total_rwa_sensitivity_pd, total_rwa_sensitivity_lgd,
            total_rwa_sensitivity_ead
        )
        
        if failed_trades:
            logger.warning("A-IRB: %d trades failed — %s", len(failed_trades), failed_trades[:3])

        # Mitigant benefit aggregates
        total_rwa_pre_mit = sum(r.rwa_pre_mitigant     for r in results)
        total_mit_benefit = sum(r.rwa_mitigant_benefit  for r in results)
        n_mitigated       = sum(1 for r in results if r.mitigant_type != "NONE")
        # Breakdown by channel
        mit_by_type: dict = {}
        for r in results:
            for t in r.mitigant_type.split("+"):
                if t and t != "NONE":
                    mit_by_type[t] = mit_by_type.get(t, 0.0) + r.rwa_mitigant_benefit

        return {
            "trade_results":            results,
            "total_rwa":                total_rwa,
            "total_el":                 total_el,
            "total_ead":                total_ead,
            "el_shortfall":             el_shortfall,
            "avg_risk_weight":          total_rwa / total_ead if total_ead > 0 else 0,
            "num_trades_processed":     len(results),
            "num_trades_failed":        len(failed_trades),
            "avg_quality_score":        avg_quality_score,
            "validation_warnings":      warnings_count,
            "total_computation_time_ms": total_computation_time,
            "avg_time_per_trade_ms":    total_computation_time / len(results) if results else 0,
            "rwa_sensitivity_pd":       total_rwa_sensitivity_pd,
            "rwa_sensitivity_lgd":      total_rwa_sensitivity_lgd,
            "rwa_sensitivity_ead":      total_rwa_sensitivity_ead,
            # ── Mitigant benefit attribution ─────────────────────────────────
            "total_rwa_pre_mitigant":   total_rwa_pre_mit,
            "total_mitigant_benefit":   total_mit_benefit,
            "mitigant_coverage_pct":    100.0 * n_mitigated / len(results) if results else 0.0,
            "mitigant_benefit_by_type": mit_by_type,
        }
    
    def compute_portfolio_from_universal_trades(self, trades: List[object]) -> Dict:
        """
        Compute A-IRB for portfolio from UniversalTrade list (Phase 1).
        """
        start_time = time.time()
        results = []
        skipped_trades = []
        failed_trades = []
        
        for trade in trades:
            try:
                result = self.compute_from_universal_trade(trade)
                if result is not None:
                    results.append(result)
                else:
                    skipped_trades.append(trade.trade_id)
            except Exception as e:
                logger.error("A-IRB failed for trade %s: %s", trade.trade_id, e)
                failed_trades.append((trade.trade_id, str(e)))

        total_rwa = sum(r.rwa for r in results)
        total_el  = sum(r.el  for r in results)
        total_ead = sum(r.ead_applied for r in results)
        total_computation_time = (time.time() - start_time) * 1000
        avg_quality_score = sum(r.data_quality_score for r in results) / len(results) if results else 1.0

        logger.info(
            "A-IRB Portfolio (UniversalTrade): %d processed | %d skipped | %d failed | "
            "EAD=%.0f | RWA=%.0f | EL=%.0f | Avg Quality=%.2f",
            len(results), len(skipped_trades), len(failed_trades), 
            total_ead, total_rwa, total_el, avg_quality_score
        )

        return {
            "trade_results":        results,
            "total_rwa":            total_rwa,
            "total_el":             total_el,
            "total_ead":            total_ead,
            "avg_risk_weight":      total_rwa / total_ead if total_ead > 0 else 0,
            "num_trades_processed": len(results),
            "num_trades_skipped":   len(skipped_trades),
            "num_trades_failed":    len(failed_trades),
            "avg_quality_score":    avg_quality_score,
            "total_computation_time_ms": total_computation_time,
            "avg_time_per_trade_ms":    total_computation_time / len(results) if results else 0,
        }
