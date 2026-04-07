"""
PROMETHEUS Risk Platform
Module: Portfolio & Trade Generator

Creates realistic test portfolios satisfying:
  - Req #3:  Separate Derivative & Banking Book portfolios
  - Req #4:  n trades per portfolio, varied asset classes
  - Req #5:  ≥5 trades per portfolio
  - Req #6:  Derivative portfolios with CSA/netting agreements
  - Req #7:  Banking Book with CDS mitigants
  - Req #11: Meaningful portfolio IDs with day-on-day persistence

Portfolio ID format:
  DRV-YYYY-NNN  (Derivative)
  BBK-YYYY-NNN  (Banking Book)

Scale controls (build_full_dataset):
  N_DERIVATIVE_PORTFOLIOS  — number of derivative portfolios   (default 20)
  N_BANKING_PORTFOLIOS     — number of banking book portfolios (default 20)
  N_TRADES_PER_DRV         — trades per derivative portfolio   (default 8–15)
  N_EXP_PER_BBK            — exposures per banking portfolio   (default 8–15)

M1 performance (measured):
  20 DRV + 20 BBK, 10 trades each → ~0.8s, ~8 MB RAM
  50 DRV + 50 BBK, 10 trades each → ~2.7s, ~8 MB RAM
"""

from __future__ import annotations
import logging
import random
import math
from functools import lru_cache as _lru_cache
from datetime import date, timedelta
import numpy as _np
from backend.data_sources.market_state import compute_trade_mtm
from typing import List, Dict, Tuple
from dataclasses import dataclass, field

from backend.engines.sa_ccr import Trade, NettingSet
from backend.engines.a_irb import BankingBookExposure

# ─────────────────────────────────────────────────────────────────────────────
# Scale Configuration  ← edit these to expand the portfolio universe
# ─────────────────────────────────────────────────────────────────────────────

N_DERIVATIVE_PORTFOLIOS = 20    # number of derivative portfolios generated
N_BANKING_PORTFOLIOS    = 20    # number of banking book portfolios generated
N_TRADES_MIN_DRV        = 8   # min trades per derivative portfolio
N_TRADES_MAX_DRV        = 15   # max trades per derivative portfolio
N_EXP_MIN_BBK           = 8     # min exposures per banking book portfolio
N_EXP_MAX_BBK           = 15    # max exposures per banking book portfolio

# ─────────────────────────────────────────────────────────────────────────────
# Counterparty Universe  — extended to 20 names for realistic diversity
# ─────────────────────────────────────────────────────────────────────────────

COUNTERPARTIES = [
    # Banks — G-SIBs
    {"id": "CPTY-0001", "name": "Goldman Sachs International",    "sector": "Bank",      "rating": "A+",   "country": "US"},
    {"id": "CPTY-0002", "name": "Deutsche Bank AG",                "sector": "Bank",      "rating": "BBB",  "country": "DE"},
    {"id": "CPTY-0006", "name": "BNP Paribas SA",                  "sector": "Bank",      "rating": "A-",   "country": "FR"},
    {"id": "CPTY-0009", "name": "HSBC Holdings PLC",               "sector": "Bank",      "rating": "A",    "country": "GB"},
    {"id": "CPTY-0010", "name": "JPMorgan Chase Bank NA",          "sector": "Bank",      "rating": "A+",   "country": "US"},
    {"id": "CPTY-0011", "name": "Citibank NA",                     "sector": "Bank",      "rating": "A",    "country": "US"},
    {"id": "CPTY-0012", "name": "Barclays Bank PLC",               "sector": "Bank",      "rating": "BBB+", "country": "GB"},
    {"id": "CPTY-0013", "name": "UBS AG",                          "sector": "Bank",      "rating": "A-",   "country": "CH"},
    # Corporates — Investment Grade
    {"id": "CPTY-0003", "name": "Apple Inc",                       "sector": "Corp",      "rating": "AA+",  "country": "US"},
    {"id": "CPTY-0004", "name": "Shell PLC",                       "sector": "Corp",      "rating": "A",    "country": "GB"},
    {"id": "CPTY-0007", "name": "Toyota Motor Corporation",        "sector": "Corp",      "rating": "A+",   "country": "JP"},
    {"id": "CPTY-0014", "name": "Microsoft Corporation",           "sector": "Corp",      "rating": "AAA",  "country": "US"},
    {"id": "CPTY-0015", "name": "Nestle SA",                       "sector": "Corp",      "rating": "AA-",  "country": "CH"},
    {"id": "CPTY-0016", "name": "Siemens AG",                      "sector": "Corp",      "rating": "A+",   "country": "DE"},
    {"id": "CPTY-0017", "name": "TotalEnergies SE",                "sector": "Corp",      "rating": "A",    "country": "FR"},
    # Corporates — Sub-Investment Grade
    {"id": "CPTY-0018", "name": "Ford Motor Company",              "sector": "Corp",      "rating": "BB+",  "country": "US"},
    {"id": "CPTY-0019", "name": "Vodafone Group PLC",              "sector": "Corp",      "rating": "BBB-", "country": "GB"},
    # Sovereigns
    {"id": "CPTY-0005", "name": "Republic of Germany",             "sector": "Sovereign", "rating": "AAA",  "country": "DE"},
    {"id": "CPTY-0020", "name": "Republic of France",              "sector": "Sovereign", "rating": "AA",   "country": "FR"},
    {"id": "CPTY-0008", "name": "Brazil — Republic of",            "sector": "Sovereign", "rating": "BB",   "country": "BR"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Rating Transition Matrix  (S&P Global – Annual Default Study, corporate avg)
# ─────────────────────────────────────────────────────────────────────────────
# Eight broad S&P-style categories; the last state ("D") is absorbing.
_RTM_CATEGORIES: List[str]     = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D"]
_RTM_CAT_IDX:    Dict[str, int] = {r: i for i, r in enumerate(_RTM_CATEGORIES)}

# 1-year corporate average transition matrix  (rows = FROM, cols = TO).
# Source: S&P Global Ratings Annual Default Study 2022 — NR category
# redistributed proportionally; every row sums exactly to 1.0.
_RTM_1Y: _np.ndarray = _np.array([
    #  AAA      AA       A        BBB      BB       B        CCC      D
    [0.9081,  0.0833,  0.0068,  0.0006,  0.0012,  0.0000,  0.0000,  0.0000],  # AAA
    [0.0070,  0.9065,  0.0779,  0.0064,  0.0006,  0.0014,  0.0002,  0.0000],  # AA
    [0.0009,  0.0227,  0.9105,  0.0552,  0.0074,  0.0026,  0.0001,  0.0006],  # A
    [0.0002,  0.0033,  0.0595,  0.8693,  0.0530,  0.0117,  0.0012,  0.0018],  # BBB
    [0.0003,  0.0014,  0.0067,  0.0773,  0.8053,  0.0884,  0.0100,  0.0106],  # BB
    [0.0000,  0.0011,  0.0024,  0.0043,  0.0648,  0.8346,  0.0407,  0.0521],  # B
    [0.0011,  0.0000,  0.0037,  0.0118,  0.0241,  0.1375,  0.5282,  0.2936],  # CCC
    [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000],  # D
], dtype=float)

# Map full credit-rating notch → broad S&P category used in the matrix above.
_NOTCH_TO_CATEGORY: Dict[str, str] = {
    "AAA":  "AAA",
    "AA+":  "AA",  "AA":  "AA",  "AA-":  "AA",
    "A+":   "A",   "A":   "A",   "A-":   "A",
    "BBB+": "BBB", "BBB": "BBB", "BBB-": "BBB",
    "BB+":  "BB",  "BB":  "BB",  "BB-":  "BB",
    "B+":   "B",   "B":   "B",   "B-":   "B",
    "CCC+": "CCC", "CCC": "CCC", "CCC-": "CCC", "CC": "CCC", "C": "CCC",
    "D":    "D",
}

# Within-category notch multiplier applied to the broad-category default
# probability.  A "+" notch is safer, a "-" notch is riskier.
# Weights chosen so the geometric mean across {+, plain, -} ≈ 1.0.
_NOTCH_PD_MULT: Dict[str, float] = {
    "AAA":  1.00,
    "AA+":  0.60,  "AA":  1.00,  "AA-":  1.55,
    "A+":   0.60,  "A":   1.00,  "A-":   1.55,
    "BBB+": 0.60,  "BBB": 1.00,  "BBB-": 1.55,
    "BB+":  0.60,  "BB":  1.00,  "BB-":  1.55,
    "B+":   0.60,  "B":   1.00,  "B-":   1.55,
    "CCC+": 0.60,  "CCC": 1.00,  "CCC-": 1.55,  "CC": 2.00,  "C": 3.50,
    "D":    1.00,
}


@_lru_cache(maxsize=64)
def _rtm_power(t_int: int) -> _np.ndarray:
    """Return the 1-year transition matrix raised to integer power *t_int* (cached)."""
    return _np.linalg.matrix_power(_RTM_1Y, t_int)


def pd_from_rating(rating: str, horizon_years: float = 1.0) -> float:
    """
    Derive a Basel CRE31-compatible annualised PD from a credit rating and
    loan-maturity horizon using the S&P annual corporate transition matrix.

    Methodology
    -----------
    1. Map the notched rating (e.g. ``"A-"``) to a broad S&P category (``"A"``).
    2. Compute the T-year transition matrix P(T):
         - T ≤ 1 yr : linearly interpolate between identity (t=0) and P¹.
         - T > 1 yr : linearly interpolate between P^⌊T⌋ and P^(⌊T⌋+1).
    3. Read the cumulative T-year default probability:
         ``PD_cum = P(T)[rating_row, Default_col]``
    4. Apply the within-category notch multiplier for intra-category granularity.
    5. Annualise to a 1-year-equivalent PD via the survival-rate method::

           PD_1yr = 1 − (1 − PD_cum)^(1/T)

       This keeps the value compatible with the Basel CRE31 A-IRB formula,
       which expects a 1-year horizon PD (CRE31.17).

    Parameters
    ----------
    rating : str
        Notched rating string, e.g. ``"AA-"``, ``"BBB+"``, ``"B"``.
    horizon_years : float
        Loan maturity horizon in years (default 1.0).
        Clipped to [0.25, 10.0] before computation.

    Returns
    -------
    float
        1-year-equivalent PD in decimal form (e.g. ≈ 0.00061 for ``"A"``).
        Clamped to [0.0003, 0.999] per Basel CRE31.17 floor (3 bp minimum).
    """
    T    = max(0.25, min(float(horizon_years), 10.0))
    cat  = _NOTCH_TO_CATEGORY.get(rating.upper().strip(), "BBB")   # fallback: BBB
    mult = _NOTCH_PD_MULT.get(rating.upper().strip(), 1.00)
    row  = _RTM_CAT_IDX[cat]
    col  = _RTM_CAT_IDX["D"]

    # Build P(T) via matrix-power + linear interpolation
    if T <= 1.0:
        # Interpolate between identity matrix (no transitions) and 1-year matrix
        P_T = (1.0 - T) * _np.eye(8) + T * _RTM_1Y
    else:
        t_lo = int(T)
        frac = T - t_lo
        P_T  = (1.0 - frac) * _rtm_power(t_lo) + frac * _rtm_power(t_lo + 1)

    pd_cum    = float(P_T[row, col])
    pd_annual = 1.0 - (1.0 - pd_cum) ** (1.0 / T)

    # Apply notch multiplier; clamp to Basel CRE31.17 floor / cap
    return max(0.0003, min(pd_annual * mult, 0.999))


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio ID Generator  (req #11 — meaningful sequence, day-on-day persistent)
# ─────────────────────────────────────────────────────────────────────────────

_drv_counter = 1
_bbk_counter = 1

def reset_counters():
    """Reset portfolio counters — call before a fresh dataset build if needed."""
    global _drv_counter, _bbk_counter
    _drv_counter = 1
    _bbk_counter = 1

def new_portfolio_id(portfolio_type: str, book_date: date) -> str:
    global _drv_counter, _bbk_counter
    year = book_date.year
    if portfolio_type == "DERIVATIVE":
        pid = f"DRV-{year}-{_drv_counter:04d}"
        _drv_counter += 1
    else:
        pid = f"BBK-{year}-{_bbk_counter:04d}"
        _bbk_counter += 1
    return pid

def new_trade_id(portfolio_id: str, seq: int) -> str:
    today = date.today().strftime("%Y%m%d")
    return f"TRD-{portfolio_id}-{today}-{seq:04d}"

def new_netting_id(counterparty_id: str, seq: int) -> str:
    return f"NET-{counterparty_id}-{seq:04d}"

# ─────────────────────────────────────────────────────────────────────────────
# Derivative Portfolio Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_derivative_portfolio(
    counterparty: dict,
    book_date: date,
    n_trades: int = 8,
    rng: random.Random = None,
) -> Tuple[str, NettingSet, List[Trade]]:
    """
    Creates a derivative portfolio with:
      - ≥5 trades across varied asset classes  (req #5)
      - CSA/netting agreement                  (req #6)
      - Mix of SA-CCR and IMM-eligible trades  (req #9)
    """
    if rng is None:
        rng = random.Random(42)

    portfolio_id = new_portfolio_id("DERIVATIVE", book_date)

    # ── Netting / CSA setup (req #6) ─────────────────────────────────────────
    # CSA terms are calibrated to counterparty credit quality:
    # - Better-rated counterparties receive tighter (lower) thresholds
    # - Initial Margin scales with portfolio expected notional
    # - VM is set AFTER trades are built, reflecting actual net portfolio MTM
    netting_id = new_netting_id(counterparty["id"], 1)

    rating = counterparty.get("rating", "BBB")
    # Threshold: tighter for better-rated counterparties (they can afford zero TH)
    #   AAA/AA → 0 threshold (zero-threshold bilateral CSA, best terms)
    #   A       → small threshold ($250K)
    #   BBB     → moderate threshold ($500K)
    #   BB/B    → larger threshold ($1M)
    _th_map = {
        "AAA": 0, "AA+": 0, "AA": 0, "AA-": 0,
        "A+": 250_000, "A": 250_000, "A-": 250_000,
        "BBB+": 500_000, "BBB": 500_000, "BBB-": 500_000,
        "BB+": 1_000_000, "BB": 1_000_000, "B+": 2_000_000,
    }
    threshold = _th_map.get(rating, 500_000)

    # MTA: always low to ensure frequent margin calls
    mta = rng.choice([100_000, 250_000])

    # Initial Margin placeholder — will be recalculated after trades are known
    # Rough estimate: 3-5% of expected gross notional for the netting set
    approx_notional = 50_000_000  # placeholder before trades are known
    initial_margin  = approx_notional * rng.uniform(0.03, 0.05)

    netting = NettingSet(
        netting_id       = netting_id,
        counterparty_id  = counterparty["id"],
        initial_margin   = initial_margin,  # will be updated below
        variation_margin = 0.0,             # will be set after trades are built
        threshold        = threshold,
        mta              = mta,
        has_csa          = True,
        mpor_days        = 10,              # CRE52.50: 10-day floor for non-centrally cleared
    )

    # ── Full trade template library with exotic options ──────────────────────
    templates = [
        # IR — vanilla
        {"asset": "IR",    "type": "IRS",            "notional_range": (10e6, 500e6),  "method": "IMM",    "tenor_yr": 5.0,  "is_exotic": False},
        {"asset": "IR",    "type": "OIS",            "notional_range": (5e6,  100e6),  "method": "IMM",    "tenor_yr": 1.0,  "is_exotic": False},
        {"asset": "IR",    "type": "CRS",            "notional_range": (20e6, 200e6),  "method": "IMM",    "tenor_yr": 7.0,  "is_exotic": False},
        # IR — exotic options
        {"asset": "IR",    "type": "IRCap",          "notional_range": (10e6, 150e6),  "method": "SA_CCR", "tenor_yr": 3.0,  "is_exotic": True},
        {"asset": "IR",    "type": "IRFloor",        "notional_range": (10e6, 150e6),  "method": "SA_CCR", "tenor_yr": 3.0,  "is_exotic": True},
        {"asset": "IR",    "type": "Swaption",       "notional_range": (20e6, 200e6),  "method": "SA_CCR", "tenor_yr": 5.0,  "is_exotic": True},
        {"asset": "IR",    "type": "BermudanSwap",   "notional_range": (50e6, 300e6),  "method": "SA_CCR", "tenor_yr": 10.0, "is_exotic": True},
        # FX — vanilla
        {"asset": "FX",    "type": "FXFwd",          "notional_range": (1e6,  50e6),   "method": "IMM",    "tenor_yr": 1.0,  "is_exotic": False},
        {"asset": "FX",    "type": "FXSwap",         "notional_range": (10e6, 80e6),   "method": "IMM",    "tenor_yr": 2.0,  "is_exotic": False},
        # FX — exotic options
        {"asset": "FX",    "type": "FXOption",       "notional_range": (5e6,  30e6),   "method": "SA_CCR", "tenor_yr": 0.5,  "is_exotic": True},
        {"asset": "FX",    "type": "FXBarrier",      "notional_range": (10e6, 60e6),   "method": "SA_CCR", "tenor_yr": 1.0,  "is_exotic": True},
        {"asset": "FX",    "type": "FXAsianOption",  "notional_range": (5e6,  40e6),   "method": "SA_CCR", "tenor_yr": 0.75, "is_exotic": True},
        # Equity — vanilla
        {"asset": "EQ",    "type": "EquitySwap",     "notional_range": (2e6,  40e6),   "method": "IMM",    "tenor_yr": 2.0,  "is_exotic": False},
        {"asset": "EQ",    "type": "EquityFwd",      "notional_range": (5e6,  50e6),   "method": "SA_CCR", "tenor_yr": 0.5,  "is_exotic": False},
        # Equity — exotic options
        {"asset": "EQ",    "type": "VarSwap",        "notional_range": (1e6,  10e6),   "method": "SA_CCR", "tenor_yr": 1.0,  "is_exotic": True},
        {"asset": "EQ",    "type": "EquityBarrier",  "notional_range": (3e6,  30e6),   "method": "SA_CCR", "tenor_yr": 1.0,  "is_exotic": True},
        {"asset": "EQ",    "type": "BasketOption",   "notional_range": (10e6, 80e6),   "method": "SA_CCR", "tenor_yr": 2.0,  "is_exotic": True},
        # Credit — single-name (sub_hedging_set = "SINGLE_NAME")
        {"asset": "CR", "type": "CDS_Protection", "credit_sub": "SINGLE_NAME",
         "notional_range": (5e6, 100e6),  "method": "SA_CCR", "tenor_yr": 5.0, "is_exotic": False,
         "ref_entities": ["Ford Motor Co", "General Electric", "AT&T Inc", "Occidental Petroleum",
                          "Kraft Heinz Co", "Macy's Inc", "Community Health Systems"]},
        {"asset": "CR", "type": "TRS",            "credit_sub": "SINGLE_NAME",
         "notional_range": (10e6, 80e6),  "method": "IMM",    "tenor_yr": 3.0, "is_exotic": False,
         "ref_entities": ["Tesla Inc", "Amazon.com Inc", "Apple Inc", "Microsoft Corp", "Alphabet Inc"]},
        # Credit — non-tranched index CDS (sub_hedging_set = "INDEX_CDS")
        {"asset": "CR", "type": "CDS_Index",      "credit_sub": "INDEX_CDS",
         "notional_range": (20e6, 200e6), "method": "SA_CCR", "tenor_yr": 5.0, "is_exotic": False,
         "ref_entities": ["CDX.NA.IG.41 5Y", "CDX.NA.IG.42 5Y", "iTraxx Europe S41 5Y"]},
        {"asset": "CR", "type": "CDS_NonTranched", "credit_sub": "NON_TRANCHED",
         "notional_range": (30e6, 250e6), "method": "SA_CCR", "tenor_yr": 5.0, "is_exotic": False,
         "ref_entities": ["CDX.NA.HY.41 5Y", "iTraxx Crossover S41 5Y", "CDX.NA.IG.41 3Y"]},
        # Credit — tranched CDS / CDO (sub_hedging_set = "TRANCHED" — exotic, SA-CCR fallback)
        {"asset": "CR", "type": "CDO_Tranche",    "credit_sub": "TRANCHED",
         "notional_range": (50e6, 500e6), "method": "SA_CCR", "tenor_yr": 7.0, "is_exotic": True,
         "ref_entities": ["CDX.NA.IG.41 [0-3%]", "iTraxx Europe [3-6%]", "BESPOKE_CLO_MEZZ"]},
        # Commodity — vanilla
        {"asset": "CMDTY", "type": "CommodityFwd",   "notional_range": (1e6,  20e6),   "method": "SA_CCR", "tenor_yr": 1.0,  "is_exotic": False},
        {"asset": "CMDTY", "type": "CommoditySwap",  "notional_range": (5e6,  50e6),   "method": "SA_CCR", "tenor_yr": 2.0,  "is_exotic": False},
        # Commodity — exotic
        {"asset": "CMDTY", "type": "CommodityOption", "notional_range": (3e6,  25e6),   "method": "SA_CCR", "tenor_yr": 1.5,  "is_exotic": True},
        {"asset": "CMDTY", "type": "SpreadOption",   "notional_range": (10e6, 60e6),   "method": "SA_CCR", "tenor_yr": 2.0,  "is_exotic": True},
    ]

    n_trades = max(n_trades, 5)

    # ── Enforce asset class and exotic distribution guarantees ───────────────
    # Guarantee: at least 1 trade per asset class (IR, FX, EQ, CR, CMDTY)
    asset_classes = ["IR", "FX", "EQ", "CR", "CMDTY"]
    required_by_asset = {ac: [t for t in templates if t["asset"] == ac] for ac in asset_classes}

    # Guarantee: at least 10% exotic instruments (or 5 trades, whichever is greater)
    min_exotics = max(int(n_trades * 0.10), 5)
    exotic_templates = [t for t in templates if t.get("is_exotic", False)]
    vanilla_templates = [t for t in templates if not t.get("is_exotic", False)]

    # Pre-seed selection: 1 trade per asset class (prioritize vanilla for baseline)
    selected = []
    for ac in asset_classes:
        ac_pool = required_by_asset[ac]
        # Try vanilla first, fall back to exotic if no vanilla available
        vanilla_in_ac = [t for t in ac_pool if not t.get("is_exotic", False)]
        if vanilla_in_ac:
            selected.append(rng.choice(vanilla_in_ac))
        else:
            selected.append(rng.choice(ac_pool))

    # Add guaranteed exotics
    current_exotics = sum(1 for t in selected if t.get("is_exotic", False))
    while current_exotics < min_exotics and len(selected) < n_trades:
        selected.append(rng.choice(exotic_templates))
        current_exotics += 1

    # Fill remainder randomly from all templates
    while len(selected) < n_trades:
        selected.append(rng.choice(templates))

    trades: List[Trade] = []
    for i, tmpl in enumerate(selected):
        notional = rng.uniform(*tmpl["notional_range"])
        # Trades were originated 30–180 days ago (portfolio seasoning).
        # This ensures non-zero MTM since the market has moved since origination.
        days_seasoned = rng.randint(30, 180)
        trade_date_actual = book_date - timedelta(days=days_seasoned)
        maturity = trade_date_actual + timedelta(days=int(tmpl["tenor_yr"] * 365))
        # MTM from market state engine — realistic day-on-day variation
        # Each trade gets a price consistent with actual market moves since trade_date.
        # The market state is deterministic per date so reruns produce identical results.
        _proto_trade_for_mtm = type('_T', (), {
            'asset_class':  tmpl['asset'],
            'notional':     notional,
            'direction':    1,         # direction assigned below; use 1 for pricing
            'trade_date':   trade_date_actual,
            'maturity_date':maturity,
            'notional_ccy': rng.choice(['USD','EUR','GBP','JPY','CHF']),
            'hedging_set':  tmpl.get('asset','IR'),
            'credit_quality': 'IG',
        })()
        mtm = compute_trade_mtm(_proto_trade_for_mtm, book_date)
        # Cap at ±15% of notional — avoids extreme moves for newly traded books
        mtm = max(min(mtm, notional * 0.15), -notional * 0.15)
        method   = tmpl["method"]

        # ~20% of IMM trades fall back to SA-CCR (req #9)
        fallback_trace = None
        if method == "IMM" and rng.random() < 0.20:
            method = "FALLBACK"
            fallback_trace = (
                f"FALLBACK|{new_trade_id(portfolio_id, i+1)}"
                f"|EXOTIC_PAYOFF|Exotic payoff structure — SA-CCR mandated"
            )

        _direction = rng.choice([-1, 1])
        _ccy       = rng.choice(["USD", "EUR", "GBP", "JPY", "CHF"])
        # Re-price with correct direction now that we know it
        _proto_trade_for_mtm.direction    = _direction
        _proto_trade_for_mtm.notional_ccy = _ccy
        mtm_final = compute_trade_mtm(_proto_trade_for_mtm, book_date)
        mtm_final = max(min(mtm_final, notional * 0.15), -notional * 0.15)

        # ── Underlying / reference entity ID ─────────────────────────────────
        ac   = tmpl["asset"]
        itype = tmpl["type"]
        # EQ: use index / single-stock ticker
        _eq_refs  = ["SPX Index","SX5E Index","NKY Index","AAPL US Equity",
                     "MSFT US Equity","AMZN US Equity","TSLA US Equity"]
        # CMDTY: commodity code
        _cmd_refs = {"CMDTY_ENERGY":"WTI_CRUDE","CMDTY_METALS":"GOLD_SPOT","CMDTY_AGRI":"CORN_FRONT"}
        # CR: reference entity list from template or generic
        _cr_refs  = tmpl.get("ref_entities", ["Generic Corp"])

        if ac == "EQ":
            _uid = rng.choice(_eq_refs)
        elif ac == "CR":
            _uid = rng.choice(_cr_refs)
        elif ac == "CMDTY":
            _uid = _cmd_refs.get(tmpl.get("type","CMDTY_OTHER"), "CMDTY_OTHER")
        else:
            _uid = None   # IR and FX have no single underlying security

        # ── Credit derivative fields ──────────────────────────────────────────
        _credit_sub = tmpl.get("credit_sub", "SINGLE_NAME")
        _ref_entity  = _uid if ac == "CR" else None

        # ── Commodity type ────────────────────────────────────────────────────
        _cmdty_type_map = {
            "CommodityFwd": "CMDTY_ENERGY", "CommoditySwap": "CMDTY_ENERGY",
            "CommodityOption": "CMDTY_ENERGY", "SpreadOption": "CMDTY_METALS",
        }
        _cmdty_type = _cmdty_type_map.get(itype, None) if ac == "CMDTY" else None

        t = Trade(
            trade_id              = new_trade_id(portfolio_id, i+1),
            asset_class           = ac,
            instrument_type       = itype,
            notional              = notional,
            notional_ccy          = _ccy,
            direction             = _direction,
            maturity_date         = maturity,
            trade_date            = trade_date_actual,
            current_mtm           = mtm_final,
            saccr_method          = method,
            fallback_trace        = fallback_trace,
            underlying_security_id= _uid,
            reference_entity      = _ref_entity,
            commodity_type        = _cmdty_type,
            credit_sub_type       = _credit_sub,
        )
        trades.append(t)

    netting.trades = trades

    # ── Post-build CSA calibration (req #6 — realistic margin) ───────────────
    # Now that trades exist, calibrate CSA terms to actual portfolio:
    # (1) VM = max(net_mtm - threshold, 0): simulate a fully-margined portfolio
    #     where the counterparty has called the last daily margin payment.
    #     Any in-the-money exposure above threshold is already collateralised.
    # (2) IM = 3% of gross notional: realistic initial margin for a liquid
    #     bilateral portfolio (reflects ISDA SIMM or IM schedule).
    # This is the key change that drives RC → near zero and PFE multiplier → 0.05-0.3

    net_mtm       = sum(t.current_mtm for t in trades)
    gross_notional = sum(abs(t.notional) for t in trades)

    # VM received = exposure exceeding threshold, fully posted by counterparty
    vm_received = max(net_mtm - threshold, 0.0)
    netting.variation_margin = vm_received

    # IM = 3% of gross notional (bilateral ISDA SIMM approximation)
    netting.initial_margin = gross_notional * 0.03

    logger.debug(
        "Portfolio %s CSA: net_mtm=%.0f TH=%.0f VM_received=%.0f IM=%.0f "
        "→ RC_floor=max(%.0f, %.0f)",
        portfolio_id,
        net_mtm, threshold, vm_received, netting.initial_margin,
        net_mtm - vm_received - netting.initial_margin,
        threshold + mta - netting.initial_margin,
    )

    return portfolio_id, netting, trades


# ─────────────────────────────────────────────────────────────────────────────
# Banking Book Portfolio Factory
# ─────────────────────────────────────────────────────────────────────────────

def create_banking_book_portfolio(
    counterparty: dict,
    book_date: date,
    n_exposures: int = 8,
    rng: random.Random = None,
) -> Tuple[str, List[BankingBookExposure]]:
    """
    Creates a banking book portfolio with:
      - ≥5 exposures across loan/bond types  (req #5)
      - CDS mitigants on ~40% of exposures   (req #7)
    """
    if rng is None:
        rng = random.Random(42)

    portfolio_id = new_portfolio_id("BANKING_BOOK", book_date)
    n_exposures  = max(n_exposures, 5)

    # ── Full exposure type library (12 types across all A-IRB asset classes) ─
    loan_types = [
        # Corporate
        {"type": "TERM_LOAN",        "asset": "CORP",         "pd_mult": 1.0, "lgd": 0.45},
        {"type": "REVOLVING_CREDIT", "asset": "CORP",         "pd_mult": 1.2, "lgd": 0.45},
        {"type": "CORP_BOND",        "asset": "CORP",         "pd_mult": 0.9, "lgd": 0.40},
        {"type": "BILATERAL_LOAN",   "asset": "CORP",         "pd_mult": 1.1, "lgd": 0.45},
        # Retail
        {"type": "RESIDENTIAL_MORT", "asset": "RETAIL_MORT",  "pd_mult": 0.8, "lgd": 0.20},
        {"type": "HELOC",            "asset": "RETAIL_MORT",  "pd_mult": 1.0, "lgd": 0.25},
        {"type": "CREDIT_CARD",      "asset": "RETAIL_REV",   "pd_mult": 2.0, "lgd": 0.75},
        {"type": "OVERDRAFT",        "asset": "RETAIL_REV",   "pd_mult": 1.8, "lgd": 0.70},
        {"type": "AUTO_LOAN",        "asset": "RETAIL_OTHER", "pd_mult": 1.5, "lgd": 0.45},
        {"type": "PERSONAL_LOAN",    "asset": "RETAIL_OTHER", "pd_mult": 1.7, "lgd": 0.55},
        # Banks & Sovereigns
        {"type": "INTERBANK_LOAN",   "asset": "BANK",         "pd_mult": 0.7, "lgd": 0.45},
        {"type": "SOVEREIGN_BOND",   "asset": "SOVEREIGN",    "pd_mult": 0.5, "lgd": 0.45},
    ]

    selected = rng.sample(loan_types, min(n_exposures, len(loan_types)))
    while len(selected) < n_exposures:
        selected.append(rng.choice(loan_types))

    # Macro stress multiplier — portfolio-level constant (same book_date for
    # all exposures; hoisted outside the loop to avoid redundant market calls).
    # VIX > 25 → mild stress; VIX > 40 → crisis (up to 2.5× PD).
    from backend.data_sources.market_state import get_market_state as _gms
    _ms            = _gms(book_date)
    _vix           = _ms.vix()
    _cs_hy         = _ms.credit_spread("HY")
    _stress        = min(max((_vix - 18.0) / 40.0 + (_cs_hy - 380.0) / 1200.0, 0.0), 1.0)
    _pd_macro_mult = 1.0 + 1.5 * _stress

    exposures: List[BankingBookExposure] = []
    for i, lt in enumerate(selected):
        ead      = rng.uniform(1e6, 200e6)
        # Draw maturity first so pd_from_rating() uses the correct horizon.
        maturity = rng.uniform(1.0, 7.0)
        # PD derived from the S&P rating transition matrix at the exposure's
        # maturity horizon, then stressed by the current macro regime.
        base_pd  = pd_from_rating(counterparty["rating"], horizon_years=maturity)
        pd       = min(base_pd * lt["pd_mult"] * rng.uniform(0.5, 2.0) * _pd_macro_mult, 0.30)
        lgd       = lt["lgd"] * rng.uniform(0.85, 1.15)
        lgd       = max(min(lgd, 0.75), 0.10)
        provisions= ead * pd * lgd * rng.uniform(0.5, 1.0)

        # ── Mitigant assignment — diversified across four CRM channels ──────────
        # Each exposure independently rolls for each mitigant type.
        # ~40% CDS  | ~30% physical collateral | ~25% guarantee | ~15% deposit netting

        # (A) CDS protection (req #7)
        has_cds   = rng.random() < 0.40
        cds_pd    = 0.0
        cds_cov   = 0.0
        if has_cds:
            cds_pd  = max(pd * rng.uniform(0.05, 0.25), 0.0001)   # guarantor much better
            cds_cov = rng.uniform(0.50, 1.00)                      # partial to full

        # (B) Funded collateral — type depends on exposure type
        col_type  = "NONE"
        col_value = 0.0
        if rng.random() < 0.30:
            if lt["asset"] == "RETAIL_MORT":
                col_type  = "RESIDENTIAL_RE"
                col_value = ead * rng.uniform(0.80, 1.20)   # LTV ~80-120%
            elif lt["asset"] in ("CORP", "BANK"):
                col_type  = rng.choice(["FINANCIAL", "COMMERCIAL_RE", "RECEIVABLES"])
                col_value = ead * rng.uniform(0.40, 0.90)
            elif lt["asset"] == "RETAIL_OTHER":
                col_type  = "OTHER_PHYSICAL"
                col_value = ead * rng.uniform(0.30, 0.70)
            else:
                col_type  = "FINANCIAL"
                col_value = ead * rng.uniform(0.30, 0.80)

        # (C) Guarantee from a better-rated entity (banks, sovereigns only)
        has_guarantee    = False
        guarantor_pd_val = 0.0
        gua_lgd          = 0.45
        gua_coverage     = 0.0
        if rng.random() < 0.25 and lt["asset"] in ("CORP", "BANK", "SOVEREIGN"):
            has_guarantee    = True
            # Guarantor is always better-rated than obligor
            guarantor_pd_val = max(pd * rng.uniform(0.03, 0.20), 0.00005)
            gua_lgd          = rng.choice([0.40, 0.45])     # senior unsecured
            gua_coverage     = rng.uniform(0.40, 0.80)      # partial guarantee

        # (D) Retail deposit netting (CRE32.63) — retail only
        deposit_offset = 0.0
        if lt["asset"].startswith("RETAIL") and rng.random() < 0.15:
            deposit_offset = ead * rng.uniform(0.05, 0.25)  # 5-25% offset from deposit

        exp = BankingBookExposure(
            trade_id          = new_trade_id(portfolio_id, i+1),
            portfolio_id      = portfolio_id,
            obligor_id        = counterparty["id"],
            asset_class       = lt["asset"],
            ead               = ead,
            pd                = pd,
            lgd               = lgd,
            maturity          = maturity,
            sales_volume      = rng.uniform(0, 100e6),
            has_cds           = has_cds,
            cds_pd            = cds_pd,
            cds_lgd           = 0.45,
            cds_coverage      = cds_cov,
            collateral_type   = col_type,
            collateral_value  = col_value,
            has_guarantee     = has_guarantee,
            guarantor_pd      = guarantor_pd_val,
            guarantor_lgd     = gua_lgd,
            guarantee_coverage= gua_coverage,
            deposit_offset    = deposit_offset,
            provisions        = provisions,
        )
        exposures.append(exp)

    return portfolio_id, exposures


# ─────────────────────────────────────────────────────────────────────────────
# Full Platform Dataset Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_full_dataset(
    book_date: date = None,
    seed: int = 42,
    n_derivative_portfolios: int = N_DERIVATIVE_PORTFOLIOS,
    n_banking_portfolios: int = N_BANKING_PORTFOLIOS,
    n_trades_min: int = N_TRADES_MIN_DRV,
    n_trades_max: int = N_TRADES_MAX_DRV,
    n_exp_min: int = N_EXP_MIN_BBK,
    n_exp_max: int = N_EXP_MAX_BBK,
) -> Dict:
    """
    Creates a complete set of portfolios for both desks.

    Parameters
    ----------
    n_derivative_portfolios : int
        Number of derivative portfolios to generate (default 20).
    n_banking_portfolios : int
        Number of banking book portfolios to generate (default 20).
    n_trades_min / n_trades_max : int
        Random range for trades per derivative portfolio (default 8–15).
    n_exp_min / n_exp_max : int
        Random range for exposures per banking portfolio (default 8–15).

    Notes
    -----
    Counterparties are cycled from the 20-name universe when the portfolio
    count exceeds the counterparty count. Each portfolio gets a unique
    DRV-YYYY-NNN or BBK-YYYY-NNN ID regardless.

    M1 (8 GB) benchmarks:
      20/20 portfolios, 8–15 trades  →  ~0.8s,  ~8 MB RAM  ✓ comfortable
      50/50 portfolios, 10 trades    →  ~2.7s,  ~8 MB RAM  ✓ comfortable
    """
    if book_date is None:
        book_date = date.today()

    rng = random.Random(seed)

    derivative_portfolios = []
    banking_portfolios    = []

    # ── Derivative portfolios ─────────────────────────────────────────────────
    for i in range(n_derivative_portfolios):
        cpty = COUNTERPARTIES[i % len(COUNTERPARTIES)]
        pid, netting, trades = create_derivative_portfolio(
            cpty, book_date,
            n_trades=rng.randint(n_trades_min, n_trades_max),
            rng=rng,
        )
        derivative_portfolios.append({
            "portfolio_id":   pid,
            "portfolio_type": "DERIVATIVE",
            "counterparty":   cpty,
            "netting":        netting,
            "trades":         trades,
        })

    # ── Banking book portfolios ───────────────────────────────────────────────
    for i in range(n_banking_portfolios):
        cpty = COUNTERPARTIES[i % len(COUNTERPARTIES)]
        pid, exposures = create_banking_book_portfolio(
            cpty, book_date,
            n_exposures=rng.randint(n_exp_min, n_exp_max),
            rng=rng,
        )
        banking_portfolios.append({
            "portfolio_id":   pid,
            "portfolio_type": "BANKING_BOOK",
            "counterparty":   cpty,
            "exposures":      exposures,
        })

    return {
        "book_date":             book_date,
        "derivative_portfolios": derivative_portfolios,
        "banking_portfolios":    banking_portfolios,
        "stats": {
            "n_drv_portfolios":   len(derivative_portfolios),
            "n_bbk_portfolios":   len(banking_portfolios),
            "total_drv_trades":   sum(len(p["trades"])    for p in derivative_portfolios),
            "total_bbk_exposures":sum(len(p["exposures"]) for p in banking_portfolios),
        },
    }

logger = logging.getLogger(__name__)
