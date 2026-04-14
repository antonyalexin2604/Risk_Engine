"""
PROMETHEUS Risk Platform
Engine: SA-CCR (Standardised Approach for Counterparty Credit Risk)
Regulatory basis: CRE52 (effective Jan 2023)

Implements:
  - Replacement Cost (RC) — CRE52.10 (unmargined), CRE52.18 (margined)
  - PFE Multiplier — CRE52.22–23
  - Add-On per asset class — CRE52.56–71
  - EAD = alpha × (RC + multiplier × AddOn_aggregate)
  - Margined EAD cap at unmargined EAD — CRE52.2

Fallback trace: every trade has saccr_method + fallback_trace_code

Regulatory Fixes Applied (CRE52 gap analysis):
  GAP-01  CRE52.52:   Margined MF = (3/2) × sqrt(MPOR/250); was missing the 3/2 scalar
  GAP-02  Table 2:    Credit SF is rating-granular (7 grades AAA→CCC); was flat IG/SG
  GAP-03  Table 2:    Credit index rho = 80% (single-name = 50%); was uniformly 50%
  GAP-04  Table 2:    Equity index SF = 20% / rho = 80%; single-name SF = 32% / rho = 50%
  GAP-05  Table 2:    Electricity commodity SF = 40% (separate hedging set); was 18%
  GAP-06  CRE52.40:   Option supervisory delta implemented (Black-Scholes + lambda-shift)
  GAP-07  CRE52.41:   CDO tranche delta implemented (attachment/detachment formula)
  GAP-08  CRE52.2:    Margined EAD now capped at unmargined EAD
  GAP-09  CRE52.46-47:Basis swap SF = ½×standard; volatility transaction SF = 5×standard
  GAP-10  CRE52.37:   Variable notional (amortising/leveraged) uses average_notional field
  GAP-11  CRE52.60:   Removed duplicate _resolve_sub_hedging_set() call in compute_addon_credit
  GAP-12  CRE52.34:   start_date field added; forward-starting swaps use correct S in SD formula
  GAP-13  Table 2:    SUPERVISORY_VOL dict added for all asset classes (required for GAP-06)
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import date, timedelta

from backend.config import SACCR

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    trade_id:          str
    asset_class:       str          # 'IR','FX','EQ','CR','CMDTY'
    instrument_type:   str          # 'IRS','CDS_Protection','CDS_Index','CDS_NonTranched',
                                    # 'CDO_Tranche','FXFwd','EquitySwap','CommodityFwd', etc.
    notional:          float        # Face / notional amount in notional_ccy
    notional_ccy:      str          # 'USD','EUR','GBP','JPY','CHF' etc.
    direction:         int          # +1 = long/payer/protection buyer, -1 = short/receiver/seller
    maturity_date:     date
    trade_date:        date

    # ── Mark-to-Market ────────────────────────────────────────────────────────
    current_mtm:       float = 0.0  # Current MTM in USD (from market_state engine)

    # ── IR specific ───────────────────────────────────────────────────────────
    fixed_rate:        Optional[float] = None   # Fixed coupon (decimal)
    reference_period:  Optional[float] = None   # Tenor in years (e.g. 5.0 for 5Y IRS)

    # ── Credit derivative classification (CRE52.47-53) ────────────────────────
    credit_sub_type:   str = "SINGLE_NAME"
    # Values:
    #   "SINGLE_NAME"      → single-name CDS/TRS on one reference entity
    #   "INDEX_CDS"        → non-tranched index (e.g. CDX IG, iTraxx) — rho treatment differs
    #   "NON_TRANCHED"     → non-tranched CDS index (alias for INDEX_CDS, regulatory
    #                        treatment identical; separate label for auditability)
    #   "TRANCHED"         → tranched synthetic CDO / CLO tranche (exotic; SA-CCR fallback)

    # ── Reference / Underlying ────────────────────────────────────────────────
    underlying_security_id: Optional[str] = None
    # IR:    Not applicable (None)
    # FX:    Not applicable (None); currency pair captured in notional_ccy
    # EQ:    Bloomberg ticker or ISIN of single stock / index (e.g. "AAPL UN Equity", "SPX Index")
    # CR:    Reference entity name or CDS ticker (e.g. "Ford Motor Co 5Y CDS", "CDX.NA.IG.41")
    # CMDTY: Commodity code (e.g. "WTI_CRUDE", "GOLD_SPOT", "CORN_FRONT")
    reference_entity:  Optional[str] = None    # CR: legal entity name
    commodity_type:    Optional[str] = None    # CMDTY: 'CMDTY_ENERGY','CMDTY_METALS','CMDTY_AGRI'

    # ── Hedging set routing (CRE52 Table 1 + CSV spec) ───────────────────────
    hedging_set:       Optional[str] = None
    # If None, auto-resolved by _resolve_hedging_set():
    #   IR    → notional_ccy (e.g. "USD", "EUR")           [all IR in same ccy = one set]
    #   FX    → currency pair string (e.g. "EURUSD")       [each pair = one set]
    #   EQ    → underlying_security_id or trade_id         [single name or index]
    #   CR    → reference_entity or underlying_security_id [single name or index]
    #   CMDTY → commodity_type (e.g. "CMDTY_ENERGY")       [oil, gas, power, metals]

    sub_hedging_set:   Optional[str] = None
    # If None, auto-resolved by _resolve_sub_hedging_set():
    #   IR    → "SHORT"  (≤1Y),  "MEDIUM"  (1–5Y),  "LONG"  (>5Y)
    #   CR    → "SINGLE_NAME" | "INDEX_CDS" | "TRANCHED" | "NON_TRANCHED"
    #   FX/EQ/CMDTY → "ALL" (no sub-split for these asset classes)

    # ── Calculation method ────────────────────────────────────────────────────
    saccr_method:      str = "SA_CCR"  # 'SA_CCR' | 'IMM' | 'FALLBACK'
    fallback_trace:    Optional[str] = None

    # ── SA-CCR sensitivities ──────────────────────────────────────────────────
    supervisory_delta: float = 1.0
    # CRE52.37-40:
    #   Linear (swaps, fwds):  +1 (long) or -1 (short)
    #   Options:               N(d1) for call,  -N(-d1) for put   (Black-Scholes delta)
    #   CDO tranche:           attachment/detachment implied delta (exotic — use SA-CCR)

    credit_quality:    str = "IG"   # 'IG' | 'SG' — legacy; superseded by rating-grade below
    credit_rating:     str = "BBB"  # 'AAA'|'AA'|'A'|'BBB'|'BB'|'B'|'CCC'|'NR' — CRE52 Table 2

    # ── Option fields (CRE52.40) ──────────────────────────────────────────────
    is_option:         bool = False
    option_type:       str  = "CALL"   # 'CALL' | 'PUT'
    option_position:   str  = "BOUGHT" # 'BOUGHT' | 'SOLD'
    strike:            Optional[float] = None   # option strike price / rate
    underlying_price:  Optional[float] = None   # forward price of underlying (P_i in CRE52.40)
    option_expiry:     Optional[date]  = None   # latest contractual exercise date (T_i)
    lambda_shift:      float = 0.0
    # lambda_shift (λ): lowest possible negative rate for this currency (CRE52.40 FAQ2)
    # e.g. 0.01 for EUR (where rates can go to -1%). Use 0.0 when rates can't be negative.

    # ── CDO tranche fields (CRE52.41) ─────────────────────────────────────────
    attachment_point:  Optional[float] = None   # A_i (e.g. 0.03 for 3% attachment)
    detachment_point:  Optional[float] = None   # D_i (e.g. 0.07 for 7% detachment)

    # ── Basis / volatility transaction flags (CRE52.46–47) ───────────────────
    is_basis:          bool = False
    # True → separate hedging set; SF = ½ × standard SF (e.g. two-float IRS LIBOR3M vs LIBOR6M)
    is_volatility:     bool = False
    # True → separate hedging set; SF = 5 × standard SF (variance/volatility swaps)

    # ── Variable notional (CRE52.37) ──────────────────────────────────────────
    notional_type:     str  = "FIXED"
    # 'FIXED'      → use notional as-is
    # 'AMORTISING' → use time-weighted average; provide average_notional
    # 'ACCRETING'  → use time-weighted average; provide average_notional
    # 'LEVERAGED'  → multiply notional by leverage_factor
    average_notional:  Optional[float] = None   # for AMORTISING/ACCRETING
    leverage_factor:   float = 1.0              # for LEVERAGED swaps (CRE52.37.iii)

    # ── Forward-starting swap (CRE52.34) ─────────────────────────────────────
    start_date:        Optional[date] = None
    # S_i in the SD formula: date when the referenced time period begins.
    # None → defaults to trade_date (i.e. S=0 for already-started swaps).
    # Set this for forward-starting IRS / swaptions (S_i > 0).

@dataclass
class NettingSet:
    netting_id:        str
    counterparty_id:   str
    trades:            List[Trade]  = field(default_factory=list)
    initial_margin:    float = 500_000.0  # IM received (positive = received)
    variation_margin:  float = 0.0  # VM received
    threshold:         float = 0.0
    mta:               float = 200_000
    has_csa:           bool = True
    mpor_days:         int = 10

@dataclass
class SAcCRResult:
    netting_id:       str
    run_date:         date
    replacement_cost: float           # Portfolio-level RC
    pfe_multiplier:   float           # Portfolio-level PFE multiplier
    add_on_ir:        float           # Portfolio IR add-on
    add_on_fx:        float           # Portfolio FX add-on
    add_on_credit:    float           # Portfolio Credit add-on
    add_on_equity:    float           # Portfolio Equity add-on
    add_on_commodity: float           # Portfolio Commodity add-on
    add_on_aggregate: float           # Total portfolio add-on
    ead:              float           # Portfolio EAD = alpha × (RC + mult × AddOn)
    alpha:            float = SACCR.alpha
    # rc, addon allocated to individual trades (see trade_results)
    trade_results:    Dict[str, dict] = field(default_factory=dict)
    # trade_results[trade_id] contains:
    #   portfolio_id, trade_id, current_mtm, rc_allocated, rc_portfolio
    #   addon_trade, addon_portfolio, pfe_trade, pfe_portfolio
    #   hedging_set, sub_hedging_set, supervisory_duration, supervisory_factor
    #   maturity_factor, supervisory_delta, sign_delta, underlying_security_id
    #   saccr_notional, saccr_adjusted_notional, effective_notional
    #   ead_trade, ead_portfolio, risk_weight_pct, rwa, ead_calc_type

# ─────────────────────────────────────────────────────────────────────────────
# Supervisory Parameters (CRE52 Table 2)
# ─────────────────────────────────────────────────────────────────────────────

# Supervisory factors by asset class / bucket (CRE52 Table 2)
SF: Dict[str, float] = {
    # Interest Rate (CRE52 Table 2)
    "IR":                   0.0050,
    # FX (CRE52 Table 2)
    "FX":                   0.0400,
    # Equity (CRE52 Table 2) — single name vs index differ
    "EQ":                   0.3200,   # single name
    "EQ_INDEX":             0.2000,   # index  (CRE52 Table 2)
    # Credit — single-name CDS, 7-grade SF per CRE52 Table 2
    "CR_AAA":               0.0038,
    "CR_AA":                0.0038,
    "CR_A":                 0.0042,
    "CR_BBB":               0.0054,
    "CR_BB":                0.0106,
    "CR_B":                 0.0160,
    "CR_CCC":               0.0600,
    # Credit — non-tranched index CDS (CRE52 Table 2)
    "CR_IDX_IG":            0.0050,   # CRE52 Table 2: IG index = 0.50%
    "CR_IDX_SG":            0.0500,   # CRE52 Table 2: SG index = 5.00%
    # Legacy IG/SG aliases — aligned to CRE52 Table 2 broad IG/SG split.
    # CRE52 Table 2 prescribes two supervisory factors for the simplified
    # IG vs SG treatment: IG = 0.50%, SG = 5.00%.  These are the values
    # used when counterparty credit quality is only known at the broad
    # investment-grade / sub-investment-grade level (no notched rating).
    "CR_IG":                0.0050,   # CRE52 Table 2: IG single-name = 0.50%
    "CR_SG":                0.0500,   # CRE52 Table 2: SG single-name = 5.00%
    "CR_IDX":               0.0038,   # AAA/AA index (legacy, prefer CR_IDX_IG)
    # Credit — tranched CDS per CRE52.41 (use SG scale conservatively)
    "CR_TRANCHED_IG":       0.0054,
    "CR_TRANCHED_SG":       0.0106,
    # Commodity — Electricity is a separate sub-class with SF=40% (CRE52 Table 2)
    "CMDTY_ELECTRICITY":    0.4000,   # Electricity (extreme vol)
    "CMDTY_ENERGY":         0.1800,   # Oil/Gas
    "CMDTY_METALS":         0.1800,   # Base and precious metals
    "CMDTY_AGRI":           0.1800,   # Agricultural
    "CMDTY_OTHER":          0.1800,   # Other commodity
}

# Per-entity systemic correlation (rho) for credit and equity aggregation
# (CRE52 Table 2)
CREDIT_RHO: Dict[str, float] = {
    "SINGLE_NAME":  0.50,   # CRE52 Table 2: single-name CDS
    "NON_TRANCHED": 0.50,   # same treatment as SINGLE_NAME for rho
    "TRANCHED":     0.50,   # conservative
    "INDEX_CDS":    0.80,   # CRE52 Table 2: index CDS
}
EQUITY_RHO: Dict[str, float] = {
    "SINGLE_NAME":  0.50,   # CRE52 Table 2: single-name equity
    "INDEX":        0.80,   # CRE52 Table 2: equity index
}

# Supervisory option volatilities (CRE52 Table 2) — mandatory, not estimates
# Used in option supervisory delta computation (GAP-06 / CRE52.40)
SUPERVISORY_VOL: Dict[str, float] = {
    "IR":           0.50,    # 50% for all IR swaptions (CRE52.72 FAQ1)
    "FX":           0.15,    # 15%
    "EQ":           1.20,    # 120% single-name equity option
    "EQ_INDEX":     0.75,    # 75% equity index option
    "CR":           1.00,    # 100% single-name credit option
    "CR_INDEX":     0.80,    # 80% credit index option
    "CMDTY_ELECTRICITY": 1.50,  # 150%
    "CMDTY_ENERGY": 0.70,   # 70% oil/gas
    "CMDTY_METALS": 0.70,
    "CMDTY_AGRI":   0.70,
    "CMDTY_OTHER":  0.70,
}

# Hedging set definition per CRE52 (Table 1) and the uploaded CSV spec
# Asset Class        → Hedging Set Basis
# IR Derivatives     → Currency (all USD IR swaps in one hedging set)
# FX Derivatives     → Currency pair (EUR/USD is one set)
# Equity Derivatives → Single equity index or single name
# Credit Derivatives → Single reference name or index
# Commodities        → Commodity type (oil, gas, power, metals)
HEDGING_SET_BASIS: Dict[str, str] = {
    "IR":    "Currency",
    "FX":    "Currency pair",
    "EQ":    "Single equity or index",
    "CR":    "Single reference name or index",
    "CMDTY": "Commodity type (energy / metals / agri / other)",
}

# Sub-hedging set definitions
# IR: maturity buckets (within-bucket netting benefit > across-bucket)
IR_SUB_HEDGING_SETS = {
    "SHORT":  "0–1 year",
    "MEDIUM": "1–5 years",
    "LONG":   "5+ years",
}

# Credit: instrument type buckets
CR_SUB_HEDGING_SETS = {
    "SINGLE_NAME":  "Single-name CDS or TRS on one reference entity",
    "INDEX_CDS":    "Non-tranched index CDS (CDX IG/HY, iTraxx Main/Xover)",
    "NON_TRANCHED": "Non-tranched index CDS (alias — same treatment as INDEX_CDS)",
    "TRANCHED":     "Tranched synthetic CDO / CLO tranche (exotic — SA-CCR fallback)",
}

# IR supervisory duration factors (CRE52.39)
def supervisory_duration(trade_date: date, start_date: date, end_date: date) -> float:
    """CRE52.39: SD = (exp(-0.05*S) - exp(-0.05*E)) / 0.05"""
    S = max((start_date - trade_date).days / 365.0, 0)
    E = max((end_date   - trade_date).days / 365.0, 0)
    if E <= 0:
        return 0.0
    return (math.exp(-0.05 * S) - math.exp(-0.05 * E)) / 0.05

# Maturity factor (CRE52.48-53)
def maturity_factor(trade: Trade, has_csa: bool, mpor_days: int) -> float:
    today = date.today()
    Mi = max((trade.maturity_date - today).days / 365.0, 10/365.0)
    if has_csa:
        # CRE52.52: MF = (3/2) × sqrt(MPOR/250)
        # The 3/2 scalar is mandatory for margined transactions.
        # MPOR floored at 10 business days (CRE52.50); 250 = business days/year.
        MF = 1.5 * math.sqrt(mpor_days / 250.0)
    else:
        # CRE52.49: Unmargined: MF = sqrt(min(M_i, 1)) where M_i in years
        # M_i is floored at 10 business days = 10/250 years.
        MF = math.sqrt(min(Mi, 1.0))
    return MF

# ─────────────────────────────────────────────────────────────────────────────
# IMM Eligibility Check + Fallback Logic (req #9)
# ─────────────────────────────────────────────────────────────────────────────

IMM_ELIGIBLE_INSTRUMENTS = {
    "IRS", "CRS", "OIS", "FXFwd", "FXOption", "EquitySwap", "TRS",
}
IMM_INELIGIBLE_REASONS = {
    "EXOTIC_PAYOFF":    "Exotic payoff structure — IMM not approved for this type",
    "NEW_PRODUCT":      "Instrument newly approved, MPLA not yet validated",
    "STRESSED_PERIOD":  "Trade originated in stress period; SA-CCR mandated",
    "MODEL_LIMIT":      "Model not calibrated for this tenor/currency pair",
    "REGULATORY_FLOOR": "IMM EAD below SA-CCR floor — SA-CCR applied (CRE53.5)",
}

def check_imm_eligibility(trade: Trade) -> Tuple[bool, Optional[str]]:
    """
    Returns (is_eligible, fallback_trace_code).
    Req #9: record trace code when falling back to SA-CCR.
    """
    if trade.instrument_type not in IMM_ELIGIBLE_INSTRUMENTS:
        code = f"FALLBACK|{trade.trade_id}|EXOTIC_PAYOFF|{IMM_INELIGIBLE_REASONS['EXOTIC_PAYOFF']}"
        return False, code
    # Check model limit (simplified check)
    if trade.notional > 5e9:
        code = f"FALLBACK|{trade.trade_id}|MODEL_LIMIT|Notional > 5bn USD threshold"
        return False, code
    return True, None

# ─────────────────────────────────────────────────────────────────────────────
# Add-On Calculations per Asset Class
# ─────────────────────────────────────────────────────────────────────────────

def _adjusted_notional_ir(trade: Trade) -> float:
    """CRE52.34: d = notional × SD, where SD uses S_i (start date) and E_i (end date).

    For forward-starting swaps, S_i > 0 (the swap hasn't started yet).
    Use trade.start_date if set; otherwise S defaults to today (S=0 for in-progress swaps).
    """
    today = date.today()
    # S_i: time until the referenced period begins (years); 0 if already started
    s_anchor = trade.start_date if trade.start_date else today
    start    = s_anchor
    end      = trade.maturity_date
    sd       = supervisory_duration(today, start, end)
    notional = _effective_trade_notional(trade)
    return notional * sd

def _effective_trade_notional(trade: Trade) -> float:
    """
    CRE52.37: Resolve the notional to use in adjusted-notional calculation.

      FIXED      → use trade.notional as-is
      AMORTISING / ACCRETING → use trade.average_notional if provided (CRE52.37.ii)
      LEVERAGED  → multiply trade.notional by trade.leverage_factor (CRE52.37.iii)
    """
    nt = trade.notional_type.upper()
    if nt in ("AMORTISING", "ACCRETING") and trade.average_notional is not None:
        return trade.average_notional
    if nt == "LEVERAGED":
        return trade.notional * trade.leverage_factor
    return trade.notional


def _adjusted_notional_other(trade: Trade) -> float:
    """For FX/EQ/CR/CMDTY: adjusted notional = notional (CRE52.44)"""
    return _effective_trade_notional(trade)

def compute_supervisory_delta(trade: Trade) -> float:
    """
    CRE52.38–41: Compute the supervisory delta for a trade.

    Non-options / non-tranches (CRE52.38):
      delta = +1 (long) or -1 (short), per trade.direction.
      For these the caller should leave supervisory_delta = +1 and use direction.

    Options (CRE52.40 + FAQ2):
      d1 = (ln((P+λ) / (K+λ)) + 0.5σ²T) / (σ√T)
      Call bought : +Φ(+d1)   Call sold : −Φ(+d1)
      Put  bought : −Φ(−d1)   Put  sold : +Φ(−d1)
      λ-shift applies when P/K ≤ 0 (negative rate environment).

    CDO tranches (CRE52.41):
      d₁ = Φ⁻¹(A) / 0.97,  d₂ = Φ⁻¹(D) / 0.97
      |delta| = 15 / (D − A) × (Φ(d₂) − Φ(d₁))
      Sign: +1 if long protection (purchased), −1 if short.

    Returns the signed supervisory delta (δ_i) combining position direction.
    """
    from math import log, sqrt, exp
    try:
        import scipy.stats as _st
        def _norm_cdf(x: float) -> float: return float(_st.norm.cdf(x))   # type: ignore[misc]
        def _norm_ppf(p: float) -> float: return float(_st.norm.ppf(p))   # type: ignore[misc]
    except ImportError:
        # Pure-math fallback using erf
        import math as _m
        def _norm_cdf(x):  # type: ignore[misc]
            return 0.5 * (1.0 + _m.erf(x / _m.sqrt(2.0)))
        def _norm_ppf(p):  # type: ignore[misc]
            # Beasley-Springer-Moro approximation for Φ⁻¹
            a = [0, -3.969683028665376e+01, 2.209460984245205e+02,
                 -2.759285104469687e+02, 1.383577518672690e+02,
                 -3.066479806614716e+01, 2.506628277459239e+00]
            b = [0, -5.447609879822406e+01, 1.615858368580409e+02,
                 -1.556989798598866e+02, 6.680131188771972e+01,
                 -1.328068155288572e+01]
            c = [0, -7.784894002430293e-03, -3.223964580411365e-01,
                 -2.400758277161838e+00, -2.549732539343734e+00,
                 4.374664141464968e+00, 2.938163982698783e+00]
            d = [0, 7.784695709041462e-03, 3.224671290700398e-01,
                 2.445134137142996e+00, 3.754408661907416e+00]
            p_low, p_high = 0.02425, 1 - 0.02425
            if p < p_low:
                q = _m.sqrt(-2 * _m.log(p))
                return (((((c[1]*q+c[2])*q+c[3])*q+c[4])*q+c[5])*q+c[6]) / \
                       ((((d[1]*q+d[2])*q+d[3])*q+d[4])*q+1)
            elif p <= p_high:
                q = p - 0.5; r = q*q
                return (((((a[1]*r+a[2])*r+a[3])*r+a[4])*r+a[5])*r+a[6])*q / \
                       (((((b[1]*r+b[2])*r+b[3])*r+b[4])*r+b[5])*r+1)
            else:
                q = _m.sqrt(-2 * _m.log(1 - p))
                return -(((((c[1]*q+c[2])*q+c[3])*q+c[4])*q+c[5])*q+c[6]) / \
                        ((((d[1]*q+d[2])*q+d[3])*q+d[4])*q+1)

    sign = 1 if trade.direction > 0 else -1

    # ── CDO tranche (CRE52.41) ──────────────────────────────────────────
    if (trade.credit_sub_type == "TRANCHED" and
            trade.attachment_point is not None and
            trade.detachment_point is not None):
        A, D = trade.attachment_point, trade.detachment_point
        if D <= A or A < 0 or D > 1:
            logger.warning("Trade %s: invalid tranche [A=%.4f, D=%.4f]; delta=1.",
                           trade.trade_id, A, D)
            return float(sign)
        # Clip away boundary singularities (Phi-inv of 0 or 1 is ±inf)
        A_clip = max(A, 1e-6)
        D_clip = min(D, 1 - 1e-6)
        d1_t = _norm_ppf(A_clip) / 0.97
        d2_t = _norm_ppf(D_clip) / 0.97
        delta_abs = (15.0 / (D - A)) * (_norm_cdf(d2_t) - _norm_cdf(d1_t))
        return sign * delta_abs

    # ── Option (CRE52.40) ───────────────────────────────────────────────
    if trade.is_option:
        P = trade.underlying_price
        K = trade.strike
        lam = trade.lambda_shift
        opt_type   = trade.option_type.upper()    # 'CALL' | 'PUT'
        opt_pos    = trade.option_position.upper() # 'BOUGHT' | 'SOLD'

        # Resolve supervisory vol from SUPERVISORY_VOL table
        ac = trade.asset_class
        if ac == "EQ" and trade.underlying_security_id:
            # Distinguish single-name vs index by a rough heuristic
            uid = (trade.underlying_security_id or "").upper()
            sv_key = "EQ_INDEX" if ("INDEX" in uid or "SPX" in uid or
                                     "SX5E" in uid or "NDX" in uid) else "EQ"
        elif ac == "CR":
            shs_tmp = _resolve_sub_hedging_set(trade)
            sv_key = "CR_INDEX" if shs_tmp in ("INDEX_CDS", "NON_TRANCHED") else "CR"
        elif ac == "CMDTY":
            sv_key = trade.commodity_type or "CMDTY_OTHER"
        else:
            sv_key = ac
        sigma = SUPERVISORY_VOL.get(sv_key, SUPERVISORY_VOL.get(ac, 0.50))

        # Expiry in years
        today = date.today()
        exp_date = trade.option_expiry or trade.maturity_date
        T = max((exp_date - today).days / 365.0, 1e-6)

        if P is None or K is None:
            logger.warning("Trade %s: option missing P/K — using delta=%.1f.",
                           trade.trade_id, float(sign))
            return float(sign)

        # Lambda-shift for negative rate environments (CRE52.40 FAQ2)
        # Apply shift BEFORE checking positivity so that negative-rate options
        # with an appropriate lambda are handled correctly.
        P_adj = P + lam
        K_adj = K + lam
        if P_adj <= 0 or K_adj <= 0:
            logger.warning("Trade %s: P+λ or K+λ ≤ 0 even after shift (P=%.4f K=%.4f λ=%.4f); "
                           "delta=%.1f.", trade.trade_id, P, K, lam, float(sign))
            return float(sign)

        d1 = (log(P_adj / K_adj) + 0.5 * sigma**2 * T) / (sigma * sqrt(T))

        if opt_type == "CALL":
            delta_abs = _norm_cdf(d1)
            delta_signed = delta_abs if opt_pos == "BOUGHT" else -delta_abs
        else:  # PUT
            delta_abs = _norm_cdf(-d1)
            delta_signed = -delta_abs if opt_pos == "BOUGHT" else delta_abs

        return delta_signed

    # ── Linear / non-option (CRE52.38) ──────────────────────────────────
    return float(sign)


    if trade.asset_class == "IR":
        d = _adjusted_notional_ir(trade)
    else:
        d = _adjusted_notional_other(trade)
    MF = maturity_factor(trade, has_csa, mpor_days)
    return trade.supervisory_delta * d * MF

def _remaining_maturity_years(trade: Trade, as_of: Optional[date] = None) -> float:
    as_of = as_of or date.today()
    return max((trade.maturity_date - as_of).days / 365.0, 0.0)

def _resolve_hedging_set(trade: Trade) -> str:
    """
    Resolve hedging set key per CRE52 Table 1 and the CSV specification.
    If explicit `hedging_set` is provided on the trade, it takes precedence.

    Hedging set basis (per CSV: asset-class-hedging-set-basis):
      IR    → Currency          (all USD IR swaps form one set)
      FX    → Currency pair     (EUR/USD is one set)
      EQ    → Single equity index or single name
      CR    → Single reference name or index
      CMDTY → Commodity type    (oil, gas, power, metals)
    """
    if trade.hedging_set:
        return trade.hedging_set

    if trade.asset_class == "IR":
        # All IR derivatives in the same currency belong to the same hedging set
        return trade.notional_ccy.upper()

    if trade.asset_class == "FX":
        # Each currency pair is its own hedging set
        # Normalise: always smaller alphabetically first (USD/EUR → EURUSD)
        base = "USD"
        ccy  = trade.notional_ccy.upper()
        pair = "".join(sorted([base, ccy]))
        return pair

    if trade.asset_class == "EQ":
        # Single name or index identifier
        uid = trade.underlying_security_id or trade.reference_entity or trade.trade_id
        return uid

    if trade.asset_class == "CR":
        # Single reference name or index identifier
        uid = trade.reference_entity or trade.underlying_security_id or trade.trade_id
        return uid

    if trade.asset_class == "CMDTY":
        # Commodity type bucket
        return trade.commodity_type or "CMDTY_OTHER"

    return trade.asset_class

def _resolve_sub_hedging_set(trade: Trade, as_of: Optional[date] = None) -> str:
    """
    Resolve sub-hedging set key per CRE52.

    If explicit `sub_hedging_set` is provided on the trade it takes precedence.

    IR sub-hedging sets (CRE52.43):
      Within-bucket netting is more generous than across-bucket netting.
      Bucket 1 (SHORT):  residual maturity 0–1 year
      Bucket 2 (MEDIUM): residual maturity 1–5 years
      Bucket 3 (LONG):   residual maturity 5+ years

    Credit derivative sub-hedging sets (CRE52.47-53):
      SINGLE_NAME  → individual CDS / TRS on one reference entity
      INDEX_CDS    → non-tranched CDS index (CDX IG/HY, iTraxx Main/Xover)
      NON_TRANCHED → alias for INDEX_CDS (same regulatory treatment)
      TRANCHED     → tranched CDO / CLO tranche (exotic instrument)

    FX / EQ / CMDTY → "ALL" (no sub-bucket split within a hedging set)
    """
    if trade.sub_hedging_set:
        return trade.sub_hedging_set

    if trade.asset_class == "IR":
        mat = _remaining_maturity_years(trade, as_of=as_of)
        if mat <= 1.0:
            return "SHORT"
        elif mat <= 5.0:
            return "MEDIUM"
        else:
            return "LONG"

    if trade.asset_class == "CR":
        # Derive from instrument type or credit_sub_type field
        sub = getattr(trade, "credit_sub_type", "SINGLE_NAME")
        if sub in CR_SUB_HEDGING_SETS:
            return sub
        # Fallback: derive from instrument type
        itype = trade.instrument_type.upper()
        if "TRANCHE" in itype or "CDO" in itype:
            return "TRANCHED"
        if "INDEX" in itype:
            return "INDEX_CDS"
        return "SINGLE_NAME"

    return "ALL"

def _effective_notional(trade: Trade, has_csa: bool, mpor_days: int) -> float:
    """Signed effective notional D_i = delta_i × d_i × MF_i (CRE52.34/56)."""
    if trade.asset_class == "IR":
        d = _adjusted_notional_ir(trade)
    else:
        d = _adjusted_notional_other(trade)
    MF = maturity_factor(trade, has_csa, mpor_days)
    # supervisory_delta on the trade may be pre-computed; use it if non-default
    delta = trade.supervisory_delta
    return delta * d * MF

def compute_addon_ir(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """
    CRE52.56–57: IR add-on via hedging set and sub-hedging set aggregation.

    Hedging set defaults to currency unless explicitly provided on the trade.
    Sub-hedging set defaults to residual maturity buckets (SHORT/MEDIUM/LONG).

    Basis transactions (CRE52.46): SF = ½ × 0.50% = 0.25%.
    Volatility transactions (CRE52.47): SF = 5 × 0.50% = 2.50%.
    Both get their own hedging set (suffixed with ':BASIS' or ':VOL').
    """
    hedging_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "IR":
            continue
        # GAP-09: apply SF scaling for basis / volatility trades
        if t.is_volatility:
            sf = SF["IR"] * 5.0
            hs_suffix = ":VOL"
        elif t.is_basis:
            sf = SF["IR"] * 0.5
            hs_suffix = ":BASIS"
        else:
            sf = SF["IR"]
            hs_suffix = ""
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * sf
        hs  = _resolve_hedging_set(t) + hs_suffix
        shs = _resolve_sub_hedging_set(t)
        if hs not in hedging_buckets:
            hedging_buckets[hs] = {}
        hedging_buckets[hs][shs] = hedging_buckets[hs].get(shs, 0.0) + en

    total_addon = 0.0
    for _, sub_bucket in hedging_buckets.items():
        d1 = sub_bucket.get("SHORT",  0.0)
        d2 = sub_bucket.get("MEDIUM", 0.0)
        d3 = sub_bucket.get("LONG",   0.0)

        # CRE52.57: IR sub-hedging set aggregation
        # ρ(B1,B2) = ρ(B2,B3) = 0.70 → coefficient 1.40
        # ρ(B1,B3) = 0.30               → coefficient 0.60
        std_component = (d1*d1 + d2*d2 + d3*d3
                         + 1.4*d1*d2 + 1.4*d2*d3 + 0.6*d1*d3)
        addon_hs = math.sqrt(max(std_component, 0.0))

        # Custom labels: add conservatively
        for key, value in sub_bucket.items():
            if key not in {"SHORT", "MEDIUM", "LONG"}:
                addon_hs += abs(value)

        total_addon += addon_hs

    return total_addon

def compute_addon_fx(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """CRE52.58–59: FX add-on by currency pair hedging set.

    Basis transactions (CRE52.46): SF = ½ × 4% = 2%.
    Volatility transactions (CRE52.47): SF = 5 × 4% = 20%.
    """
    pair_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "FX":
            continue
        if t.is_volatility:
            sf = SF["FX"] * 5.0
            hs_suffix = ":VOL"
        elif t.is_basis:
            sf = SF["FX"] * 0.5
            hs_suffix = ":BASIS"
        else:
            sf = SF["FX"]
            hs_suffix = ""
        en  = _effective_notional(t, has_csa, mpor_days) * t.direction * sf
        hs  = _resolve_hedging_set(t) + hs_suffix
        shs = _resolve_sub_hedging_set(t)
        if hs not in pair_buckets:
            pair_buckets[hs] = {}
        pair_buckets[hs][shs] = pair_buckets[hs].get(shs, 0.0) + en

    return sum(abs(sum(sub.values())) for sub in pair_buckets.values())

def compute_addon_credit(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """
    CRE52.60–64: Credit add-on with rating-granular SF and per-entity rho.

    GAP-02 (CRE52 Table 2): SF is 7-grade: AAA/AA=0.38%, A=0.42%, BBB=0.54%,
                             BB=1.06%, B=1.60%, CCC=6.00%.
    GAP-03 (CRE52 Table 2): Index CDS rho = 80% (single-name = 50%).
    GAP-09 (CRE52.46-47):   Basis trades SF = ½x; volatility trades SF = 5x.
    GAP-11:                  Removed duplicate _resolve_sub_hedging_set() call.

    Aggregation formula (single-factor):
      AddOn = sqrt( (sum_e rho_e * AddOn_e)^2 + sum_e (1 - rho_e^2) * AddOn_e^2 )
    """
    # Per-entity: {hedging_set: (effective_notional, rho, sf)}
    entity_en:  Dict[str, float] = {}
    entity_rho: Dict[str, float] = {}

    # Rating → SF lookup (CRE52 Table 2 — 7 grades)
    RATING_SF: Dict[str, str] = {
        "AAA": "CR_AAA", "AA": "CR_AA", "A": "CR_A",
        "BBB": "CR_BBB", "BB": "CR_BB", "B": "CR_B", "CCC": "CR_CCC",
        "NR":  "CR_BBB",  # unrated → conservative BBB
        "IG":  "CR_BBB",  # legacy mapping
        "SG":  "CR_BB",   # legacy mapping
    }

    for t in trades:
        if t.asset_class != "CR":
            continue
        # GAP-11: resolve shs exactly once
        shs = _resolve_sub_hedging_set(t)

        # GAP-02: 7-grade rating-based SF
        # credit_quality "IG"/"SG" takes precedence over the defaulted credit_rating="BBB"
        cq_     = getattr(t, "credit_quality", "IG").upper()
        cr_     = getattr(t, "credit_rating",  "BBB").upper()
        rating  = cq_ if cq_ in ("IG", "SG") else cr_
        if shs == "TRANCHED":
            sf_key = "CR_TRANCHED_IG" if rating in ("AAA","AA","A","BBB","IG") else "CR_TRANCHED_SG"
        elif shs in ("INDEX_CDS", "NON_TRANCHED"):
            sf_key = "CR_IDX_IG" if rating in ("AAA","AA","A","BBB","IG") else "CR_IDX_SG"
        else:
            sf_key = RATING_SF.get(rating, "CR_BBB")

        # GAP-09: basis / volatility SF scaling
        base_sf = SF[sf_key]
        if t.is_volatility:
            sf_val = base_sf * 5.0
            hs_suffix = ":VOL"
        elif t.is_basis:
            sf_val = base_sf * 0.5
            hs_suffix = ":BASIS"
        else:
            sf_val = base_sf
            hs_suffix = ""

        en  = _effective_notional(t, has_csa, mpor_days) * t.direction * sf_val
        hs  = _resolve_hedging_set(t) + hs_suffix

        # GAP-03: per-entity rho — index=80%, single-name/tranched=50%
        rho = CREDIT_RHO.get(shs, 0.50)

        entity_en[hs]  = entity_en.get(hs, 0.0) + en
        entity_rho[hs] = rho   # last write wins; all trades in same HS share sub-type

    if not entity_en:
        return 0.0

    # Single-factor aggregation (CRE52.64)
    systematic   = sum(entity_rho[hs] * entity_en[hs] for hs in entity_en) ** 2
    idiosyncratic = sum((1 - entity_rho[hs]**2) * entity_en[hs]**2 for hs in entity_en)
    return math.sqrt(systematic + idiosyncratic)

def compute_addon_equity(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """
    CRE52.65–68: Equity add-on with per-entity SF and rho.

    GAP-04 (CRE52 Table 2):
      Single-name: SF = 32%, rho = 50%.
      Index:       SF = 20%, rho = 80%.
    GAP-09 (CRE52.46-47): basis SF = ½x; volatility SF = 5x.

    Index detection: trade.underlying_security_id contains 'INDEX', common index
    tickers (SPX, SX5E, NDX, RUT, FTSE, DAX, NIKKEI, HSI) or the trade is
    tagged is_volatility=True on an EQ underlying (variance swap on index).
    """
    entity_en:  Dict[str, float] = {}
    entity_rho: Dict[str, float] = {}

    _INDEX_KEYWORDS = frozenset([
        "INDEX", "SPX", "SX5E", "NDX", "RUT", "FTSE", "DAX",
        "NIKKEI", "HSI", "KOSPI", "ASX", "CAC", "IBEX",
    ])

    for t in trades:
        if t.asset_class != "EQ":
            continue

        uid = (t.underlying_security_id or "").upper()
        is_index = any(kw in uid for kw in _INDEX_KEYWORDS)
        rho    = EQUITY_RHO["INDEX"] if is_index else EQUITY_RHO["SINGLE_NAME"]
        sf_key = "EQ_INDEX" if is_index else "EQ"
        base_sf = SF[sf_key]

        # GAP-09: basis / volatility SF scaling
        if t.is_volatility:
            sf_val    = base_sf * 5.0
            hs_suffix = ":VOL"
        elif t.is_basis:
            sf_val    = base_sf * 0.5
            hs_suffix = ":BASIS"
        else:
            sf_val    = base_sf
            hs_suffix = ""

        en  = _effective_notional(t, has_csa, mpor_days) * t.direction * sf_val
        hs  = _resolve_hedging_set(t) + hs_suffix

        entity_en[hs]  = entity_en.get(hs, 0.0) + en
        entity_rho[hs] = rho

    if not entity_en:
        return 0.0

    # Single-factor aggregation (CRE52.68)
    systematic    = sum(entity_rho[hs] * entity_en[hs] for hs in entity_en) ** 2
    idiosyncratic = sum((1 - entity_rho[hs]**2) * entity_en[hs]**2 for hs in entity_en)
    return math.sqrt(systematic + idiosyncratic)

def compute_addon_commodity(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """
    CRE52.69–71: Commodity add-on by hedging set and commodity type.

    GAP-05 (CRE52 Table 2): Electricity is a separate hedging set with SF=40%.
      Hedging sets: CMDTY_ELECTRICITY (40%), CMDTY_ENERGY (18% oil/gas),
                    CMDTY_METALS (18%), CMDTY_AGRI (18%), CMDTY_OTHER (18%).
    GAP-09 (CRE52.46-47): Basis trades SF = ½x; volatility trades SF = 5x.

    Aggregation formula per hedging set (rho=40%):
      AddOn_HS = sqrt( (rho * sum_type D_type)^2 + (1-rho^2) * sum_type D_type^2 )
    No offsetting between the five hedging sets (CRE52.69).
    """
    subtype_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "CMDTY":
            continue
        hs = _resolve_hedging_set(t)
        # Electricity trades should carry commodity_type='CMDTY_ELECTRICITY'
        base_sf = SF.get(hs, SF["CMDTY_OTHER"])

        # GAP-09: basis / volatility SF scaling
        if t.is_volatility:
            sf_val    = base_sf * 5.0
            hs_suffix = ":VOL"
        elif t.is_basis:
            sf_val    = base_sf * 0.5
            hs_suffix = ":BASIS"
        else:
            sf_val    = base_sf
            hs_suffix = ""

        shs = _resolve_sub_hedging_set(t)
        en  = _effective_notional(t, has_csa, mpor_days) * t.direction * sf_val
        hs_key = hs + hs_suffix
        if hs_key not in subtype_buckets:
            subtype_buckets[hs_key] = {}
        subtype_buckets[hs_key][shs] = subtype_buckets[hs_key].get(shs, 0.0) + en

    rho = 0.40
    total_addon = 0.0
    # No offsetting between hedging sets: sum each HS addon separately
    for _, sub in subtype_buckets.items():
        D_types = list(sub.values())
        D_sum   = sum(D_types)
        D_sq    = sum(v**2 for v in D_types)
        hs_addon = math.sqrt(rho**2 * D_sum**2 + (1 - rho**2) * D_sq)
        total_addon += hs_addon
    return total_addon

# ─────────────────────────────────────────────────────────────────────────────
# Replacement Cost (CRE52.12–22)
# ─────────────────────────────────────────────────────────────────────────────

def compute_replacement_cost(ns: NettingSet) -> float:
    """
    Replacement Cost per CRE52.

    Unmargined (CRE52.10):
      RC = max(V - C, 0)

    Margined (CRE52.18):
      RC = max(V - C, TH + MTA - NICA, 0)
      where V    = net MTM of all trades
            C    = haircut value of net collateral (VM + IM posted by counterparty)
            TH   = positive threshold before VM is due
            MTA  = minimum transfer amount
            NICA = Net Independent Collateral Amount (IM received)
    """
    V = sum(t.current_mtm for t in ns.trades)
    C = ns.variation_margin + ns.initial_margin   # net collateral
    if ns.has_csa:
        NICA = ns.initial_margin
        RC = max(V - C, ns.threshold + ns.mta - NICA, 0.0)
    else:
        RC = max(V, 0.0)
    return RC

# ─────────────────────────────────────────────────────────────────────────────
# PFE Multiplier (CRE52.23)
# ─────────────────────────────────────────────────────────────────────────────

def compute_pfe_multiplier(ns: NettingSet, addon_agg: float) -> float:
    """
    multiplier = min(1, floor + (1-floor) × exp(V-C / 2(1-floor)×AddOn))
    floor = 0.05
    """
    if addon_agg <= 0:
        return SACCR.floor_multiplier
    V = sum(t.current_mtm for t in ns.trades)
    C = ns.variation_margin + ns.initial_margin
    floor = SACCR.floor_multiplier
    exponent = (V - C) / (2 * (1 - floor) * addon_agg)
    mult = min(1.0, floor + (1.0 - floor) * math.exp(exponent))
    return max(mult, floor)

# ─────────────────────────────────────────────────────────────────────────────
# Master SA-CCR Calculator
# ─────────────────────────────────────────────────────────────────────────────

class SACCREngine:
    """
    Full SA-CCR EAD calculator per CRE52.
    Supports fallback logic per req #9.
    """

    def __init__(self):
        self.alpha = SACCR.alpha
        logger.info("SA-CCR Engine initialised (CRE52, α=%.1f)", self.alpha)

    def compute_ead(self, ns: NettingSet, run_date: Optional[date] = None,
                    portfolio_id: str = "") -> SAcCRResult:
        """
        Full SA-CCR EAD with trade-level attribution (CRE52.7).

        Produces:
          - Portfolio-level: RC, PFE multiplier, 5 add-ons, EAD
          - Trade-level (trade_results dict):
              All fields requested for the derivative attribution table.
        """
        run_date = run_date or date.today()

        saccr_trades = [t for t in ns.trades if t.saccr_method in ("SA_CCR", "FALLBACK")]
        imm_trades   = [t for t in ns.trades if t.saccr_method == "IMM"]

        if imm_trades:
            logger.info("Netting set %s: %d trade(s) under IMM (excluded from SA-CCR)",
                        ns.netting_id, len(imm_trades))

        # ── Portfolio-level add-ons ───────────────────────────────────────────
        addon_ir   = compute_addon_ir(saccr_trades,   ns.has_csa, ns.mpor_days)
        addon_fx   = compute_addon_fx(saccr_trades,   ns.has_csa, ns.mpor_days)
        addon_cr   = compute_addon_credit(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_eq   = compute_addon_equity(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_cm   = compute_addon_commodity(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_agg  = addon_ir + addon_fx + addon_cr + addon_eq + addon_cm

        rc   = compute_replacement_cost(ns)
        mult = compute_pfe_multiplier(ns, addon_agg)
        pfe  = mult * addon_agg
        ead  = self.alpha * (rc + pfe)

        # GAP-08 CRE52.2: Margined EAD must be capped at unmargined EAD
        if ns.has_csa:
            ns_unmargined          = NettingSet(
                netting_id        = ns.netting_id + "_UNMGD",
                counterparty_id   = ns.counterparty_id,
                trades            = ns.trades,
                initial_margin    = ns.initial_margin,
                variation_margin  = ns.variation_margin,
                threshold         = ns.threshold,
                mta               = ns.mta,
                has_csa           = False,           # unmargined
                mpor_days         = ns.mpor_days,
            )
            addon_agg_u = (compute_addon_ir(saccr_trades,    False, ns.mpor_days) +
                           compute_addon_fx(saccr_trades,    False, ns.mpor_days) +
                           compute_addon_credit(saccr_trades, False, ns.mpor_days) +
                           compute_addon_equity(saccr_trades, False, ns.mpor_days) +
                           compute_addon_commodity(saccr_trades, False, ns.mpor_days))
            rc_u    = compute_replacement_cost(ns_unmargined)
            mult_u  = compute_pfe_multiplier(ns_unmargined, addon_agg_u)
            ead_cap = self.alpha * (rc_u + mult_u * addon_agg_u)
            if ead > ead_cap:
                logger.info("SA-CCR [%s] margined EAD %.0f capped at unmargined EAD %.0f (CRE52.2)",
                            ns.netting_id, ead, ead_cap)
                ead = ead_cap

        logger.info("SA-CCR [%s] RC=%.0f  mult=%.4f  AddOn=%.0f  EAD=%.0f",
                    ns.netting_id, rc, mult, addon_agg, ead)

        # ── Per-asset-class add-on buckets (for trade-level attribution) ──────
        addon_by_class = {"IR": addon_ir, "FX": addon_fx, "CR": addon_cr,
                          "EQ": addon_eq, "CMDTY": addon_cm}

        # ── Trade-level attribution table ─────────────────────────────────────
        # RC allocation: pro-rata by |MTM|
        net_mtm_pos  = sum(max(t.current_mtm, 0) for t in ns.trades)
        total_abs_mtm= sum(abs(t.current_mtm) for t in ns.trades) or 1.0

        # EAD allocation: pro-rata by effective notional within asset class
        def _en(t):
            """Unsigned effective notional for proportional allocation."""
            if t.asset_class == "IR":
                adj = _adjusted_notional_ir(t)
            else:
                adj = _adjusted_notional_other(t)
            mf  = maturity_factor(t, ns.has_csa, ns.mpor_days)
            return abs(t.supervisory_delta) * adj * mf

        class_en_total: Dict[str, float] = {}
        for t in saccr_trades + imm_trades:
            class_en_total[t.asset_class] = class_en_total.get(t.asset_class, 0) + _en(t)

        # Risk weight mapping (CRE20 / CRR2 standard — 100% for unrated OTC)
        RW_PCT = {"AAA": 20, "AA": 20, "A": 50, "BBB": 100, "BB": 100,
                  "B": 150, "NR": 100, "DEFAULT": 100}

        trade_results: Dict[str, dict] = {}
        for t in (saccr_trades + imm_trades):
            ac     = t.asset_class
            hs     = _resolve_hedging_set(t)
            shs    = _resolve_sub_hedging_set(t, as_of=run_date)
            mf     = maturity_factor(t, ns.has_csa, ns.mpor_days)
            en_t   = _en(t)
            en_tot = class_en_total.get(ac, 1.0) or 1.0

            # Adjusted notional (SD × Notional for IR; plain notional for others)
            if ac == "IR":
                adj_notional = _adjusted_notional_ir(t)
            else:
                adj_notional = _adjusted_notional_other(t)

            # Supervisory duration (meaningful for IR only; 1.0 proxy for others)
            if ac == "IR":
                # GAP-12: use start_date (S_i) for forward-starting swaps
                s_anchor = t.start_date if t.start_date else run_date
                sd = supervisory_duration(run_date, s_anchor, t.maturity_date)
            else:
                sd = 1.0

            # SF for this trade (GAP-02: rating-granular credit SF)
            # RATING_SF_MAP: notched rating / broad quality → SF dict key.
            # Notched ratings (AAA-CCC) use the granular per-grade SF.
            # Broad labels "IG" and "SG" use the CRE52 Table 2 IG/SG aggregate
            # supervisory factors (0.50% and 5.00%) — matched to CR_IG / CR_SG.
            RATING_SF_MAP: Dict[str, str] = {
                "AAA": "CR_AAA", "AA": "CR_AA", "A": "CR_A",
                "BBB": "CR_BBB", "BB": "CR_BB", "B": "CR_B", "CCC": "CR_CCC",
                "NR":  "CR_BBB",   # unrated → BBB conservative proxy
                "IG":  "CR_IG",    # CRE52 Table 2: IG aggregate = 0.50%
                "SG":  "CR_SG",    # CRE52 Table 2: SG aggregate = 5.00%
            }
            if ac == "IR":
                sf_val = SF["IR"] * (5.0 if t.is_volatility else 0.5 if t.is_basis else 1.0)
            elif ac == "FX":
                sf_val = SF["FX"] * (5.0 if t.is_volatility else 0.5 if t.is_basis else 1.0)
            elif ac == "EQ":
                uid    = (t.underlying_security_id or "").upper()
                _KW    = frozenset(["INDEX","SPX","SX5E","NDX","RUT","FTSE",
                                    "DAX","NIKKEI","HSI","KOSPI","ASX","CAC","IBEX"])
                eq_key = "EQ_INDEX" if any(k in uid for k in _KW) else "EQ"
                sf_val = SF[eq_key] * (5.0 if t.is_volatility else 0.5 if t.is_basis else 1.0)
            elif ac == "CR":
                # Priority: credit_quality "IG"/"SG" (CRE52 broad labels) takes
                # precedence over credit_rating when the broad label is present.
                # credit_rating defaults to "BBB" which would otherwise shadow
                # an explicitly set credit_quality="SG".
                cq = getattr(t, "credit_quality", "IG").upper()
                cr = getattr(t, "credit_rating",  "BBB").upper()
                # Use broad IG/SG label when explicitly set; else use granular rating
                rating = cq if cq in ("IG", "SG") else cr
                if shs == "TRANCHED":
                    sf_val = SF["CR_TRANCHED_IG"] if rating in ("AAA","AA","A","BBB","IG") else SF["CR_TRANCHED_SG"]
                elif shs in ("INDEX_CDS", "NON_TRANCHED"):
                    sf_val = SF["CR_IDX_IG"] if rating in ("AAA","AA","A","BBB","IG") else SF["CR_IDX_SG"]
                else:
                    sf_val = SF.get(RATING_SF_MAP.get(rating, "CR_BBB"), SF["CR_BBB"])
                sf_val *= (5.0 if t.is_volatility else 0.5 if t.is_basis else 1.0)
            elif ac == "CMDTY":
                ct_key = t.commodity_type or "CMDTY_OTHER"
                sf_val = SF.get(ct_key, SF["CMDTY_OTHER"]) * \
                         (5.0 if t.is_volatility else 0.5 if t.is_basis else 1.0)
            else:
                sf_val = 0.0

            # Effective notional (signed: delta × adj_notional × MF)
            eff_notional_signed = t.supervisory_delta * adj_notional * mf * t.direction

            # Proportional RC allocation (by positive MTM share)
            rc_trade = rc * (max(t.current_mtm, 0) / max(net_mtm_pos, 1e-9))

            # Proportional add-on allocation (by effective notional share within class)
            addon_class = addon_by_class.get(ac, 0.0)
            addon_trade  = addon_class * (en_t / en_tot)

            # PFE allocation (same proportion as add-on, scaled by multiplier)
            pfe_trade = mult * addon_trade

            # EAD allocation (proportional, consistent with portfolio EAD)
            if ead > 0:
                ead_trade = ead * (en_t / (sum(class_en_total.values()) or 1.0))
            else:
                ead_trade = 0.0

            # Risk weight (100% default for CCR; read from credit_quality if available)
            rw_pct = RW_PCT.get(getattr(t, "credit_quality", "NR").upper()[:3], 100)
            rwa_t  = ead_trade * rw_pct / 100.0 * 12.5

            trade_results[t.trade_id] = {
                # Identifiers
                "portfolio_id":             portfolio_id,
                "trade_id":                 t.trade_id,
                # MTM and RC
                "current_mtm":              t.current_mtm,
                "rc_allocated":             round(rc_trade, 2),
                "rc_portfolio":             round(rc, 2),
                # Add-on
                "addon_trade":              round(addon_trade, 2),
                "addon_portfolio":          round(addon_agg, 2),
                # PFE
                "pfe_trade":                round(pfe_trade, 2),
                "pfe_portfolio":            round(pfe, 2),
                # Hedging / sub-hedging
                "hedging_set":              hs,
                "sub_hedging_set":          shs,
                "hedging_set_basis":        HEDGING_SET_BASIS.get(ac, ac),
                # SA-CCR decomposition
                "supervisory_duration":     round(sd, 6),
                "supervisory_factor":       sf_val,
                "maturity_factor":          round(mf, 6),
                "supervisory_delta":        t.supervisory_delta,
                "sign_delta":               int(math.copysign(1, t.direction * t.supervisory_delta)),
                # Notionals
                "underlying_security_id":   t.underlying_security_id,
                "saccr_notional":           t.notional,
                "saccr_adjusted_notional":  round(adj_notional, 2),
                "effective_notional":       round(eff_notional_signed, 2),
                # EAD
                "ead_trade":                round(ead_trade, 2),
                "ead_portfolio":            round(ead, 2),
                # Capital
                "risk_weight_pct":          rw_pct,
                "rwa":                      round(rwa_t, 2),
                "ead_calc_type":            t.saccr_method,
                # Pass-through for display
                "asset_class":              ac,
                "instrument_type":          t.instrument_type,
                "notional_ccy":             t.notional_ccy,
                "direction":                t.direction,
                "maturity_date":            t.maturity_date.isoformat(),
                "trade_date":               t.trade_date.isoformat(),
                "credit_quality":           getattr(t, "credit_quality", "IG"),
                "credit_rating":            getattr(t, "credit_rating", "BBB"),
                "fallback_trace":           t.fallback_trace,
            }

        return SAcCRResult(
            netting_id        = ns.netting_id,
            run_date          = run_date,
            replacement_cost  = rc,
            pfe_multiplier    = mult,
            add_on_ir         = addon_ir,
            add_on_fx         = addon_fx,
            add_on_credit     = addon_cr,
            add_on_equity     = addon_eq,
            add_on_commodity  = addon_cm,
            add_on_aggregate  = addon_agg,
            ead               = ead,
            trade_results     = trade_results,
        )

    def assign_method(self, trade: Trade) -> Trade:
        """
        Req #9: determine SA-CCR vs IMM per trade, validate supervisory delta.

        Also computes supervisory_delta for:
          - Options (CRE52.40): Black-Scholes with lambda-shift
          - CDO tranches (CRE52.41): attachment/detachment formula
          - Linear trades: clamps to ±1 if wrongly set (CRE52.38)
        """
        if trade.saccr_method == "IMM":
            eligible, trace = check_imm_eligibility(trade)
            if not eligible:
                trade.saccr_method   = "FALLBACK"
                trade.fallback_trace = trace
                logger.warning("Trade %s: IMM → SA-CCR fallback. Reason: %s",
                               trade.trade_id, trace)

        # GAP-06/07: auto-compute supervisory delta for options and CDO tranches
        if trade.is_option or trade.credit_sub_type == "TRANCHED":
            trade.supervisory_delta = compute_supervisory_delta(trade)
        else:
            # CRE52.38: validate supervisory_delta direction for linear instruments
            linear = {"IRS", "CRS", "OIS", "FXFwd", "EquityFwd", "TRS", "CommodityFwd"}
            if trade.instrument_type in linear and trade.supervisory_delta not in (1.0, -1.0):
                logger.warning(
                    "Trade %s: supervisory_delta=%.4f for linear instrument %s; "
                    "expected ±1. Clamping to sign.",
                    trade.trade_id, trade.supervisory_delta, trade.instrument_type
                )
                trade.supervisory_delta = 1.0 if trade.supervisory_delta >= 0 else -1.0
        return trade
