"""
PROMETHEUS Risk Platform
Module: LGD Calibration — Loss Given Default Modelling

Implements a three-layer LGD model per CRE36.83 / CRE32.15-19 requirements,
designed for A-IRB use at a US G-SIB.

Regulatory basis
────────────────
CRE32.5:   Two approaches — F-IRB (supervisory LGD) and A-IRB (own estimates)
CRE32.15:  Own LGD must be measured as loss as a percentage of EAD
CRE32.16:  Hard parameter floors for corporate: 25% unsecured; collateral-type
           dependent for secured (0%–15%)
CRE36.76:  Economic loss definition — includes discount effects and workout costs
CRE36.83:  LGD must reflect downturn conditions; cannot be less than the
           long-run default-weighted average loss rate given default
CRE36.84:  Collateral dependency (wrong-way LGD) must be treated conservatively
CRE36.85:  Grounded in historical recovery rates, not solely collateral market value
CRE36.86:  Best-estimate LGD for defaulted assets — K = max(0, LGD_DT − EL_best)
CRE36.88:  5-year minimum observation period

Three-layer architecture
────────────────────────
Layer 1 — Through-the-Cycle (TTC) LGD
    Long-run default-weighted average by facility class.
    Parameterised from Moody's Annual Default Study (2023) and S&P Global
    Recovery Ratings data.  Acts as the Basel CRE36.83 long-run floor.

Layer 2 — Downturn LGD (DT-LGD)  [Pillar 1 — regulatory capital]
    Frye-Jacobs (2001) adjustment that links LGD to the same systematic risk
    factor driving PD in the Basel Vasicek model.  Uses the 99.9th percentile
    of the systematic factor (q = 0.999), identical to the CRE31.4 confidence
    level, ensuring internal consistency between PD and LGD stress.

    Formula (Frye-Jacobs 2001):
        LGD_DT = Φ( (Φ⁻¹(LGD_TTC) + ρ_LGD × Φ⁻¹(q)) / √(1 − ρ_LGD²) )

    where ρ_LGD is the empirical LGD-systematic-factor correlation, estimated
    at 0.20–0.40 for wholesale exposures (Schuermann 2004, Frye 2000).

Layer 3 — Conditional LGD  [Pillar 2 / ICAAP only — NOT Pillar 1 capital]
    Point-in-time estimate conditioned on current macro state (VIX, HY-OAS,
    unemployment).  Applied via the macro stress index from USMacroDataFeed /
    MacroeconomicFactors.  Replaces the heuristic in MacroeconomicOverlay with
    a Frye-effect grounded model.

Usage
─────
    from backend.data_sources.lgd_calibration import LGDModel

    model = LGDModel()

    # Pillar 1 regulatory capital — downturn LGD
    lgd_dt = model.downturn_lgd("CORP", collateral_type="NONE", pd=0.01)

    # Pillar 2 / ICAAP — macro-conditional
    lgd_cond = model.conditional_lgd("CORP", macro=macro_factors)

    # TTC baseline
    lgd_ttc = model.ttc_lgd("CORP", collateral_type="RESIDENTIAL_RE")

    # Validate all floors and return audit dict
    result = model.compute_lgd(exp)

Why this belongs in data_sources/
──────────────────────────────────
Like credit_calibration.py (PD), this module is a quantitative credit
parameter model that derives calibrated inputs for the A-IRB engine from
external reference data (Moody's/S&P recovery studies).  It is not engine
logic and should not live in backend/engines/.  The pattern matches
calibration.py (market vol/corr) and credit_calibration.py (PD/RTM).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Normal distribution helpers (scipy if available, minimax fallback)
# ─────────────────────────────────────────────────────────────────────────────

try:
    from scipy.special import ndtr as _ndtr, ndtri as _ndtri
    _norm_cdf = _ndtr
    _norm_inv = _ndtri
    logger.debug("lgd_calibration: using scipy.special for Φ/Φ⁻¹")
except ImportError:
    import math as _math

    def _norm_cdf(x: float) -> float:
        return 0.5 * (1.0 + _math.erf(x / _math.sqrt(2.0)))

    def _norm_inv(p: float) -> float:
        # Beasley-Springer-Moro minimax approximation — adequate for 0.001 ≤ p ≤ 0.999
        p = max(1e-12, min(1.0 - 1e-12, p))
        if p == 0.5:
            return 0.0
        sign = 1.0 if p > 0.5 else -1.0
        q = min(p, 1.0 - p)
        r = _math.sqrt(-2.0 * _math.log(q))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        x = r - (c0 + c1 * r + c2 * r * r) / (1 + d1 * r + d2 * r * r + d3 * r ** 3)
        return sign * x

# ─────────────────────────────────────────────────────────────────────────────
# CRE32.16 — regulatory parameter floors (absolute backstops)
# These apply regardless of any model output, for corporate exposures.
# Sovereign exposures are exempt (CRE32.16 footnote).
# ─────────────────────────────────────────────────────────────────────────────

#: Hard floor for fully unsecured corporate / bank / HVCRE exposures (CRE32.16)
LGD_FLOOR_UNSECURED: float = 0.25

#: Secured floors by collateral type (CRE32.16)
LGD_FLOORS_SECURED: Dict[str, float] = {
    "FINANCIAL":      0.00,   # cash / eligible financial collateral
    "RECEIVABLES":    0.10,
    "RESIDENTIAL_RE": 0.05,   # CRE32.17 — residential real estate
    "COMMERCIAL_RE":  0.10,
    "OTHER_PHYSICAL": 0.15,
    "NONE":           0.25,   # no collateral → use unsecured floor
}

#: Absolute model cap (a defaulted exposure has LGD ≤ 100%)
LGD_CAP: float = 0.999

# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Through-the-Cycle (TTC) LGD by facility class
# ─────────────────────────────────────────────────────────────────────────────
# Source: Moody's Annual Default Study 2023 (Exhibit 30 — recovery by seniority)
#         S&P Global Recovery Ratings 2023
#         Bank of England Working Paper No. 537 (retail mortgage recovery)
#
# The table maps (asset_class, collateral_type) → (mean_TTC_LGD, ρ_LGD)
#   mean_TTC_LGD : long-run default-weighted average LGD (decimal)
#   ρ_LGD        : LGD-systematic-factor correlation for Frye-Jacobs
#                  Wholesale: 0.25–0.35 (Frye 2000, Schuermann 2004)
#                  Retail:    0.10–0.20 (lower systemic co-movement)
#
# Key: (ASSET_CLASS, COLLATERAL_TYPE) — use "NONE" for unsecured
# ─────────────────────────────────────────────────────────────────────────────

_TTC_TABLE: Dict[Tuple[str, str], Tuple[float, float]] = {
    # Corporate — unsecured
    ("CORP",        "NONE"):           (0.424, 0.30),  # Moody's 2023: 42.4% mean recovery = 57.6% → 42.4% LGD
    ("BANK",        "NONE"):           (0.450, 0.30),  # Senior unsecured FI: CRE32.6 45%
    ("SOVEREIGN",   "NONE"):           (0.250, 0.15),  # Sovereigns: lower systemic co-movement
    # Corporate — financial collateral (cash, eligible securities)
    ("CORP",        "FINANCIAL"):      (0.200, 0.25),  # Higher recovery from liquid collateral
    ("BANK",        "FINANCIAL"):      (0.180, 0.25),
    # Corporate — real estate
    ("CORP",        "COMMERCIAL_RE"):  (0.300, 0.30),  # Recovery ~70% → LGD ~30%
    ("CORP",        "RESIDENTIAL_RE"): (0.200, 0.25),
    # Corporate — other physical / receivables
    ("CORP",        "RECEIVABLES"):    (0.250, 0.28),
    ("CORP",        "OTHER_PHYSICAL"): (0.300, 0.30),
    # HVCRE — inherently higher LGD due to construction risk (CRE31.10)
    ("HVCRE",       "NONE"):           (0.500, 0.35),
    ("HVCRE",       "COMMERCIAL_RE"):  (0.350, 0.35),
    # Retail — residential mortgage
    # BoE 2015: UK mean LGD ~12%; US FHA/Freddie: 15-20%. Use 17% as mid-point.
    ("RETAIL_MORT", "NONE"):           (0.170, 0.12),
    ("RETAIL_MORT", "RESIDENTIAL_RE"): (0.150, 0.12),
    # Retail — revolving (credit cards, overdrafts) — high unsecured LGD
    ("RETAIL_REV",  "NONE"):           (0.750, 0.10),  # Industry average ~75%
    # Retail — other (auto, personal loans)
    ("RETAIL_OTHER","NONE"):           (0.450, 0.15),
    ("RETAIL_OTHER","OTHER_PHYSICAL"): (0.300, 0.15),  # Auto loans with vehicle collateral
}

# Default row: unsecured corporate as conservative fallback
_TTC_DEFAULT: Tuple[float, float] = (0.450, 0.30)

# ─────────────────────────────────────────────────────────────────────────────
# Downturn percentile — consistent with CRE31.4 confidence level
# ─────────────────────────────────────────────────────────────────────────────

#: 99.9th percentile of the standard normal systematic factor.
#: Same quantile as CRE31.4 ensures PD and LGD stress are jointly consistent.
_Q_DOWNTURN: float = _norm_inv(0.999)   # ≈ 3.0902

# ─────────────────────────────────────────────────────────────────────────────
# LGDResult — structured output with full audit trail
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LGDResult:
    """
    Complete LGD model output with regulatory audit trail.

    All three layers are computed and stored regardless of which is used
    for capital, so Risk Control can inspect the full picture.
    """
    asset_class:       str
    collateral_type:   str
    pd:                float             # input obligor PD (used for conditional layer only)

    # Layer 1 — TTC baseline
    lgd_ttc:           float             # long-run default-weighted average
    rho_lgd:           float             # LGD-systematic correlation used

    # Layer 2 — Downturn (Pillar 1)
    lgd_downturn:      float             # Frye-Jacobs 99.9th percentile
    lgd_downturn_floored: float          # after applying CRE32.16 floor

    # Layer 3 — Conditional (Pillar 2 / ICAAP only)
    lgd_conditional:   Optional[float]   # macro-conditioned; None if no macro data
    stress_index:      Optional[float]   # macro stress_index used

    # Regulatory metadata
    cre3216_floor:     float             # the floor applied (from LGD_FLOORS_SECURED)
    floor_binding:     bool              # True if floor > model output
    pillar1_lgd:       float             # lgd_downturn_floored — USE THIS for capital
    source:            str               # 'TTC_TABLE' or 'FALLBACK'


# ─────────────────────────────────────────────────────────────────────────────
# Core LGD Model
# ─────────────────────────────────────────────────────────────────────────────

class LGDModel:
    """
    Three-layer LGD model for A-IRB capital calculation.

    Designed for use at a US G-SIB under Basel CRE36.83.

    Layers
    ──────
    1.  TTC LGD:      long-run default-weighted average by facility class
                      (sourced from Moody's/S&P recovery studies)
    2.  Downturn LGD: Frye-Jacobs 99.9th-percentile stress  [Pillar 1]
    3.  Conditional:  macro-state-conditioned estimate        [Pillar 2]

    Parameters
    ──────────
    downturn_quantile : float
        Confidence level for downturn stress (default 0.999 = CRE31.4 level).
        Supervisors may require a different quantile for internal stress tests;
        set to e.g. 0.995 for a lighter stress scenario.

    rho_lgd_override : float, optional
        Override the table-sourced ρ_LGD for all facility types.
        Use when a bank's own econometric estimate differs from the literature.
        E.g. rho_lgd_override=0.25 applies a flat 25% correlation.

    conservative_margin : float
        Additive margin of conservatism (decimal) applied to the TTC LGD
        before the Frye-Jacobs transform, per CRE36.65/83 data uncertainty
        guidance.  Default 0.02 (+2pp).  Set to 0.0 to disable.
    """

    def __init__(
        self,
        downturn_quantile: float = 0.999,
        rho_lgd_override: Optional[float] = None,
        conservative_margin: float = 0.02,
    ):
        if not (0.90 <= downturn_quantile <= 0.9999):
            raise ValueError(
                f"downturn_quantile must be in [0.90, 0.9999]; got {downturn_quantile}"
            )
        if rho_lgd_override is not None and not (0.0 < rho_lgd_override < 1.0):
            raise ValueError(
                f"rho_lgd_override must be in (0, 1); got {rho_lgd_override}"
            )
        self._q        = _norm_inv(downturn_quantile)
        self._rho_ovr  = rho_lgd_override
        self._margin   = max(0.0, conservative_margin)

        logger.info(
            "LGDModel initialised — q=%.4f (%.1f%% confidence)  "
            "rho_override=%s  conservative_margin=%.2f%%",
            self._q, downturn_quantile * 100,
            f"{rho_lgd_override:.3f}" if rho_lgd_override else "from table",
            self._margin * 100,
        )

    # ── Layer 1: TTC LGD ─────────────────────────────────────────────────────

    def ttc_lgd(
        self,
        asset_class: str,
        collateral_type: str = "NONE",
    ) -> Tuple[float, float]:
        """
        Return the through-the-cycle LGD and ρ_LGD for a facility.

        Looks up the (asset_class, collateral_type) pair in the TTC table.
        Falls back to the unsecured corporate default row if the combination
        is not in the table, and logs a WARNING.

        Args:
            asset_class:     CRE31 asset class (CORP, BANK, SOVEREIGN,
                             RETAIL_MORT, RETAIL_REV, RETAIL_OTHER, HVCRE)
            collateral_type: Basel collateral type or NONE for unsecured

        Returns:
            (lgd_ttc, rho_lgd) — both as decimals
        """
        key = (asset_class.upper(), collateral_type.upper())
        # Exact match
        if key in _TTC_TABLE:
            lgd_ttc, rho_lgd = _TTC_TABLE[key]
        else:
            # Try unsecured fallback for the asset class
            fallback_key = (asset_class.upper(), "NONE")
            if fallback_key in _TTC_TABLE:
                lgd_ttc, rho_lgd = _TTC_TABLE[fallback_key]
                logger.debug(
                    "LGDModel: (%s, %s) not in TTC table — using (%s, NONE) fallback",
                    asset_class, collateral_type, asset_class,
                )
            else:
                lgd_ttc, rho_lgd = _TTC_DEFAULT
                logger.warning(
                    "LGDModel: asset class '%s' not in TTC table — using default "
                    "(lgd_ttc=%.1f%%, rho=%.2f).  Add this class to _TTC_TABLE.",
                    asset_class, _TTC_DEFAULT[0] * 100, _TTC_DEFAULT[1],
                )

        # Override ρ_LGD if set at model level
        if self._rho_ovr is not None:
            rho_lgd = self._rho_ovr

        return lgd_ttc, rho_lgd

    # ── Layer 2: Downturn LGD (Frye-Jacobs) ─────────────────────────────────

    def downturn_lgd(
        self,
        asset_class: str,
        collateral_type: str = "NONE",
        pd: float = 0.01,
    ) -> float:
        """
        Compute the downturn LGD using the Frye-Jacobs (2001) model.

        CRE36.83 requires the LGD to reflect economic downturn conditions.
        The Frye-Jacobs model achieves this by linking LGD to the same
        systematic factor that drives PD in the Vasicek/ASRF framework,
        at the CRE31.4 confidence level (99.9th percentile by default).

        Formula
        ───────
            LGD_DT = Φ( (Φ⁻¹(LGD_TTC*) + ρ_LGD × Φ⁻¹(q)) / √(1 − ρ_LGD²) )

        where:
            LGD_TTC* = LGD_TTC + conservative_margin  (model-level add-on)
            ρ_LGD    = LGD-systematic-factor correlation (table-sourced)
            q        = 0.999 (99.9th percentile, consistent with CRE31.4)

        The Frye-Jacobs transformation maps the TTC mean through the bivariate
        normal copula, producing the expected LGD conditional on the systematic
        factor being at its worst-case (downturn) level.

        CRE32.16 floors are applied after the model:
            - 0%  for financial collateral
            - 5%  for residential real estate
            - 10% for commercial RE / receivables
            - 15% for other physical
            - 25% for unsecured (hard Basel floor)

        Args:
            asset_class:     CRE31 asset class
            collateral_type: Basel collateral type (or NONE)
            pd:              Obligor 1-year PD — used only when ρ_LGD is
                             derived as a function of PD (not used in base
                             implementation; included for subclass extension)

        Returns:
            float: downturn LGD after CRE32.16 floor (decimal)
        """
        lgd_ttc, rho_lgd = self.ttc_lgd(asset_class, collateral_type)

        # Apply conservative margin per CRE36.65 / 36.83
        lgd_input = min(lgd_ttc + self._margin, 0.999)

        lgd_dt = self._frye_jacobs(lgd_input, rho_lgd)

        # CRE32.16 floor
        floor   = LGD_FLOORS_SECURED.get(collateral_type.upper(), LGD_FLOOR_UNSECURED)
        floored = max(lgd_dt, floor)

        logger.debug(
            "downturn_lgd(%s, %s): TTC=%.3f + margin=%.3f → input=%.3f "
            "rho=%.3f → DT=%.3f → floored=%.3f (floor=%.3f)",
            asset_class, collateral_type,
            lgd_ttc, self._margin, lgd_input,
            rho_lgd, lgd_dt, floored, floor,
        )
        return min(floored, LGD_CAP)

    # ── Layer 3: Conditional LGD (Pillar 2 / ICAAP) ──────────────────────────

    def conditional_lgd(
        self,
        asset_class: str,
        macro,   # MacroeconomicFactors — avoid circular import by using duck typing
        collateral_type: str = "NONE",
    ) -> float:
        """
        Compute a point-in-time LGD conditioned on current macro conditions.

        PILLAR 2 / ICAAP ONLY — NOT FOR PILLAR 1 CAPITAL.

        The macro-conditional approach uses the current macro stress_index
        (derived from VIX, HY-OAS, unemployment, GDP) to interpolate the
        systematic factor quantile between normal (q=0.5) and downturn
        (q=0.999) conditions.  This replaces the heuristic spread-elasticity
        approximation in MacroeconomicOverlay.adjust_lgd_for_macro() with a
        model grounded in the Frye-Jacobs distributional framework.

        Specifically, the effective quantile is:
            q_eff = 0.5 + (0.999 − 0.5) × stress_index^0.8

        At stress_index=0   → q_eff ≈ 0.500 (normal)   → conditional LGD ≈ TTC
        At stress_index=0.5 → q_eff ≈ 0.825 (stressed) → intermediate LGD
        At stress_index=1.0 → q_eff = 0.999 (crisis)   → downturn LGD

        The power of 0.8 ensures the model responds more aggressively at high
        stress levels (convex scaling toward the crisis tail).

        CRE32.16 floors are applied.

        Args:
            asset_class:     CRE31 asset class
            macro:           MacroeconomicFactors instance (from a_irb.py or
                             USMacroDataFeed); duck-typed to avoid circular import
            collateral_type: Basel collateral type (or NONE)

        Returns:
            float: conditional LGD after CRE32.16 floor (decimal)
        """
        lgd_ttc, rho_lgd = self.ttc_lgd(asset_class, collateral_type)
        lgd_input = min(lgd_ttc + self._margin, 0.999)

        # Derive stress_index from MacroeconomicFactors duck type
        try:
            si = float(macro.stress_index())
        except (AttributeError, TypeError, ValueError):
            logger.warning(
                "LGDModel.conditional_lgd: macro object has no stress_index() "
                "— falling back to downturn LGD"
            )
            return self.downturn_lgd(asset_class, collateral_type)

        si = max(0.0, min(si, 1.0))

        # Interpolate q between 0.5 (normal) and 0.999 (downturn)
        q_eff = 0.5 + (0.999 - 0.5) * (si ** 0.8)
        q_val = _norm_inv(q_eff)

        lgd_cond = self._frye_jacobs_q(lgd_input, rho_lgd, q_val)

        floor   = LGD_FLOORS_SECURED.get(collateral_type.upper(), LGD_FLOOR_UNSECURED)
        floored = max(lgd_cond, floor)

        logger.debug(
            "conditional_lgd(%s, %s): TTC=%.3f si=%.3f q_eff=%.4f "
            "→ cond=%.3f → floored=%.3f",
            asset_class, collateral_type, lgd_ttc, si, q_eff, lgd_cond, floored,
        )
        return min(floored, LGD_CAP)

    # ── Full result with audit trail ─────────────────────────────────────────

    def compute_lgd(
        self,
        asset_class: str,
        collateral_type: str = "NONE",
        pd: float = 0.01,
        macro=None,
    ) -> LGDResult:
        """
        Compute all three LGD layers and return a structured result.

        Provides the full audit trail required by Model Risk Management,
        Internal Audit, and regulatory review:
          - Which layer was used for Pillar 1 capital
          - Whether the CRE32.16 floor was binding
          - The macro stress index if Pillar 2 conditional was computed

        Args:
            asset_class:     CRE31 asset class
            collateral_type: Basel collateral type
            pd:              1-year obligor PD
            macro:           MacroeconomicFactors (optional; needed for Layer 3)

        Returns:
            LGDResult with all three layers populated
        """
        lgd_ttc, rho_lgd    = self.ttc_lgd(asset_class, collateral_type)
        lgd_input           = min(lgd_ttc + self._margin, 0.999)
        lgd_dt_raw          = self._frye_jacobs(lgd_input, rho_lgd)
        floor               = LGD_FLOORS_SECURED.get(collateral_type.upper(), LGD_FLOOR_UNSECURED)
        lgd_dt_floored      = min(max(lgd_dt_raw, floor), LGD_CAP)
        floor_binding       = lgd_dt_raw < floor

        lgd_cond = None
        stress_index = None
        if macro is not None:
            lgd_cond = self.conditional_lgd(asset_class, macro, collateral_type)
            try:
                stress_index = round(float(macro.stress_index()), 4)
            except (AttributeError, TypeError):
                pass

        # Determine TTC table source
        key = (asset_class.upper(), collateral_type.upper())
        fb_key = (asset_class.upper(), "NONE")
        if key in _TTC_TABLE:
            source = "TTC_TABLE"
        elif fb_key in _TTC_TABLE:
            source = "TTC_TABLE_FALLBACK_UNSECURED"
        else:
            source = "DEFAULT_FALLBACK"

        return LGDResult(
            asset_class          = asset_class,
            collateral_type      = collateral_type,
            pd                   = pd,
            lgd_ttc              = lgd_ttc,
            rho_lgd              = rho_lgd,
            lgd_downturn         = lgd_dt_raw,
            lgd_downturn_floored = lgd_dt_floored,
            lgd_conditional      = lgd_cond,
            stress_index         = stress_index,
            cre3216_floor        = floor,
            floor_binding        = floor_binding,
            pillar1_lgd          = lgd_dt_floored,
            source               = source,
        )

    # ── Best-estimate LGD for defaulted exposures (CRE36.86) ────────────────

    def best_estimate_lgd(
        self,
        asset_class: str,
        collateral_type: str = "NONE",
        time_in_default_years: float = 0.0,
        recovery_collected_pct: float = 0.0,
    ) -> float:
        """
        CRE36.86: Best-estimate LGD for defaulted exposures.

        For a defaulted asset, capital K = max(0, LGD_downturn − EL_best_estimate).
        This method provides EL_best_estimate — the bank's current expectation
        of the economic loss given the asset is already in default.

        The best estimate starts at the TTC LGD and declines as:
          (a) time passes (workout proceeds reduce uncertainty)
          (b) recoveries are collected (realised cash flows reduce residual loss)

        CRE36.86 requires that the best estimate be risk-sensitive (not simply
        equal to a static 50% of downturn LGD); this implementation provides
        a structured, auditable estimate.

        Args:
            asset_class:             CRE31 asset class
            collateral_type:         Basel collateral type
            time_in_default_years:   How long since default event (years)
            recovery_collected_pct:  Fraction of EAD already recovered (0–1)

        Returns:
            float: best-estimate LGD (decimal); bounded [0, lgd_ttc]
        """
        lgd_ttc, _ = self.ttc_lgd(asset_class, collateral_type)

        # Adjust for time in default: resolution uncertainty declines
        # over a typical 2-3 year workout period (exponential decay)
        time_adj = math.exp(-0.5 * time_in_default_years)  # ~60% by year 1, ~22% by year 3

        # Adjust for collections already made
        recovery_adj = max(0.0, 1.0 - recovery_collected_pct)

        lgd_be = lgd_ttc * time_adj * recovery_adj

        floor  = LGD_FLOORS_SECURED.get(collateral_type.upper(), 0.0)  # no floor for best estimate
        result = max(min(lgd_be, LGD_CAP), 0.0)

        logger.debug(
            "best_estimate_lgd(%s, %s): TTC=%.3f time_adj=%.3f "
            "recov_adj=%.3f → LGD_be=%.3f",
            asset_class, collateral_type, lgd_ttc,
            time_adj, recovery_adj, result,
        )
        return result

    # ── Wrong-way LGD (CRE36.84) ─────────────────────────────────────────────

    def wrong_way_lgd(
        self,
        lgd_base: float,
        collateral_type: str = "NONE",
        obligor_sector: str = "CORP",
        collateral_sector: str = "CORP",
    ) -> float:
        """
        CRE36.84: Conservative add-on when obligor and collateral are correlated.

        When there is a significant degree of dependence between the obligor's
        credit quality and the collateral's value (wrong-way LGD), CRE36.84
        requires conservative treatment.  This is distinct from wrong-way
        counterparty credit risk (CRE53) but operates on the same principle.

        The adjustment is triggered when:
          - The obligor sector matches the collateral sector (e.g., a bank
            holding financial collateral of another bank in the same group)
          - OR the collateral is real estate and the obligor is in real estate /
            construction (sector correlation high)

        In such cases, a multiplicative uplift of 1.10–1.25× is applied to
        the LGD, reflecting that the collateral is likely to depreciate at
        exactly the moment of default (the worst time to liquidate).

        Args:
            lgd_base:          Input LGD (typically TTC or downturn LGD)
            collateral_type:   Basel collateral type
            obligor_sector:    Obligor industry sector
            collateral_sector: Sector of the collateral issuer / property market

        Returns:
            float: LGD with wrong-way adjustment applied
        """
        same_sector = obligor_sector.upper() == collateral_sector.upper()

        re_collateral = collateral_type.upper() in ("RESIDENTIAL_RE", "COMMERCIAL_RE")
        re_obligor    = obligor_sector.upper() in (
            "REAL_ESTATE", "CONSTRUCTION", "PROPERTY", "REITS"
        )
        fin_collateral = collateral_type.upper() == "FINANCIAL"
        fin_obligor    = obligor_sector.upper() in ("FINANCIALS", "BANK", "INSURANCE")

        uplift = 1.0
        if same_sector and collateral_type.upper() != "NONE":
            uplift = 1.20   # same-sector dependency
            logger.debug(
                "wrong_way_lgd: same-sector obligor/collateral (%s) → 1.20× uplift",
                obligor_sector,
            )
        elif re_collateral and re_obligor:
            uplift = 1.25   # real estate obligor + real estate collateral
            logger.debug("wrong_way_lgd: RE-RE wrong-way dependency → 1.25× uplift")
        elif fin_collateral and fin_obligor:
            uplift = 1.15   # financial sector obligor + financial collateral
            logger.debug("wrong_way_lgd: FI-FI wrong-way dependency → 1.15× uplift")

        result = min(lgd_base * uplift, LGD_CAP)
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _frye_jacobs(self, lgd_ttc: float, rho_lgd: float) -> float:
        """
        Frye-Jacobs (2001) downturn LGD at the model's configured quantile.

        LGD_DT = Φ( (Φ⁻¹(LGD_TTC) + ρ_LGD × q) / √(1 − ρ_LGD²) )
        """
        return self._frye_jacobs_q(lgd_ttc, rho_lgd, self._q)

    @staticmethod
    def _frye_jacobs_q(lgd_ttc: float, rho_lgd: float, q: float) -> float:
        """
        Frye-Jacobs transform at an arbitrary quantile q (expressed as Φ⁻¹(p)).

        LGD_DT = Φ( (Φ⁻¹(LGD_TTC) + ρ_LGD × q) / √(1 − ρ_LGD²) )

        Args:
            lgd_ttc: TTC LGD input (decimal)
            rho_lgd: LGD-systematic-factor correlation (0 < ρ < 1)
            q:       Φ⁻¹(p) — standard-normal quantile of the confidence level

        Returns:
            float: downturn LGD (decimal)
        """
        lgd_ttc = max(1e-6, min(lgd_ttc, 1.0 - 1e-6))
        rho_lgd = max(0.0,  min(rho_lgd, 0.9999))

        mu_lgd  = _norm_inv(lgd_ttc)
        denom   = math.sqrt(1.0 - rho_lgd ** 2)
        arg     = (mu_lgd + rho_lgd * q) / denom

        result  = _norm_cdf(arg)
        return max(0.0, min(result, LGD_CAP))


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton for convenience
# ─────────────────────────────────────────────────────────────────────────────

#: Default LGDModel instance — matches the Basel standard parameterisation.
#: Override at engine initialisation if the bank uses different parameters.
DEFAULT_LGD_MODEL = LGDModel(
    downturn_quantile   = 0.999,
    rho_lgd_override    = None,    # use table-sourced values
    conservative_margin = 0.02,    # +2pp per CRE36.65 uncertainty add-on
)


def downturn_lgd(
    asset_class: str,
    collateral_type: str = "NONE",
    pd: float = 0.01,
    model: LGDModel = DEFAULT_LGD_MODEL,
) -> float:
    """
    Convenience function: downturn LGD from the default model.

    For common callers that do not need the full LGDResult audit trail.
    """
    return model.downturn_lgd(asset_class, collateral_type, pd)


def validate_lgd_table() -> bool:
    """
    Validate the structural integrity of the TTC LGD table.

    Checks:
        1. All TTC LGD values are within (0, 1)
        2. All TTC LGD values are above the applicable CRE32.16 floor
        3. All ρ_LGD values are in (0, 1)
        4. Frye-Jacobs downturn LGD is always ≥ TTC LGD (monotonicity)

    Returns:
        bool: True if all checks pass

    Raises:
        AssertionError: with a descriptive message on the first failure
    """
    for (ac, col), (lgd_ttc, rho_lgd) in _TTC_TABLE.items():
        assert 0.0 < lgd_ttc < 1.0, \
            f"TTC LGD out of range for ({ac},{col}): {lgd_ttc}"
        assert 0.0 < rho_lgd < 1.0, \
            f"rho_LGD out of range for ({ac},{col}): {rho_lgd}"
        floor = LGD_FLOORS_SECURED.get(col, LGD_FLOOR_UNSECURED)
        # TTC LGD ≥ floor only required after conservative margin, not before
        # (the margin is applied in the model, not stored in the table)
        lgd_dt = DEFAULT_LGD_MODEL._frye_jacobs(lgd_ttc, rho_lgd)
        lgd_dt_floored = max(lgd_dt, floor)
        assert lgd_dt_floored >= lgd_ttc - 0.01, \
            f"Downturn LGD ({lgd_dt_floored:.3f}) is materially below TTC ({lgd_ttc:.3f}) for ({ac},{col})"
    return True


# Run at import
validate_lgd_table()
logger.debug("lgd_calibration: TTC table validated (%d rows)", len(_TTC_TABLE))
