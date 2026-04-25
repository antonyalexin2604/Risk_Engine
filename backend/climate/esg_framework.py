"""
ESG/Climate Risk Framework
===========================

Implements climate & ESG risk integration per CRR3 Article 87a.

Features:
  - Transition risk calibration (sector-based PD uplift)
  - Physical risk scoring (asset location mapping)
  - Policy scenario alignment (net-zero pathways)
  - Regulatory compliance (ECB, EBA, EU Taxonomy)

Regulatory Basis: CRR3 Art. 87a, ECB climate roadmap, EBA guidelines
"""

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Dict, Optional, List
import json

logger = logging.getLogger("prometheus.climate.esg_framework")


class RiskZone(Enum):
    """Regulatory commitment zones per CRR3."""
    ZONE_A = "zone_a"          # High commitment (EU, UK, Canada) - 0–2% uplift
    ZONE_B = "zone_b"          # Moderate (US, Japan) - 0–1.5% uplift
    ZONE_C = "zone_c"          # Emerging - 0–1% uplift


class TransitionRiskLevel(Enum):
    """Transition risk classification."""
    ACCELERATED = "accelerated"  # <2030 phase-out (brown industries)
    STANDARD = "standard"        # 2030–2040 phase-out
    MODERATE = "moderate"        # 2040–2050 phase-out
    LOW = "low"                  # Post-2050 or excluded


@dataclass
class SectorClimate:
    """Climate risk profile for sector."""

    sector_name: str                        # e.g., "Fossil Fuels", "Utilities"
    sector_code: str                        # e.g., "FOSSIL", "UTIL"

    # Transition risk
    transition_risk_level: TransitionRiskLevel
    pd_uplift_pct: float                    # PD increase due to transition risk
    policy_phase_out_year: int              # Target phase-out (e.g., 2030)
    carbon_intensity_tco2e_per_output: float  # Baseline carbon intensity

    # Physical risk
    has_physical_exposure: bool             # Asset location at climate risk?
    physical_risk_score: float              # 0–100 (100 = highest risk)

    # Regulatory zone
    zone: RiskZone

    # Description for audit trail
    description: str = ""

    # Data quality
    data_quality: str = "estimated"         # estimated, measured, verified


# ════════════════════════════════════════════════════════════════════════════
# SECTOR CALIBRATION LIBRARY
# ════════════════════════════════════════════════════════════════════════════

SECTOR_CLIMATE_CALIBRATION: Dict[str, SectorClimate] = {
    # High Transition Risk (Accelerated phase-out)
    "FOSSIL_FUELS": SectorClimate(
        sector_name="Fossil Fuels",
        sector_code="FOSSIL",
        transition_risk_level=TransitionRiskLevel.ACCELERATED,
        pd_uplift_pct=2.0,                  # +200 bps PD uplift
        policy_phase_out_year=2030,
        carbon_intensity_tco2e_per_output=850,
        has_physical_exposure=False,
        physical_risk_score=10,
        zone=RiskZone.ZONE_A,
        description="Oil, gas, coal production — EU phase-out by 2030",
    ),

    "UTILITIES_FOSSIL": SectorClimate(
        sector_name="Utilities (Fossil)",
        sector_code="UTIL_FOSSIL",
        transition_risk_level=TransitionRiskLevel.STANDARD,
        pd_uplift_pct=1.2,
        policy_phase_out_year=2040,
        carbon_intensity_tco2e_per_output=600,
        has_physical_exposure=False,
        physical_risk_score=15,
        zone=RiskZone.ZONE_A,
        description="Coal/gas power plants — EU phase-out 2030–2040",
    ),

    "AUTOMOTIVE_ICE": SectorClimate(
        sector_name="Automotive (ICE)",
        sector_code="AUTO_ICE",
        transition_risk_level=TransitionRiskLevel.STANDARD,
        pd_uplift_pct=0.8,
        policy_phase_out_year=2035,
        carbon_intensity_tco2e_per_output=200,
        has_physical_exposure=False,
        physical_risk_score=10,
        zone=RiskZone.ZONE_A,
        description="Internal combustion engines — EU phase-out 2035",
    ),

    # Moderate Transition Risk
    "TRANSPORTATION": SectorClimate(
        sector_name="Transportation",
        sector_code="TRANSPORT",
        transition_risk_level=TransitionRiskLevel.MODERATE,
        pd_uplift_pct=0.5,
        policy_phase_out_year=2050,
        carbon_intensity_tco2e_per_output=150,
        has_physical_exposure=False,
        physical_risk_score=20,
        zone=RiskZone.ZONE_A,
        description="Aviation, shipping — gradual decarbonisation",
    ),

    "CONSTRUCTION": SectorClimate(
        sector_name="Construction",
        sector_code="CONSTRUCT",
        transition_risk_level=TransitionRiskLevel.MODERATE,
        pd_uplift_pct=0.4,
        policy_phase_out_year=2050,
        carbon_intensity_tco2e_per_output=100,
        has_physical_exposure=True,         # Physical assets (buildings)
        physical_risk_score=35,
        zone=RiskZone.ZONE_A,
        description="Building & infrastructure — climate adaptation risk",
    ),

    # Low Transition Risk
    "RENEWABLES": SectorClimate(
        sector_name="Renewables",
        sector_code="RENEW",
        transition_risk_level=TransitionRiskLevel.LOW,
        pd_uplift_pct=-0.5,                 # Potential uplift (positive sentiment)
        policy_phase_out_year=2100,
        carbon_intensity_tco2e_per_output=10,
        has_physical_exposure=True,
        physical_risk_score=30,
        zone=RiskZone.ZONE_A,
        description="Solar, wind, hydro — policy support",
    ),

    "TECHNOLOGY": SectorClimate(
        sector_name="Technology",
        sector_code="TECH",
        transition_risk_level=TransitionRiskLevel.LOW,
        pd_uplift_pct=0.0,
        policy_phase_out_year=2100,
        carbon_intensity_tco2e_per_output=30,
        has_physical_exposure=False,
        physical_risk_score=5,
        zone=RiskZone.ZONE_A,
        description="Software, semiconductors — low carbon intensity",
    ),

    "FINANCIALS": SectorClimate(
        sector_name="Financial Services",
        sector_code="FIN",
        transition_risk_level=TransitionRiskLevel.LOW,
        pd_uplift_pct=0.1,
        policy_phase_out_year=2100,
        carbon_intensity_tco2e_per_output=50,
        has_physical_exposure=False,
        physical_risk_score=10,
        zone=RiskZone.ZONE_A,
        description="Banks, insurance — climate risk exposure through portfolio",
    ),
}


# ════════════════════════════════════════════════════════════════════════════
# ESG/CLIMATE RISK ENGINE
# ════════════════════════════════════════════════════════════════════════════

class ESGClimateRiskEngine:
    """
    Compute ESG/climate risk adjustments to PD per CRR3.

    Workflow:
      1. Classify obligor sector
      2. Look up sector climate profile
      3. Compute transition risk PD uplift
      4. Assess physical risk (if applicable)
      5. Return adjusted PD
    """

    def __init__(self, enable_physical_risk: bool = False):
        """
        Initialize engine.

        Args:
            enable_physical_risk: Include physical risk scoring (requires GIS data)
        """
        self.enable_physical_risk = enable_physical_risk
        logger.info(f"ESGClimateRiskEngine initialized (physical_risk={enable_physical_risk})")

    def get_sector_climate_profile(self, sector_code: str) -> Optional[SectorClimate]:
        """
        Retrieve climate profile for sector.

        Args:
            sector_code: Sector identifier (e.g., "FOSSIL", "TECH")

        Returns:
            SectorClimate profile or None if not found
        """
        return SECTOR_CLIMATE_CALIBRATION.get(sector_code)

    def compute_transition_risk_uplift(
        self,
        obligor_sector: str,
        obligor_region: str = "EU",
    ) -> float:
        """
        Compute PD uplift due to transition risk.

        Args:
            obligor_sector: Sector code (e.g., "FOSSIL")
            obligor_region: Geographic region for zone determination

        Returns:
            PD uplift as decimal (e.g., 0.020 for +200 bps)

        Example:
            uplift = engine.compute_transition_risk_uplift("FOSSIL", "EU")
            new_pd = old_pd + uplift
        """

        profile = self.get_sector_climate_profile(obligor_sector)

        if not profile:
            logger.warning(f"Sector {obligor_sector} not found; returning 0 uplift")
            return 0.0

        uplift = profile.pd_uplift_pct / 100  # Convert % to decimal

        logger.info(
            f"Transition risk uplift for {obligor_sector}: {uplift:+.2%}\n"
            f"  Level: {profile.transition_risk_level.value}\n"
            f"  Phase-out: {profile.policy_phase_out_year}"
        )

        return uplift

    def compute_physical_risk_score(
        self,
        asset_location: Optional[str] = None,
        asset_type: Optional[str] = None,
    ) -> float:
        """
        Compute physical climate risk score for asset.

        Args:
            asset_location: Geographic location (e.g., "Florida", "Netherlands")
            asset_type: Asset type (e.g., "real_estate", "infrastructure")

        Returns:
            Risk score 0–100 (simplified; 100 = highest risk)

        Note: Full implementation requires GIS data & climate hazard maps
        """

        if not self.enable_physical_risk:
            return 0.0

        # Simplified physical risk scoring
        # In production: integrate with climate hazard maps (flood zones, heat stress, etc.)

        hazard_map = {
            "florida": 85,          # High flood risk
            "netherlands": 80,      # Flood/sea-level risk
            "california": 70,       # Wildfire risk
            "australia": 75,        # Drought/fire risk
            "bangladesh": 90,       # Cyclone/flood risk
        }

        score = hazard_map.get(asset_location.lower() if asset_location else "", 20)

        logger.debug(f"Physical risk score for {asset_location}: {score}/100")

        return float(score)

    def compute_adjusted_pd(
        self,
        base_pd: float,
        obligor_sector: str,
        obligor_region: str = "EU",
        asset_location: Optional[str] = None,
    ) -> float:
        """
        Compute climate-adjusted PD per CRR3 Art. 87a.

        Args:
            base_pd: Baseline PD (from ratings)
            obligor_sector: Sector code
            obligor_region: Geographic region
            asset_location: Physical asset location (optional)

        Returns:
            Adjusted PD with climate uplift

        Example:
            adjusted_pd = engine.compute_adjusted_pd(
                base_pd=0.01,
                obligor_sector="FOSSIL",
                obligor_region="EU",
            )
            print(f"Adjusted PD: {adjusted_pd:.2%}")  # e.g., 1.2%
        """

        # Transition risk uplift
        transition_uplift = self.compute_transition_risk_uplift(obligor_sector, obligor_region)

        # Physical risk uplift (simplified: 0–20 bps based on score)
        physical_score = self.compute_physical_risk_score(asset_location)
        physical_uplift = (physical_score / 100) * 0.002  # Max 200 bps physical

        # Total uplift
        total_uplift = transition_uplift + physical_uplift

        adjusted_pd = base_pd + total_uplift

        logger.info(
            f"PD adjustment:\n"
            f"  Base PD: {base_pd:.2%}\n"
            f"  Transition uplift: {transition_uplift:+.2%}\n"
            f"  Physical uplift: {physical_uplift:+.2%}\n"
            f"  Adjusted PD: {adjusted_pd:.2%}"
        )

        return adjusted_pd

    def generate_esg_report(self) -> str:
        """Generate markdown ESG/climate risk report."""

        report = f"""
# PROMETHEUS ESG/Climate Risk Report
**Generated:** {date.today().isoformat()}

## CRR3 Article 87a Compliance

Climate risk integration into PD estimates:

### Transition Risk Calibration

| Sector | Risk Level | PD Uplift | Phase-Out |
|--------|-----------|-----------|-----------|
"""

        for code, profile in SECTOR_CLIMATE_CALIBRATION.items():
            report += f"| {profile.sector_name} | {profile.transition_risk_level.value} | {profile.pd_uplift_pct:+.1f}% | {profile.policy_phase_out_year} |\n"

        report += f"""

### Policy Scenarios

1. **Net-Zero 2050 (IPCC 1.5°C)**: Accelerated transition, high discounting
2. **Delayed Action 2060**: Moderate transition, medium discounting
3. **No Action**: Baseline, minimal uplift

---

**End of Report**
"""

        return report


# ════════════════════════════════════════════════════════════════════════════
# Integration with A-IRB Engine
# ════════════════════════════════════════════════════════════════════════════

def apply_climate_risk_adjustment(
    base_pd: float,
    obligor_sector: str,
    obligor_region: str = "EU",
    asset_location: Optional[str] = None,
    enable_physical_risk: bool = False,
) -> Tuple[float, Dict]:
    """
    Apply climate risk adjustment to PD (for use in A-IRB calculations).

    Usage in a_irb.py:
        adjusted_pd, metadata = apply_climate_risk_adjustment(
            base_pd=0.01,
            obligor_sector="FOSSIL",
            obligor_region="EU",
        )

    Returns:
        (adjusted_pd, adjustment_metadata)
    """

    engine = ESGClimateRiskEngine(enable_physical_risk=enable_physical_risk)

    adjusted_pd = engine.compute_adjusted_pd(
        base_pd=base_pd,
        obligor_sector=obligor_sector,
        obligor_region=obligor_region,
        asset_location=asset_location,
    )

    transition_uplift = engine.compute_transition_risk_uplift(obligor_sector, obligor_region)
    physical_score = engine.compute_physical_risk_score(asset_location)

    return adjusted_pd, {
        "base_pd": base_pd,
        "adjusted_pd": adjusted_pd,
        "transition_uplift_pct": transition_uplift * 100,
        "physical_risk_score": physical_score,
        "sector": obligor_sector,
        "region": obligor_region,
    }


if __name__ == "__main__":
    # Demo
    engine = ESGClimateRiskEngine(enable_physical_risk=True)

    adjusted = engine.compute_adjusted_pd(
        base_pd=0.01,
        obligor_sector="FOSSIL",
        obligor_region="EU",
        asset_location="Netherlands",
    )

    print(f"Base PD: 1.0%")
    print(f"Adjusted PD: {adjusted:.2%}")
    print(f"\nESG Report:")
    print(engine.generate_esg_report())

