"""
PROMETHEUS Risk Platform
Operational Risk Engine — Unit Tests

FILE PATH: tests/test_operational_risk.py

Run with: python -m pytest tests/test_operational_risk.py -v
"""

import pytest
from datetime import date
from backend.engines.operational_risk import (
    LossEvent,
    BusinessIndicatorInput,
    SMAResult,
    compute_business_indicator,
    compute_bic,
    compute_loss_component,
    compute_ilm,
    compute_sma_capital,
    BASEL_EVENT_TYPES,
    BASEL_BUSINESS_LINES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test Data Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_bi_inputs():
    """Sample Business Indicator inputs for 3 years."""
    return [
        BusinessIndicatorInput(
            year=2023,
            interest_income=500,
            interest_expense=250,
            dividend_income=50,
            services_income=300,
            services_expense=100,
            financial_income=150,
            financial_expense=50,
            other_operating_income=100,
            trading_book_pnl=200,
            banking_book_pnl=150,
        ),
        BusinessIndicatorInput(
            year=2024,
            interest_income=550,
            interest_expense=275,
            dividend_income=60,
            services_income=320,
            services_expense=110,
            financial_income=160,
            financial_expense=55,
            other_operating_income=110,
            trading_book_pnl=220,
            banking_book_pnl=165,
        ),
        BusinessIndicatorInput(
            year=2025,
            interest_income=600,
            interest_expense=300,
            dividend_income=70,
            services_income=340,
            services_expense=120,
            financial_income=170,
            financial_expense=60,
            other_operating_income=120,
            trading_book_pnl=240,
            banking_book_pnl=180,
        ),
    ]


@pytest.fixture
def sample_loss_events():
    """Sample loss events over 10 years."""
    events = []
    
    # Generate 10 years of loss data
    for year in range(2015, 2025):
        for i in range(20):  # 20 events per year
            event = LossEvent(
                event_id=f"LOSS_{year}_{i+1:03d}",
                event_date=date(year, 6, 15),
                discovery_date=date(year, 6, 20),
                booking_date=date(year, 7, 1),
                event_type="EXTERNAL_FRAUD",
                business_line="RETAIL_BANKING",
                gross_loss_amount=1.0,  # EUR 1M each
                recoveries=0.1,
                insurance_recovery=0.0,
            )
            events.append(event)
    
    return events


# ─────────────────────────────────────────────────────────────────────────────
# Data Structure Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_loss_event_creation():
    """Test LossEvent object creation and properties."""
    event = LossEvent(
        event_id="TEST_001",
        event_date=date(2024, 1, 15),
        discovery_date=date(2024, 1, 20),
        booking_date=date(2024, 2, 1),
        event_type="EXTERNAL_FRAUD",
        business_line="RETAIL_BANKING",
        gross_loss_amount=5.0,
        recoveries=0.5,
        insurance_recovery=1.0,
        description="Test event",
    )
    
    assert event.event_id == "TEST_001"
    assert event.gross_loss_amount == 5.0
    assert event.net_loss_amount == 3.5  # 5.0 - 0.5 - 1.0
    assert event.event_type in BASEL_EVENT_TYPES
    assert event.business_line in BASEL_BUSINESS_LINES


def test_business_indicator_calculation():
    """Test BI component calculations."""
    bi = BusinessIndicatorInput(
        year=2024,
        interest_income=100,
        interest_expense=50,
        dividend_income=10,
        services_income=80,
        services_expense=30,
        financial_income=40,
        financial_expense=20,
        other_operating_income=25,
        trading_book_pnl=60,
        banking_book_pnl=45,
    )
    
    # Services component: abs(100) + abs(50) + abs(10) + abs(80) + abs(30) + abs(40) + abs(20) + abs(25) = 355
    assert bi.compute_bi_services() == 355.0
    
    # Banking component: abs(45) = 45
    assert bi.compute_bi_banking() == 45.0
    
    # Financial component: abs(60) = 60
    assert bi.compute_bi_financial() == 60.0
    
    # Total BI: 355 + 45 + 60 = 460
    assert bi.compute_bi() == 460.0


# ─────────────────────────────────────────────────────────────────────────────
# Business Indicator Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_business_indicator_3_years(sample_bi_inputs):
    """Test 3-year average BI calculation."""
    bi_avg = compute_business_indicator(sample_bi_inputs)
    
    # Should return average of 3 years
    assert bi_avg > 0
    assert isinstance(bi_avg, float)


def test_compute_business_indicator_single_year():
    """Test BI calculation with only 1 year."""
    bi_inputs = [
        BusinessIndicatorInput(
            year=2024,
            interest_income=1000,
            interest_expense=500,
        )
    ]
    
    bi_avg = compute_business_indicator(bi_inputs)
    assert bi_avg == 1500.0  # abs(1000) + abs(500)


def test_compute_business_indicator_empty():
    """Test BI calculation with no inputs."""
    with pytest.raises(ValueError, match="At least 1 year"):
        compute_business_indicator([])


# ─────────────────────────────────────────────────────────────────────────────
# BIC Tests (Tiered Coefficients)
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_bic_tier_1():
    """Test BIC for BI ≤ EUR 1 billion (12% tier)."""
    # BI = EUR 500 million → BIC = 500 × 0.12 = 60
    bic = compute_bic(500)
    assert abs(bic - 60.0) < 0.01


def test_compute_bic_tier_2():
    """Test BIC spanning two tiers (12% and 15%)."""
    # BI = EUR 2 billion = EUR 2000 million
    # First EUR 1bn: 1000 × 0.12 = 120
    # Next EUR 1bn: 1000 × 0.15 = 150
    # Total BIC = 270
    bic = compute_bic(2000)
    assert abs(bic - 270.0) < 0.01


def test_compute_bic_tier_3():
    """Test BIC spanning three tiers."""
    # BI = EUR 5 billion = EUR 5000 million
    # Tier 1 (0-1bn): 1000 × 0.12 = 120
    # Tier 2 (1-3bn): 2000 × 0.15 = 300
    # Tier 3 (3-5bn): 2000 × 0.18 = 360
    # Total BIC = 780
    bic = compute_bic(5000)
    assert abs(bic - 780.0) < 0.01


def test_compute_bic_large_bank():
    """Test BIC for large bank (EUR 50 billion BI)."""
    # EUR 50bn should span all tiers
    bic = compute_bic(50000)
    assert bic > 0
    # Should be using highest tier (23%) for top portion


# ─────────────────────────────────────────────────────────────────────────────
# Loss Component Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_loss_component_10_years(sample_loss_events):
    """Test LC calculation with full 10 years of data."""
    lc, years, avg_annual_loss = compute_loss_component(sample_loss_events, years_required=10)
    
    # 20 events/year × EUR 0.9M net loss = EUR 18M per year
    # Average over 10 years = EUR 18M
    # LC = 15 × 18 = 270
    assert years == 10
    assert abs(avg_annual_loss - 18.0) < 0.1
    assert abs(lc - 270.0) < 1.0


def test_compute_loss_component_insufficient_years():
    """Test LC with fewer than 10 years → LC = 0."""
    # Only 5 years of data
    events = [
        LossEvent(
            event_id=f"LOSS_{year}",
            event_date=date(year, 1, 1),
            discovery_date=date(year, 1, 1),
            booking_date=date(year, 1, 1),
            event_type="EXTERNAL_FRAUD",
            business_line="RETAIL_BANKING",
            gross_loss_amount=1.0,
        )
        for year in range(2020, 2025)
    ]
    
    lc, years, avg_annual_loss = compute_loss_component(events, years_required=10)
    
    assert years == 5
    assert lc == 0.0  # Insufficient data → LC = 0


def test_compute_loss_component_empty():
    """Test LC with no loss events."""
    lc, years, avg_annual_loss = compute_loss_component([], years_required=10)
    
    assert lc == 0.0
    assert years == 0
    assert avg_annual_loss == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# ILM Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_ilm_normal_case():
    """Test ILM with normal LC and BIC values."""
    # LC = 270, BIC = 780
    # Ratio = 270/780 = 0.346
    # ILM = ln(exp(1) - 1 + 0.346^0.8)
    ilm = compute_ilm(lc=270, bic=780)
    
    assert ilm > 0
    assert ilm <= 1.0  # Should be capped at 1.0


def test_compute_ilm_zero_lc():
    """Test ILM when LC = 0 (insufficient loss data)."""
    ilm = compute_ilm(lc=0, bic=100)
    
    assert ilm == 1.0  # Default to 1.0


def test_compute_ilm_zero_bic():
    """Test ILM with BIC = 0 → ValueError."""
    with pytest.raises(ValueError, match="BIC cannot be zero"):
        compute_ilm(lc=100, bic=0)


def test_compute_ilm_capping():
    """Test ILM capping at 1.0."""
    # Very large LC relative to BIC should cap at 1.0
    ilm = compute_ilm(lc=10000, bic=100)
    
    assert ilm == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# End-to-End SMA Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_sma_capital_full(sample_bi_inputs, sample_loss_events):
    """Test full SMA capital calculation."""
    result = compute_sma_capital(sample_bi_inputs, sample_loss_events)
    
    assert isinstance(result, SMAResult)
    assert result.business_indicator > 0
    assert result.bic > 0
    assert result.loss_component > 0
    assert result.ilm > 0
    assert result.ilm <= 1.0
    assert result.operational_risk_capital > 0
    assert result.rwa_operational == result.operational_risk_capital * 12.5
    assert result.years_of_loss_data == 10
    assert result.total_loss_events == 200


def test_compute_sma_capital_no_losses(sample_bi_inputs):
    """Test SMA with no loss history → ILM defaults to 1.0."""
    result = compute_sma_capital(sample_bi_inputs, [])
    
    assert result.loss_component == 0.0
    assert result.ilm == 1.0
    assert result.operational_risk_capital == result.bic * 1.0
    assert result.years_of_loss_data == 0


def test_compute_sma_capital_rwa_formula(sample_bi_inputs, sample_loss_events):
    """Test RWA = Capital × 12.5."""
    result = compute_sma_capital(sample_bi_inputs, sample_loss_events)
    
    expected_rwa = result.operational_risk_capital * 12.5
    assert abs(result.rwa_operational - expected_rwa) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Regulatory Compliance Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_ope25_tiered_coefficients():
    """Verify OPE25 tiered coefficient structure."""
    # Tier boundaries (EUR billions)
    tier_boundaries = [1000, 3000, 10000, 30000]  # In millions
    
    # Test each tier boundary
    for boundary in tier_boundaries:
        bic = compute_bic(boundary)
        assert bic > 0


def test_ope25_10_year_requirement():
    """Verify OPE25 requires 10 years of loss data for LC."""
    # 9 years → LC = 0
    events_9_years = [
        LossEvent(
            event_id=f"E_{year}",
            event_date=date(year, 1, 1),
            discovery_date=date(year, 1, 1),
            booking_date=date(year, 1, 1),
            event_type="EXTERNAL_FRAUD",
            business_line="RETAIL_BANKING",
            gross_loss_amount=1.0,
        )
        for year in range(2015, 2024)  # 9 years
    ]
    
    lc, years, _ = compute_loss_component(events_9_years, years_required=10)
    assert years == 9
    assert lc == 0.0  # Not enough data
    
    # 10 years → LC > 0
    events_10_years = events_9_years + [
        LossEvent(
            event_id="E_2025",
            event_date=date(2025, 1, 1),
            discovery_date=date(2025, 1, 1),
            booking_date=date(2025, 1, 1),
            event_type="EXTERNAL_FRAUD",
            business_line="RETAIL_BANKING",
            gross_loss_amount=1.0,
        )
    ]
    
    lc, years, _ = compute_loss_component(events_10_years, years_required=10)
    assert years == 10
    assert lc > 0  # Now we have enough data


def test_ope25_ilm_cap_at_1():
    """Verify ILM is capped at 1.0 per OPE25."""
    # Even with very high LC/BIC ratio, ILM should not exceed 1.0
    ilm = compute_ilm(lc=100000, bic=100)
    assert ilm == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_result_to_dict(sample_bi_inputs, sample_loss_events):
    """Test SMAResult serialization to dict."""
    result = compute_sma_capital(sample_bi_inputs, sample_loss_events)
    
    result_dict = result.to_dict()
    
    assert "business_indicator_eur_m" in result_dict
    assert "bic_eur_m" in result_dict
    assert "loss_component_eur_m" in result_dict
    assert "ilm" in result_dict
    assert "operational_risk_capital_eur_m" in result_dict
    assert "rwa_operational_eur_m" in result_dict


def test_loss_event_to_dict():
    """Test LossEvent serialization to dict."""
    event = LossEvent(
        event_id="TEST_001",
        event_date=date(2024, 1, 1),
        discovery_date=date(2024, 1, 5),
        booking_date=date(2024, 1, 15),
        event_type="EXTERNAL_FRAUD",
        business_line="RETAIL_BANKING",
        gross_loss_amount=5.0,
    )
    
    event_dict = event.to_dict()
    
    assert event_dict["event_id"] == "TEST_001"
    assert event_dict["gross_loss_amount"] == 5.0
    assert event_dict["net_loss_amount"] == 5.0  # No recoveries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
