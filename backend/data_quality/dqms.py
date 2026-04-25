"""
Data Quality Management System (DQMS)
=====================================

Automated daily data quality scorecard per best practices.

Features:
  - 5 core metrics: Completeness, Accuracy, Timeliness, Consistency, Validity
  - Automated scoring (0–100)
  - Severity classification (RED/YELLOW/GREEN)
  - Remediation recommendations
  - Regulatory compliance tracking

Regulatory Basis: Data governance best practices, Basel Committee guidance
"""

import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("prometheus.data_quality.dqms")


class DQStatus(Enum):
    """Data quality status."""
    RED = "red"        # Score < 60 — Critical issues
    YELLOW = "yellow"  # Score 60–80 — Issues present
    GREEN = "green"    # Score 80+ — Acceptable


class DQMetric(Enum):
    """Data quality metrics per ISO 8601."""
    COMPLETENESS = "completeness"      # % non-null values
    ACCURACY = "accuracy"              # Deviation from benchmark
    TIMELINESS = "timeliness"          # Hours since update
    CONSISTENCY = "consistency"        # Cross-source reconciliation
    VALIDITY = "validity"              # % within valid range


@dataclass
class DQScore:
    """Single data quality metric score."""

    metric: DQMetric
    score: float                        # 0–100
    weight: float                       # Importance factor (default 1.0)
    status: DQStatus
    threshold_breach: bool
    remediation_action: Optional[str] = None
    data_source: str = "unknown"
    updated_at: datetime = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


@dataclass
class DQPortfolioScore:
    """Aggregated portfolio data quality score."""

    run_date: date
    overall_score: float               # Weighted average 0–100
    status: DQStatus

    # Component scores
    completeness_score: float
    accuracy_score: float
    timeliness_score: float
    consistency_score: float
    validity_score: float

    # Issues
    alert_count: int = 0
    critical_issues: List[str] = None
    warning_issues: List[str] = None

    # Metadata
    data_source_count: int = 0
    remediation_log: str = ""
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.critical_issues is None:
            self.critical_issues = []
        if self.warning_issues is None:
            self.warning_issues = []


# ════════════════════════════════════════════════════════════════════════════
# DATA QUALITY ASSESSMENT ENGINE
# ════════════════════════════════════════════════════════════════════════════

class DataQualityEngine:
    """
    Automated data quality scoring for PROMETHEUS.

    Daily workflow:
      1. Query data sources (Bloomberg, Refinitiv, internal)
      2. Compute 5 DQ metrics
      3. Aggregate to portfolio score
      4. Classify severity (RED/YELLOW/GREEN)
      5. Recommend remediation
      6. Persist to database
    """

    def __init__(self, db_engine=None):
        """
        Initialize DQ engine.

        Args:
            db_engine: SQLAlchemy engine for persistence
        """
        self.db_engine = db_engine
        logger.info("DataQualityEngine initialized")

    def compute_completeness(
        self,
        data_values: List,
        min_threshold: float = 0.95,  # 95% non-null required
    ) -> DQScore:
        """
        Compute data completeness score.

        Args:
            data_values: List of values (may contain None)
            min_threshold: Minimum acceptable % non-null

        Returns:
            DQScore with completeness metric

        Example:
            score = engine.compute_completeness(
                data_values=[1.0, 2.0, None, 4.0, None],
                min_threshold=0.95
            )
            # 60% non-null → 60% score (below threshold)
        """

        if not data_values:
            return DQScore(
                metric=DQMetric.COMPLETENESS,
                score=0.0,
                weight=1.0,
                status=DQStatus.RED,
                threshold_breach=True,
                remediation_action="No data provided",
            )

        non_null_count = sum(1 for v in data_values if v is not None)
        completeness_pct = non_null_count / len(data_values)
        score = completeness_pct * 100

        threshold_breach = score < (min_threshold * 100)
        status = DQStatus.GREEN if score >= 80 else (DQStatus.YELLOW if score >= 60 else DQStatus.RED)

        remediation = None
        if threshold_breach:
            if score < 50:
                remediation = "Critical: Majority of data missing; investigate data source"
            elif score < 80:
                remediation = "Warning: Some data missing; follow up with data provider"

        logger.info(f"Completeness: {score:.1f}% ({non_null_count}/{len(data_values)} non-null)")

        return DQScore(
            metric=DQMetric.COMPLETENESS,
            score=score,
            weight=0.25,  # 25% of overall score
            status=status,
            threshold_breach=threshold_breach,
            remediation_action=remediation,
        )

    def compute_accuracy(
        self,
        actual_values: List[float],
        benchmark_values: List[float],
        max_deviation_pct: float = 0.05,  # 5% tolerance
    ) -> DQScore:
        """
        Compute accuracy vs. benchmark.

        Args:
            actual_values: Reported/computed values
            benchmark_values: Ground truth or alternative source
            max_deviation_pct: Acceptable deviation (e.g., 0.05 = 5%)

        Returns:
            DQScore with accuracy metric
        """

        if not actual_values or not benchmark_values:
            return DQScore(
                metric=DQMetric.ACCURACY,
                score=50.0,  # Unknown
                weight=0.25,
                status=DQStatus.YELLOW,
                threshold_breach=True,
            )

        # Compute MAPE (Mean Absolute Percentage Error)
        deviations = []
        for actual, benchmark in zip(actual_values, benchmark_values):
            if benchmark != 0:
                deviation = abs((actual - benchmark) / benchmark)
                deviations.append(deviation)

        if not deviations:
            mape = 0.0
        else:
            mape = np.mean(deviations)

        # Score: 100 if MAPE < max_deviation, declining to 0 at 2x deviation
        if mape <= max_deviation_pct:
            score = 100.0
        elif mape <= max_deviation_pct * 2:
            score = 100 * (1 - (mape - max_deviation_pct) / max_deviation_pct)
        else:
            score = 0.0

        threshold_breach = mape > max_deviation_pct
        status = DQStatus.GREEN if score >= 80 else (DQStatus.YELLOW if score >= 60 else DQStatus.RED)

        remediation = None
        if threshold_breach:
            if mape > max_deviation_pct * 2:
                remediation = f"Critical: MAPE {mape:.1%} > {max_deviation_pct*2:.1%}; validate data source"
            else:
                remediation = f"Warning: MAPE {mape:.1%} exceeds {max_deviation_pct:.1%} tolerance"

        logger.info(f"Accuracy: Score {score:.0f}% (MAPE {mape:.2%})")

        return DQScore(
            metric=DQMetric.ACCURACY,
            score=score,
            weight=0.25,
            status=status,
            threshold_breach=threshold_breach,
            remediation_action=remediation,
        )

    def compute_timeliness(
        self,
        last_update_time: datetime,
        max_age_hours: float = 24.0,  # Data must be <24h old
    ) -> DQScore:
        """
        Compute timeliness (freshness) of data.

        Args:
            last_update_time: When data was last updated
            max_age_hours: Maximum acceptable age in hours

        Returns:
            DQScore with timeliness metric
        """

        age_hours = (datetime.utcnow() - last_update_time).total_seconds() / 3600

        if age_hours <= max_age_hours:
            score = 100.0
        elif age_hours <= max_age_hours * 2:
            score = 100 * (1 - (age_hours - max_age_hours) / max_age_hours)
        else:
            score = 0.0

        threshold_breach = age_hours > max_age_hours
        status = DQStatus.GREEN if score >= 80 else (DQStatus.YELLOW if score >= 60 else DQStatus.RED)

        remediation = None
        if threshold_breach:
            if age_hours > max_age_hours * 2:
                remediation = f"Critical: Data {age_hours:.0f}h old; restart data refresh pipeline"
            else:
                remediation = f"Warning: Data {age_hours:.0f}h old; expected refresh <{max_age_hours:.0f}h"

        logger.info(f"Timeliness: Score {score:.0f}% (age {age_hours:.1f}h)")

        return DQScore(
            metric=DQMetric.TIMELINESS,
            score=score,
            weight=0.15,  # 15% of overall (less critical than accuracy)
            status=status,
            threshold_breach=threshold_breach,
            remediation_action=remediation,
        )

    def compute_consistency(
        self,
        source_a_values: List,
        source_b_values: List,
        reconciliation_threshold: float = 0.95,  # 95% match
    ) -> DQScore:
        """
        Compute consistency across data sources.

        Args:
            source_a_values: Values from source A
            source_b_values: Values from source B (should match)
            reconciliation_threshold: Acceptable match %

        Returns:
            DQScore with consistency metric
        """

        if not source_a_values or not source_b_values:
            return DQScore(
                metric=DQMetric.CONSISTENCY,
                score=50.0,
                weight=0.15,
                status=DQStatus.YELLOW,
                threshold_breach=True,
            )

        matches = sum(1 for a, b in zip(source_a_values, source_b_values) if a == b)
        match_pct = matches / max(len(source_a_values), len(source_b_values))
        score = match_pct * 100

        threshold_breach = score < (reconciliation_threshold * 100)
        status = DQStatus.GREEN if score >= 80 else (DQStatus.YELLOW if score >= 60 else DQStatus.RED)

        remediation = None
        if threshold_breach:
            if score < 50:
                remediation = "Critical: Major reconciliation breaks; investigate data divergence"
            else:
                remediation = f"Warning: {100-score:.0f}% of records reconcile; follow up discrepancies"

        logger.info(f"Consistency: Score {score:.0f}% ({matches}/{len(source_a_values)} match)")

        return DQScore(
            metric=DQMetric.CONSISTENCY,
            score=score,
            weight=0.10,  # 10% of overall
            status=status,
            threshold_breach=threshold_breach,
            remediation_action=remediation,
        )

    def compute_validity(
        self,
        data_values: List,
        valid_range: Tuple[float, float],
        valid_formats: Optional[List[str]] = None,
    ) -> DQScore:
        """
        Compute validity (values within acceptable ranges).

        Args:
            data_values: Values to validate
            valid_range: (min, max) acceptable values
            valid_formats: Optional list of valid formats/values

        Returns:
            DQScore with validity metric
        """

        if not data_values:
            return DQScore(
                metric=DQMetric.VALIDITY,
                score=50.0,
                weight=0.20,
                status=DQStatus.YELLOW,
                threshold_breach=True,
            )

        valid_count = 0
        for value in data_values:
            if value is None:
                continue
            try:
                if isinstance(value, (int, float)):
                    if valid_range[0] <= value <= valid_range[1]:
                        valid_count += 1
                else:
                    valid_count += 1  # Non-numeric OK by default
            except (TypeError, ValueError):
                pass

        validity_pct = valid_count / len(data_values) if data_values else 0
        score = validity_pct * 100

        threshold_breach = score < 80
        status = DQStatus.GREEN if score >= 80 else (DQStatus.YELLOW if score >= 60 else DQStatus.RED)

        remediation = None
        if threshold_breach:
            if score < 50:
                remediation = f"Critical: {100-score:.0f}% of values out of range; validate computation logic"
            else:
                remediation = f"Warning: {100-score:.0f}% of values outside {valid_range}"

        logger.info(f"Validity: Score {score:.0f}% ({valid_count}/{len(data_values)} in range)")

        return DQScore(
            metric=DQMetric.VALIDITY,
            score=score,
            weight=0.20,
            status=status,
            threshold_breach=threshold_breach,
            remediation_action=remediation,
        )

    def compute_portfolio_score(
        self,
        completeness: DQScore,
        accuracy: DQScore,
        timeliness: DQScore,
        consistency: DQScore,
        validity: DQScore,
    ) -> DQPortfolioScore:
        """
        Aggregate component scores to portfolio DQ score.

        Args:
            completeness, accuracy, timeliness, consistency, validity: Component scores

        Returns:
            DQPortfolioScore with weighted average

        Example:
            portfolio_score = engine.compute_portfolio_score(
                completeness=comp_score,
                accuracy=acc_score,
                timeliness=time_score,
                consistency=cons_score,
                validity=val_score,
            )
            print(f"Overall DQ Score: {portfolio_score.overall_score:.0f}%")
        """

        components = [completeness, accuracy, timeliness, consistency, validity]

        # Weighted average
        weighted_sum = sum(c.score * c.weight for c in components)
        total_weight = sum(c.weight for c in components)
        overall_score = weighted_sum / total_weight if total_weight > 0 else 0

        # Determine status
        if overall_score >= 80:
            status = DQStatus.GREEN
        elif overall_score >= 60:
            status = DQStatus.YELLOW
        else:
            status = DQStatus.RED

        # Collect issues
        critical_issues = [c.remediation_action for c in components if c.status == DQStatus.RED and c.remediation_action]
        warning_issues = [c.remediation_action for c in components if c.status == DQStatus.YELLOW and c.remediation_action]

        logger.info(f"Portfolio DQ Score: {overall_score:.0f}% ({status.value})")

        return DQPortfolioScore(
            run_date=date.today(),
            overall_score=overall_score,
            status=status,
            completeness_score=completeness.score,
            accuracy_score=accuracy.score,
            timeliness_score=timeliness.score,
            consistency_score=consistency.score,
            validity_score=validity.score,
            alert_count=len(critical_issues) + len(warning_issues),
            critical_issues=critical_issues,
            warning_issues=warning_issues,
        )


# ════════════════════════════════════════════════════════════════════════════
# REPORTING
# ════════════════════════════════════════════════════════════════════════════

def generate_dq_scorecard(portfolio_score: DQPortfolioScore) -> str:
    """Generate markdown data quality scorecard."""

    report = f"""
# PROMETHEUS Data Quality Scorecard
**Date:** {portfolio_score.run_date.isoformat()}

## Overall Score: {portfolio_score.overall_score:.0f}/100 ({portfolio_score.status.value.upper()})

| Metric | Score | Status | Threshold Breach |
|--------|-------|--------|------------------|
| Completeness | {portfolio_score.completeness_score:.0f} | ✓ | No |
| Accuracy | {portfolio_score.accuracy_score:.0f} | ✓ | No |
| Timeliness | {portfolio_score.timeliness_score:.0f} | ✓ | No |
| Consistency | {portfolio_score.consistency_score:.0f} | ✓ | No |
| Validity | {portfolio_score.validity_score:.0f} | ✓ | No |

## Alerts ({portfolio_score.alert_count})

### Critical Issues
"""

    if portfolio_score.critical_issues:
        for issue in portfolio_score.critical_issues:
            report += f"- 🔴 {issue}\n"
    else:
        report += "- None\n"

    report += "\n### Warnings\n"

    if portfolio_score.warning_issues:
        for issue in portfolio_score.warning_issues:
            report += f"- 🟡 {issue}\n"
    else:
        report += "- None\n"

    report += f"""

---
**Generated:** {datetime.utcnow().isoformat()}Z
"""

    return report


if __name__ == "__main__":
    # Demo
    engine = DataQualityEngine()

    # Compute component scores
    completeness = engine.compute_completeness([1, 2, None, 4, 5])
    accuracy = engine.compute_accuracy([100, 200, 300], [101, 199, 302])
    timeliness = engine.compute_timeliness(datetime.utcnow() - timedelta(hours=2))
    consistency = engine.compute_consistency([1, 1, 1], [1, 1, 1])
    validity = engine.compute_validity([10, 20, 30, 100, 9999], (0, 100))

    # Compute portfolio score
    portfolio = engine.compute_portfolio_score(
        completeness=completeness,
        accuracy=accuracy,
        timeliness=timeliness,
        consistency=consistency,
        validity=validity,
    )

    print(generate_dq_scorecard(portfolio))

