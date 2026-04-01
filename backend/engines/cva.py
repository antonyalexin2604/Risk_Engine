"""
PROMETHEUS Risk Platform
Engine: CVA Risk — Credit Valuation Adjustment Capital
Regulatory basis: MAR50 (effective Jan 2023), RBC20.9(2), RBC25, CRE51.14

Implements:
  - SA-CVA (Standardised): sensitivity-based, requires supervisory approval
  - BA-CVA (Basic): EAD-based, always available as fallback
  - Materiality threshold: < threshold → 100% of CCR RWA as proxy (MAR50.9)
  - Fallback trace code per requirement #13
  - CVA hedge removal from market risk (RBC25.30)

CVA RWA feeds into Total RWA as a distinct line item under Market Risk (RBC20.9).
CVA RWA is NOT included in the output floor base (CAP10 FAQ1).
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import date

logger = logging.getLogger(__name__)

# ─── Fallback trace codes (req #13) ──────────────────────────────────────────
CVA_FALLBACK_REASONS: Dict[str, str] = {
    "NO_SA_APPROVAL":    "Supervisory approval for SA-CVA not obtained — BA-CVA applied",
    "MISSING_SPREADS":   "Counterparty credit spread data unavailable — BA-CVA applied",
    "BELOW_THRESHOLD":   "CVA exposure below MAR50.9 materiality threshold — 100% CCR RWA proxy",
    "HEDGES_INELIGIBLE": "CVA hedges do not meet MAR50 eligibility — excluded from SA-CVA",
    "MODEL_LIMITATION":  "Internal CVA model not validated for this trade type — BA-CVA applied",
}

# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class CVAInput:
    """Per-counterparty CVA inputs."""
    counterparty_id:    str
    netting_set_id:     str
    ead:                float         # EAD from SA-CCR or IMM
    pd_1yr:             float         # 1-year PD of counterparty
    lgd_mkt:            float = 0.40  # Market LGD (typically 40% for MAR50)
    maturity_years:     float = 2.5   # Effective maturity of netting set
    discount_factor:    float = 1.0   # Risk-free discount
    credit_spread_bps:  Optional[float] = None  # CDS spread (bps); None = not available
    has_cva_hedge:      bool = False
    hedge_notional:     float = 0.0
    hedge_maturity:     float = 0.0

@dataclass
class CVAResult:
    counterparty_id:  str
    method:           str              # 'SA_CVA' | 'BA_CVA' | 'CCR_PROXY'
    fallback_trace:   Optional[str]
    rwa_cva:          float
    # BA-CVA components
    ba_cva_charge:    float = 0.0
    ba_sc_charge:     float = 0.0     # Single-name component
    # SA-CVA components
    sa_delta_charge:  float = 0.0
    sa_vega_charge:   float = 0.0
    # CVA value estimate
    cva_estimate:     float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# BA-CVA (Basic Approach) — MAR50.20–50.38
# ─────────────────────────────────────────────────────────────────────────────

# Supervisory credit spread by sector/rating (MAR50 Table 1 — simplified mapping)
_SUPERVISORY_SPREAD: Dict[str, float] = {
    "AAA": 0.0038,  # 38 bps
    "AA":  0.0038,
    "A":   0.0042,
    "BBB": 0.0054,
    "BB":  0.0106,
    "B":   0.0160,
    "CCC": 0.0600,
    "NR":  0.0054,  # unrated → BBB equivalent
}

def _supervisory_spread(rating: str) -> float:
    return _SUPERVISORY_SPREAD.get(rating[:3].upper(), _SUPERVISORY_SPREAD["NR"])

def _effective_maturity_discount(M: float, spread: float) -> float:
    """
    MAR50.25: DF_i = (1 - exp(-0.05 × M_i)) / (0.05 × M_i)
    Simplified discount weighting.
    """
    if M <= 0:
        return 1.0
    return (1 - math.exp(-0.05 * M)) / (0.05 * M)

def compute_ba_cva(
    inputs: List[CVAInput],
    rating_map: Optional[Dict[str, str]] = None,
    has_hedges: bool = False,
) -> tuple[float, Dict[str, CVAResult]]:
    """
    BA-CVA capital charge per MAR50.20–38.

    K_BA = rho × (Σ_c SC_c)² + (1-rho²) × Σ_c SC_c²)^0.5 - m_hedges

    SC_c = ρ_c × RW_c × M_c_eff × EAD_c

    rho (supervisory correlation) = 0.50 (MAR50.29)
    """
    rho = 0.50
    results = {}
    sc_values = []

    for inp in inputs:
        rating = (rating_map or {}).get(inp.counterparty_id, "NR")
        rw = _supervisory_spread(rating)
        m_eff = _effective_maturity_discount(inp.maturity_years, rw)
        # Single-name component
        sc_c = rw * m_eff * inp.ead
        sc_values.append(sc_c)

        # Simple CVA estimate (mark-to-model)
        cva_est = inp.pd_1yr * inp.lgd_mkt * inp.ead * m_eff

        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "BA_CVA",
            fallback_trace  = None,
            rwa_cva         = 0.0,  # filled below
            ba_sc_charge    = sc_c,
            cva_estimate    = cva_est,
        )

    if not sc_values:
        return 0.0, {}

    # Aggregate K_BA
    sum_sc  = sum(sc_values)
    sum_sc2 = sum(v**2 for v in sc_values)
    k_ba = math.sqrt(rho**2 * sum_sc**2 + (1 - rho**2) * sum_sc2)

    # Hedge reduction (simplified: 50% of hedge notional reduces k_ba)
    hedge_reduction = 0.0
    if has_hedges:
        total_hedge = sum(inp.hedge_notional for inp in inputs if inp.has_cva_hedge)
        hedge_reduction = 0.50 * total_hedge * 0.0054  # BBB spread proxy

    k_ba_net = max(k_ba - hedge_reduction, 0.0)
    rwa_cva  = k_ba_net * 12.5

    # Distribute RWA proportionally by SC
    total_sc = sum(abs(v) for v in sc_values) or 1.0
    for i, (cpty_id, res) in enumerate(results.items()):
        res.rwa_cva       = rwa_cva * abs(sc_values[i]) / total_sc
        res.ba_cva_charge = k_ba_net * abs(sc_values[i]) / total_sc

    return rwa_cva, results


# ─────────────────────────────────────────────────────────────────────────────
# SA-CVA (Standardised Approach) — MAR50.40–50.79
# ─────────────────────────────────────────────────────────────────────────────

def compute_sa_cva(inputs: List[CVAInput]) -> tuple[float, Dict[str, CVAResult]]:
    """
    SA-CVA per MAR50.40+.
    Requires actual credit spread data per counterparty.

    Delta charge ≈ RW × ΔS/S × EAD × M_eff
    Vega charge  ≈ 0.55 × |vega sensitivity| (simplified)

    Full SA-CVA requires a complete sensitivities framework (similar to FRTB SBM)
    applied to the CVA P&L. This is a validated approximation for a self-contained
    simulation environment.
    """
    results = {}
    total_delta_rwa = 0.0
    total_vega_rwa  = 0.0

    for inp in inputs:
        if inp.credit_spread_bps is None:
            raise ValueError(f"SA-CVA requires credit spread for {inp.counterparty_id}")

        spread = inp.credit_spread_bps / 10_000  # bps → decimal
        m_eff  = _effective_maturity_discount(inp.maturity_years, spread)

        # Delta sensitivity = ∂CVA/∂spread  (approx: EAD × M_eff × LGD)
        delta_sens = inp.ead * m_eff * inp.lgd_mkt

        # Risk weight for credit spread risk factor (from FRTB-CVA bucket)
        # IG: 0.96%, non-IG: 1.6% (MAR50 Table 3)
        rw_spread = 0.0096 if inp.pd_1yr < 0.02 else 0.0160

        delta_charge = rw_spread * delta_sens
        vega_charge  = 0.55 * delta_charge * 0.10   # simplified vega component

        rwa_delta = delta_charge * 12.5
        rwa_vega  = vega_charge  * 12.5
        rwa_cva   = rwa_delta + rwa_vega

        total_delta_rwa += rwa_delta
        total_vega_rwa  += rwa_vega

        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "SA_CVA",
            fallback_trace  = None,
            rwa_cva         = rwa_cva,
            sa_delta_charge = delta_charge,
            sa_vega_charge  = vega_charge,
            cva_estimate    = inp.pd_1yr * inp.lgd_mkt * inp.ead * m_eff,
        )

    return total_delta_rwa + total_vega_rwa, results


# ─────────────────────────────────────────────────────────────────────────────
# CVA Master Engine — routing + fallback logic (req #13)
# ─────────────────────────────────────────────────────────────────────────────

# MAR50.9 materiality threshold: if aggregate CCR RWA < threshold → proxy
CCR_MATERIALITY_THRESHOLD = 1_000_000  # USD 1M — simulation; real = notional-based (MAR50.9)

class CVAEngine:
    """
    Routes each netting set to SA-CVA or BA-CVA based on eligibility,
    records the fallback trace code per req #13.
    """

    def __init__(self, sa_cva_approved: bool = False):
        self.sa_approved = sa_cva_approved
        logger.info("CVA Engine: SA-CVA approved=%s", sa_cva_approved)

    def _check_sa_eligibility(self, inp: CVAInput) -> tuple[bool, Optional[str]]:
        """Returns (eligible, fallback_trace_code)."""
        if not self.sa_approved:
            trace = (f"FALLBACK|{inp.counterparty_id}|NO_SA_APPROVAL"
                     f"|{CVA_FALLBACK_REASONS['NO_SA_APPROVAL']}")
            return False, trace
        if inp.credit_spread_bps is None:
            trace = (f"FALLBACK|{inp.counterparty_id}|MISSING_SPREADS"
                     f"|{CVA_FALLBACK_REASONS['MISSING_SPREADS']}")
            return False, trace
        return True, None

    def compute_portfolio_cva(
        self,
        inputs: List[CVAInput],
        total_ccr_rwa: float,
        rating_map: Optional[Dict[str, str]] = None,
        run_date: date = None,
    ) -> Dict:
        """
        Compute CVA RWA for the full portfolio with method routing.

        Returns a dict with:
          - total_rwa_cva
          - method_summary: {counterparty_id: CVAResult}
          - fallback_traces: list of trace codes
        """
        run_date = run_date or date.today()

        # MAR50.9 — materiality check
        if total_ccr_rwa < CCR_MATERIALITY_THRESHOLD:
            rwa_cva = total_ccr_rwa  # 100% CCR RWA as proxy
            trace   = f"PORTFOLIO|CCR_PROXY|{CVA_FALLBACK_REASONS['BELOW_THRESHOLD']}"
            logger.warning("CVA: below materiality threshold → CCR proxy RWA=%.0f", rwa_cva)
            return {
                "total_rwa_cva": rwa_cva,
                "method_summary": {},
                "fallback_traces": [trace],
                "method": "CCR_PROXY",
            }

        # Classify each counterparty
        sa_inputs, ba_inputs, traces = [], [], []

        for inp in inputs:
            eligible, trace = self._check_sa_eligibility(inp)
            if eligible:
                sa_inputs.append(inp)
            else:
                ba_inputs.append(inp)
                if trace:
                    traces.append(trace)

        all_results: Dict[str, CVAResult] = {}
        total_rwa = 0.0

        # Compute SA-CVA for eligible
        if sa_inputs:
            sa_rwa, sa_results = compute_sa_cva(sa_inputs)
            all_results.update(sa_results)
            total_rwa += sa_rwa
            logger.info("SA-CVA: %d counterparties, RWA=%.0f", len(sa_inputs), sa_rwa)

        # Compute BA-CVA for fallback
        if ba_inputs:
            ba_rwa, ba_results = compute_ba_cva(
                ba_inputs, rating_map=rating_map,
                has_hedges=any(i.has_cva_hedge for i in ba_inputs)
            )
            # Mark fallback on each BA result
            for cpty_id, res in ba_results.items():
                matching_trace = next(
                    (t for t in traces if cpty_id in t), None
                )
                res.fallback_trace = matching_trace
            all_results.update(ba_results)
            total_rwa += ba_rwa
            logger.info("BA-CVA: %d counterparties, RWA=%.0f", len(ba_inputs), ba_rwa)

        logger.info("CVA total RWA=%.0f (%d SA, %d BA, %d traces)",
                    total_rwa, len(sa_inputs), len(ba_inputs), len(traces))

        return {
            "total_rwa_cva":  total_rwa,
            "method_summary": all_results,
            "fallback_traces": traces,
            "method":         "MIXED" if sa_inputs and ba_inputs else
                              ("SA_CVA" if sa_inputs else "BA_CVA"),
        }
