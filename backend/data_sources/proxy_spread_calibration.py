"""
PROMETHEUS Risk Platform
Proxy Spread Calibration Module — MAR50.32(3) Compliance

Maintains monthly-reviewed proxy credit spread calibrations for illiquid counterparties.

Regulatory Requirement (MAR50.32(3)):
    "Banks must estimate spreads from LIQUID PEERS via a documented sector + rating
    + region mapping algorithm. This mapping must be calibrated to live peer CDS
    data and REVIEWED AT LEAST MONTHLY by the credit desk."

Key Compliance Features:
    1. Calibration metadata with review dates
    2. Peer CDS name audit trail
    3. Stale calibration alerts (>30 days)
    4. Review workflow tracking
    5. Historical calibration archive
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class ProxySpreadCalibration:
    """
    MAR50.32(3) compliant proxy spread calibration record.

    Each calibration represents the estimated CDS spread for a specific
    sector/credit_quality/region combination, derived from liquid peer names.
    """
    sector: str                    # 'Financials', 'Energy', 'Consumer', etc.
    credit_quality: str            # 'IG', 'HY', 'NR'
    region: str                    # 'US', 'EUR', 'EM', etc.
    calibrated_spread_bps: float   # Estimated spread in basis points
    calibration_date: date         # When this calibration was performed
    peer_names: List[str]          # Liquid CDS reference names used
    peer_spreads: List[float]      # Their live spreads (bps) at calibration_date
    review_status: str             # 'APPROVED' | 'PENDING' | 'EXPIRED' | 'REJECTED'
    reviewer: str                  # Credit desk analyst email/name
    next_review_date: date         # Must review by this date (max 30 days)
    notes: str = ""                # Optional reviewer notes

    def is_stale(self, as_of_date: Optional[date] = None) -> bool:
        """
        Check if calibration is stale (>30 days old or past review date).
        Stale calibrations should not be used for regulatory capital.
        """
        as_of = as_of_date or date.today()
        return (
            as_of > self.next_review_date or
            (as_of - self.calibration_date).days > 30 or
            self.review_status != "APPROVED"
        )

    def days_until_review(self, as_of_date: Optional[date] = None) -> int:
        """Days remaining until next review. Negative = overdue."""
        as_of = as_of_date or date.today()
        return (self.next_review_date - as_of).days

    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        return {
            "sector": self.sector,
            "credit_quality": self.credit_quality,
            "region": self.region,
            "calibrated_spread_bps": self.calibrated_spread_bps,
            "calibration_date": self.calibration_date.isoformat(),
            "peer_names": self.peer_names,
            "peer_spreads": self.peer_spreads,
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "next_review_date": self.next_review_date.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProxySpreadCalibration:
        """Deserialize from JSON."""
        return cls(
            sector=data["sector"],
            credit_quality=data["credit_quality"],
            region=data["region"],
            calibrated_spread_bps=data["calibrated_spread_bps"],
            calibration_date=date.fromisoformat(data["calibration_date"]),
            peer_names=data["peer_names"],
            peer_spreads=data["peer_spreads"],
            review_status=data["review_status"],
            reviewer=data["reviewer"],
            next_review_date=date.fromisoformat(data["next_review_date"]),
            notes=data.get("notes", ""),
        )


class ProxySpreadRegistry:
    """
    Central registry for proxy spread calibrations.

    Production deployment:
        - Store calibrations in PostgreSQL table `cva.proxy_spread_calibrations`
        - Integrate with credit desk review workflow (email alerts, dashboard)
        - Archive historical calibrations for audit trail
        - Log all calibration updates for compliance review
    """

    def __init__(self, calibration_file: Optional[str] = None):
        """
        Parameters
        ----------
        calibration_file : Path to JSON file storing calibrations.
                          Default: backend/data_sources/proxy_spread_calibrations.json
        """
        if calibration_file is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            calibration_file = os.path.join(base_dir, "proxy_spread_calibrations.json")

        self.calibration_file = calibration_file
        self.calibrations: Dict[Tuple[str, str, str], ProxySpreadCalibration] = {}
        self._load()

    def _load(self) -> None:
        """Load calibrations from JSON file."""
        if not os.path.exists(self.calibration_file):
            logger.warning(
                "Proxy spread calibration file not found: %s — using empty registry",
                self.calibration_file,
            )
            return

        try:
            with open(self.calibration_file, "r") as f:
                data = json.load(f)

            for cal_dict in data.get("calibrations", []):
                cal = ProxySpreadCalibration.from_dict(cal_dict)
                key = (cal.sector, cal.credit_quality, cal.region)
                self.calibrations[key] = cal

            logger.info(
                "Loaded %d proxy spread calibrations from %s",
                len(self.calibrations), self.calibration_file,
            )
        except Exception as exc:
            logger.error(
                "Failed to load proxy spread calibrations from %s: %s",
                self.calibration_file, exc,
            )

    def save(self) -> None:
        """Persist calibrations to JSON file."""
        try:
            data = {
                "last_updated": date.today().isoformat(),
                "calibrations": [cal.to_dict() for cal in self.calibrations.values()],
            }
            with open(self.calibration_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Saved %d calibrations to %s", len(self.calibrations), self.calibration_file)
        except Exception as exc:
            logger.error("Failed to save calibrations: %s", exc)

    def get_calibration(
        self,
        sector: str,
        credit_quality: str,
        region: str,
        allow_stale: bool = False,
    ) -> Optional[ProxySpreadCalibration]:
        """
        Retrieve calibration for sector/credit_quality/region.

        Parameters
        ----------
        allow_stale : If False (default), return None for stale calibrations.
                      This forces the caller to handle missing/expired data.

        Returns
        -------
        ProxySpreadCalibration if found and fresh (or allow_stale=True), else None.
        """
        key = (sector, credit_quality, region)
        cal = self.calibrations.get(key)

        if cal is None:
            return None

        if not allow_stale and cal.is_stale():
            logger.warning(
                "Proxy spread calibration STALE: %s/%s/%s — calibrated %s, "
                "review due %s, status=%s",
                sector, credit_quality, region,
                cal.calibration_date.isoformat(),
                cal.next_review_date.isoformat(),
                cal.review_status,
            )
            return None

        return cal

    def add_or_update_calibration(self, calibration: ProxySpreadCalibration) -> None:
        """
        Add new calibration or update existing one.
        Automatically saves to file.
        """
        key = (calibration.sector, calibration.credit_quality, calibration.region)
        self.calibrations[key] = calibration
        self.save()
        logger.info(
            "Updated proxy calibration: %s/%s/%s → %.0f bps (reviewer: %s)",
            calibration.sector, calibration.credit_quality, calibration.region,
            calibration.calibrated_spread_bps, calibration.reviewer,
        )

    def get_stale_calibrations(self, as_of_date: Optional[date] = None) -> List[ProxySpreadCalibration]:
        """
        Return all stale calibrations requiring review.
        Use for daily monitoring / email alerts.
        """
        as_of = as_of_date or date.today()
        return [
            cal for cal in self.calibrations.values()
            if cal.is_stale(as_of)
        ]

    def get_calibrations_due_for_review(self, days_ahead: int = 7) -> List[ProxySpreadCalibration]:
        """
        Return calibrations due for review within `days_ahead` days.
        Use for proactive review scheduling.
        """
        cutoff = date.today() + timedelta(days=days_ahead)
        return [
            cal for cal in self.calibrations.values()
            if cal.next_review_date <= cutoff and cal.review_status == "APPROVED"
        ]

    def export_audit_report(self, output_file: str) -> None:
        """
        Export full calibration audit trail to CSV for regulatory review.
        """
        import csv
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "sector", "credit_quality", "region", "spread_bps",
                "calibration_date", "next_review_date", "days_until_review",
                "status", "reviewer", "peer_count", "peer_names",
            ])
            writer.writeheader()
            for cal in sorted(self.calibrations.values(), key=lambda c: c.calibration_date):
                writer.writerow({
                    "sector": cal.sector,
                    "credit_quality": cal.credit_quality,
                    "region": cal.region,
                    "spread_bps": f"{cal.calibrated_spread_bps:.1f}",
                    "calibration_date": cal.calibration_date.isoformat(),
                    "next_review_date": cal.next_review_date.isoformat(),
                    "days_until_review": cal.days_until_review(),
                    "status": cal.review_status,
                    "reviewer": cal.reviewer,
                    "peer_count": len(cal.peer_names),
                    "peer_names": ", ".join(cal.peer_names),
                })
        logger.info("Exported proxy spread audit report to %s", output_file)


def initialize_default_calibrations() -> ProxySpreadRegistry:
    """
    Create initial calibration set with sensible defaults.

    PRODUCTION: Replace these static values with live peer CDS data from:
        - Bloomberg CDS screens (CDSW)
        - Markit CDX/iTraxx indices
        - Internal credit desk spread feeds

    This function should be run ONCE to bootstrap the registry, then
    replaced with monthly live calibration updates from the credit desk.
    """
    registry = ProxySpreadRegistry()

    # Example calibrations — replace with live data
    default_calibrations = [
        # US Financials
        ProxySpreadCalibration(
            sector="Financials", credit_quality="IG", region="US",
            calibrated_spread_bps=110.0,
            calibration_date=date.today() - timedelta(days=15),
            peer_names=["JPM 5Y CDS", "BAC 5Y CDS", "C 5Y CDS", "WFC 5Y CDS"],
            peer_spreads=[95.0, 105.0, 120.0, 118.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=15),
            notes="Calibrated from Big 4 US bank CDS spreads"
        ),
        ProxySpreadCalibration(
            sector="Financials", credit_quality="HY", region="US",
            calibrated_spread_bps=420.0,
            calibration_date=date.today() - timedelta(days=10),
            peer_names=["Regional Bank A", "Regional Bank B"],
            peer_spreads=[410.0, 430.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=20),
        ),
        # US Energy
        ProxySpreadCalibration(
            sector="Energy", credit_quality="IG", region="US",
            calibrated_spread_bps=130.0,
            calibration_date=date.today() - timedelta(days=20),
            peer_names=["XOM 5Y CDS", "CVX 5Y CDS", "COP 5Y CDS"],
            peer_spreads=[115.0, 125.0, 145.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=10),
        ),
        ProxySpreadCalibration(
            sector="Energy", credit_quality="HY", region="US",
            calibrated_spread_bps=480.0,
            calibration_date=date.today() - timedelta(days=12),
            peer_names=["OXY 5Y CDS", "APA 5Y CDS"],
            peer_spreads=[465.0, 495.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=18),
        ),
        # US Technology
        ProxySpreadCalibration(
            sector="Technology", credit_quality="IG", region="US",
            calibrated_spread_bps=100.0,
            calibration_date=date.today() - timedelta(days=8),
            peer_names=["AAPL 5Y CDS", "MSFT 5Y CDS", "ORCL 5Y CDS"],
            peer_spreads=[85.0, 90.0, 115.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=22),
        ),
        # EUR Financials
        ProxySpreadCalibration(
            sector="Financials", credit_quality="IG", region="EUR",
            calibrated_spread_bps=120.0,
            calibration_date=date.today() - timedelta(days=18),
            peer_names=["DBK 5Y CDS", "BNP 5Y CDS", "SAN 5Y CDS"],
            peer_spreads=[135.0, 105.0, 120.0],
            review_status="APPROVED",
            reviewer="credit.desk@prometheus.risk",
            next_review_date=date.today() + timedelta(days=12),
        ),
    ]

    for cal in default_calibrations:
        registry.add_or_update_calibration(cal)

    logger.info("Initialized %d default proxy spread calibrations", len(default_calibrations))
    return registry


# Singleton registry for application-wide use
_GLOBAL_REGISTRY: Optional[ProxySpreadRegistry] = None

def get_proxy_spread_registry() -> ProxySpreadRegistry:
    """Get the global proxy spread registry (lazy initialization)."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ProxySpreadRegistry()
        if not _GLOBAL_REGISTRY.calibrations:
            # Bootstrap with defaults if empty
            logger.warning(
                "Proxy spread registry empty — initializing with default calibrations. "
                "PRODUCTION: Replace with live peer CDS calibration workflow."
            )
            _GLOBAL_REGISTRY = initialize_default_calibrations()
    return _GLOBAL_REGISTRY

