"""
PROMETHEUS Scenario Analysis Module
====================================

Regulatory scenario library and portfolio stress testing framework.

Components:
  - Scenario definitions (BCBS, ECB, FED regulatory + custom)
  - Scenario engine (apply shocks to market parameters)
  - Portfolio re-pricing (compute RWA under each scenario)
  - Backtesting & validation

Reference: MAR31 (IMA scenarios), CRE99 (backtesting)
"""

from .library import (
    Scenario,
    ScenarioType,
    get_regulatory_scenario,
    get_all_scenarios,
)
from .engine import ScenarioAnalysisEngine

__all__ = [
    "Scenario",
    "ScenarioType",
    "get_regulatory_scenario",
    "get_all_scenarios",
    "ScenarioAnalysisEngine",
]

