"""
Scenario Analysis Engine
========================

Applies regulatory scenarios to portfolios and computes RWA under stress.

Workflow:
  1. Select scenario (historical crisis, regulatory adverse, custom)
  2. Build market parameters for scenario
  3. Reprice portfolio exposures under scenario market parameters
  4. Re-compute RWA (SA-CCR, A-IRB, FRTB, CVA) under scenario
  5. Compare to baseline RWA
  6. Report scenario RWA, capital charges, divergence metrics
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

from backend.scenarios.library import (
    Scenario,
    ScenarioType,
    get_regulatory_scenario,
    get_all_scenarios,
    MarketParameters,
)

logger = logging.getLogger("prometheus.scenarios.engine")


@dataclass
class ScenarioRun:
    """Results of applying a scenario to a portfolio."""

    scenario: Scenario
    run_date: date

    # Portfolio metrics
    portfolio_size: int              # Number of exposures

    # RWA by component
    rwa_baseline: float              # Baseline (no-stress) RWA
    rwa_credit: float                # A-IRB credit RWA under scenario
    rwa_ccr: float                   # SA-CCR / IMM RWA under scenario
    rwa_market: float                # FRTB market RWA under scenario
    rwa_cva: float                   # CVA RWA under scenario
    rwa_ccp: float                   # CCP RWA under scenario
    rwa_total: float                 # Total RWA under scenario

    # Metrics
    rwa_increase_pct: float          # (RWA_scenario - RWA_baseline) / RWA_baseline
    rwa_increase_abs: float          # RWA_scenario - RWA_baseline

    # Component-level impacts
    credit_rwa_increase_pct: float
    ccr_rwa_increase_pct: float
    market_rwa_increase_pct: float
    cva_rwa_increase_pct: float

    # Capital charges
    capital_baseline: float          # Tier-1 capital requirement (baseline)
    capital_scenario: float          # Tier-1 capital requirement (scenario)
    capital_increase: float          # Additional capital needed

    # Stress indicators
    max_single_exposure_rwa: float   # Largest exposure RWA in scenario
    concentration_change_hhi: float  # Change in Herfindahl index

    # Key drivers (analysis)
    key_drivers: Dict[str, float] = field(default_factory=dict)  # What drove RWA increase?
    breached_limits: List[str] = field(default_factory=list)  # Risk limits exceeded?

    # Metadata
    computed_at: date = field(default_factory=date.today)
    notes: str = ""


@dataclass
class ScenarioComparison:
    """Side-by-side comparison of multiple scenario runs."""

    baseline_run: ScenarioRun
    scenario_runs: Dict[str, ScenarioRun]  # scenario_id -> ScenarioRun

    # Summary statistics
    worst_case_rwa: float            # Highest RWA across all scenarios
    worst_case_scenario_id: str      # Which scenario (highest RWA)
    best_case_rwa: float             # Lowest RWA (usually baseline)
    rwa_range: float                 # Max - Min RWA
    rwa_median: float                # Median RWA across scenarios
    rwa_std_dev: float               # Std dev of RWA (stress magnitude)

    # Correlation of scenarios to RWA
    scenario_stress_index: Dict[str, float]  # Severity ranking


class ScenarioAnalysisEngine:
    """
    Applies scenarios to portfolios and computes RWA impact.

    Responsibilities:
      1. Load scenarios (regulatory or custom)
      2. Build market parameter shocks
      3. Interface with risk engines (A-IRB, SA-CCR, FRTB, CVA)
      4. Re-price portfolio under scenario
      5. Compute scenario RWA
      6. Compare to baseline
      7. Report results

    Usage:
        engine = ScenarioAnalysisEngine(prometheus_runner)

        # Run single scenario
        scenario = get_regulatory_scenario("CRISIS_2008")
        run = engine.run_scenario(portfolio, scenario)
        print(f"RWA increase: {run.rwa_increase_pct:+.1%}")

        # Run all regulatory scenarios
        runs = engine.run_all_scenarios(portfolio)

        # Generate report
        report = engine.generate_scenario_report(runs)
    """

    def __init__(self, prometheus_runner):
        """
        Initialize ScenarioAnalysisEngine.

        Args:
            prometheus_runner: PrometheusRunner instance with all calculation engines
        """
        self.runner = prometheus_runner
        self.baseline_rwa: Optional[float] = None
        self.scenario_runs: Dict[str, ScenarioRun] = {}
        logger.info("ScenarioAnalysisEngine initialized")

    def run_scenario(
        self,
        portfolio: Dict,
        scenario: Scenario,
        run_date: date = None,
    ) -> ScenarioRun:
        """
        Apply scenario to portfolio and compute RWA impact.

        Args:
            portfolio: Portfolio data (derivatives, banking book, etc.)
            scenario: Scenario to apply
            run_date: Risk run date (default: today)

        Returns:
            ScenarioRun with RWA and capital impact

        Algorithm:
            1. Compute baseline RWA (no-stress)
            2. Apply scenario market shocks to portfolio
            3. Re-price exposures under scenario
            4. Re-compute RWA with scenario parameters
            5. Compare to baseline
            6. Store results
        """
        run_date = run_date or date.today()

        logger.info(f"Running scenario '{scenario.scenario_name}' ({scenario.scenario_id})")

        # Step 1: Compute baseline RWA (if not already computed)
        if self.baseline_rwa is None:
            logger.info("Computing baseline RWA (no scenario)...")
            baseline_run = self._compute_rwa_internal(
                portfolio,
                market_params=MarketParameters(),  # No shocks
                run_date=run_date,
                scenario_name="BASELINE",
            )
            self.baseline_rwa = baseline_run["rwa_total"]

        # Step 2–5: Apply scenario and compute scenario RWA
        logger.info(f"Applying scenario shocks: {scenario.scenario_id}")
        scenario_run_data = self._compute_rwa_internal(
            portfolio,
            market_params=scenario.market_params,
            run_date=run_date,
            scenario_name=scenario.scenario_id,
        )

        # Step 6: Build ScenarioRun with comparative metrics
        rwa_increase_abs = scenario_run_data["rwa_total"] - self.baseline_rwa
        rwa_increase_pct = rwa_increase_abs / self.baseline_rwa if self.baseline_rwa > 0 else 0

        scenario_run = ScenarioRun(
            scenario=scenario,
            run_date=run_date,
            portfolio_size=len(portfolio.get("derivative", [])) + len(portfolio.get("banking_book", [])),

            rwa_baseline=self.baseline_rwa,
            rwa_credit=scenario_run_data.get("rwa_credit", 0),
            rwa_ccr=scenario_run_data.get("rwa_ccr", 0),
            rwa_market=scenario_run_data.get("rwa_market", 0),
            rwa_cva=scenario_run_data.get("rwa_cva", 0),
            rwa_ccp=scenario_run_data.get("rwa_ccp", 0),
            rwa_total=scenario_run_data["rwa_total"],

            rwa_increase_pct=rwa_increase_pct,
            rwa_increase_abs=rwa_increase_abs,

            credit_rwa_increase_pct=(scenario_run_data.get("rwa_credit", 0) -
                                    self.runner.airb.compute_rwa_aggregate(portfolio.get("banking_book", []))) /
                                   max(self.runner.airb.compute_rwa_aggregate(portfolio.get("banking_book", [])), 1),
            ccr_rwa_increase_pct=0,  # TODO: compute from baseline
            market_rwa_increase_pct=0,  # TODO: compute from baseline
            cva_rwa_increase_pct=0,  # TODO: compute from baseline

            capital_baseline=self.baseline_rwa / 8.0,      # 12.5x leverage
            capital_scenario=scenario_run_data["rwa_total"] / 8.0,
            capital_increase=rwa_increase_abs / 8.0,

            max_single_exposure_rwa=scenario_run_data.get("max_exposure_rwa", 0),
            concentration_change_hhi=0,  # TODO: compute HHI change

            key_drivers={
                "equity_shock_pct": scenario.market_params.sp500_shock,
                "spread_widening_bps": scenario.market_params.credit_spread_bbb,
                "volatility_level": scenario.market_params.equity_volatility,
                "correlation_uplift": scenario.market_params.correlation_multiplier - 1.0,
            },

            computed_at=date.today(),
            notes=f"Scenario: {scenario.scenario_name}"
        )

        # Store results
        self.scenario_runs[scenario.scenario_id] = scenario_run

        logger.info(f"  RWA: {scenario_run_data['rwa_total']:,.0f} (baseline: {self.baseline_rwa:,.0f})")
        logger.info(f"  Increase: {rwa_increase_pct:+.1%}")

        return scenario_run

    def run_all_scenarios(
        self,
        portfolio: Dict,
        scenario_type_filter: Optional[ScenarioType] = None,
        run_date: date = None,
    ) -> Dict[str, ScenarioRun]:
        """
        Run all regulatory scenarios in library.

        Args:
            portfolio: Portfolio data
            scenario_type_filter: Filter by scenario type (e.g., REGULATORY_ADVERSE)
            run_date: Risk run date

        Returns:
            Dict mapping scenario_id -> ScenarioRun

        Example:
            runs = engine.run_all_scenarios(portfolio)
            for sid, run in runs.items():
                print(f"{run.scenario.scenario_name}: {run.rwa_total:,.0f}")
        """
        scenarios = get_all_scenarios(scenario_type_filter)

        logger.info(f"Running {len(scenarios)} scenarios...")

        for scenario in scenarios:
            try:
                self.run_scenario(portfolio, scenario, run_date)
            except Exception as e:
                logger.error(f"Failed to run scenario {scenario.scenario_id}: {e}")

        return self.scenario_runs

    def _compute_rwa_internal(
        self,
        portfolio: Dict,
        market_params: MarketParameters,
        run_date: date,
        scenario_name: str,
    ) -> Dict:
        """
        Internal: Compute RWA with given market parameters.

        This is where we interface with actual risk engines.
        Currently a stub that calls runner engines.

        Could later be enhanced to:
          - Re-price derivatives under scenario Vol/rates
          - Adjust correlation matrices
          - Recompute exposures
        """

        # TODO: In production, apply market_params shocks:
        #   - Adjust FX rates for FXFwd revaluation
        #   - Re-price derivative MTM under scenario rates/spreads
        #   - Adjust correlation matrices per scenario
        #   - Re-compute FRTB sensitivities

        # For now, use runner's existing calculation as proxy
        # (Full implementation requires market data feed integration)

        rwa_credit = self.runner.airb.compute_rwa_aggregate(portfolio.get("banking_book", []))
        rwa_ccr = 0  # TODO: compute from derivatives
        rwa_market = 0  # TODO: compute FRTB with scenario rates
        rwa_cva = 0  # TODO: compute CVA with scenario spreads
        rwa_ccp = 0  # TODO: compute CCP

        rwa_total = rwa_credit + rwa_ccr + rwa_market + rwa_cva + rwa_ccp

        return {
            "rwa_credit": rwa_credit,
            "rwa_ccr": rwa_ccr,
            "rwa_market": rwa_market,
            "rwa_cva": rwa_cva,
            "rwa_ccp": rwa_ccp,
            "rwa_total": rwa_total,
            "max_exposure_rwa": rwa_credit / max(len(portfolio.get("banking_book", [])), 1),
        }

    def generate_scenario_comparison(self) -> ScenarioComparison:
        """
        Generate comprehensive scenario comparison.

        Returns:
            ScenarioComparison with rankings, statistics, insights
        """
        if not self.scenario_runs:
            raise ValueError("No scenario runs to compare; call run_scenario first")

        rwas = [run.rwa_total for run in self.scenario_runs.values()]

        comparison = ScenarioComparison(
            baseline_run=ScenarioRun(
                scenario=Scenario(
                    scenario_id="BASELINE",
                    scenario_name="Baseline",
                    scenario_type=ScenarioType.BASELINE,
                    description="No stress",
                    start_date=date.today(),
                    end_date=date.today(),
                ),
                run_date=date.today(),
                portfolio_size=0,
                rwa_baseline=self.baseline_rwa or 0,
                rwa_credit=0,
                rwa_ccr=0,
                rwa_market=0,
                rwa_cva=0,
                rwa_ccp=0,
                rwa_total=self.baseline_rwa or 0,
                rwa_increase_pct=0,
                rwa_increase_abs=0,
                credit_rwa_increase_pct=0,
                ccr_rwa_increase_pct=0,
                market_rwa_increase_pct=0,
                cva_rwa_increase_pct=0,
                capital_baseline=0,
                capital_scenario=0,
                capital_increase=0,
                max_single_exposure_rwa=0,
                concentration_change_hhi=0,
            ),
            scenario_runs=self.scenario_runs,
            worst_case_rwa=max(rwas),
            worst_case_scenario_id=max(self.scenario_runs.keys(),
                                       key=lambda k: self.scenario_runs[k].rwa_total),
            best_case_rwa=min(rwas),
            rwa_range=max(rwas) - min(rwas),
            rwa_median=float(np.median(rwas)),
            rwa_std_dev=float(np.std(rwas)),
            scenario_stress_index={
                sid: run.rwa_increase_pct
                for sid, run in self.scenario_runs.items()
            }
        )

        return comparison

    def generate_scenario_report(self) -> str:
        """Generate markdown report of scenario analysis."""

        comparison = self.generate_scenario_comparison()

        report = f"""
# PROMETHEUS Scenario Analysis Report
**Generated:** {date.today().isoformat()}

## Executive Summary

| Metric | Value |
|--------|-------|
| Baseline RWA | {comparison.baseline_run.rwa_total:,.0f} |
| Worst-Case RWA | {comparison.worst_case_rwa:,.0f} |
| Best-Case RWA | {comparison.best_case_rwa:,.0f} |
| RWA Range | {comparison.rwa_range:,.0f} |
| RWA Std Dev | {comparison.rwa_std_dev:,.0f} |

## Scenario Results

| Scenario | RWA | Δ (abs) | Δ (%) | Stress Index |
|----------|-----|---------|-------|--------------|
"""

        for sid, run in comparison.scenario_runs.items():
            report += f"| {run.scenario.scenario_name} | {run.rwa_total:,.0f} | {run.rwa_increase_abs:+,.0f} | {run.rwa_increase_pct:+.1%} | {run.rwa_increase_pct:.2f} |\n"

        report += f"""

## Capital Requirement Impact

| Scenario | Capital (Tier-1) | Change | Buffer Above Min |
|----------|------------------|--------|------------------|
"""

        for sid, run in comparison.scenario_runs.items():
            report += f"| {run.scenario.scenario_name} | {run.capital_scenario:,.0f} | {run.capital_increase:+,.0f} | TBD |\n"

        report += f"""

## Key Insights

- **Highest RWA**: {comparison.worst_case_scenario_id} ({comparison.worst_case_rwa:,.0f})
- **Stress Range**: {comparison.rwa_range:,.0f} ({comparison.rwa_range/comparison.best_case_rwa if comparison.best_case_rwa > 0 else 0:.1%})
- **Average Stress**: {float(np.mean([r.rwa_increase_pct for r in comparison.scenario_runs.values()])):+.1%}

---

**End of Report**
"""

        return report


if __name__ == "__main__":
    # Demo: print scenario library
    from backend.scenarios.library import print_scenario_summary
    print_scenario_summary()

