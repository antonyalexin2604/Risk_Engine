"""
Test Suite: Sensitivities & Greeks Module
===========================================

Validates:
  - Greek computation (delta, gamma, vega, rho)
  - Parameter sensitivities (PD, LGD, correlation, maturity)
  - Portfolio Greeks aggregation
  - Sensitivity reporting
"""

import sys
import os
from datetime import date
from copy import deepcopy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("PROMETHEUS_SKIP_CALIBRATION", "1")

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch

from backend.sensitivities import (
    SensitivityAnalyzer,
    Greek,
    GreekType,
    GreekPortfolio,
    RiskMetric,
)
from backend.engines.a_irb import BankingBookExposure


class TestGreekDefinitions:
    """Test Greek data structures."""

    def test_greek_creation(self):
        """Greek should initialize correctly."""
        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="PD",
            parameter_class="A_IRB",
            base_value=0.01,
            shock_size=0.001,
            shock_direction="up",
            rwa_base=1_000_000,
            rwa_shocked=1_050_000,
            rwa_delta=50_000,
            rwa_delta_pct=0.05,
            rwa_delta_bps=500,
        )

        assert greek.greek_type == GreekType.DELTA
        assert greek.parameter_name == "PD"
        assert greek.rwa_delta_pct == 0.05

    def test_greek_magnitude_classification(self):
        """Greek should classify magnitude correctly."""
        # Negligible
        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="PD",
            parameter_class="A_IRB",
            base_value=0.01,
            shock_size=0.001,
            shock_direction="up",
            rwa_base=1_000_000,
            rwa_shocked=1_000_500,
            rwa_delta=500,
            rwa_delta_pct=0.0005,
            rwa_delta_bps=5,
            magnitude="negligible",
        )
        assert greek.magnitude == "negligible"

    def test_greek_to_dict(self):
        """Greek should export to dictionary."""
        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="PD",
            parameter_class="A_IRB",
            base_value=0.01,
            shock_size=0.001,
            shock_direction="up",
            rwa_base=1_000_000,
            rwa_shocked=1_050_000,
            rwa_delta=50_000,
            rwa_delta_pct=0.05,
            rwa_delta_bps=500,
        )

        d = greek.to_dict()
        assert d["parameter"] == "PD"
        assert d["greek"] == "delta"
        assert "rwa_delta_pct" in d


class TestGreekPortfolio:
    """Test portfolio-level Greeks collection."""

    def test_greek_portfolio_initialization(self):
        """Portfolio should initialize."""
        portfolio = GreekPortfolio(
            portfolio_date=date.today(),
            engine_type="A_IRB",
        )

        assert portfolio.portfolio_date == date.today()
        assert portfolio.engine_type == "A_IRB"
        assert len(portfolio.greeks) == 0

    def test_greek_portfolio_add_and_retrieve(self):
        """Should add and retrieve Greeks."""
        portfolio = GreekPortfolio(
            portfolio_date=date.today(),
            engine_type="A_IRB",
        )

        greek = Greek(
            greek_type=GreekType.DELTA,
            parameter_name="PD",
            parameter_class="A_IRB",
            base_value=0.01,
            shock_size=0.001,
            shock_direction="up",
            rwa_base=1_000_000,
            rwa_shocked=1_050_000,
            rwa_delta=50_000,
            rwa_delta_pct=0.05,
            rwa_delta_bps=500,
        )

        portfolio.add_greek(greek)

        assert len(portfolio.greeks) == 1
        assert portfolio.greeks[0].parameter_name == "PD"

    def test_get_top_sensitivities(self):
        """Should rank Greeks by magnitude."""
        portfolio = GreekPortfolio(
            portfolio_date=date.today(),
            engine_type="A_IRB",
        )

        # Add Greeks with different magnitudes
        greeks = [
            Greek(
                greek_type=GreekType.DELTA,
                parameter_name="PD",
                parameter_class="A_IRB",
                base_value=0.01,
                shock_size=0.001,
                shock_direction="up",
                rwa_base=1_000_000,
                rwa_shocked=1_100_000,  # 10% impact
                rwa_delta=100_000,
                rwa_delta_pct=0.10,
                rwa_delta_bps=1000,
            ),
            Greek(
                greek_type=GreekType.DELTA,
                parameter_name="LGD",
                parameter_class="A_IRB",
                base_value=0.45,
                shock_size=0.05,
                shock_direction="up",
                rwa_base=1_000_000,
                rwa_shocked=1_030_000,  # 3% impact
                rwa_delta=30_000,
                rwa_delta_pct=0.03,
                rwa_delta_bps=300,
            ),
        ]

        for greek in greeks:
            portfolio.add_greek(greek)

        top = portfolio.get_top_sensitivities(1)

        # PD should be top (10% vs 3%)
        assert len(top) == 1
        assert top[0].parameter_name == "PD"


class TestSensitivityAnalyzer:
    """Test sensitivity computation."""

    @pytest.fixture
    def mock_runner(self):
        """Create mock runner."""
        runner = Mock()
        runner.airb = Mock()
        return runner

    @pytest.fixture
    def analyzer(self, mock_runner):
        """Create analyzer."""
        return SensitivityAnalyzer(mock_runner)

    def test_analyzer_initialization(self, analyzer):
        """Analyzer should initialize."""
        assert analyzer.runner is not None
        assert analyzer.trace_engine is None

    @pytest.fixture
    def sample_portfolio(self):
        """Create sample banking book portfolio."""
        exposures = []
        for i in range(5):
            exp = Mock(spec=BankingBookExposure)
            exp.trade_id = f"EXP-{i:03d}"
            exp.pd = 0.01 + (i * 0.001)
            exp.lgd = 0.45
            exp.ead = 10_000_000
            exp.maturity = 2.5
            exp.asset_class = "CORP"
            exposures.append(exp)
        return exposures

    def test_delta_pd_computation(self, analyzer, sample_portfolio):
        """Should compute PD delta correctly."""
        # Mock the runner's compute_rwa_aggregate
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=[1_000_000, 1_050_000]  # baseline, then shocked
        )

        greek = analyzer.compute_delta_airb_pd(sample_portfolio, shock_size=0.001)

        assert greek.greek_type == GreekType.DELTA
        assert greek.parameter_name == "PD (Probability of Default)"
        assert greek.rwa_delta == 50_000  # Difference
        assert greek.rwa_delta_pct == pytest.approx(0.05, rel=0.01)

    def test_delta_lgd_computation(self, analyzer, sample_portfolio):
        """Should compute LGD delta correctly."""
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=[1_000_000, 1_030_000]
        )

        greek = analyzer.compute_delta_airb_lgd(sample_portfolio, shock_size=0.05)

        assert greek.parameter_name == "LGD (Loss Given Default)"
        assert greek.rwa_delta_pct == pytest.approx(0.03, rel=0.01)

    def test_all_greeks_computation(self, analyzer, sample_portfolio):
        """Should compute all A-IRB Greeks."""
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            return_value=1_000_000
        )

        # Mock to return different RWAs for each shock
        call_count = [0]

        def side_effect_func(portfolio):
            call_count[0] += 1
            # Return progressively higher RWA for each call
            return 1_000_000 + (call_count[0] * 30_000)

        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=side_effect_func
        )

        portfolio_greeks = analyzer.compute_all_greeks_airb(sample_portfolio)

        assert len(portfolio_greeks.greeks) == 4  # PD, LGD, M, Correlation
        assert all(greek.parameter_class == "A_IRB" for greek in portfolio_greeks.greeks)

    def test_magnitude_classification(self, analyzer):
        """Should classify magnitudes correctly."""
        test_cases = [
            (0.0005, "negligible"),
            (0.005, "low"),
            (0.025, "medium"),
            (0.075, "high"),
            (0.150, "extreme"),
        ]

        for pct_change, expected_magnitude in test_cases:
            magnitude = analyzer._classify_magnitude(pct_change)
            assert magnitude == expected_magnitude


class TestSensitivityValidation:
    """Validate sensitivity results."""

    @pytest.fixture
    def mock_runner(self):
        runner = Mock()
        runner.airb = Mock()
        return runner

    @pytest.fixture
    def analyzer(self, mock_runner):
        return SensitivityAnalyzer(mock_runner)

    @pytest.fixture
    def sample_portfolio(self):
        exposures = []
        for i in range(3):
            exp = Mock(spec=BankingBookExposure)
            exp.pd = 0.01
            exp.lgd = 0.45
            exp.ead = 10_000_000
            exp.maturity = 2.5
            exp.asset_class = "CORP"
            exposures.append(exp)
        return exposures

    def test_pd_shock_increases_rwa(self, analyzer, sample_portfolio):
        """Increasing PD should increase RWA (monotonicity)."""
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=[1_000_000, 1_050_000]
        )

        greek = analyzer.compute_delta_airb_pd(sample_portfolio)

        # PD increase should increase RWA
        assert greek.rwa_shocked > greek.rwa_base
        assert greek.rwa_delta > 0
        assert greek.rwa_delta_pct > 0

    def test_lgd_shock_increases_rwa(self, analyzer, sample_portfolio):
        """Increasing LGD should increase RWA."""
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=[1_000_000, 1_030_000]
        )

        greek = analyzer.compute_delta_airb_lgd(sample_portfolio)

        assert greek.rwa_shocked > greek.rwa_base
        assert greek.rwa_delta > 0

    def test_sensitivities_ordering(self, analyzer, sample_portfolio):
        """Sensitivities should be in reasonable order."""
        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            return_value=1_000_000
        )

        # Mock to return different RWAs
        shocks = [
            1_100_000,  # PD delta: 10%
            1_035_000,  # LGD delta: 3.5%
            1_015_000,  # Maturity delta: 1.5%
            1_008_000,  # Correlation delta: 0.8%
        ]

        analyzer.runner.airb.compute_rwa_aggregate = Mock(
            side_effect=[1_000_000] + shocks
        )

        portfolio_greeks = analyzer.compute_all_greeks_airb(sample_portfolio)

        # Sort by magnitude
        sorted_greeks = portfolio_greeks.get_top_sensitivities(len(portfolio_greeks.greeks))

        # PD should be most sensitive
        assert sorted_greeks[0].parameter_name == "PD (Probability of Default)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

