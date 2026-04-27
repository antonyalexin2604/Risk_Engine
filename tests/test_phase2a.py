"""
Phase 2A Test Suite - Output Floor, ESG, Data Quality
======================================================

Comprehensive tests for all Phase 2A foundational modules.
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

# Test Output Floor
from backend.capital.output_floor import DynamicOutputFloorCalculator


class TestDynamicOutputFloor:
    """Test dynamic output floor calculations."""

    def test_floor_multiplier_normal_regime(self):
        """Normal regime should return 73.0% (72.5% + 0.5%)."""
        calc = DynamicOutputFloorCalculator()
        multiplier = calc.compute_floor_multiplier(
            sa_rwa=1_000_000,
            airb_rwa=800_000,
            regime="normal"
        )
        assert 0.72 < multiplier < 0.74, f"Expected ~0.73, got {multiplier}"

    def test_floor_multiplier_stressed_regime(self):
        """Stressed regime should return 74.0% (72.5% + 1.5%)."""
        calc = DynamicOutputFloorCalculator()
        multiplier = calc.compute_floor_multiplier(
            sa_rwa=1_000_000,
            airb_rwa=800_000,
            regime="stressed"
        )
        assert 0.73 < multiplier < 0.75, f"Expected ~0.74, got {multiplier}"

    def test_floor_not_binding(self):
        """If total RWA > floor, floor should not bind."""
        calc = DynamicOutputFloorCalculator()
        floored, impact, status = calc.apply_floor(
            total_rwa=1_500_000,
            sa_rwa=1_000_000,
            airb_rwa=900_000,
        )
        assert status == "not_binding"
        assert floored == 1_500_000  # RWA unchanged
        assert impact == 0.0

    def test_floor_binding(self):
        """If total RWA < floor, floor should bind."""
        calc = DynamicOutputFloorCalculator()
        floored, impact, status = calc.apply_floor(
            total_rwa=500_000,
            sa_rwa=1_000_000,
            airb_rwa=600_000,
        )
        assert status == "binding"
        assert floored > 500_000  # RWA increased by floor
        assert impact > 0


# Test ESG/Climate Framework
from backend.climate.esg_framework import ESGClimateRiskEngine, SECTOR_CLIMATE_CALIBRATION


class TestESGClimateRisk:
    """Test ESG/climate risk calculations."""

    def test_sector_library_completeness(self):
        """Should have 8+ sector profiles."""
        assert len(SECTOR_CLIMATE_CALIBRATION) >= 8

    def test_sector_fossil_fuels_high_uplift(self):
        """Fossil fuels should have highest PD uplift."""
        fossil = SECTOR_CLIMATE_CALIBRATION.get("FOSSIL_FUELS")
        assert fossil is not None
        assert fossil.pd_uplift_pct > 1.5  # Should be ~2%

    def test_sector_tech_low_uplift(self):
        """Technology should have low/zero uplift."""
        tech = SECTOR_CLIMATE_CALIBRATION.get("TECHNOLOGY")
        assert tech is not None
        assert tech.pd_uplift_pct <= 0.1  # Should be 0%

    def test_transition_risk_uplift_calculation(self):
        """Should compute PD uplift as decimal."""
        engine = ESGClimateRiskEngine()
        uplift = engine.compute_transition_risk_uplift("FOSSIL", "EU")
        assert isinstance(uplift, float)
        assert uplift > 0.01  # Should be ~2%

    def test_adjusted_pd_increases_for_brown_sectors(self):
        """PD should increase for high-carbon sectors."""
        engine = ESGClimateRiskEngine()
        base_pd = 0.01
        adjusted = engine.compute_adjusted_pd(
            base_pd=base_pd,
            obligor_sector="FOSSIL",
            obligor_region="EU"
        )
        assert adjusted > base_pd


# Test Data Quality Scorecard
from backend.data_quality.dqms import DataQualityEngine, DQStatus


class TestDataQualityScorecard:
    """Test data quality scoring."""

    def test_completeness_all_values_present(self):
        """100% non-null should score 100."""
        engine = DataQualityEngine()
        score = engine.compute_completeness([1, 2, 3, 4, 5])
        assert score.score == 100.0
        assert score.status == DQStatus.GREEN

    def test_completeness_values_missing(self):
        """Partial non-null should score lower."""
        engine = DataQualityEngine()
        score = engine.compute_completeness([1, 2, None, None, 5])
        assert score.score == 60.0  # 3/5 = 60%
        assert score.status == DQStatus.YELLOW or score.status == DQStatus.RED

    def test_accuracy_within_tolerance(self):
        """Values within 5% should score well."""
        engine = DataQualityEngine()
        score = engine.compute_accuracy(
            actual_values=[100, 200, 300],
            benchmark_values=[100, 200, 300],
            max_deviation_pct=0.05
        )
        assert score.score == 100.0
        assert score.status == DQStatus.GREEN

    def test_accuracy_outside_tolerance(self):
        """Values >10% off should score lower."""
        engine = DataQualityEngine()
        score = engine.compute_accuracy(
            actual_values=[100, 200, 300],
            benchmark_values=[110, 220, 330],  # 10% off
            max_deviation_pct=0.05
        )
        assert score.score < 50.0

    def test_timeliness_fresh_data(self):
        """Data <1h old should score 100."""
        engine = DataQualityEngine()
        now = datetime.utcnow()
        score = engine.compute_timeliness(now - timedelta(minutes=30))
        assert score.score == 100.0
        assert score.status == DQStatus.GREEN

    def test_timeliness_stale_data(self):
        """Data >24h old should score lower."""
        engine = DataQualityEngine()
        now = datetime.utcnow()
        score = engine.compute_timeliness(now - timedelta(hours=48))
        assert score.score < 50.0
        assert score.status == DQStatus.RED or score.status == DQStatus.YELLOW

    def test_validity_values_in_range(self):
        """Values in range should score high."""
        engine = DataQualityEngine()
        score = engine.compute_validity([10, 20, 30], valid_range=(0, 100))
        assert score.score == 100.0
        assert score.status == DQStatus.GREEN

    def test_validity_values_out_of_range(self):
        """Values outside range should score lower."""
        engine = DataQualityEngine()
        score = engine.compute_validity([10, 200, 300], valid_range=(0, 100))
        assert score.score == 100/3 * 100  # 1/3 in range
        assert score.score < 50.0

    def test_portfolio_score_aggregation(self):
        """Portfolio score should aggregate components."""
        engine = DataQualityEngine()

        # Create component scores
        completeness = engine.compute_completeness([1, 2, 3])
        accuracy = engine.compute_accuracy([100, 200], [100, 200])
        timeliness = engine.compute_timeliness(datetime.utcnow())
        consistency = engine.compute_consistency([1, 1], [1, 1])
        validity = engine.compute_validity([10, 20], (0, 100))

        # Compute portfolio
        portfolio = engine.compute_portfolio_score(
            completeness, accuracy, timeliness, consistency, validity
        )

        assert 0 <= portfolio.overall_score <= 100
        assert portfolio.status in [DQStatus.RED, DQStatus.YELLOW, DQStatus.GREEN]


# Integration Tests
class TestPhase2AIntegration:
    """Test Phase 2A modules working together."""

    def test_output_floor_with_climate_adjusted_pd(self):
        """Should integrate output floor with ESG risk."""
        from backend.capital.output_floor import apply_output_floor_to_rwa
        from backend.climate.esg_framework import apply_climate_risk_adjustment

        # Apply climate adjustment
        adjusted_pd, metadata = apply_climate_risk_adjustment(
            base_pd=0.01,
            obligor_sector="FOSSIL",
        )

        # Apply floor
        floored_rwa, floor_metadata = apply_output_floor_to_rwa(
            total_rwa=1_000_000,
            rwa_components={"credit": 800_000},
            run_date=date.today(),
        )

        assert adjusted_pd > 0.01  # Climate uplift applied
        assert floored_rwa >= 1_000_000  # Floor applied

    def test_data_quality_with_dq_engine(self):
        """Should compute comprehensive DQ score."""
        engine = DataQualityEngine()

        completeness = engine.compute_completeness([1, 2, 3])
        accuracy = engine.compute_accuracy([100, 200], [100, 200])
        timeliness = engine.compute_timeliness(datetime.utcnow())
        consistency = engine.compute_consistency([1, 1], [1, 1])
        validity = engine.compute_validity([10, 20], (0, 100))

        portfolio = engine.compute_portfolio_score(
            completeness, accuracy, timeliness, consistency, validity
        )

        # Should have no critical issues in this test
        assert len(portfolio.critical_issues) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

