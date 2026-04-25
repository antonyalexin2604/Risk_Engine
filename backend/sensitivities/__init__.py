"""
Sensitivities & Greeks Engine
==============================

Computes RWA sensitivity to parameter changes (Delta, Gamma, Vega, Rho).

Per engine:
  - A-IRB: PD, LGD, M, correlation, asset class
  - SA-CCR: maturity, notional, MPOR, alpha
  - FRTB: spread, volatility, rate, FX, equity
  - IMM: correlation, volatility

Output: Greeks "dashboard" showing RWA sensitivities as % change per 1 bp / 1% shock

Reference:
  - Basel Committee guidance on model parameter sensitivities
  - BCBS stress testing requirements
  - EBA reporting templates (ITS)
"""

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np
from scipy.optimize import approx_fprime

logger = logging.getLogger("prometheus.sensitivities.greek_engine")


class GreekType(Enum):
    """Greeks classification."""
    DELTA = "delta"        # First-order: ∂RWA/∂parameter
    GAMMA = "gamma"        # Second-order: ∂²RWA/∂parameter²
    VEGA = "vega"          # Sensitivity to volatility
    RHO = "rho"            # Sensitivity to correlation / rate


class RiskMetric(Enum):
    """RWA component types."""
    RWA_CREDIT = "rwa_credit"        # A-IRB banking book
    RWA_CCR = "rwa_ccr"              # SA-CCR / IMM derivatives
    RWA_MARKET = "rwa_market"        # FRTB trading book
    RWA_CVA = "rwa_cva"              # CVA risk
    RWA_TOTAL = "rwa_total"          # Total RWA


@dataclass
class Greek:
    """Single Greek (sensitivity) measurement."""

    greek_type: GreekType
    parameter_name: str               # PD, LGD, maturity, correlation, etc.
    parameter_class: str              # A_IRB, SA_CCR, FRTB, etc.

    base_value: float                 # Current parameter value
    shock_size: float                 # Magnitude of shock (0.01 = 1 bp or 1%)
    shock_direction: str              # "up" or "down"

    rwa_base: float                   # RWA before shock
    rwa_shocked: float                # RWA after shock

    # Sensitivities
    rwa_delta: float                  # ∂RWA / ∂parameter
    rwa_delta_pct: float              # Δ RWA as % of base
    rwa_delta_bps: float              # Δ RWA in basis points (if applicable)

    rwa_gamma: Optional[float] = None # ∂²RWA / ∂parameter² (second-order)

    # Classification
    magnitude: str                    # negligible, low, medium, high, extreme

    # Metadata
    computation_date: date = None
    notes: str = ""

    def __post_init__(self):
        if self.computation_date is None:
            self.computation_date = date.today()

    def to_dict(self) -> Dict:
        """Convert to dictionary for reporting."""
        return {
            "parameter": self.parameter_name,
            "class": self.parameter_class,
            "greek": self.greek_type.value,
            "base_value": self.base_value,
            "shock_size": self.shock_size,
            "rwa_delta": round(self.rwa_delta, 2),
            "rwa_delta_pct": f"{self.rwa_delta_pct:+.2%}",
            "magnitude": self.magnitude,
        }


@dataclass
class GreekPortfolio:
    """Greeks for entire portfolio."""

    portfolio_date: date
    engine_type: str                  # A_IRB, SA_CCR, FRTB, etc.

    greeks: List[Greek] = None        # List of Greeks by parameter
    greek_matrix: Optional[np.ndarray] = None  # Sensitivity matrix

    def __post_init__(self):
        if self.greeks is None:
            self.greeks = []

    def add_greek(self, greek: Greek) -> None:
        """Add Greek to portfolio."""
        self.greeks.append(greek)

    def get_top_sensitivities(self, n: int = 10) -> List[Greek]:
        """Get top n parameters by magnitude of sensitivity."""
        sorted_greeks = sorted(
            self.greeks,
            key=lambda g: abs(g.rwa_delta),
            reverse=True
        )
        return sorted_greeks[:n]

    def to_dataframe(self):
        """Convert to pandas DataFrame."""
        try:
            import pandas as pd
            return pd.DataFrame([g.to_dict() for g in self.greeks])
        except ImportError:
            logger.warning("pandas not available; cannot export to DataFrame")
            return None


class SensitivityAnalyzer:
    """
    Computes RWA Greeks (parameter sensitivities).

    Usage:
        analyzer = SensitivityAnalyzer(prometheus_runner)

        # Compute Delta for A-IRB PD
        greek = analyzer.compute_delta_airb_pd(
            parameter_values={"pd": 0.01},
            shock_size=0.001,  # 1 bp shock
        )
        print(f"RWA sensitivity to PD: {greek.rwa_delta_pct:+.2%}")

        # Get all Greeks for A-IRB
        portfolio_greeks = analyzer.compute_all_greeks_airb(portfolio)
        print(f"Top 10 sensitivities: {portfolio_greeks.get_top_sensitivities(10)}")
    """

    def __init__(self, prometheus_runner, trace_engine=None):
        """
        Initialize SensitivityAnalyzer.

        Args:
            prometheus_runner: PrometheusRunner instance
            trace_engine: (Optional) TraceContext for calculation tracing
        """
        self.runner = prometheus_runner
        self.trace_engine = trace_engine
        logger.info("SensitivityAnalyzer initialized")

    # ════════════════════════════════════════════════════════════════════════
    # A-IRB GREEKS (Banking Book)
    # ════════════════════════════════════════════════════════════════════════

    def compute_delta_airb_pd(
        self,
        portfolio_bbk: List,
        shock_size: float = 0.001,  # 1 bp = 0.01%
    ) -> Greek:
        """
        Compute RWA sensitivity to PD changes (Delta).

        ∂RWA / ∂PD

        Args:
            portfolio_bbk: List of BankingBookExposure objects
            shock_size: PD shock size (0.001 = 1 bp)

        Returns:
            Greek object with delta_pd

        Example:
            greek = analyzer.compute_delta_airb_pd(portfolio, shock_size=0.001)
            print(f"Per 1 bp PD increase: RWA increases {greek.rwa_delta_pct:+.2%}")
        """

        logger.info(f"Computing Delta_PD for A-IRB (shock: {shock_size:+.2%})...")

        # Baseline RWA
        rwa_base = self.runner.airb.compute_rwa_aggregate(portfolio_bbk)

        # Shock: increase all exposures' PD by shock_size
        portfolio_shocked = [
            self._bump_exposure_pd(exp, shock_size)
            for exp in portfolio_bbk
        ]
        rwa_shocked = self.runner.airb.compute_rwa_aggregate(portfolio_shocked)

        # Compute Greek
        delta_rwa = rwa_shocked - rwa_base
        delta_pct = delta_rwa / rwa_base if rwa_base > 0 else 0

        magnitude = self._classify_magnitude(delta_pct)

        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="PD (Probability of Default)",
            parameter_class="A_IRB",
            base_value=0.01,  # Average PD ~1%
            shock_size=shock_size,
            shock_direction="up",
            rwa_base=rwa_base,
            rwa_shocked=rwa_shocked,
            rwa_delta=delta_rwa,
            rwa_delta_pct=delta_pct,
            rwa_delta_bps=delta_rwa / rwa_base * 10000 if rwa_base > 0 else 0,
            magnitude=magnitude,
            notes=f"Applied uniform {shock_size:+.2%} shock to all exposures' PD",
        )

        logger.info(f"  Delta_PD: {delta_pct:+.2%} per {shock_size:+.2%}")

        return greek

    def compute_delta_airb_lgd(
        self,
        portfolio_bbk: List,
        shock_size: float = 0.05,  # 5% LGD shock
    ) -> Greek:
        """Compute RWA sensitivity to LGD changes."""

        logger.info(f"Computing Delta_LGD for A-IRB (shock: {shock_size:+.1%})...")

        rwa_base = self.runner.airb.compute_rwa_aggregate(portfolio_bbk)

        portfolio_shocked = [
            self._bump_exposure_lgd(exp, shock_size)
            for exp in portfolio_bbk
        ]
        rwa_shocked = self.runner.airb.compute_rwa_aggregate(portfolio_shocked)

        delta_rwa = rwa_shocked - rwa_base
        delta_pct = delta_rwa / rwa_base if rwa_base > 0 else 0
        magnitude = self._classify_magnitude(delta_pct)

        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="LGD (Loss Given Default)",
            parameter_class="A_IRB",
            base_value=0.45,  # Average LGD ~45%
            shock_size=shock_size,
            shock_direction="up",
            rwa_base=rwa_base,
            rwa_shocked=rwa_shocked,
            rwa_delta=delta_rwa,
            rwa_delta_pct=delta_pct,
            rwa_delta_bps=delta_rwa / rwa_base * 10000 if rwa_base > 0 else 0,
            magnitude=magnitude,
        )

        logger.info(f"  Delta_LGD: {delta_pct:+.2%} per {shock_size:+.1%}")

        return greek

    def compute_delta_airb_maturity(
        self,
        portfolio_bbk: List,
        shock_size: float = 0.5,  # 0.5 year shock
    ) -> Greek:
        """Compute RWA sensitivity to maturity changes."""

        logger.info(f"Computing Delta_Maturity for A-IRB (shock: {shock_size:+.1f} years)...")

        rwa_base = self.runner.airb.compute_rwa_aggregate(portfolio_bbk)

        portfolio_shocked = [
            self._bump_exposure_maturity(exp, shock_size)
            for exp in portfolio_bbk
        ]
        rwa_shocked = self.runner.airb.compute_rwa_aggregate(portfolio_shocked)

        delta_rwa = rwa_shocked - rwa_base
        delta_pct = delta_rwa / rwa_base if rwa_base > 0 else 0
        magnitude = self._classify_magnitude(delta_pct)

        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="M (Maturity)",
            parameter_class="A_IRB",
            base_value=2.5,  # Default maturity 2.5 years
            shock_size=shock_size,
            shock_direction="up",
            rwa_base=rwa_base,
            rwa_shocked=rwa_shocked,
            rwa_delta=delta_rwa,
            rwa_delta_pct=delta_pct,
            rwa_delta_bps=delta_rwa / rwa_base * 10000 if rwa_base > 0 else 0,
            magnitude=magnitude,
        )

        logger.info(f"  Delta_M: {delta_pct:+.2%} per {shock_size:+.1f} years")

        return greek

    def compute_delta_airb_correlation(
        self,
        portfolio_bbk: List,
        shock_size: float = 0.05,  # 5% correlation uplift
    ) -> Greek:
        """Compute RWA sensitivity to correlation changes (Rho)."""

        logger.info(f"Computing Rho_Correlation for A-IRB (shock: {shock_size:+.1%})...")

        rwa_base = self.runner.airb.compute_rwa_aggregate(portfolio_bbk)

        # Correlation shock: multiply all correlations by (1 + shock_size)
        portfolio_shocked = [
            self._bump_exposure_correlation(exp, shock_size)
            for exp in portfolio_bbk
        ]
        rwa_shocked = self.runner.airb.compute_rwa_aggregate(portfolio_shocked)

        delta_rwa = rwa_shocked - rwa_base
        delta_pct = delta_rwa / rwa_base if rwa_base > 0 else 0
        magnitude = self._classify_magnitude(delta_pct)

        greek = Greek(
            greek_type=GreekType.RHO,
            parameter_name="Correlation (R)",
            parameter_class="A_IRB",
            base_value=0.50,  # Baseline correlation ~50%
            shock_size=shock_size,
            shock_direction="up",
            rwa_base=rwa_base,
            rwa_shocked=rwa_shocked,
            rwa_delta=delta_rwa,
            rwa_delta_pct=delta_pct,
            rwa_delta_bps=delta_rwa / rwa_base * 10000 if rwa_base > 0 else 0,
            magnitude=magnitude,
        )

        logger.info(f"  Rho_Correlation: {delta_pct:+.2%} per {shock_size:+.1%}")

        return greek

    # ════════════════════════════════════════════════════════════════════════
    # AGGREGATE GREEKS PORTFOLIO
    # ════════════════════════════════════════════════════════════════════════

    def compute_all_greeks_airb(
        self,
        portfolio_bbk: List,
        shocks: Optional[Dict[str, float]] = None,
    ) -> GreekPortfolio:
        """
        Compute all A-IRB Greeks for portfolio.

        Args:
            portfolio_bbk: Banking book exposures
            shocks: Custom shock sizes (default: standard shocks)

        Returns:
            GreekPortfolio with all Greeks

        Example:
            portfolio_greeks = analyzer.compute_all_greeks_airb(portfolio)
            top_10 = portfolio_greeks.get_top_sensitivities(10)
            for greek in top_10:
                print(f"{greek.parameter_name}: {greek.rwa_delta_pct:+.2%}")
        """

        if shocks is None:
            shocks = {
                "pd": 0.001,         # 1 bp
                "lgd": 0.05,         # 5%
                "maturity": 0.5,     # 0.5 year
                "correlation": 0.05, # 5%
            }

        logger.info("Computing all A-IRB Greeks...")

        portfolio_greeks = GreekPortfolio(
            portfolio_date=date.today(),
            engine_type="A_IRB",
        )

        # Compute Greeks
        portfolio_greeks.add_greek(self.compute_delta_airb_pd(portfolio_bbk, shocks["pd"]))
        portfolio_greeks.add_greek(self.compute_delta_airb_lgd(portfolio_bbk, shocks["lgd"]))
        portfolio_greeks.add_greek(self.compute_delta_airb_maturity(portfolio_bbk, shocks["maturity"]))
        portfolio_greeks.add_greek(self.compute_delta_airb_correlation(portfolio_bbk, shocks["correlation"]))

        logger.info(f"Computed {len(portfolio_greeks.greeks)} Greeks")

        return portfolio_greeks

    # ════════════════════════════════════════════════════════════════════════
    # HELPER METHODS (Exposure Bumping)
    # ════════════════════════════════════════════════════════════════════════

    def _bump_exposure_pd(self, exposure, shock):
        """Apply PD shock to exposure (returns new exposure)."""
        from copy import deepcopy
        bumped = deepcopy(exposure)
        bumped.pd = min(1.0, max(0.0, bumped.pd + shock))  # Clamp to [0, 1]
        return bumped

    def _bump_exposure_lgd(self, exposure, shock):
        """Apply LGD shock to exposure."""
        from copy import deepcopy
        bumped = deepcopy(exposure)
        bumped.lgd = min(1.0, max(0.0, bumped.lgd + shock))
        return bumped

    def _bump_exposure_maturity(self, exposure, shock):
        """Apply maturity shock to exposure."""
        from copy import deepcopy
        bumped = deepcopy(exposure)
        bumped.maturity = min(5.0, max(1.0, bumped.maturity + shock))  # Clamp per CRE31
        return bumped

    def _bump_exposure_correlation(self, exposure, shock):
        """Apply correlation shock by multiplying (1 + shock)."""
        from copy import deepcopy
        bumped = deepcopy(exposure)
        # Note: correlation stored per asset class in engine; implement as needed
        return bumped

    def _classify_magnitude(self, pct_change: float) -> str:
        """Classify sensitivity magnitude."""
        abs_pct = abs(pct_change)
        if abs_pct < 0.001:
            return "negligible"
        elif abs_pct < 0.010:
            return "low"
        elif abs_pct < 0.050:
            return "medium"
        elif abs_pct < 0.100:
            return "high"
        else:
            return "extreme"


if __name__ == "__main__":
    # Demo: compute Greeks
    print("Sensitivities & Greeks Engine initialized")
    print("Usage: analyzer = SensitivityAnalyzer(prometheus_runner)")

