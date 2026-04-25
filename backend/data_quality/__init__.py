"""
Data Quality Management System Module
======================================

Automated data quality scorecard with 5 core metrics.
"""

from .dqms import (
    DataQualityEngine,
    DQScore,
    DQPortfolioScore,
    DQStatus,
    DQMetric,
    generate_dq_scorecard,
)

__all__ = [
    "DataQualityEngine",
    "DQScore",
    "DQPortfolioScore",
    "DQStatus",
    "DQMetric",
    "generate_dq_scorecard",
]

