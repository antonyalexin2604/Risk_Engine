"""
PROMETHEUS Risk Platform
Unit Tests for Proxy Spread Calibration Module

Test Coverage:
- ProxySpreadCalibration dataclass functionality
- ProxySpreadRegistry CRUD operations
- Stale calibration detection (MAR50.32(3) compliance)
- Review workflow mechanics
- Audit trail export
- Edge cases and error handling

Run: pytest test_proxy_spread_calibration.py -v
"""

import pytest
from datetime import date, timedelta
import json
import os
import tempfile
from pathlib import Path

# Assuming proxy_spread_calibration.py is in backend/data_sources/
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.data_sources.proxy_spread_calibration import (
    ProxySpreadCalibration,
    ProxySpreadRegistry,
    initialize_default_calibrations,
)


class TestProxySpreadCalibration:
    """Test ProxySpreadCalibration dataclass"""

    def test_calibration_creation(self):
        """Test basic calibration object creation"""
        cal = ProxySpreadCalibration(
            sector="Financials",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=110.0,
            calibration_date=date(2026, 3, 1),
            peer_names=["JPM 5Y CDS", "BAC 5Y CDS"],
            peer_spreads=[95.0, 105.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date(2026, 3, 31),
        )
        
        assert cal.sector == "Financials"
        assert cal.credit_quality == "IG"
        assert cal.region == "US"
        assert cal.calibrated_spread_bps == 110.0
        assert len(cal.peer_names) == 2

    def test_is_stale_approved_within_30_days(self):
        """Fresh approved calibration should NOT be stale"""
        cal = ProxySpreadCalibration(
            sector="Energy",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=10),
            peer_names=["XOM 5Y CDS"],
            peer_spreads=[115.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),
        )
        
        assert not cal.is_stale()
        assert cal.days_until_review() == 20

    def test_is_stale_over_30_days(self):
        """Calibration >30 days old IS stale (MAR50.32(3))"""
        cal = ProxySpreadCalibration(
            sector="Energy",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=35),
            peer_names=["XOM 5Y CDS"],
            peer_spreads=[115.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() - timedelta(days=5),  # Past due
        )
        
        assert cal.is_stale()

    def test_is_stale_past_review_date(self):
        """Calibration past review date IS stale"""
        cal = ProxySpreadCalibration(
            sector="Technology",
            credit_quality="HY",
            region="EUR",
            calibrated_spread_bps=450.0,
            calibration_date=date.today() - timedelta(days=15),
            peer_names=["TECH1"],
            peer_spreads=[440.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() - timedelta(days=1),  # Overdue by 1 day
        )
        
        assert cal.is_stale()
        assert cal.days_until_review() == -1  # Negative = overdue

    def test_is_stale_non_approved_status(self):
        """Non-APPROVED status IS stale regardless of dates"""
        for status in ["PENDING", "EXPIRED", "REJECTED"]:
            cal = ProxySpreadCalibration(
                sector="Consumer",
                credit_quality="IG",
                region="US",
                calibrated_spread_bps=120.0,
                calibration_date=date.today() - timedelta(days=5),
                peer_names=["WMT 5Y CDS"],
                peer_spreads=[110.0],
                review_status=status,
                reviewer="test@prometheus.risk",
                next_review_date=date.today() + timedelta(days=25),
            )
            assert cal.is_stale(), f"Status {status} should be stale"

    def test_serialization_roundtrip(self):
        """Test to_dict() and from_dict() preserve data"""
        original = ProxySpreadCalibration(
            sector="Financials",
            credit_quality="HY",
            region="EUR",
            calibrated_spread_bps=420.0,
            calibration_date=date(2026, 2, 15),
            peer_names=["BANK1", "BANK2"],
            peer_spreads=[410.0, 430.0],
            review_status="APPROVED",
            reviewer="analyst@prometheus.risk",
            next_review_date=date(2026, 3, 15),
            notes="Based on European regional banks"
        )
        
        serialized = original.to_dict()
        deserialized = ProxySpreadCalibration.from_dict(serialized)
        
        assert deserialized.sector == original.sector
        assert deserialized.credit_quality == original.credit_quality
        assert deserialized.region == original.region
        assert deserialized.calibrated_spread_bps == original.calibrated_spread_bps
        assert deserialized.calibration_date == original.calibration_date
        assert deserialized.peer_names == original.peer_names
        assert deserialized.peer_spreads == original.peer_spreads
        assert deserialized.review_status == original.review_status
        assert deserialized.reviewer == original.reviewer
        assert deserialized.next_review_date == original.next_review_date
        assert deserialized.notes == original.notes


class TestProxySpreadRegistry:
    """Test ProxySpreadRegistry operations"""

    @pytest.fixture
    def temp_registry_file(self):
        """Create temporary JSON file for testing"""
        fd, path = tempfile.mkstemp(suffix='.json')
        os.close(fd)
        yield path
        os.unlink(path)

    @pytest.fixture
    def registry(self, temp_registry_file):
        """Create registry with temp file"""
        return ProxySpreadRegistry(calibration_file=temp_registry_file)

    def test_empty_registry_initialization(self, registry):
        """New registry should be empty"""
        assert len(registry.calibrations) == 0

    def test_add_calibration(self, registry):
        """Test adding a new calibration"""
        cal = ProxySpreadCalibration(
            sector="Financials",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=110.0,
            calibration_date=date.today(),
            peer_names=["JPM 5Y CDS"],
            peer_spreads=[105.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=30),
        )
        
        registry.add_or_update_calibration(cal)
        
        assert len(registry.calibrations) == 1
        key = ("Financials", "IG", "US")
        assert key in registry.calibrations

    def test_update_existing_calibration(self, registry):
        """Test updating an existing calibration (same sector/quality/region)"""
        # Add initial
        cal1 = ProxySpreadCalibration(
            sector="Energy",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=30),
            peer_names=["XOM 5Y CDS"],
            peer_spreads=[125.0],
            review_status="APPROVED",
            reviewer="old@prometheus.risk",
            next_review_date=date.today(),
        )
        registry.add_or_update_calibration(cal1)
        
        # Update with new values
        cal2 = ProxySpreadCalibration(
            sector="Energy",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=135.0,  # Updated spread
            calibration_date=date.today(),
            peer_names=["XOM 5Y CDS", "CVX 5Y CDS"],  # More peers
            peer_spreads=[130.0, 140.0],
            review_status="APPROVED",
            reviewer="new@prometheus.risk",  # New reviewer
            next_review_date=date.today() + timedelta(days=30),
        )
        registry.add_or_update_calibration(cal2)
        
        assert len(registry.calibrations) == 1  # Still only 1 entry
        
        key = ("Energy", "IG", "US")
        stored = registry.calibrations[key]
        assert stored.calibrated_spread_bps == 135.0  # Updated value
        assert stored.reviewer == "new@prometheus.risk"
        assert len(stored.peer_names) == 2

    def test_get_calibration_success(self, registry):
        """Test retrieving an existing calibration"""
        cal = ProxySpreadCalibration(
            sector="Technology",
            credit_quality="IG",
            region="US",
            calibrated_spread_bps=100.0,
            calibration_date=date.today() - timedelta(days=10),
            peer_names=["AAPL 5Y CDS"],
            peer_spreads=[85.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),
        )
        registry.add_or_update_calibration(cal)
        
        retrieved = registry.get_calibration("Technology", "IG", "US")
        
        assert retrieved is not None
        assert retrieved.calibrated_spread_bps == 100.0

    def test_get_calibration_not_found(self, registry):
        """Test retrieving non-existent calibration"""
        result = registry.get_calibration("NonExistent", "IG", "US")
        assert result is None

    def test_get_calibration_reject_stale(self, registry):
        """Test that stale calibrations are rejected by default"""
        stale_cal = ProxySpreadCalibration(
            sector="Financials",
            credit_quality="HY",
            region="EUR",
            calibrated_spread_bps=420.0,
            calibration_date=date.today() - timedelta(days=40),  # >30 days
            peer_names=["BANK1"],
            peer_spreads=[410.0],
            review_status="APPROVED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() - timedelta(days=10),  # Past due
        )
        registry.add_or_update_calibration(stale_cal)
        
        # Should return None when allow_stale=False (default)
        result = registry.get_calibration("Financials", "HY", "EUR", allow_stale=False)
        assert result is None

    def test_get_calibration_allow_stale(self, registry):
        """Test that stale calibrations can be retrieved if explicitly allowed"""
        stale_cal = ProxySpreadCalibration(
            sector="Financials",
            credit_quality="HY",
            region="EUR",
            calibrated_spread_bps=420.0,
            calibration_date=date.today() - timedelta(days=40),
            peer_names=["BANK1"],
            peer_spreads=[410.0],
            review_status="EXPIRED",
            reviewer="test@prometheus.risk",
            next_review_date=date.today() - timedelta(days=10),
        )
        registry.add_or_update_calibration(stale_cal)
        
        # Should return calibration when allow_stale=True
        result = registry.get_calibration("Financials", "HY", "EUR", allow_stale=True)
        assert result is not None
        assert result.calibrated_spread_bps == 420.0

    def test_get_stale_calibrations(self, registry):
        """Test identifying stale calibrations"""
        # Add 2 fresh, 2 stale
        fresh1 = ProxySpreadCalibration(
            sector="Energy", credit_quality="IG", region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=10),
            peer_names=["XOM"], peer_spreads=[125.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),
        )
        fresh2 = ProxySpreadCalibration(
            sector="Technology", credit_quality="IG", region="US",
            calibrated_spread_bps=100.0,
            calibration_date=date.today() - timedelta(days=5),
            peer_names=["AAPL"], peer_spreads=[85.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=25),
        )
        stale1 = ProxySpreadCalibration(
            sector="Financials", credit_quality="HY", region="EUR",
            calibrated_spread_bps=420.0,
            calibration_date=date.today() - timedelta(days=35),  # >30 days
            peer_names=["BANK1"], peer_spreads=[410.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() - timedelta(days=5),  # Overdue
        )
        stale2 = ProxySpreadCalibration(
            sector="Consumer", credit_quality="IG", region="US",
            calibrated_spread_bps=120.0,
            calibration_date=date.today() - timedelta(days=10),
            peer_names=["WMT"], peer_spreads=[115.0],
            review_status="PENDING",  # Not approved = stale
            reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),
        )
        
        for cal in [fresh1, fresh2, stale1, stale2]:
            registry.add_or_update_calibration(cal)
        
        stale_list = registry.get_stale_calibrations()
        
        assert len(stale_list) == 2
        assert stale1 in stale_list
        assert stale2 in stale_list

    def test_get_calibrations_due_for_review(self, registry):
        """Test identifying calibrations due for review soon"""
        # Add calibrations with different review dates
        due_soon = ProxySpreadCalibration(
            sector="Energy", credit_quality="IG", region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=20),
            peer_names=["XOM"], peer_spreads=[125.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=5),  # Due in 5 days
        )
        due_later = ProxySpreadCalibration(
            sector="Technology", credit_quality="IG", region="US",
            calibrated_spread_bps=100.0,
            calibration_date=date.today() - timedelta(days=5),
            peer_names=["AAPL"], peer_spreads=[85.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),  # Due in 20 days
        )
        
        registry.add_or_update_calibration(due_soon)
        registry.add_or_update_calibration(due_later)
        
        # Get calibrations due within 7 days
        due_list = registry.get_calibrations_due_for_review(days_ahead=7)
        
        assert len(due_list) == 1
        assert due_soon in due_list

    def test_persistence_across_registry_instances(self, temp_registry_file):
        """Test that calibrations persist across registry instances"""
        # Create first registry and add calibration
        registry1 = ProxySpreadRegistry(calibration_file=temp_registry_file)
        cal = ProxySpreadCalibration(
            sector="Financials", credit_quality="IG", region="US",
            calibrated_spread_bps=110.0,
            calibration_date=date.today(),
            peer_names=["JPM"], peer_spreads=[105.0],
            review_status="APPROVED", reviewer="test@prometheus.risk",
            next_review_date=date.today() + timedelta(days=30),
        )
        registry1.add_or_update_calibration(cal)
        
        # Create second registry from same file
        registry2 = ProxySpreadRegistry(calibration_file=temp_registry_file)
        
        # Should load the calibration
        assert len(registry2.calibrations) == 1
        retrieved = registry2.get_calibration("Financials", "IG", "US")
        assert retrieved is not None
        assert retrieved.calibrated_spread_bps == 110.0

    def test_export_audit_report(self, registry, tmp_path):
        """Test CSV audit report generation"""
        # Add sample calibrations
        cal1 = ProxySpreadCalibration(
            sector="Financials", credit_quality="IG", region="US",
            calibrated_spread_bps=110.0,
            calibration_date=date(2026, 3, 1),
            peer_names=["JPM 5Y CDS", "BAC 5Y CDS"],
            peer_spreads=[95.0, 105.0],
            review_status="APPROVED", reviewer="analyst1@prometheus.risk",
            next_review_date=date(2026, 3, 31),
        )
        cal2 = ProxySpreadCalibration(
            sector="Energy", credit_quality="HY", region="US",
            calibrated_spread_bps=480.0,
            calibration_date=date(2026, 2, 15),
            peer_names=["OXY 5Y CDS"],
            peer_spreads=[465.0],
            review_status="EXPIRED", reviewer="analyst2@prometheus.risk",
            next_review_date=date(2026, 2, 28),
        )
        
        registry.add_or_update_calibration(cal1)
        registry.add_or_update_calibration(cal2)
        
        # Export to CSV
        output_file = tmp_path / "audit_report.csv"
        registry.export_audit_report(str(output_file))
        
        # Verify file exists and has content
        assert output_file.exists()
        
        import csv
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            assert len(rows) == 2
            assert rows[0]['sector'] == 'Energy'  # Sorted by date (oldest first)
            assert rows[1]['sector'] == 'Financials'
            assert rows[0]['status'] == 'EXPIRED'
            assert rows[1]['peer_count'] == '2'


class TestDefaultCalibrations:
    """Test default calibration initialization"""

    def test_initialize_default_calibrations(self):
        """Test that default calibrations cover key sectors"""
        registry = initialize_default_calibrations()
        
        # Should have multiple calibrations
        assert len(registry.calibrations) > 0
        
        # Check for key sector/region combinations
        us_fin_ig = registry.get_calibration("Financials", "IG", "US")
        assert us_fin_ig is not None
        assert us_fin_ig.calibrated_spread_bps > 0
        
        us_energy_ig = registry.get_calibration("Energy", "IG", "US")
        assert us_energy_ig is not None
        
        us_tech_ig = registry.get_calibration("Technology", "IG", "US")
        assert us_tech_ig is not None

    def test_default_calibrations_have_peers(self):
        """Test that default calibrations include peer names"""
        registry = initialize_default_calibrations()
        
        for cal in registry.calibrations.values():
            assert len(cal.peer_names) > 0, "All calibrations should have peer names"
            assert len(cal.peer_spreads) == len(cal.peer_names), \
                "peer_spreads and peer_names should have same length"


# Run with: pytest test_proxy_spread_calibration.py -v --tb=short
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
