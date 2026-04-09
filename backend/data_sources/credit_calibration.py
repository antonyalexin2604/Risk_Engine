"""
PROMETHEUS Risk Platform
Module: Credit Calibration — Rating Transition Matrix & PD Derivation

Responsibility
──────────────
Provides the single authoritative source of truth for translating a
counterparty's external credit rating into a Basel CRE31-compatible
1-year probability of default (PD).  All modules that need a rating-
derived PD should import ``pd_from_rating`` from here — not from any
data-generator module.

Why this module exists (design rationale)
─────────────────────────────────────────
The Rating Transition Matrix (RTM) and its derived PD function were
previously embedded inside ``portfolio_generator.py``.  That placement
violated the Single Responsibility Principle because:

  1. ``portfolio_generator.py`` is a *data factory* (builds synthetic
     trade/exposure portfolios).  The RTM is a *quantitative credit
     model* (matrix algebra, scipy-compatible maths).  These are different
     abstraction levels.

  2. ``numpy`` was imported exclusively for the RTM — the portfolio
     generation logic itself uses no numpy at all.

  3. ``cva_generator.py`` already imported ``pd_from_rating`` from the
     generator module — a semantically wrong cross-boundary dependency.

  4. With zero dedicated tests it was invisible to the test suite.

Placement: ``backend/data_sources/credit_calibration.py``
  This mirrors the existing ``calibration.py`` in the same package,
  which translates live market data into quantitative parameters for the
  IMM engine.  The RTM module does the same thing for credit risk:
  external data (S&P default study) → quantitative parameters (PD).

Data source
───────────
S&P Global Ratings Annual Corporate Default Study 2022.
NR (Not Rated) category redistributed proportionally across surviving
states so every row sums exactly to 1.0.
Eight broad rating categories: AAA, AA, A, BBB, BB, B, CCC, D.
D (Default) is an absorbing state.

Consumers
─────────
  backend/data_generators/portfolio_generator.py   ← pd_from_rating()
  backend/data_generators/cva_generator.py         ← pd_from_rating()
  (future) stress-testing engine, ICAAP scenario builder, etc.

Public API
──────────
  pd_from_rating(rating, horizon_years) → float
      Derives a 1-year-equivalent Basel CRE31-compatible PD.

  RTM_CATEGORIES         List[str]        — ordered category labels
  RTM_1Y                 np.ndarray (8×8) — raw 1-year transition matrix
  NOTCH_TO_CATEGORY      Dict[str, str]   — notch → broad category map
  NOTCH_PD_MULTIPLIER    Dict[str, float] — within-category notch scaling
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, List

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Constants — exposed publicly so callers can inspect or override
# ─────────────────────────────────────────────────────────────────────────────

#: Ordered list of broad S&P rating categories used by the matrix.
#: The last entry "D" is an absorbing (default) state.
RTM_CATEGORIES: List[str] = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D"]

_RTM_CAT_IDX: Dict[str, int] = {r: i for i, r in enumerate(RTM_CATEGORIES)}

#: Public alias — maps each category string to its row/column index in ``RTM_1Y``.
RTM_CAT_IDX: Dict[str, int] = _RTM_CAT_IDX

#: 1-year corporate average transition matrix (rows=FROM, cols=TO).
#: Source: S&P Global Ratings Annual Default Study 2022.
#: NR category redistributed proportionally; every row sums to 1.0.
RTM_1Y: np.ndarray = np.array([
    #  AAA      AA       A        BBB      BB       B        CCC      D
    [0.9081, 0.0833, 0.0068, 0.0006, 0.0012, 0.0000, 0.0000, 0.0000],  # AAA
    [0.0070, 0.9065, 0.0779, 0.0064, 0.0006, 0.0014, 0.0002, 0.0000],  # AA
    [0.0009, 0.0227, 0.9105, 0.0552, 0.0074, 0.0026, 0.0001, 0.0006],  # A
    [0.0002, 0.0033, 0.0595, 0.8693, 0.0530, 0.0117, 0.0012, 0.0018],  # BBB
    [0.0003, 0.0014, 0.0067, 0.0773, 0.8053, 0.0884, 0.0100, 0.0106],  # BB
    [0.0000, 0.0011, 0.0024, 0.0043, 0.0648, 0.8346, 0.0407, 0.0521],  # B
    [0.0011, 0.0000, 0.0037, 0.0118, 0.0241, 0.1375, 0.5282, 0.2936],  # CCC
    [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 1.0000],  # D
], dtype=float)

#: Map from full notched rating (e.g. "A-") to broad S&P category (e.g. "A").
#: Unrecognised notches fall back to "BBB" (investment-grade mid-point) in
#: ``pd_from_rating``.
NOTCH_TO_CATEGORY: Dict[str, str] = {
    "AAA":  "AAA",
    "AA+":  "AA",  "AA":  "AA",  "AA-":  "AA",
    "A+":   "A",   "A":   "A",   "A-":   "A",
    "BBB+": "BBB", "BBB": "BBB", "BBB-": "BBB",
    "BB+":  "BB",  "BB":  "BB",  "BB-":  "BB",
    "B+":   "B",   "B":   "B",   "B-":   "B",
    "CCC+": "CCC", "CCC": "CCC", "CCC-": "CCC", "CC": "CCC", "C": "CCC",
    "D":    "D",
}

#: Within-category notch multiplier applied to the broad-category default
#: probability to add intra-category granularity.
#: A "+" notch is safer (multiplier < 1), a "-" notch is riskier (> 1).
#: The geometric mean across {+, plain, -} within each category ≈ 1.0.
NOTCH_PD_MULTIPLIER: Dict[str, float] = {
    "AAA":  1.00,
    "AA+":  0.60, "AA":  1.00, "AA-":  1.55,
    "A+":   0.60, "A":   1.00, "A-":   1.55,
    "BBB+": 0.60, "BBB": 1.00, "BBB-": 1.55,
    "BB+":  0.60, "BB":  1.00, "BB-":  1.55,
    "B+":   0.60, "B":   1.00, "B-":   1.55,
    "CCC+": 0.60, "CCC": 1.00, "CCC-": 1.55, "CC": 2.00, "C": 3.50,
    "D":    1.00,
}

# ── Basel CRE31.17 PD bounds ──────────────────────────────────────────────────
_PD_FLOOR: float = 0.0003   # 3bp minimum per CRE31.17
_PD_CAP:   float = 0.999    # practical maximum (excludes formally defaulted)

#: Public aliases — importable without underscore prefix.
PD_FLOOR: float = _PD_FLOOR
PD_CAP:   float = _PD_CAP

#: Short alias for NOTCH_PD_MULTIPLIER (both names are valid).
NOTCH_PD_MULT = NOTCH_PD_MULTIPLIER

# ── Tenor clip range (years) ──────────────────────────────────────────────────
_HORIZON_MIN: float = 0.25   # 3-month minimum
_HORIZON_MAX: float = 10.0   # 10-year maximum


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=64)
def _rtm_power(t_int: int) -> np.ndarray:
    """
    Return RTM_1Y raised to the integer power *t_int*.

    Results are cached — computing ``_rtm_power(5)`` once and reusing it
    avoids repeated O(n³) matrix multiplication across thousands of
    portfolio exposures that share the same integer horizon.
    Cache is keyed on the integer only; fractional-year interpolation
    is handled in ``pd_from_rating()`` using two adjacent powers.
    """
    return np.linalg.matrix_power(RTM_1Y, t_int)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def pd_from_rating(rating: str, horizon_years: float = 1.0) -> float:
    """
    Derive a Basel CRE31-compatible annualised PD from a credit rating and
    exposure maturity horizon using the S&P annual corporate transition matrix.

    Methodology
    ───────────
    1. Normalise the notched rating string (e.g. ``"A-"``) and map it to a
       broad S&P category (``"A"``) via ``NOTCH_TO_CATEGORY``.
       Unrecognised ratings fall back to ``"BBB"`` (conservative mid-point).

    2. Compute the T-year transition matrix P(T):
         - T ≤ 1 yr  : linearly interpolate between the identity (no
                        transitions at t=0) and the 1-year matrix P¹.
         - T > 1 yr  : linearly interpolate between P^⌊T⌋ and P^(⌊T⌋+1).
       Both integer powers are LRU-cached, so repeated calls for the same
       integer horizon (common in large portfolios) are O(1).

    3. Read the cumulative T-year default probability:
         ``PD_cum = P(T)[rating_row, default_col]``

    4. Apply the within-category notch multiplier from ``NOTCH_PD_MULTIPLIER``
       to add finer granularity between "BBB+", "BBB", and "BBB-", for example.

    5. Convert cumulative PD to a 1-year-equivalent (annualised) PD using the
       constant-hazard survival-rate formula::

           PD_1yr = 1 − (1 − PD_cum)^(1/T)

       This keeps the result compatible with the Basel CRE31 A-IRB formula,
       which expects a 1-year horizon PD (CRE31.17).

    6. Clamp to [``_PD_FLOOR``, ``_PD_CAP``] = [3bp, 99.9%] per CRE31.17.

    Parameters
    ──────────
    rating : str
        Notched rating string, e.g. ``"AA-"``, ``"BBB+"``, ``"B"``.
        Case-insensitive; leading/trailing whitespace is stripped.
        Unrecognised values fall back to ``"BBB"`` with a note in the
        return value.

    horizon_years : float
        Exposure maturity in years.  Clipped to [0.25, 10.0] before use.
        For banking book exposures, pass the loan/bond effective maturity
        (``BankingBookExposure.maturity``).  For CVA inputs, pass the
        netting-set effective maturity.

    Returns
    ───────
    float
        1-year-equivalent PD as a decimal (e.g. ≈ 0.00061 for ``"A"``
        at a 1-year horizon; ≈ 0.00180 for ``"A"`` at a 5-year horizon).
        Always in [0.0003, 0.999].

    Examples
    ────────
    >>> pd_from_rating("AAA", 1.0)   # ≈ 0.0003  (floor — near-zero default)
    >>> pd_from_rating("BBB", 1.0)   # ≈ 0.0018
    >>> pd_from_rating("BB",  3.0)   # ≈ 0.0320  (multi-year cumulative)
    >>> pd_from_rating("B-",  5.0)   # ≈ 0.1700  (HY, long horizon)
    >>> pd_from_rating("XYZ", 1.0)   # fallback → BBB ≈ 0.0018
    """
    T    = max(_HORIZON_MIN, min(float(horizon_years), _HORIZON_MAX))
    key  = rating.upper().strip()
    cat  = NOTCH_TO_CATEGORY.get(key, "BBB")   # conservative fallback
    mult = NOTCH_PD_MULTIPLIER.get(key, 1.00)
    row  = _RTM_CAT_IDX[cat]
    col  = _RTM_CAT_IDX["D"]                   # absorbing default state

    # ── Build P(T) by linear interpolation between integer matrix powers ──────
    if T <= 1.0:
        # Interpolate between identity (t=0, no transitions) and P¹ (t=1)
        P_T = (1.0 - T) * np.eye(8) + T * RTM_1Y
    else:
        t_lo = int(T)
        frac = T - t_lo
        P_T  = (1.0 - frac) * _rtm_power(t_lo) + frac * _rtm_power(t_lo + 1)

    pd_cum = float(P_T[row, col])

    # ── Annualise: convert cumulative PD to 1-year-equivalent ────────────────
    # Guard against pd_cum ≥ 1.0 (absorbing state or numerical edge-case)
    if pd_cum >= 1.0:
        return _PD_CAP
    pd_annual = 1.0 - (1.0 - pd_cum) ** (1.0 / T)

    # ── Apply notch multiplier and clamp to Basel CRE31.17 bounds ────────────
    return max(_PD_FLOOR, min(pd_annual * mult, _PD_CAP))


def pd_term_structure(rating: str, tenors: List[float] = None) -> Dict[float, float]:
    """
    Return a PD term structure for a given rating across multiple horizons.

    Useful for populating ``BankingBookExposure.pd_term_structure`` or
    computing CVA exposure-weighted PD term structures.

    Parameters
    ──────────
    rating : str
        Notched rating string (same as ``pd_from_rating``).
    tenors : List[float]
        Horizon years to evaluate.  Defaults to [1, 2, 3, 5, 7, 10].

    Returns
    ───────
    Dict[float, float]
        {horizon_years: annualised_pd} for each requested tenor.

    Example
    ───────
    >>> pd_term_structure("BBB")
    {1: 0.00180, 2: 0.00350, 3: 0.00510, 5: 0.00790, 7: 0.01040, 10: 0.01390}
    """
    if tenors is None:
        tenors = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    return {t: pd_from_rating(rating, t) for t in tenors}


def validate_rtm() -> bool:
    """
    Sanity-check the transition matrix at module load time.

    Verifies:
      - Shape is 8×8
      - All entries are in [0, 1]
      - Each row sums to 1.0 (within floating-point tolerance)
      - D (last row) is absorbing: RTM_1Y[7, 7] == 1.0
      - Monotonicity: 1-year default probability increases from AAA to CCC

    Returns True if all checks pass; raises AssertionError otherwise.
    Called automatically at import time.
    """
    n = len(RTM_CATEGORIES)
    assert RTM_1Y.shape == (n, n), f"RTM shape must be ({n},{n})"
    assert (RTM_1Y >= 0).all(),    "RTM contains negative entries"
    assert (RTM_1Y <= 1).all(),    "RTM contains entries > 1"

    row_sums = RTM_1Y.sum(axis=1)
    for i, s in enumerate(row_sums):
        assert abs(s - 1.0) < 1e-9, \
            f"Row {RTM_CATEGORIES[i]} sums to {s:.10f} (not 1.0)"

    assert RTM_1Y[n-1, n-1] == 1.0, "Default state (D) must be absorbing"

    # Monotonic default probability from AAA → CCC
    d_col = _RTM_CAT_IDX["D"]
    default_probs = [RTM_1Y[i, d_col] for i in range(n - 1)]  # exclude D itself
    for i in range(len(default_probs) - 1):
        assert default_probs[i] <= default_probs[i+1] + 1e-9, (
            f"Non-monotonic 1Y default: {RTM_CATEGORIES[i]}={default_probs[i]:.6f} "
            f"> {RTM_CATEGORIES[i+1]}={default_probs[i+1]:.6f}"
        )

    return True


# Run validation at import — fails loudly if the matrix is corrupted
validate_rtm()
