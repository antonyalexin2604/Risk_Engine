"""
Test Suite: Scenario Analysis Module
=====================================

Validates:
  - Scenario definitions (BCBS, ECB, FED, custom)
  - Scenario engine (apply scenarios, compute RWA)
  - Scenario comparison and reporting
"""

import sys
import os
from datetime import date, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("PROMETHEUS_SKIP_CALIBRATION", "1")

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock

from backend.scenarios.library import (
    Scenario,
    ScenarioType,
    MarketParameters,
    LiquidityRegime,
    get_regulatory_scenario,
    get_all_scenarios,
    create_2007_2009_crisis_scenario,
    create_ecb_crdp_scenario,
    create_fed_adverse_scenario,
)
from backend.scenarios.engine import (
    ScenarioRun,
    ScenarioComparison,
    ScenarioAnalysisEngine,
)


class TestScenarioLibrary:
    """Test regulatory scenario library."""

    def test_baseline_scenario_creation(self):
        """Baseline scenario should be defined."""
        baseline = get_regulatory_scenario("BASELINE_CURRENT")
        assert baseline is not None
        assert baseline.scenario_type == ScenarioType.BASELINE
        assert baseline.market_params.correlation_multiplier == 1.0

    def test_2008_crisis_scenario_parameters(self):
        """2008 crisis should have correct parameters."""
        crisis = get_regulatory_scenario("CRISIS_2008")
        assert crisis is not None
        assert crisis.scenario_type == ScenarioType.HISTORICAL_CRISIS

        # Equity shock should be negative and significant
        assert crisis.market_params.sp500_shock < -0.50, "2008 equity shock should be >50%"

        # Spreads should widen significantly
        assert crisis.market_params.credit_spread_bbb > 300, "BBB spreads should widen >300 bps"

        # Correlation should spike
        assert crisis.market_params.correlation_multiplier > 1.30, "Correlations should spike"

        # Volatility should be high
        assert crisis.market_params.equity_volatility > 0.60, "VIX equivalent should be >60"

    def test_ecb_crdp_scenario(self):
        """ECB CRDP scenario should reflect sovereign stress."""
        crdp = get_regulatory_scenario("ECB_CRDP")
        assert crdp is not None

        # Financial CDS should spike (contagion)
        assert crdp.market_params.cds_spread_financial > 200, "Financial CDS should spike"

        # Should be regulatory
        assert crdp.is_regulatory
        assert "ECB" in crdp.regulatory_basis

    def test_fed_adverse_scenario(self):
        """FED adverse scenario should match specifications."""
        adverse = get_regulatory_scenario("FED_ADVERSE")
        assert adverse is not None

        # Equity shock ~35%
        assert adverse.market_params.sp500_shock < -0.30, "S&P shock should be ~35%"

        # Rates should rise (reflation)
        assert adverse.market_params.rate_shock_usd_10y > 50, "Rates should rise 100+ bps"

    def test_scenario_registry_retrieval(self):
        """All scenarios should be retrievable."""
        all_scenarios = get_all_scenarios()
        assert len(all_scenarios) >= 5, "Should have at least 5 regulatory scenarios"

        # All should be Scenario instances
        for scenario in all_scenarios:
            assert isinstance(scenario, Scenario)

    def test_scenario_type_filtering(self):
        """Scenario filtering by type should work."""
        regulatory_scenarios = get_all_scenarios(ScenarioType.REGULATORY_ADVERSE)
        assert len(regulatory_scenarios) > 0

        # All filtered should have correct type
        for scenario in regulatory_scenarios:
            assert scenario.scenario_type == ScenarioType.REGULATORY_ADVERSE

    def test_market_parameters_shocks_reasonable(self):
        """All market parameter shocks should be reasonable."""
        crisis = get_regulatory_scenario("CRISIS_2008")
        mp = crisis.market_params

        # Rates should be in reasonable range
        assert mp.rate_shock_usd_10y > -500, "Rate shocks should not be extreme"
        assert mp.rate_shock_usd_10y < 500

        # Spreads should not exceed 1000 bps
        assert mp.credit_spread_hy < 1000, "Spread shocks should be <1000 bps"

        # Volatility should be between 0 and 1
        assert 0 < mp.equity_volatility < 1

    def test_custom_scenario_registration(self):
        """Custom scenarios should be registrable."""
        custom = Scenario(
            scenario_id="TEST_CUSTOM",
            scenario_name="Test Scenario",
            scenario_type=ScenarioType.CUSTOM,
            description="For testing",
            start_date=date.today(),
            end_date=date.today(),
            market_params=MarketParameters(
                sp500_shock=-0.20,
                credit_spread_bbb=150,
            ),
        )

        from backend.scenarios.library import register_custom_scenario
        register_custom_scenario(custom)

        # Should be retrievable
        retrieved = get_regulatory_scenario("TEST_CUSTOM")
        assert retrieved is not None
        assert retrieved.scenario_id == "TEST_CUSTOM"


class TestScenarioEngine:
    """Test scenario analysis engine."""

    @pytest.fixture
    def mock_runner(self):
        """Create mock PrometheusRunner."""
        runner = Mock()
        runner.airb = Mock()
        runner.airb.compute_rwa_aggregate = Mock(return_value=1_000_000.0)
        runner.saccr = Mock()
        runner.imm = Mock()
        runner.frtb = Mock()
        runner.cva = Mock()
        return runner

    @pytest.fixture
    def scenario_engine(self, mock_runner):
        """Create ScenarioAnalysisEngine."""
        return ScenarioAnalysisEngine(mock_runner)

    def test_scenario_engine_initialization(self, scenario_engine):
        """Engine should initialize correctly."""
        assert scenario_engine.runner is not None
        assert scenario_engine.baseline_rwa is None
        assert len(scenario_engine.scenario_runs) == 0

    def test_scenario_run_creation(self, scenario_engine, mock_runner):
        """Scenario run should compute RWA impact."""
        portfolio = {
            "banking_book": [Mock()],
            "derivative": [],
        }

        scenario = get_regulatory_scenario("BASELINE_CURRENT")

        # Run should set baseline_rwa
        run = scenario_engine.run_scenario(portfolio, scenario)

        assert scenario_engine.baseline_rwa == 1_000_000.0
        assert run.scenario == scenario
        assert run.rwa_total >= 0
        assert len(scenario_engine.scenario_runs) > 0

    def test_scenario_comparison_generation(self, scenario_engine, mock_runner):
        """Comparison should aggregate multiple scenarios."""
        portfolio = {"banking_book": [Mock()], "derivative": []}

        scenarios = [
            get_regulatory_scenario("BASELINE_CURRENT"),
            get_regulatory_scenario("CRISIS_2008"),
            get_regulatory_scenario("FED_ADVERSE"),
        ]

        for scenario in scenarios:
            scenario_engine.run_scenario(portfolio, scenario)

        comparison = scenario_engine.generate_scenario_comparison()

        assert comparison is not None
        assert len(comparison.scenario_runs) == len(scenarios)
        assert comparison.worst_case_rwa >= comparison.best_case_rwa
        assert comparison.rwa_range >= 0

    def test_scenario_report_generation(self, scenario_engine, mock_runner):
        """Engine should generate markdown report."""
        portfolio = {"banking_book": [Mock()], "derivative": []}

        scenario = get_regulatory_scenario("CRISIS_2008")
        scenario_engine.run_scenario(portfolio, scenario)

        report = scenario_engine.generate_scenario_report()

        assert "PROMETHEUS Scenario Analysis Report" in report
        assert "Executive Summary" in report
        assert "Scenario Results" in report
        assert len(report) > 500  # Non-trivial report


class TestScenarioValidation:
    """Validate scenario reasonableness."""

    def test_crisis_worse_than_baseline(self):
        """Crisis scenario should have worse RWA impact than baseline."""
        baseline = get_regulatory_scenario("BASELINE_CURRENT")
        crisis = get_regulatory_scenario("CRISIS_2008")

        # Crisis should have larger equity shock
        assert abs(crisis.market_params.sp500_shock) > abs(baseline.market_params.sp500_shock)

        # Crisis should have larger spread widening
        assert crisis.market_params.credit_spread_bbb > baseline.market_params.credit_spread_bbb

    def test_scenario_hierarchy(self):
        """Stress scenarios should have graduated severity."""
        adverse = get_regulatory_scenario("FED_ADVERSE")
        severe = get_regulatory_scenario("FED_SEVERELY_ADVERSE")

        # Severely adverse should have worse equity shock
        assert abs(severe.market_params.sp500_shock) >= abs(adverse.market_params.sp500_shock)

        # Severely adverse should have wider spreads
        assert severe.market_params.credit_spread_bbb >= adverse.market_params.credit_spread_bbb

    def test_regulatory_alignment(self):
        """Regulatory scenarios should have basis documented."""
        fed_adverse = get_regulatory_scenario("FED_ADVERSE")
        assert fed_adverse.is_regulatory
        assert "FED" in str(fed_adverse.regulatory_basis).upper()

        ecb = get_regulatory_scenario("ECB_CRDP")
        assert ecb.is_regulatory
        assert "ECB" in str(ecb.regulatory_basis).upper()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

