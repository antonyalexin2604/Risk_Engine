"""
PROMETHEUS Risk Platform
Engine: SA-CCR (Standardised Approach for Counterparty Credit Risk)
Regulatory basis: CRE52 (effective Jan 2023)

Implements:
  - Replacement Cost (RC) — CRE52.12–22
  - PFE Multiplier — CRE52.23
  - Add-On per asset class — CRE52.24–75
  - EAD = alpha × (RC + multiplier × AddOn_aggregate)

Fallback trace: every trade has saccr_method + fallback_trace_code
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
    instrument_type:   str          # 'IRS','CDS','FXFwd','EquitySwap','CommodityFwd'
    notional:          float
    notional_ccy:      str
    direction:         int           # +1 = long/payer, -1 = short/receiver
    maturity_date:     date
    trade_date:        date
    current_mtm:       float = 0.0
    fixed_rate:        Optional[float] = None
    reference_period:  Optional[float] = None   # for IR: tenor in years
    hedging_set:       Optional[str] = None
    sub_hedging_set:   Optional[str] = None
    saccr_method:      str = "SA_CCR"            # 'SA_CCR' | 'IMM' | 'FALLBACK'
    fallback_trace:    Optional[str] = None

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
    netting_id:     str
    run_date:       date
    replacement_cost: float
    pfe_multiplier: float
    add_on_ir:      float
    add_on_fx:      float
    add_on_credit:  float
    add_on_equity:  float
    add_on_commodity: float
    add_on_aggregate: float
    ead:            float
    alpha:          float = SACCR.alpha
    trade_results:  Dict[str, dict] = field(default_factory=dict)

# ─────────────────────────────────────────────────────────────────────────────
# Supervisory Parameters (CRE52 Table 2)
# ─────────────────────────────────────────────────────────────────────────────

# Supervisory factors by asset class / bucket
SF: Dict[str, float] = {
    "IR":     0.0050,
    "FX":     0.0400,
    "EQ":     0.3200,
    "CR_IG":  0.0050,   # Investment Grade single-name CDS
    "CR_SG":  0.0500,   # Speculative Grade
    "CR_IDX": 0.0050,   # IG index
    "CMDTY_ENERGY":   0.1800,
    "CMDTY_METALS":   0.1800,
    "CMDTY_AGRI":     0.1800,
    "CMDTY_OTHER":    0.1800,
}

# IR supervisory duration factors (CRE52.39)
def supervisory_duration(trade_date: date, start_date: date, end_date: date) -> float:
    """CRE52.39: SD = (exp(-0.05*S) - exp(-0.05*E)) / 0.05"""
    S = max((start_date - trade_date).days / 365.0, 0)
    E = max((end_date   - trade_date).days / 365.0, 0)
    if E <= 0:
        return 0.0
    return (math.exp(-0.05 * S) - math.exp(-0.05 * E)) / 0.05

# Maturity factor (CRE52.22)
def maturity_factor(trade: Trade, has_csa: bool, mpor_days: int) -> float:
    today = date.today()
    Mi = max((trade.maturity_date - today).days / 365.0, 10/365.0)
    if has_csa:
        MF = math.sqrt(mpor_days / 250.0)
    else:
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
    """CRE52.39: d = notional × SD"""
    today = date.today()
    start = trade.trade_date
    end   = trade.maturity_date
    sd    = supervisory_duration(today, start, end)
    return trade.notional * sd

def _adjusted_notional_other(trade: Trade) -> float:
    """For FX/EQ/CR/CMDTY: adjusted notional = notional (CRE52.44)"""
    return trade.notional

def _effective_notional(trade: Trade, has_csa: bool, mpor_days: int) -> float:
    if trade.asset_class == "IR":
        d = _adjusted_notional_ir(trade)
    else:
        d = _adjusted_notional_other(trade)
    MF = maturity_factor(trade, has_csa, mpor_days)
    delta = getattr(trade, 'supervisory_delta', 1.0)
    return delta * d * MF

def _remaining_maturity_years(trade: Trade, as_of: Optional[date] = None) -> float:
    as_of = as_of or date.today()
    return max((trade.maturity_date - as_of).days / 365.0, 0.0)

def _resolve_hedging_set(trade: Trade) -> str:
    """
    Resolve hedging set key.
    If explicit `hedging_set` is provided on the trade, it takes precedence.
    """
    if trade.hedging_set:
        return trade.hedging_set

    if trade.asset_class == "IR":
        return trade.notional_ccy
    if trade.asset_class == "FX":
        return trade.notional_ccy
    if trade.asset_class in ("CR", "EQ"):
        return getattr(trade, 'reference_entity', trade.trade_id)
    if trade.asset_class == "CMDTY":
        return getattr(trade, 'commodity_type', 'CMDTY_OTHER')
    return trade.asset_class

def _resolve_sub_hedging_set(trade: Trade, as_of: Optional[date] = None) -> str:
    """
    Resolve sub-hedging set key.
    If explicit `sub_hedging_set` is provided on the trade, it takes precedence.

    For IR, default buckets are by residual maturity:
      - SHORT: <= 1y
      - MEDIUM: >1y and <=5y
      - LONG: >5y
    """
    if trade.sub_hedging_set:
        return trade.sub_hedging_set

    if trade.asset_class == "IR":
        mat = _remaining_maturity_years(trade, as_of=as_of)
        if mat <= 1.0:
            return "SHORT"
        if mat <= 5.0:
            return "MEDIUM"
        return "LONG"

    return "ALL"

def compute_addon_ir(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """
    CRE52.39–43: IR add-on via hedging set and sub-hedging set aggregation.

    Hedging set defaults to currency unless explicitly provided on the trade.
    Sub-hedging set defaults to residual maturity buckets (SHORT/MEDIUM/LONG)
    unless explicitly provided on the trade.
    """
    hedging_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "IR":
            continue
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * SF["IR"]
        hs = _resolve_hedging_set(t)
        shs = _resolve_sub_hedging_set(t)
        if hs not in hedging_buckets:
            hedging_buckets[hs] = {}
        hedging_buckets[hs][shs] = hedging_buckets[hs].get(shs, 0.0) + en

    total_addon = 0.0
    for _, sub_bucket in hedging_buckets.items():
        d1 = sub_bucket.get("SHORT", 0.0)
        d2 = sub_bucket.get("MEDIUM", 0.0)
        d3 = sub_bucket.get("LONG", 0.0)

        # CRE52.43 simplified cross-bucket correlation for IR maturity buckets
        std_component = d1 * d1 + d2 * d2 + d3 * d3 + 1.4 * d1 * d2 + 1.4 * d2 * d3 + 0.6 * d1 * d3
        addon_hs = math.sqrt(max(std_component, 0.0))

        # If custom sub-hedging labels are provided, conservatively add them in absolute terms.
        for key, value in sub_bucket.items():
            if key not in {"SHORT", "MEDIUM", "LONG"}:
                addon_hs += abs(value)

        total_addon += addon_hs

    return total_addon

def compute_addon_fx(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """CRE52.44–46: FX add-on by hedging set and optional sub-hedging set."""
    pair_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "FX":
            continue
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * SF["FX"]
        hs = _resolve_hedging_set(t)
        shs = _resolve_sub_hedging_set(t)
        if hs not in pair_buckets:
            pair_buckets[hs] = {}
        pair_buckets[hs][shs] = pair_buckets[hs].get(shs, 0.0) + en

    return sum(abs(sum(sub.values())) for sub in pair_buckets.values())

def compute_addon_credit(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """CRE52.47–53: Credit add-on with hedging set and sub-hedging support."""
    entity_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "CR":
            continue
        sf_key = "CR_IG"  # simplified; real implementation grades CDS
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * SF[sf_key]
        hs = _resolve_hedging_set(t)
        shs = _resolve_sub_hedging_set(t)
        if hs not in entity_buckets:
            entity_buckets[hs] = {}
        entity_buckets[hs][shs] = entity_buckets[hs].get(shs, 0.0) + en

    entity_en = {hs: sum(sub.values()) for hs, sub in entity_buckets.items()}
    # systemic correlation rho=0.5 (CRE52.53)
    rho = 0.50
    EN_sum = sum(entity_en.values())
    ind_var = sum(v**2 for v in entity_en.values())
    addon = math.sqrt(rho**2 * EN_sum**2 + (1-rho**2) * ind_var)
    return addon

def compute_addon_equity(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """CRE52.54–60: Equity add-on with hedging set and sub-hedging support."""
    entity_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "EQ":
            continue
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * SF["EQ"]
        hs = _resolve_hedging_set(t)
        shs = _resolve_sub_hedging_set(t)
        if hs not in entity_buckets:
            entity_buckets[hs] = {}
        entity_buckets[hs][shs] = entity_buckets[hs].get(shs, 0.0) + en

    entity_en = {hs: sum(sub.values()) for hs, sub in entity_buckets.items()}
    rho = 0.50
    EN_sum = sum(entity_en.values())
    ind_var = sum(v**2 for v in entity_en.values())
    return math.sqrt(rho**2 * EN_sum**2 + (1-rho**2) * ind_var)

def compute_addon_commodity(trades: List[Trade], has_csa: bool, mpor_days: int) -> float:
    """CRE52.61–67: Commodity add-on by hedging set and sub-hedging set."""
    subtype_buckets: Dict[str, Dict[str, float]] = {}
    for t in trades:
        if t.asset_class != "CMDTY":
            continue
        hs = _resolve_hedging_set(t)
        shs = _resolve_sub_hedging_set(t)
        sf_val = SF.get(hs, SF["CMDTY_OTHER"])
        en = _effective_notional(t, has_csa, mpor_days) * t.direction * sf_val
        if hs not in subtype_buckets:
            subtype_buckets[hs] = {}
        subtype_buckets[hs][shs] = subtype_buckets[hs].get(shs, 0.0) + en

    hs_en = {hs: sum(sub.values()) for hs, sub in subtype_buckets.items()}
    rho = 0.40
    EN_sum = sum(hs_en.values())
    ind_var = sum(v**2 for v in hs_en.values())
    return math.sqrt(rho**2 * EN_sum**2 + (1-rho**2) * ind_var)

# ─────────────────────────────────────────────────────────────────────────────
# Replacement Cost (CRE52.12–22)
# ─────────────────────────────────────────────────────────────────────────────

def compute_replacement_cost(ns: NettingSet) -> float:
    """
    RC for margined netting sets (CRE52.16):
    RC = max(V - C, TH + MTA - NICA, 0)
    where V  = net MTM, C = net collateral
          TH = threshold, MTA = minimum transfer amount
          NICA = Net Independent Collateral Amount
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

    def compute_ead(self, ns: NettingSet, run_date: Optional[date] = None) -> SAcCRResult:
        run_date = run_date or date.today()

        # Partition trades: SA-CCR vs IMM
        saccr_trades = [t for t in ns.trades if t.saccr_method in ("SA_CCR", "FALLBACK")]
        imm_trades   = [t for t in ns.trades if t.saccr_method == "IMM"]

        if imm_trades:
            logger.info("Netting set %s: %d trade(s) under IMM (excluded from SA-CCR)",
                        ns.netting_id, len(imm_trades))

        # Add-Ons
        addon_ir   = compute_addon_ir(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_fx   = compute_addon_fx(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_cr   = compute_addon_credit(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_eq   = compute_addon_equity(saccr_trades, ns.has_csa, ns.mpor_days)
        addon_cm   = compute_addon_commodity(saccr_trades, ns.has_csa, ns.mpor_days)

        addon_agg  = addon_ir + addon_fx + addon_cr + addon_eq + addon_cm

        # RC and PFE components
        rc   = compute_replacement_cost(ns)
        mult = compute_pfe_multiplier(ns, addon_agg)
        pfe  = mult * addon_agg

        # EAD = alpha × (RC + PFE)  [CRE52.7]
        ead  = self.alpha * (rc + pfe)

        logger.info(
            "SA-CCR [%s] RC=%.0f  mult=%.4f  AddOn=%.0f  EAD=%.0f",
            ns.netting_id, rc, mult, addon_agg, ead
        )

        return SAcCRResult(
            netting_id    = ns.netting_id,
            run_date      = run_date,
            replacement_cost  = rc,
            pfe_multiplier    = mult,
            add_on_ir         = addon_ir,
            add_on_fx         = addon_fx,
            add_on_credit     = addon_cr,
            add_on_equity     = addon_eq,
            add_on_commodity  = addon_cm,
            add_on_aggregate  = addon_agg,
            ead               = ead,
        )

    def assign_method(self, trade: Trade) -> Trade:
        """
        Req #9: determine SA-CCR vs IMM per trade.
        Records fallback trace code.
        """
        if trade.saccr_method == "IMM":
            eligible, trace = check_imm_eligibility(trade)
            if not eligible:
                trade.saccr_method   = "FALLBACK"
                trade.fallback_trace = trace
                logger.warning("Trade %s: IMM → SA-CCR fallback. Reason: %s",
                               trade.trade_id, trace)
        return trade
