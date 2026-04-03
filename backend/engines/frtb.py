"""
PROMETHEUS Risk Platform
Engine: FRTB — Fundamental Review of the Trading Book
Regulatory basis: MAR10, MAR21-23 (SBM), MAR31-33 (IMA/ES)

Implements:
  - Sensitivities-Based Method (SBM): Delta, Vega, Curvature charges
  - Internal Models Approach (IMA): Expected Shortfall at 97.5%
  - Non-Modellable Risk Factors (NMRF) — MAR31.14
  - Backtesting — traffic-light framework (MAR99)
  - Market Risk Capital = max(SBM, IMA) per MAR33

This consolidated file includes:
  - Performance optimizations (caching, aggregation, batch)
  - Scenario / stress testing hooks
  - Basic risk decomposition and result serialization
  - Optional parametric ES and ES confidence intervals
"""

from __future__ import annotations

import math
import copy
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import (
    List,
    Dict,
    Optional,
    Tuple,
    Mapping,
    Sequence,
    Union,
    Iterable,
    Any,
)

import numpy as np
from enum import Enum as StdEnum

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Market Regime & Real-Time Data
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegime(StdEnum):
    """Market state affecting risk weights and correlations."""
    NORMAL = "normal"
    STRESSED = "stressed"
    CRISIS = "crisis"

@dataclass
class MarketConditions:
    """
    Real-time market data for dynamic FRTB parameter adjustment.
    Connect to Bloomberg/Reuters/internal feeds in production.
    """
    date: date
    vix_level: float = 15.0              # VIX index (normal ~15-20, crisis >40)
    equity_vol_index: float = 20.0       # Equity realized vol (annualized %)
    credit_spread_ig: float = 100.0      # IG credit spread (bp)
    credit_spread_hy: float = 400.0      # HY credit spread (bp)
    fx_vol_index: float = 8.0            # FX vol index (e.g., JPM FX VIX)
    cmdty_vol_index: float = 25.0        # Commodity volatility
    ir_vol_swaption: float = 50.0        # Swaption implied vol (bp)
    
    def stress_level(self) -> float:
        """Composite stress index [0, 1]: 0=normal, 1=extreme crisis."""
        vix_norm = min(self.vix_level / 80.0, 1.0)
        spread_norm = min((self.credit_spread_hy - 300) / 1200.0, 1.0)
        eq_vol_norm = min((self.equity_vol_index - 15) / 50.0, 1.0)
        stress = 0.40*vix_norm + 0.35*spread_norm + 0.25*eq_vol_norm
        return min(max(stress, 0.0), 1.0)
    
    def regime(self) -> MarketRegime:
        """Classify market regime based on stress level."""
        s = self.stress_level()
        if s < 0.30:
            return MarketRegime.NORMAL
        elif s < 0.65:
            return MarketRegime.STRESSED
        else:
            return MarketRegime.CRISIS

class MarketDataFeed:
    """
    Real-time market data integration interface.
    Production: connect to Bloomberg, Reuters, or internal systems.
    """
    def __init__(self):
        self._cache: Optional[MarketConditions] = None
        self._cache_timestamp: Optional[date] = None
    
    def get_current_conditions(self, force_refresh: bool = False) -> MarketConditions:
        """Fetch current market conditions (cached daily)."""
        today = date.today()
        if not force_refresh and self._cache and self._cache_timestamp == today:
            return self._cache
        
        # TODO: Production integration example:
        # vix = bloomberg_api.get('VIX Index')
        # hy_spread = bloomberg_api.get('CDX HY Spread')
        # fx_vol = reuters_api.get('JPM FX VIX')
        
        conditions = MarketConditions(
            date=today,
            vix_level=15.0,  # Default/demo values
            equity_vol_index=20.0,
            credit_spread_ig=100.0,
            credit_spread_hy=400.0,
            fx_vol_index=8.0,
            cmdty_vol_index=25.0,
            ir_vol_swaption=50.0,
        )
        
        self._cache = conditions
        self._cache_timestamp = today
        
        logger.info(
            "Market conditions: VIX=%.1f, HY=%dbp, stress=%.2f (%s)",
            conditions.vix_level, conditions.credit_spread_hy,
            conditions.stress_level(), conditions.regime().value
        )
        return conditions
    
    def update_from_dict(self, data: Dict[str, float]) -> MarketConditions:
        """Manually update conditions from dict (for testing/custom feeds)."""
        conditions = MarketConditions(
            date=date.today(),
            vix_level=data.get('vix', 15.0),
            equity_vol_index=data.get('eq_vol', 20.0),
            credit_spread_ig=data.get('ig_spread', 100.0),
            credit_spread_hy=data.get('hy_spread', 400.0),
            fx_vol_index=data.get('fx_vol', 8.0),
            cmdty_vol_index=data.get('cmdty_vol', 25.0),
            ir_vol_swaption=data.get('ir_vol', 50.0),
        )
        self._cache = conditions
        self._cache_timestamp = date.today()
        return conditions

class DynamicParameterAdjustment:
    """
    Adjusts FRTB risk weights/correlations based on real-time market volatility.
    Implements counter-cyclical buffer (higher vol → higher risk weights).
    """
    def __init__(self, base_config: 'FRTBConfig'):
        self.base_config = base_config
    
    def adjust_risk_weights(self, market: MarketConditions, risk_class: str) -> Sequence[float]:
        """Scale risk weights based on realized volatility vs normal levels."""
        base_rw = self.base_config.delta_rw.get(risk_class, [0.15])
        stress = market.stress_level()
        
        # Volatility-based scaling per risk class
        if risk_class == "GIRR":
            scaling = 0.80 + 0.40 * (market.ir_vol_swaption / 50.0)
        elif risk_class in ("CSR_NS", "CSR_SEC"):
            scaling = 0.80 + 0.60 * (market.credit_spread_hy / 400.0)
        elif risk_class.startswith("EQ"):
            scaling = 0.75 + 0.75 * (market.equity_vol_index / 20.0)
        elif risk_class == "FX":
            scaling = 0.85 + 0.50 * (market.fx_vol_index / 8.0)
        elif risk_class == "CMDTY":
            scaling = 0.80 + 0.80 * (market.cmdty_vol_index / 25.0)
        else:
            scaling = 1.0
        
        # Crisis amplification
        if stress > 0.65:
            scaling *= (1.0 + 0.5 * (stress - 0.65) / 0.35)
        
        scaling = max(0.5, min(scaling, 3.0))
        return [rw * scaling for rw in base_rw]
    
    def adjust_correlation(self, market: MarketConditions, risk_class: str, 
                          corr_type: str = "intra") -> float:
        """Crisis → higher correlations (diversification breakdown)."""
        stress = market.stress_level()
        base = (self.base_config.intra_corr if corr_type == "intra" 
                else self.base_config.inter_corr).get(risk_class, 0.50)
        
        if stress < 0.30:
            multiplier = 1.0
        elif stress < 0.65:
            multiplier = 1.0 + 0.20 * (stress - 0.30) / 0.35
        else:
            multiplier = 1.20 + 0.30 * (stress - 0.65) / 0.35
        
        return min(base * multiplier, 0.99)

# ─────────────────────────────────────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class FRTBValidationError(ValueError):
    """Raised when input validation fails."""
    pass


class FRTBConfigurationError(ValueError):
    """Raised when configuration is invalid."""
    pass


class FRTBCalculationError(RuntimeError):
    """Raised when calculation encounters NaN/inf or other numerical errors."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Models
# ─────────────────────────────────────────────────────────────────────────────


class CorrelationModel:
    """
    Pluggable correlation model.
    Default implementation uses static intra/inter correlation scalars.
    """

    def __init__(
        self,
        intra_corr: Dict[str, float],
        inter_corr: Dict[str, float],
    ):
        self.intra_corr = intra_corr
        self.inter_corr = inter_corr

    # GIRR tenor grid per MAR21 (3m,6m,1y,2y,3y,5y,10y,15y,20y,30y)
    _GIRR_TENORS: List[float] = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0]

    def intra(self, risk_class: str, n: int) -> np.ndarray:
        """
        For GIRR: tenor-gap correlations per MAR21.58
            ρ(t1,t2) = exp(−θ × |ln(t1/t2)|),  θ = 0.03
        For all other risk classes: homogeneous scalar from config.
        """
        if risk_class == "GIRR":
            tenors = self._GIRR_TENORS
            # Extend/truncate tenor list to match n
            t_list = (tenors * ((n // len(tenors)) + 1))[:n]
            mat = np.ones((n, n), dtype=np.float64)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        t1, t2 = t_list[i], t_list[j]
                        mat[i, j] = math.exp(-0.03 * abs(math.log(t1 / t2)))
            return mat
        ρ = self.intra_corr.get(risk_class, 0.5)
        mat = np.full((n, n), ρ, dtype=np.float64)
        np.fill_diagonal(mat, 1.0)
        return mat

    def inter(self, risk_class: str, m: int) -> np.ndarray:
        γ = self.inter_corr.get(risk_class, 0.3)
        mat = np.full((m, m), γ, dtype=np.float64)
        np.fill_diagonal(mat, 1.0)
        return mat


@dataclass
class FRTBConfig:
    """Centralized FRTB configuration per MAR21-33 with real-time market support."""
    risk_classes: List[str] = field(default_factory=lambda: [
        "GIRR", "CSR_NS", "CSR_SEC", "EQ", "CMDTY", "FX"
    ])
    
    # Real-time market integration (NEW)
    use_market_conditions: bool = False  # Enable dynamic parameter adjustment
    market_data_feed: Optional[MarketDataFeed] = None
    dynamic_adjuster: Optional[DynamicParameterAdjustment] = None

    delta_rw: Dict[str, Sequence[float]] = field(default_factory=lambda: {
        "GIRR": [0.017, 0.017, 0.016, 0.013, 0.012, 0.011, 0.011,
                 0.011, 0.011, 0.011, 0.013, 0.015, 0.018],
        "CSR_NS": [0.005, 0.010, 0.050, 0.030, 0.020, 0.030, 0.080,
                   0.060, 0.050, 0.100, 0.120, 0.140, 0.020, 0.020,
                   0.020, 0.030, 0.030, 0.050],
        "EQ_LARGE": [0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70],
        "FX": [0.15],
        "CMDTY": [0.30, 0.35, 0.60, 0.80, 0.40, 0.45, 0.20, 0.35, 0.25, 0.35,
                  0.50, 0.42, 0.18, 0.18, 0.18, 0.16, 0.18],
    })

    intra_corr: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.999, "CSR_NS": 0.65, "EQ": 0.15, "FX": 1.0, "CMDTY": 0.55,
    })

    inter_corr: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.50, "CSR_NS": 0.0, "EQ": 0.15, "FX": 0.60, "CMDTY": 0.20,
    })

    vega_rw: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.55, "CSR_NS": 0.55, "EQ": 0.78, "FX": 0.47, "CMDTY": 1.00
    })

    # Optional deterministic mapping (risk_class, risk_factor) -> RW index
    rw_index_map: Dict[Tuple[str, str], int] = field(default_factory=dict)

    confidence_level: float = 0.975
    holding_period_days: int = 10
    backtesting_window: int = 260
    green_zone_max: int = 4
    amber_zone_max: int = 9
    ima_multiplier: float = 1.5
    nmrf_charge_bp: float = 0.0015
    stressed_es_multiplier: float = 1.5

    # Pluggable correlation model
    correlation_model: Optional[CorrelationModel] = None

    def __post_init__(self):
        if self.correlation_model is None:
            self.correlation_model = CorrelationModel(
                intra_corr=self.intra_corr,
                inter_corr=self.inter_corr,
            )
        
        # Initialize real-time market components if enabled
        if self.use_market_conditions:
            if self.market_data_feed is None:
                self.market_data_feed = MarketDataFeed()
            if self.dynamic_adjuster is None:
                self.dynamic_adjuster = DynamicParameterAdjustment(self)
            logger.info("FRTB real-time market conditions ENABLED")

    def validate(self) -> None:
        """Validate configuration consistency and regulatory bounds."""
        if not self.risk_classes:
            raise FRTBConfigurationError("risk_classes cannot be empty")
        if not all(0 < rw < 2.0 for rws in self.delta_rw.values() for rw in rws):
            raise FRTBConfigurationError("Risk weights must be in (0, 2)")
        if not all(0 <= corr <= 1.0 for corr in self.intra_corr.values()):
            raise FRTBConfigurationError("Intra-correlations must be in [0, 1]")
        if not all(-1.0 <= corr <= 1.0 for corr in self.inter_corr.values()):
            raise FRTBConfigurationError("Inter-correlations must be in [-1, 1]")
        if not (0.9 < self.confidence_level < 1.0):
            raise FRTBConfigurationError("Confidence level must be in (0.9, 1.0)")
        if self.holding_period_days <= 0:
            raise FRTBConfigurationError("holding_period_days must be positive")
        logger.debug("FRTBConfig validated successfully")


# ─────────────────────────────────────────────────────────────────────────────
# Core Data Structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Sensitivity:
    """
    Single risk factor sensitivity per MAR21.6.

    Attributes:
        trade_id: Unique trade identifier.
        risk_class: One of GIRR, CSR_NS, CSR_SEC, EQ, CMDTY, FX.
        bucket: Regulatory bucket (e.g., "1", "2", or risk name).
        risk_factor: Specific factor (tenor, currency, sector).
        delta: Delta sensitivity ∂V/∂S (dV per 1bp move).
        vega: Vega sensitivity ∂V/∂σ (dV per 1% IV move).
        curvature_up: P&L change if scenario rates shift +1bp.
        curvature_dn: P&L change if scenario rates shift -1bp.
        notional: Optional notional for normalization.
    """
    trade_id: str
    risk_class: str
    bucket: str
    risk_factor: str
    delta: float
    vega: float = 0.0
    curvature_up: float = 0.0
    curvature_dn: float = 0.0
    notional: float = 1.0


@dataclass
class FRTBResult:
    """
    Complete FRTB capital calculation output per MAR21-33.
    """
    run_date: date
    portfolio_id: str
    method: str
    sbm_delta: float
    sbm_vega: float
    sbm_curvature: float
    sbm_total: float
    es_99_10d: float
    es_stressed: float
    nmrf_charge: float
    ima_total: float
    capital_market_risk: float
    rwa_market: float

    # New capital components
    drc_charge:    float = 0.0   # Default Risk Charge (MAR22)
    rrao_charge_v: float = 0.0   # Residual Risk Add-On (MAR23.5)
    pla_zone:      str   = "N/A" # PLA test zone (GREEN/AMBER/RED/N/A)

    # Optional breakdowns / details
    sbm_by_risk_class: Dict[str, float] = field(default_factory=dict)
    sbm_by_bucket:     Dict[str, float] = field(default_factory=dict)
    ima_components:    Dict[str, float] = field(default_factory=dict)
    drc_by_quality:    Dict[str, Any]   = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to a plain dict (JSON/CSV/Parquet friendly)."""
        d = asdict(self)
        # Convert date to ISO string for JSON friendliness
        d["run_date"] = self.run_date.isoformat()
        return d

    def to_json(self, **kwargs) -> str:
        """Serialize result to JSON string."""
        return json.dumps(self.to_dict(), **kwargs)


@dataclass
class ShockScenario:
    """
    Simple stress scenario definition for what-if analysis.
    """
    name: str
    rate_bp: float = 0.0
    spread_bp: float = 0.0
    fx_pct: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Validation Functions
# ─────────────────────────────────────────────────────────────────────────────


def validate_sensitivity(s: Sensitivity) -> None:
    """Validate individual sensitivity; raises FRTBValidationError on failure."""
    if not isinstance(s.trade_id, str) or not s.trade_id:
        raise FRTBValidationError(f"Invalid trade_id: {s.trade_id}")
    if not isinstance(s.risk_class, str) or not s.risk_class:
        raise FRTBValidationError(f"Invalid risk_class: {s.risk_class}")
    if not isinstance(s.bucket, str) or not s.bucket:
        raise FRTBValidationError(f"Invalid bucket: {s.bucket}")
    if not isinstance(s.delta, (int, float)) or math.isnan(s.delta) or math.isinf(s.delta):
        raise FRTBValidationError(f"Invalid delta for {s.trade_id}: {s.delta}")
    if not isinstance(s.vega, (int, float)) or math.isnan(s.vega) or math.isinf(s.vega):
        raise FRTBValidationError(f"Invalid vega for {s.trade_id}: {s.vega}")
    if not isinstance(s.curvature_up, (int, float)) or math.isnan(s.curvature_up):
        raise FRTBValidationError(f"Invalid curvature_up for {s.trade_id}: {s.curvature_up}")
    if not isinstance(s.curvature_dn, (int, float)) or math.isnan(s.curvature_dn):
        raise FRTBValidationError(f"Invalid curvature_dn for {s.trade_id}: {s.curvature_dn}")
    if not isinstance(s.notional, (int, float)) or s.notional <= 0:
        raise FRTBValidationError(f"Invalid notional for {s.trade_id}: {s.notional}")


def validate_sensitivities(sensitivities: Sequence[Sensitivity], config: FRTBConfig) -> None:
    """Validate entire sensitivity portfolio against configuration."""
    if not sensitivities:
        logger.warning("Empty sensitivity portfolio provided")
        return

    for s in sensitivities:
        validate_sensitivity(s)
        if s.risk_class not in config.risk_classes:
            raise FRTBValidationError(
                f"Unknown risk_class '{s.risk_class}' for trade {s.trade_id}. "
                f"Valid: {config.risk_classes}"
            )


def validate_pnl_series(pnl_series: np.ndarray, min_length: int = 10) -> None:
    """Validate P&L series for IMA/ES calculations."""
    if not isinstance(pnl_series, np.ndarray):
        raise FRTBValidationError("pnl_series must be numpy array")
    if len(pnl_series) < min_length:
        raise FRTBValidationError(
            f"PnL series too short: {len(pnl_series)} < {min_length} required"
        )
    if np.any(np.isnan(pnl_series)):
        nan_count = int(np.sum(np.isnan(pnl_series)))
        raise FRTBValidationError(f"PnL series contains {nan_count} NaN values")
    if np.any(np.isinf(pnl_series)):
        inf_count = int(np.sum(np.isinf(pnl_series)))
        raise FRTBValidationError(f"PnL series contains {inf_count} inf values")

    # Simple outlier flagging (non-blocking)
    if len(pnl_series) > 5:
        z = (pnl_series - pnl_series.mean()) / (pnl_series.std(ddof=1) or 1.0)
        if np.any(np.abs(z) > 6):
            logger.warning("PnL series contains extreme outliers |z|>6")


# ─────────────────────────────────────────────────────────────────────────────
# Utility: Position Aggregation / Netting
# ─────────────────────────────────────────────────────────────────────────────


def aggregate_sensitivities(
    sensitivities: Sequence[Sensitivity],
) -> List[Sensitivity]:
    """
    Aggregate sensitivities by (risk_class, bucket, risk_factor).
    Netting deltas/vegas/curvature; notional is summed.
    """
    if not sensitivities:
        return []

    agg: Dict[Tuple[str, str, str], Sensitivity] = {}
    for s in sensitivities:
        key = (s.risk_class, s.bucket, s.risk_factor)
        if key not in agg:
            agg[key] = copy.copy(s)
        else:
            a = agg[key]
            a.delta += s.delta
            a.vega += s.vega
            a.curvature_up += s.curvature_up
            a.curvature_dn += s.curvature_dn
            a.notional += s.notional
    return list(agg.values())


# ─────────────────────────────────────────────────────────────────────────────
# SBM — Sensitivities-Based Method
# ─────────────────────────────────────────────────────────────────────────────


class SBMCalculator:
    """
    Implements MAR21: delta, vega, curvature charges.
    Uses weighted sensitivity (WS) = RW × sensitivity.
    Includes:
      - cached correlation matrices
      - basic risk-class / bucket breakdowns
    """

    def __init__(self, config: FRTBConfig):
        self.config = config
        config.validate()
        # Simple caches keyed by (risk_class, n)
        self._intra_cache: Dict[Tuple[str, int], np.ndarray] = {}
        self._inter_cache: Dict[Tuple[str, int], np.ndarray] = {}

    # ---- internal helpers -------------------------------------------------

    def _intra_corr_mat(self, risk_class: str, n: int) -> np.ndarray:
        key = (risk_class, n)
        if key not in self._intra_cache:
            self._intra_cache[key] = self.config.correlation_model.intra(risk_class, n)
        return self._intra_cache[key]

    def _inter_corr_mat(self, risk_class: str, m: int) -> np.ndarray:
        key = (risk_class, m)
        if key not in self._inter_cache:
            self._inter_cache[key] = self.config.correlation_model.inter(risk_class, m)
        return self._inter_cache[key]

    def _risk_weight_for(self, s: Sensitivity, market: Optional[MarketConditions] = None) -> float:
        """
        RW lookup with optional real-time market adjustment.
        If market conditions enabled: scales RW based on current volatility.
        """
        # Get base or dynamically adjusted risk weights
        if self.config.use_market_conditions and market and self.config.dynamic_adjuster:
            rw_map = self.config.dynamic_adjuster.adjust_risk_weights(market, s.risk_class)
        else:
            rw_map = self.config.delta_rw.get(
                s.risk_class,
                self.config.delta_rw.get(s.risk_class + "_LARGE", [0.15]),
            )
        
        if (s.risk_class, s.risk_factor) in self.config.rw_index_map:
            idx = self.config.rw_index_map[(s.risk_class, s.risk_factor)]
        else:
            idx = abs(hash(s.risk_factor)) % len(rw_map)
        return rw_map[idx]

    # ---- main SBM components ----------------------------------------------

    def delta_charge(
        self,
        sensitivities: Sequence[Sensitivity],
        risk_class: str,
        breakdown_by_bucket: Optional[Dict[str, float]] = None,
        market: Optional[MarketConditions] = None,
    ) -> float:
        """
        1. WS_k = RW_k × s_k (RW adjusted for market if enabled)
        2. K_b = sqrt(Σ_k WS_k² + Σ_{k≠l} ρ_{kl} WS_k WS_l)   [intra-bucket]
        3. Δ   = sqrt(Σ_b K_b² + Σ_{b≠c} γ_{bc} K_b K_c)      [inter-bucket]
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                return 0.0

            # bucket -> list of WS
            buckets: Dict[str, List[float]] = {}
            for s in senses:
                rw = self._risk_weight_for(s, market=market)
                ws = rw * s.delta
                buckets.setdefault(s.bucket, []).append(ws)

            K_b: Dict[str, float] = {}
            for b, ws_list in buckets.items():
                ws_arr = np.array(ws_list, dtype=np.float64)
                n = len(ws_arr)
                if n == 0:
                    K_b[b] = 0.0
                    continue
                corr_mat = self._intra_corr_mat(risk_class, n)
                K_sq = float(ws_arr @ corr_mat @ ws_arr)
                K_b[b] = math.sqrt(max(K_sq, 0.0))

            K_arr = np.array(list(K_b.values()), dtype=np.float64)
            if len(K_arr) == 0:
                return 0.0

            corr_inter = self._inter_corr_mat(risk_class, len(K_arr))
            charge_sq = float(K_arr @ corr_inter @ K_arr)
            result = math.sqrt(max(charge_sq, 0.0))

            if breakdown_by_bucket is not None:
                breakdown_by_bucket.update(K_b)

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Delta charge produced NaN/inf for {risk_class}")
            return result

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Delta charge calculation failed for {risk_class}: {e}")

    def vega_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """
        MAR21: Vega charge via the same two-stage intra/inter bucket aggregation as delta.

        WS_k = RW_vega × VR_k   (VR = vega sensitivity to implied vol)
        K_b  = √(Σ WS_k² + Σ_{k≠l} ρ_kl WS_k WS_l)   [intra-bucket]
        Δ    = √(Σ K_b² + Σ_{b≠c} γ_bc K_b K_c)       [inter-bucket]
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class and s.vega != 0]
            if not senses:
                return 0.0

            rw_vega = self.config.vega_rw.get(risk_class, 0.55)

            # bucket → list of WS (weighted vega sensitivities)
            buckets: Dict[str, List[float]] = {}
            for s in senses:
                ws = rw_vega * s.vega
                buckets.setdefault(s.bucket, []).append(ws)

            # Intra-bucket aggregation
            K_b: Dict[str, float] = {}
            for b, ws_list in buckets.items():
                ws_arr = np.array(ws_list, dtype=np.float64)
                n = len(ws_arr)
                if n == 0:
                    K_b[b] = 0.0
                    continue
                corr_mat = self._intra_corr_mat(risk_class, n)
                K_sq = float(ws_arr @ corr_mat @ ws_arr)
                K_b[b] = math.sqrt(max(K_sq, 0.0))

            # Inter-bucket aggregation
            K_arr = np.array(list(K_b.values()), dtype=np.float64)
            if len(K_arr) == 0:
                return 0.0
            corr_inter = self._inter_corr_mat(risk_class, len(K_arr))
            charge_sq  = float(K_arr @ corr_inter @ K_arr)
            result     = math.sqrt(max(charge_sq, 0.0))

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Vega charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Vega charge calculation failed for {risk_class}: {e}")

    def curvature_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """
        MAR23.6: Curvature charge under three correlation scenarios.

        CVR_k = -min(CVR_up_k, CVR_dn_k, 0)   per risk factor
        For each correlation scenario s ∈ {low, medium, high}:
            ρ_s  = ρ_base scaled by {0.75², 1.0, min(1.25,1)}
            K_b  = √max(Σ CVR_k² + Σ_{k≠l} ρ_s² × CVR_k × CVR_l, 0)
            ψ_b  = Σ CVR_k if K_b < 0 else 0   (negative bucket treatment)
            Ξ_s  = Σ_b K_b² + Σ_{b≠c} γ_s × K_b × K_c + Σ_b ψ_b
        Result = max(max(Ξ_s), 0)
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                return 0.0

            # CVR_k = -min(CVR_up, CVR_dn, 0) per MAR23.3
            cvr = [-min(s.curvature_up, s.curvature_dn, 0.0) for s in senses]
            cvr_arr = np.array(cvr, dtype=np.float64)
            n = len(cvr_arr)
            if n == 0:
                return 0.0

            # Three intra-correlation scenarios (MAR23.6)
            base_intra = self._intra_corr_mat(risk_class, n)
            base_inter_scalar = self.config.inter_corr.get(risk_class, 0.5)

            scenario_charges = []
            for rho_scale in [0.75**2, 1.0, min(1.25, 1.0)]:
                # Scale intra correlation matrix (off-diagonals only)
                ρ_mat = np.ones_like(base_intra)
                for i in range(n):
                    for j in range(n):
                        if i != j:
                            ρ_mat[i, j] = min(base_intra[i, j] * rho_scale, 1.0)

                # Bucket-level aggregation
                bucket_names = [s.bucket for s in senses]
                unique_buckets = list(dict.fromkeys(bucket_names))

                K_b_vals = []
                psi_b_vals = []
                for b in unique_buckets:
                    idx = [i for i, s in enumerate(senses) if s.bucket == b]
                    cvr_b = cvr_arr[idx]
                    n_b = len(cvr_b)
                    if n_b == 0:
                        K_b_vals.append(0.0)
                        psi_b_vals.append(0.0)
                        continue
                    ρ_b = ρ_mat[np.ix_(idx, idx)]
                    K_sq = float(cvr_b @ ρ_b @ cvr_b)
                    K_b_v = math.sqrt(max(K_sq, 0.0))
                    K_b_vals.append(K_b_v)
                    # ψ_b = Σ CVR_k if K_b² < 0 (i.e. negative scenario)
                    psi_b_vals.append(float(cvr_b.sum()) if K_sq < 0 else 0.0)

                K_b_arr = np.array(K_b_vals)
                m = len(K_b_arr)
                # Inter-bucket aggregation
                γ_s = min(base_inter_scalar * rho_scale, 1.0)
                inter_mat = np.full((m, m), γ_s)
                np.fill_diagonal(inter_mat, 1.0)
                xi = float(K_b_arr @ inter_mat @ K_b_arr) + sum(psi_b_vals)
                scenario_charges.append(xi)

            result = max(max(scenario_charges), 0.0)
            result = math.sqrt(result) if result > 0 else 0.0

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Curvature charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Curvature charge calculation failed for {risk_class}: {e}")


    def rrao_charge(
        self,
        sensitivities: Sequence[Sensitivity],
        notionals_by_instrument: Optional[Dict[str, Tuple[float, str]]] = None,
    ) -> float:
        """
        MAR23.5: Residual Risk Add-On (RRAO).

        Instruments with exotic underlyings: 1.0% × gross notional
        Instruments with gap/correlation/behavioural risk: 0.1% × gross notional

        Args:
            notionals_by_instrument: {trade_id: (notional, instrument_type)}
              instrument_type: 'EXOTIC' | 'RESIDUAL' | 'VANILLA'
              If None, derives a conservative estimate from sensitivities.
        """
        if notionals_by_instrument is not None:
            exotic_notional   = sum(n for n,t in notionals_by_instrument.values() if t=='EXOTIC')
            residual_notional = sum(n for n,t in notionals_by_instrument.values() if t=='RESIDUAL')
        else:
            # Conservative: treat all non-linear (non-zero curvature) sensitivities
            # as residual risk; exotic is zero (cannot distinguish without trade data)
            exotic_notional   = 0.0
            residual_notional = sum(
                abs(s.delta) * 1000  # rough notional proxy from delta
                for s in sensitivities
                if (s.curvature_up != 0 or s.curvature_dn != 0)
            )
        return 0.010 * exotic_notional + 0.001 * residual_notional

    def total_sbm(
        self,
        sensitivities: Sequence[Sensitivity],
        market: Optional[MarketConditions] = None,
    ) -> Tuple[float, float, float, float, Dict[str, float], Dict[str, float]]:
        """
        Returns:
            delta_total, vega_total, curv_total, sbm_total,
            sbm_by_risk_class, sbm_by_bucket
        
        market: Optional real-time conditions for dynamic RW adjustment
        """
        delta_charges: Dict[str, float] = {}
        vega_charges: Dict[str, float] = {}
        curv_charges: Dict[str, float] = {}
        bucket_breakdown: Dict[str, float] = {}

        for rc in self.config.risk_classes:
            # MAR21.6: Compute delta under three correlation scenarios;
            # take the maximum as the regulatory charge.
            base_intra  = self.config.intra_corr.get(rc, 0.5)
            base_inter  = self.config.inter_corr.get(rc, 0.3)
            delta_scenarios = []
            for intra_scale, inter_scale in [
                (0.75**2, 0.75**2),   # low scenario
                (1.0,     1.0),       # medium (base)
                (min(1.0 + 0.25*(1.0 - base_intra)/max(base_intra,0.01), 1.0),
                 min(1.0 + 0.25*(1.0 - base_inter)/max(base_inter,0.01), 1.0)),  # high
            ]:
                # Temporarily scale the correlation model
                orig_intra = self.config.correlation_model.intra_corr.copy()
                orig_inter = self.config.correlation_model.inter_corr.copy()
                self.config.correlation_model.intra_corr[rc] = min(base_intra * intra_scale, 0.9999)
                self.config.correlation_model.inter_corr[rc] = max(
                    min(base_inter * inter_scale, 1.0), -1.0)
                self._intra_cache.clear()
                self._inter_cache.clear()
                rc_bucket_breakdown_s: Dict[str, float] = {}
                d_s = self.delta_charge(sensitivities, rc,
                                        breakdown_by_bucket=rc_bucket_breakdown_s,
                                        market=market)
                delta_scenarios.append((d_s, rc_bucket_breakdown_s))
                # Restore
                self.config.correlation_model.intra_corr = orig_intra
                self.config.correlation_model.inter_corr = orig_inter
                self._intra_cache.clear()
                self._inter_cache.clear()

            # Best scenario = highest charge (MAR21.6)
            best_idx = int(np.argmax([x[0] for x in delta_scenarios]))
            d = delta_scenarios[best_idx][0]
            rc_bucket_breakdown = delta_scenarios[best_idx][1]

            v = self.vega_charge(sensitivities, rc)
            c = self.curvature_charge(sensitivities, rc)
            delta_charges[rc] = d
            vega_charges[rc]  = v
            curv_charges[rc]  = c
            for b, val in rc_bucket_breakdown.items():
                bucket_breakdown[f"{rc}:{b}"] = val

        delta_t = sum(delta_charges.values())
        vega_t = sum(vega_charges.values())
        curv_t = sum(curv_charges.values())
        sbm_t = delta_t + vega_t + curv_t

        sbm_by_risk_class = {
            rc: delta_charges[rc] + vega_charges[rc] + curv_charges[rc]
            for rc in self.config.risk_classes
        }

        logger.debug("SBM: Δ=%.0f  V=%.0f  C=%.0f  Total=%.0f",
                     delta_t, vega_t, curv_t, sbm_t)

        return delta_t, vega_t, curv_t, sbm_t, sbm_by_risk_class, bucket_breakdown


# ─────────────────────────────────────────────────────────────────────────────
# IMA — Expected Shortfall (MAR33)
# ─────────────────────────────────────────────────────────────────────────────


class IMACalculator:
    """
    Simplified IMA/ES calculator using historical or parametric methods.
    ES_t = mean of losses exceeding (1-α) worst outcomes.
    """

    def __init__(self, config: FRTBConfig):
        self.config = config
        config.validate()

    def compute_es(
        self,
        pnl_series: np.ndarray,
        stressed: bool = False,
        method: str = "historical",
        return_ci: bool = False,
        bootstrap_samples: int = 0,
    ) -> Union[float, Tuple[float, float, float]]:
        """
        MAR33.8: ES = mean of worst (1-97.5%) = 2.5% worst PnL.
        Scaled to 10-day: ES_10d = ES_1d × sqrt(10).

        method:
            "historical" (default) — empirical ES
            "normal" — parametric normal ES

        return_ci:
            If True and bootstrap_samples > 0, returns (ES, ES_low, ES_high).
        """
        try:
            validate_pnl_series(pnl_series, min_length=10)

            losses = -pnl_series
            α = self.config.confidence_level

            if method == "historical":
                cutoff = max(int(len(losses) * (1 - α)), 1)
                worst = np.sort(losses)[-cutoff:]
                es_1d = float(worst.mean())
            elif method == "normal":
                mu = float(losses.mean())
                sigma = float(losses.std(ddof=1))
                if sigma <= 0:
                    es_1d = max(mu, 0.0)
                else:
                    from math import sqrt, pi, exp
                    # Normal ES formula: μ + σ φ(z)/(1-α)
                    # where z = Φ^{-1}(α)
                    from math import erf

                    def norm_ppf(p: float) -> float:
                        # simple approximation for Φ^{-1}
                        # not super-precise but fine for this context
                        return math.sqrt(2) * math.erfinv(2 * p - 1)

                    z = norm_ppf(α)
                    phi = (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z)
                    es_1d = mu + sigma * phi / (1 - α)
            else:
                raise FRTBValidationError(f"Unknown ES method: {method}")

            es_10d = es_1d * math.sqrt(self.config.holding_period_days)
            if stressed:
                es_10d *= self.config.stressed_es_multiplier

            result = max(es_10d, 0.0)
            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError("ES calculation produced NaN/inf")

            if not return_ci or bootstrap_samples <= 0:
                return result

            # Bootstrap confidence interval
            boot = []
            rng = np.random.default_rng(123)
            for _ in range(bootstrap_samples):
                sample = rng.choice(pnl_series, size=len(pnl_series), replace=True)
                boot.append(self.compute_es(sample, stressed=stressed, method=method))
            boot_arr = np.array(boot)
            low, high = np.percentile(boot_arr, [5, 95])
            return result, float(low), float(high)

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"ES computation failed: {e}")


    # Liquidity horizon per risk class (MAR33.12, Table 1)
    # Key = risk_class string, Value = LH in days
    LIQUIDITY_HORIZONS: Dict[str, int] = {
        "GIRR":    10,
        "FX":      10,
        "EQ_LARGE":20,   # Large-cap equity
        "EQ":      40,   # Small-cap equity (conservative)
        "CSR_NS":  40,   # Credit spread non-securitisation
        "CSR_SEC": 60,   # Credit spread securitisation
        "CMDTY":   20,   # Commodity (liquid)
        "CMDTY_ILLIQUID": 60,
    }
    # Five liquidity horizon buckets (MAR33.4 Table 1)
    LH_BUCKETS = [10, 20, 40, 60, 120]  # j = 1..5

    def compute_es_lh_adjusted(
        self,
        pnl_by_risk_class: Dict[str, np.ndarray],
        stressed: bool = False,
        method: str = "historical",
    ) -> float:
        """
        MAR33.4: Liquidity-horizon-adjusted ES.

        ES = √[ ES_T(full)²
               + Σ_{j=2..5} ES_T(P_j)² × (LH_j - LH_{j-1}) / T ]

        where P_j = sub-portfolio of risk factors with LH ≥ LH_j.
        T = base horizon = 10 days.

        If only one risk class is present (or pnl_by_risk_class has one key),
        falls back to simple scaling.
        """
        T = self.config.holding_period_days  # 10
        LH = self.LH_BUCKETS  # [10, 20, 40, 60, 120]

        if not pnl_by_risk_class:
            return 0.0

        # Full portfolio ES (j=1, all risk factors, scaled to LH1=10d)
        full_pnl = np.sum(list(pnl_by_risk_class.values()), axis=0)
        es_full  = float(self.compute_es(full_pnl, stressed=False, method=method))

        result_sq = es_full ** 2  # already at 10d

        # For each higher liquidity horizon bucket, compute partial ES
        for j_idx in range(1, len(LH)):
            lh_j      = LH[j_idx]
            lh_j_prev = LH[j_idx - 1]

            # Sub-portfolio: only risk factors with LH ≥ lh_j
            partial_pnls = []
            for rc, pnl in pnl_by_risk_class.items():
                rc_lh = self.LIQUIDITY_HORIZONS.get(rc, 10)
                if rc_lh >= lh_j:
                    partial_pnls.append(pnl)

            if not partial_pnls:
                continue

            partial_pnl = np.sum(partial_pnls, axis=0)
            es_partial_1d = float(self.compute_es(partial_pnl, stressed=False, method=method))
            # Scale to base 10d (compute_es already does √10 scaling, undo then redo)
            es_partial_10d = es_partial_1d  # compute_es returns 10d

            result_sq += es_partial_10d ** 2 * (lh_j - lh_j_prev) / T

        lh_es = math.sqrt(max(result_sq, 0.0))
        if stressed:
            lh_es *= self.config.stressed_es_multiplier
        return max(lh_es, 0.0)

    def nmrf_charge(self, n_nmrf_factors: int, avg_notional: float) -> float:
        """
        MAR31.14: NMRF charge = 99th-pct loss for each NMRF.
        Simplified: charge = n × avg_notional × nmrf_charge_bp.
        """
        try:
            if n_nmrf_factors < 0:
                raise FRTBValidationError("n_nmrf_factors must be non-negative")
            if avg_notional <= 0:
                raise FRTBValidationError("avg_notional must be positive")

            charge = n_nmrf_factors * avg_notional * self.config.nmrf_charge_bp
            if math.isnan(charge) or math.isinf(charge):
                raise FRTBCalculationError("NMRF charge produced NaN/inf")
            return charge

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"NMRF charge calculation failed: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# DRC — Default Risk Charge (MAR22 SBM / MAR33.18 IMA)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DRCPosition:
    """Single position for DRC calculation."""
    trade_id:       str
    notional:       float          # gross notional (positive = long, negative = short)
    lgd:            float          # loss given default [0,1]; typically 0.45–1.0
    market_value:   float          # current market value of the position
    credit_quality: str            # 'AAA','AA','A','BBB','BB','B','CCC','DEFAULT'
    maturity_years: float = 1.0    # residual maturity in years (for maturity cap)
    asset_class:    str   = "CORP" # CORP | SOVERIGN | SECURITISATION

# Supervisory DRC risk weights per credit quality (MAR22, Table MAR22.2)
_DRC_RW: Dict[str, float] = {
    "AAA":     0.005,
    "AA":      0.02,
    "A":       0.03,
    "BBB":     0.06,
    "BB":      0.15,
    "B":       0.30,
    "CCC":     0.50,
    "DEFAULT": 1.00,
    "UNRATED": 0.15,
}

class DRCCalculator:
    """
    Standardised Default Risk Charge per MAR22.

    Algorithm:
      1. Compute gross JTD per position:
           JTD_long  = max(LGD × Notional − MV,  0)  for long positions
           JTD_short = max(−LGD × Notional + MV, 0)  for short positions
      2. Net long vs short within the same credit quality bucket.
         Short positions can only offset 50% of long JTD (MAR22.24).
      3. Apply supervisory risk weight per quality bucket.
      4. Sum across all buckets → DRC.
    """

    def compute(self, positions: List[DRCPosition]) -> Dict[str, Any]:
        """
        Compute standardised DRC for a list of positions.
        Returns dict with total DRC and bucket breakdown.
        """
        if not positions:
            return {"drc_total": 0.0, "by_quality": {}, "jtd_net": 0.0}

        # Step 1: Gross JTD per position
        long_jtd_by_q:  Dict[str, float] = {}
        short_jtd_by_q: Dict[str, float] = {}

        for pos in positions:
            q   = pos.credit_quality.upper()
            rw  = _DRC_RW.get(q, _DRC_RW["UNRATED"])

            if pos.notional >= 0:
                # Long position: JTD = max(LGD × N − MV, 0)
                jtd = max(pos.lgd * pos.notional - pos.market_value, 0.0)
                long_jtd_by_q[q] = long_jtd_by_q.get(q, 0.0) + jtd
            else:
                # Short position: JTD_short = max(−LGD × N + MV, 0)
                jtd = max(-pos.lgd * pos.notional + pos.market_value, 0.0)
                short_jtd_by_q[q] = short_jtd_by_q.get(q, 0.0) + jtd

        # Step 2: Net JTD per bucket, 50% short offset (MAR22.24)
        drc_total = 0.0
        by_quality: Dict[str, Dict[str, float]] = {}
        all_qualities = set(list(long_jtd_by_q.keys()) + list(short_jtd_by_q.keys()))

        for q in all_qualities:
            rw     = _DRC_RW.get(q, _DRC_RW["UNRATED"])
            jtd_l  = long_jtd_by_q.get(q, 0.0)
            jtd_s  = short_jtd_by_q.get(q, 0.0)
            # Net JTD = long JTD − 50% of short JTD (conservative offset)
            net_jtd = max(jtd_l - 0.50 * jtd_s, 0.0)
            drc_q   = rw * net_jtd
            drc_total += drc_q
            by_quality[q] = {
                "jtd_long": jtd_l, "jtd_short": jtd_s,
                "jtd_net": net_jtd, "rw": rw, "drc": drc_q,
            }

        return {
            "drc_total":  drc_total,
            "by_quality": by_quality,
            "jtd_net":    sum(v["jtd_net"] for v in by_quality.values()),
        }

    @staticmethod
    def positions_from_sensitivities(
        sensitivities: Sequence["Sensitivity"],
        avg_notional: float = 1_000_000,
    ) -> List[DRCPosition]:
        """
        Derive approximate DRC positions from credit sensitivities.
        Used when explicit position data is unavailable (fallback).
        Quality bucket derived from bucket number heuristic.
        """
        quality_map = {
            "1":  "AAA",  "2":  "AA",   "3":  "A",   "4":  "BBB",
            "5":  "BBB",  "6":  "BB",   "7":  "BB",  "8":  "B",
            "9":  "B",   "10": "CCC",  "11": "CCC", "12": "DEFAULT",
        }
        positions = []
        for s in sensitivities:
            if s.risk_class not in ("CSR_NS", "CSR_SEC"):
                continue
            q = quality_map.get(s.bucket, "BBB")
            # Notional proxy from delta sensitivity
            notional = s.delta * 10_000  # 1bp delta → approximate notional
            if abs(notional) < 1:
                notional = avg_notional * (1 if s.delta >= 0 else -1)
            positions.append(DRCPosition(
                trade_id=s.trade_id, notional=notional,
                lgd=0.45, market_value=0.0,
                credit_quality=q, maturity_years=1.0,
            ))
        return positions

# ─────────────────────────────────────────────────────────────────────────────
# FRTB Master Engine
# ─────────────────────────────────────────────────────────────────────────────


class FRTBEngine:
    """
    FRTB capital calculator (SBM + IMA) per MAR21-33.
    Validates inputs, manages configuration, and orchestrates calculations.
    Includes:
      - position aggregation
      - scenario / what-if hooks
      - batch processing
      - basic risk decomposition
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()
        try:
            self.config.validate()
        except FRTBConfigurationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise

        self.sbm = SBMCalculator(self.config)
        self.ima = IMACalculator(self.config)
        logger.info("FRTB Engine initialised (SBM + IMA, MAR21-33)")


    def _ima_multiplier(self, backtesting_exceptions: int = 0) -> float:
        """
        MAR33.9: IMA multiplier mc = 1.5 + add-on based on backtesting exceptions.

        Exceptions (250d):  0-4 → +0.00  (green)
                            5   → +0.20
                            6   → +0.26
                            7   → +0.33
                            8   → +0.38
                            9   → +0.42
                           10+  → +0.50  (red zone, model revocation risk)
        """
        addon_table = {0:0.0, 1:0.0, 2:0.0, 3:0.0, 4:0.0,
                       5:0.20, 6:0.26, 7:0.33, 8:0.38, 9:0.42}
        addon = addon_table.get(backtesting_exceptions,
                                0.50 if backtesting_exceptions >= 10 else 0.0)
        return 1.5 + addon

    # ---- core compute -----------------------------------------------------

    def compute(
        self,
        portfolio_id: str,
        sensitivities: Sequence[Sensitivity],
        pnl_series: Optional[np.ndarray] = None,
        n_nmrf: int = 3,
        avg_notional: float = 1_000_000,
        run_date: Optional[date] = None,
        es_method: str = "historical",
        market_conditions: Optional[MarketConditions] = None,
        backtesting_exceptions: int = 0,
        pnl_by_risk_class: Optional[Dict[str, np.ndarray]] = None,
        drc_positions: Optional[List[DRCPosition]] = None,
        notionals_by_instrument: Optional[Dict[str, tuple]] = None,
        rtpl: Optional[np.ndarray] = None,
        hpl: Optional[np.ndarray] = None,
    ) -> FRTBResult:
        """
        backtesting_exceptions: number of VaR exceptions in the 250-day window.
            Drives the IMA multiplier per MAR33.9 (1.50 to 2.00).
        pnl_by_risk_class: {risk_class: pnl_array} for liquidity-horizon-adjusted ES.
            If provided, ES is computed using the MAR33.4 five-horizon formula.
            If None, falls back to simple √10 scaling (backward compatible).
        """
        """
        Compute complete FRTB capital charge with optional real-time market overlay.
        
        Args:
            market_conditions: Optional real-time market data.
                If None and use_market_conditions=True, fetches current conditions.
        """
        try:
            run_date = run_date or date.today()

            # Fetch real-time market conditions if enabled
            market: Optional[MarketConditions] = None
            if self.config.use_market_conditions:
                if market_conditions is not None:
                    market = market_conditions
                elif self.config.market_data_feed is not None:
                    market = self.config.market_data_feed.get_current_conditions()
                
                if market:
                    logger.info(
                        "FRTB with real-time conditions: regime=%s, stress=%.2f, VIX=%.1f",
                        market.regime().value, market.stress_level(), market.vix_level
                    )

            # Validate & aggregate
            validate_sensitivities(sensitivities, self.config)
            agg_sens = aggregate_sensitivities(sensitivities)

            if pnl_series is not None:
                validate_pnl_series(pnl_series)

            # ── SBM (with market overlay if enabled) ──
            delta_t, vega_t, curv_t, sbm_t, sbm_by_rc, sbm_by_bucket = self.sbm.total_sbm(agg_sens, market=market)

            # ── IMA / ES ──
            if pnl_by_risk_class:
                # MAR33.4: liquidity-horizon-adjusted ES (preferred path)
                es_base    = self.ima.compute_es_lh_adjusted(pnl_by_risk_class, stressed=False, method=es_method)
                es_stressed= self.ima.compute_es_lh_adjusted(pnl_by_risk_class, stressed=True,  method=es_method)
            elif pnl_series is not None and len(pnl_series) > 0:
                es_base    = self.ima.compute_es(pnl_series, stressed=False, method=es_method)
                es_stressed= self.ima.compute_es(pnl_series, stressed=True,  method=es_method)
            else:
                logger.info("No PnL series provided; generating synthetic for demonstration")
                rng = np.random.default_rng(42)
                pnl_series = rng.normal(0, avg_notional * 0.01, self.config.backtesting_window)
                es_base    = self.ima.compute_es(pnl_series, stressed=False, method=es_method)
                es_stressed= self.ima.compute_es(pnl_series, stressed=True,  method=es_method)

            nmrf_ch = self.ima.nmrf_charge(n_nmrf, avg_notional)
            ima_t   = max(es_base, es_stressed) + nmrf_ch

            # ── DRC (MAR22 / MAR33.18) ──────────────────────────────────────
            drc_calc = DRCCalculator()
            if drc_positions is None:
                drc_positions = DRCCalculator.positions_from_sensitivities(
                    agg_sens, avg_notional)
            drc_result  = drc_calc.compute(drc_positions)
            drc_total   = drc_result["drc_total"]
            drc_by_qual = drc_result["by_quality"]

            # ── RRAO (MAR23.5) ───────────────────────────────────────────────
            rrao_total = self.sbm.rrao_charge(agg_sens, notionals_by_instrument)

            # ── PLA test (MAR32) — desk IMA eligibility ───────────────────────
            pla_zone = "N/A"
            if rtpl is not None and hpl is not None:
                pla_res  = self.pla_test(rtpl, hpl)
                pla_zone = pla_res["zone"]
                if pla_zone == "RED":
                    logger.warning(
                        "FRTB [%s]: PLA test FAILED (RED) — desk forced to SBM", portfolio_id)
                    ima_t = 0.0   # IMA not available; SBM dominates

            # Capital = max(SBM + DRC + RRAO, mc × IMA + DRC)   [MAR33.8-33.9]
            mc = self._ima_multiplier(backtesting_exceptions)
            sbm_with_extras = sbm_t + drc_total + rrao_total
            ima_with_drc    = mc * ima_t + drc_total
            capital = max(sbm_with_extras, ima_with_drc)
            rwa     = capital * 12.5

            logger.info(
                "FRTB [%s] SBM=%.0f  IMA=%.0f  Capital=%.0f  RWA=%.0f",
                portfolio_id, sbm_t, ima_t, capital, rwa
            )

            ima_components = {
                "es_base_10d": es_base,
                "es_stressed_10d": es_stressed,
                "nmrf_charge": nmrf_ch,
                "ima_total": ima_t,
            }

            ima_components = {
                "es_base_10d":    es_base,
                "es_stressed_10d":es_stressed,
                "nmrf_charge":    nmrf_ch,
                "ima_total":      ima_t,
                "drc_total":      drc_total,
                "rrao_total":     rrao_total,
            }

            logger.info(
                "FRTB [%s] SBM=%.0f  DRC=%.0f  RRAO=%.0f  IMA=%.0f  "
                "Capital=%.0f  RWA=%.0f  PLA=%s",
                portfolio_id, sbm_t, drc_total, rrao_total, ima_t, capital, rwa, pla_zone
            )

            return FRTBResult(
                run_date=run_date,
                portfolio_id=portfolio_id,
                method="SBM+IMA",
                sbm_delta=delta_t,
                sbm_vega=vega_t,
                sbm_curvature=curv_t,
                sbm_total=sbm_t,
                es_99_10d=es_base,
                es_stressed=es_stressed,
                nmrf_charge=nmrf_ch,
                ima_total=ima_t,
                capital_market_risk=capital,
                rwa_market=rwa,
                drc_charge=drc_total,
                rrao_charge_v=rrao_total,
                pla_zone=pla_zone,
                sbm_by_risk_class=sbm_by_rc,
                sbm_by_bucket=sbm_by_bucket,
                ima_components=ima_components,
                drc_by_quality=drc_by_qual,
            )

        except (FRTBValidationError, FRTBCalculationError) as e:
            logger.error(f"FRTB computation failed for {portfolio_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in FRTB computation: {e}")
            raise FRTBCalculationError(f"Unexpected error: {e}")

    # ---- batch processing -------------------------------------------------


    def pla_test(
        self,
        rtpl: np.ndarray,
        hpl: np.ndarray,
    ) -> Dict[str, Any]:
        """
        MAR32.10: Profit & Loss Attribution (PLA) test.

        Compares RTPL (risk-theoretical P&L, using approved risk factors only)
        against HPL (hypothetical P&L, full desk revaluation).

        Green zone:  Spearman ≥ 0.80  AND  KS p-value ≥ 0.05
        Amber zone:  (Spearman ≥ 0.70  OR  KS p-value ≥ 0.05) and not Green
        Red zone:    Spearman < 0.70  AND  KS p-value < 0.05
                     → desk must revert to SBM

        Returns dict with zone, statistics, and capital surcharge flag.
        """
        try:
            from scipy.stats import spearmanr, ks_2samp
        except ImportError:
            logger.warning("scipy not available — PLA test using simplified statistics")
            # Fallback: Pearson correlation as proxy for Spearman
            n = min(len(rtpl), len(hpl))
            rtpl_s, hpl_s = rtpl[:n], hpl[:n]
            mean_r, mean_h = rtpl_s.mean(), hpl_s.mean()
            corr = float(np.dot(rtpl_s-mean_r, hpl_s-mean_h) / (
                np.linalg.norm(rtpl_s-mean_r) * np.linalg.norm(hpl_s-mean_h) + 1e-12))
            return {"zone": "GREEN" if corr >= 0.80 else "AMBER" if corr >= 0.70 else "RED",
                    "spearman": corr, "ks_pvalue": 0.10, "note": "scipy unavailable"}

        n = min(len(rtpl), len(hpl))
        rtpl_s, hpl_s = rtpl[:n], hpl[:n]

        spearman_corr, _ = spearmanr(rtpl_s, hpl_s)
        ks_stat, ks_pvalue = ks_2samp(rtpl_s, hpl_s)

        spearman_corr = float(spearman_corr)
        ks_pvalue     = float(ks_pvalue)

        if spearman_corr >= 0.80 and ks_pvalue >= 0.05:
            zone = "GREEN"
        elif spearman_corr >= 0.70 or ks_pvalue >= 0.05:
            zone = "AMBER"
        else:
            zone = "RED"

        logger.info("PLA test: Spearman=%.3f  KS_p=%.3f  → %s zone", spearman_corr, ks_pvalue, zone)

        return {
            "zone":           zone,
            "spearman":       spearman_corr,
            "ks_stat":        ks_stat,
            "ks_pvalue":      ks_pvalue,
            "ima_eligible":   zone in ("GREEN", "AMBER"),
            "capital_surcharge_required": zone == "AMBER",
        }

    def compute_batch(
        self,
        portfolios: Iterable[Dict[str, Any]],
    ) -> List[FRTBResult]:
        """
        Compute FRTB for multiple portfolios.
        portfolios: iterable of dicts with keys accepted by self.compute.
        """
        results: List[FRTBResult] = []
        for p in portfolios:
            results.append(self.compute(**p))
        return results

    # ---- scenario / what-if analysis -------------------------------------

    @staticmethod
    def apply_shock_to_sensitivities(
        sensitivities: Sequence[Sensitivity],
        scenario: ShockScenario,
    ) -> List[Sensitivity]:
        """
        Very simple shock application:
          - rate_bp: scales GIRR deltas
          - spread_bp: scales CSR_NS / CSR_SEC deltas
          - fx_pct: scales FX deltas
        """
        shocked: List[Sensitivity] = []
        for s in sensitivities:
            s_new = copy.copy(s)
            if s_new.risk_class == "GIRR":
                s_new.delta *= (1 + scenario.rate_bp / 10000.0)
            elif s_new.risk_class in ("CSR_NS", "CSR_SEC"):
                s_new.delta *= (1 + scenario.spread_bp / 10000.0)
            elif s_new.risk_class == "FX":
                s_new.delta *= (1 + scenario.fx_pct)
            shocked.append(s_new)
        return shocked

    def run_scenarios(
        self,
        portfolio_id: str,
        sensitivities: Sequence[Sensitivity],
        pnl_series: Optional[np.ndarray],
        scenarios: Sequence[ShockScenario],
        **kwargs,
    ) -> Dict[str, FRTBResult]:
        """
        Run multiple shock scenarios and return a mapping:
            scenario_name -> FRTBResult
        """
        results: Dict[str, FRTBResult] = {}
        for sc in scenarios:
            shocked_sens = self.apply_shock_to_sensitivities(sensitivities, sc)
            res = self.compute(
                portfolio_id=f"{portfolio_id}:{sc.name}",
                sensitivities=shocked_sens,
                pnl_series=pnl_series,
                **kwargs,
            )
            results[sc.name] = res
        return results

    # ---- parameter overrides ---------------------------------------------

    def compute_with_overrides(
        self,
        overrides: Dict[str, Dict[str, Any]],
        **compute_kwargs,
    ) -> FRTBResult:
        """
        Compute capital with configuration overrides (what-if on parameters).
        overrides example:
            {
              "delta_rw": {"GIRR": [0.02, ...]},
              "intra_corr": {"EQ": 0.3},
            }
        """
        cfg = copy.deepcopy(self.config)
        for section, vals in overrides.items():
            attr = getattr(cfg, section, None)
            if isinstance(attr, dict):
                attr.update(vals)
            else:
                setattr(cfg, section, vals)
        cfg.validate()
        engine = FRTBEngine(config=cfg)
        return engine.compute(**compute_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Backtesting — Traffic Light Framework (MAR99)
# ─────────────────────────────────────────────────────────────────────────────


class BacktestEngine:
    """
    Compares predicted VaR/ES vs actual P&L losses.
    MAR99: 0-4 exceptions = Green, 5-9 = Amber, 10+ = Red.
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()

    def evaluate(
        self,
        predicted: np.ndarray,   # 1-day VaR/ES predictions (positive = loss)
        actual_pnl: np.ndarray,  # actual daily P&L (negative = loss)
    ) -> Dict[str, Any]:
        """
        Evaluate backtesting exceptions against traffic light zones.
        """
        try:
            if len(predicted) != len(actual_pnl):
                raise FRTBValidationError("Length mismatch: predicted vs actual_pnl")
            if np.any(np.isnan(predicted)) or np.any(np.isnan(actual_pnl)):
                raise FRTBValidationError("Predicted or actual_pnl contains NaN")

            exceptions = int(np.sum(-actual_pnl > predicted))
            n = len(predicted)

            if exceptions <= self.config.green_zone_max:
                zone = "GREEN"
            elif exceptions <= self.config.amber_zone_max:
                zone = "AMBER"
            else:
                zone = "RED"

            logger.info(
                "Backtesting: %d exceptions / %d days → %s zone",
                exceptions, n, zone
            )

            mean_loss = float(((-actual_pnl[actual_pnl < 0]).mean())) if any(actual_pnl < 0) else 0.0

            return {
                "exceptions": exceptions,
                "window_days": n,
                "traffic_light": zone,
                "exception_pct": exceptions / n if n > 0 else 0.0,
                "mean_predicted": float(predicted.mean()),
                "mean_loss": mean_loss,
            }

        except FRTBValidationError:
            raise
        except Exception as e:
            raise FRTBCalculationError(f"Backtesting evaluation failed: {e}")
