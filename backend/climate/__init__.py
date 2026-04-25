"""
Climate Risk Framework Module
==============================

ESG and climate risk integration per CRR3 Article 87a.
"""

from .esg_framework import (
    ESGClimateRiskEngine,
    SectorClimate,
    RiskZone,
    TransitionRiskLevel,
    apply_climate_risk_adjustment,
    SECTOR_CLIMATE_CALIBRATION,
)

__all__ = [
    "ESGClimateRiskEngine",
    "SectorClimate",
    "RiskZone",
    "TransitionRiskLevel",
    "apply_climate_risk_adjustment",
    "SECTOR_CLIMATE_CALIBRATION",
]

