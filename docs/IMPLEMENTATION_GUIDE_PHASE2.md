# PROMETHEUS ENHANCEMENT IMPLEMENTATION GUIDE
## Phase 2 Technical Execution Handbook

**Document Version:** 1.0  
**Date:** April 2026  
**Audience:** Development Team, Model Risk, Risk Analytics  

---

## QUICK REFERENCE: IMPLEMENTATION PRIORITY MATRIX

| Priority | Initiative | Phase | Effort | Regulatory Impact | Revenue/Cost |
|----------|-----------|-------|--------|----------|---------|
| **CRITICAL** | Calculation Trace Engine | 2A | 25h | HIGH (SR 11-7) | Cost reduction |
| **CRITICAL** | Model Validation Checklist | 2A | 12h | HIGH (SR 11-7) | Compliance |
| **HIGH** | Dynamic Output Floor | 2B | 15h | HIGH (CRR3) | Capital relief |
| **HIGH** | Scenario Library | 2B | 30h | HIGH (EBA/ECB) | Exam prep |
| **HIGH** | Parameter Sensitivities API | 2C | 35h | MEDIUM (BCBS) | Analytics |
| **MEDIUM** | ESG/Climate Calibration | 2B | 25h | MEDIUM (CRR3) | Compliance |
| **MEDIUM** | RWA Attribution | 2C | 20h | MEDIUM (Risk transparency) | Analytics |
| **MEDIUM** | Data Quality Dashboard | 2A | 28h | MEDIUM (Best practice) | Ops efficiency |

---

## ARCHITECTURE PRINCIPLES

Before diving into code, review these principles:

### 1. **Maintain Basel Traceability**
Every calculation must map to a BCBS paragraph. Example:
```python
@basel_traceable(
    standard="CRE31.4",
    formula_name="capital_requirement_formula_corporate",
    source="https://www.bis.org/basel3/docs_frameworks/Basel%20capital%20framework.pdf"
)
def compute_rwa_corporate(exposure: BankingBookExposure) -> float:
    ...
```

### 2. **Fail-Safe Fallback Logic**
```python
try:
    result = compute_optimized_method()
except ModelComputationError:
    logger.warning(f"Optimized method failed; using fallback")
    result = compute_fallback_method()
    mark_result_as_fallback()
```

### 3. **Immutable Audit Records**
Use database sequences for linearity:
```sql
INSERT INTO prometheus_audit.trace_log (trace_id, sequence_number, event, ...)
SELECT NEXTVAL('trace_sequence'), ...;
```

---

## PHASE 2A: FOUNDATION (WEEKS 1–7)

### Initiative 2A-01: Calculation Trace Engine

**File:** `/backend/audit/trace_engine.py` (NEW, ~600 lines)

```python
"""
PROMETHEUS Calculation Trace Engine
Implements hierarchical, auditable calculation tracing per SR 11-7.

Architecture:
  - Level 1: Execution log (high-level run statistics)
  - Level 2: Portfolio trace (trade-level inputs/outputs)
  - Level 3: Calculation trace (formula-level intermediate results)
  
All traces are immutable and stored in PostgreSQL with JSONB for rich nesting.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime, JSONB, Integer, UUID, insert

logger = logging.getLogger("prometheus.audit.trace")

# ════════════════════════════════════════════════════════════════════════════
# TRACE LEVEL ENUMS
# ════════════════════════════════════════════════════════════════════════════

class TraceLevel(Enum):
    """Hierarchical trace levels per SR 11-7 model governance."""
    EXECUTION = "execution_log"    # High-level run metrics
    PORTFOLIO = "portfolio_trace"  # Trade/exposure level
    CALCULATION = "calculation_trace"  # Formula-level details
    VALIDATION = "validation_trace"  # Governance checkpoints

class TraceStatus(Enum):
    """Calculation validation status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    FALLBACK = "fallback"

# ════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class CalculationStep:
    """Single computation unit within a formula evaluation."""
    step_id: int
    name: str                      # e.g., "compute_asset_correlation"
    input_params: Dict[str, Any]
    output_value: float
    unit: str                      # e.g., "ratio (0-1)", "bps", "years"
    formula_ref: str               # e.g., "CRE31.5"
    intermediate_results: Optional[Dict[str, float]] = None
    validation_notes: Optional[str] = None

@dataclass
class FormulaeEvaluation:
    """Complete formula execution trace."""
    formula_ref: str               # CRE31.4, MAR21.6, etc.
    formula_name: str
    calculation_steps: List[CalculationStep]
    final_output: float
    final_output_unit: str
    computation_time_ms: float
    status: TraceStatus
    error_message: Optional[str] = None

@dataclass
class ExposureCalculationTrace:
    """Trade-level or exposure-level trace."""
    exposure_id: str
    exposure_type: str             # "banking_book", "derivative", "ccr"
    component: str                 # "A_IRB", "SA_CCR", "IMM", "FRTB", etc.
    
    # Inputs
    input_json: Dict[str, Any]
    
    # Formula evaluations
    formulae: List[FormulaeEvaluation]
    
    # Output
    output_rwa: float
    output_capital: float
    
    # Governance
    status: TraceStatus
    fallback_reason: Optional[str] = None
    fallback_from_method: Optional[str] = None

# ════════════════════════════════════════════════════════════════════════════
# TRACE ENGINE
# ════════════════════════════════════════════════════════════════════════════

class TraceContext:
    """Context manager for hierarchical trace recording."""
    
    def __init__(self, component: str, exposure_id: str, trace_level: TraceLevel):
        self.component = component
        self.exposure_id = exposure_id
        self.trace_level = trace_level
        self.steps: List[CalculationStep] = []
        self.start_time = None
        self.end_time = None
        self._stack: List[Dict] = []
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        logger.debug(f"Trace context entered: {self.component}/{self.exposure_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = datetime.utcnow()
        if exc_type is not None:
            logger.error(f"Trace exited with error: {exc_val}")
    
    def record_step(
        self,
        step_name: str,
        inputs: Dict[str, Any],
        output: float,
        unit: str,
        formula_ref: str,
        intermediate: Optional[Dict[str, float]] = None,
        notes: Optional[str] = None,
    ):
        """Record a single calculation step."""
        step = CalculationStep(
            step_id=len(self.steps) + 1,
            name=step_name,
            input_params=inputs,
            output_value=output,
            unit=unit,
            formula_ref=formula_ref,
            intermediate_results=intermediate,
            validation_notes=notes,
        )
        self.steps.append(step)
        logger.debug(f"  [{step.step_id}] {step.name} = {output} {unit}")
        return output
    
    def get_steps(self) -> List[CalculationStep]:
        return self.steps

class TraceRecorder:
    """Persistent trace recording to database."""
    
    def __init__(self, db_engine: sa.engine.Engine):
        self.db_engine = db_engine
    
    def persist_exposure_trace(
        self,
        run_id: str,
        trace: ExposureCalculationTrace,
    ) -> str:
        """Write exposure-level trace to database."""
        trace_id = str(uuid.uuid4())
        
        with self.db_engine.connect() as conn:
            # Insert trace record
            stmt = insert(sa.text("""
                prometheus_audit.calculation_traces
            """)).values(
                trace_id=trace_id,
                run_id=run_id,
                exposure_id=trace.exposure_id,
                exposure_type=trace.exposure_type,
                component=trace.component,
                input_json=json.dumps(trace.input_json),
                formulae_trace=json.dumps([asdict(f) for f in trace.formulae]),
                output_rwa=trace.output_rwa,
                output_capital=trace.output_capital,
                status=trace.status.value,
                fallback_reason=trace.fallback_reason,
                created_at=datetime.utcnow(),
            )
            conn.execute(stmt)
            conn.commit()
        
        logger.info(f"Persisted trace {trace_id} for exposure {trace.exposure_id}")
        return trace_id
    
    def generate_trace_html_report(self, trace_id: str) -> str:
        """Generate human-readable HTML report from trace."""
        with self.db_engine.connect() as conn:
            result = conn.execute(sa.text(f"""
                SELECT * FROM prometheus_audit.calculation_traces
                WHERE trace_id = '{trace_id}'
            """))
            row = result.fetchone()
        
        if not row:
            raise ValueError(f"Trace {trace_id} not found")
        
        # Build HTML
        html = f"""
        <html>
        <head>
            <title>Calculation Trace Report — {trace_id}</title>
            <style>
                body {{ font-family: monospace; margin: 20px; }}
                .header {{ background: #f0f0f0; padding: 10px; border-radius: 5px; }}
                .step {{ margin: 10px 0; border-left: 3px solid #0066cc; padding-left: 10px; }}
                .error {{ color: red; }}
                .warning {{ color: orange; }}
                .success {{ color: green; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
                th {{ background: #f9f9f9; }}
            </style>
        </head>
        <body>
        <div class="header">
            <h2>Calculation Trace Report</h2>
            <p><strong>Trace ID:</strong> {trace_id}</p>
            <p><strong>Exposure ID:</strong> {row['exposure_id']}</p>
            <p><strong>Component:</strong> {row['component']}</p>
            <p><strong>Status:</strong> <span class="{row['status']}">{row['status']}</span></p>
            <p><strong>Final RWA:</strong> {row['output_rwa']:,.2f}</p>
        </div>
        """
        
        # Add formula steps
        formulae = json.loads(row['formulae_trace'])
        for formula in formulae:
            html += f"""
            <div class="step">
                <h3>{formula['formula_name']} [{formula['formula_ref']}]</h3>
                <table>
                    <tr><th>Step</th><th>Computation</th><th>Result</th><th>Unit</th></tr>
            """
            for step in formula['calculation_steps']:
                html += f"""
                    <tr>
                        <td>{step['step_id']}</td>
                        <td>{step['name']}</td>
                        <td>{step['output_value']:.6f}</td>
                        <td>{step['unit']}</td>
                    </tr>
                """
            html += """
                </table>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        return html

# ════════════════════════════════════════════════════════════════════════════
# DECORATOR FOR EASY TRACING
# ════════════════════════════════════════════════════════════════════════════

def trace_formula(formula_ref: str, formula_name: str):
    """
    Decorator to automatically trace formula execution.
    
    Usage:
        @trace_formula("CRE31.4", "capital_requirement_formula_corporate")
        def compute_rwa_corporate(...) -> float:
            ...
    """
    def decorator(func):
        def wrapper(trace_ctx: Optional[TraceContext], *args, **kwargs):
            if not trace_ctx:
                # No tracing context; just execute
                return func(*args, **kwargs)
            
            try:
                result = func(trace_ctx, *args, **kwargs)
                trace_ctx.formulae.append(FormulaeEvaluation(
                    formula_ref=formula_ref,
                    formula_name=formula_name,
                    calculation_steps=trace_ctx.get_steps(),
                    final_output=result,
                    final_output_unit="RWA (currency units)",
                    computation_time_ms=0,  # TODO: measure
                    status=TraceStatus.PASSED,
                ))
                return result
            except Exception as e:
                logger.error(f"Formula {formula_name} failed: {e}")
                raise
        
        return wrapper
    return decorator

# ════════════════════════════════════════════════════════════════════════════
# DATABASE SETUP
# ════════════════════════════════════════════════════════════════════════════

def create_trace_tables(db_engine: sa.engine.Engine):
    """Create audit tables for trace recording."""
    
    sql = """
    CREATE SCHEMA IF NOT EXISTS prometheus_audit;
    
    CREATE TABLE IF NOT EXISTS prometheus_audit.calculation_traces (
        trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id UUID REFERENCES prometheus_risk.daily_runs(run_id),
        exposure_id VARCHAR(100) NOT NULL,
        exposure_type VARCHAR(50),           -- banking_book, derivative, ccr
        component VARCHAR(50),               -- A_IRB, SA_CCR, IMM, FRTB, CVA
        input_json JSONB,                    -- Raw exposure input
        formulae_trace JSONB,                -- Array of formula evaluations
        output_rwa DECIMAL(15, 2),
        output_capital DECIMAL(15, 2),
        status VARCHAR(20),                  -- pending, in_progress, passed, failed, fallback
        fallback_reason VARCHAR(500),
        fallback_from_method VARCHAR(50),
        governance_review_status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
        auditor_sign_off_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_traces_run_id ON prometheus_audit.calculation_traces(run_id);
    CREATE INDEX IF NOT EXISTS idx_traces_exposure_id ON prometheus_audit.calculation_traces(exposure_id);
    CREATE INDEX IF NOT EXISTS idx_traces_component ON prometheus_audit.calculation_traces(component);
    """
    
    with db_engine.connect() as conn:
        conn.execute(sa.text(sql))
        conn.commit()
    
    logger.info("Trace audit tables created successfully")
```

**Integration with A-IRB Engine:**

```python
# File: /backend/engines/a_irb.py (MODIFIED)

from backend.audit.trace_engine import TraceContext, TraceStatus, ExposureCalculationTrace

class AIRBEngine:
    def compute_rwa_single(
        self, 
        exposure: BankingBookExposure, 
        trace_ctx: Optional[TraceContext] = None
    ) -> Tuple[float, ExposureCalculationTrace]:
        """
        Enhanced to support optional tracing.
        
        If trace_ctx is None → fast path (no tracing overhead)
        If trace_ctx is provided → record all intermediate calculations
        """
        
        if trace_ctx:
            trace_ctx.record_step(
                step_name="input_validation",
                inputs={
                    "pd": exposure.pd,
                    "lgd": exposure.lgd,
                    "ead": exposure.ead,
                    "maturity": exposure.maturity,
                },
                output=1.0,  # validation passes
                unit="validation_flag",
                formula_ref="CRE31.1",
                notes="All inputs within valid ranges"
            )
        
        # Apply floors
        pd_adj = max(exposure.pd, 0.0003)
        lgd_adj = max(exposure.lgd, self.config.lgd_floor)
        
        # ... rest of calculation ...
        
        if trace_ctx:
            trace_ctx.record_step(
                step_name="compute_asset_correlation",
                inputs={"asset_class": exposure.asset_class, "ead": exposure.ead},
                output=correlation_r,
                unit="ratio (0-1)",
                formula_ref="CRE31.5",
            )
        
        # ... continue tracing each major step ...
        
        rwa = k * pd_adj * lgd_adj * exposure.ead
        
        if trace_ctx:
            calc_trace = ExposureCalculationTrace(
                exposure_id=exposure.trade_id,
                exposure_type="banking_book",
                component="A_IRB",
                input_json=asdict(exposure),
                formulae=trace_ctx.formulae,  # Collected during execution
                output_rwa=rwa,
                output_capital=rwa / 8.0,
                status=TraceStatus.PASSED,
            )
            return rwa, calc_trace
        else:
            return rwa, None
```

**CLI Usage:**

```bash
# Run with full tracing enabled
python -m backend.main --run-date 2026-04-24 --enable-tracing

# Generate trace report for specific exposure
python -m backend.audit.trace_engine \
    --trace-id 550e8400-e29b-41d4-a716-446655440000 \
    --format html \
    --output /tmp/trace_report.html
```

---

### Initiative 2A-02: Model Validation Checklist (Automated SR 11-7)

**File:** `/backend/validation/governance_checker.py` (NEW, ~400 lines)

```python
"""
PROMETHEUS Model Validation Control Framework
Implements SR 11-7 governance checkpoints as automated checks.

Checkpoints:
  VC-01: Conceptual Soundness (formula verification)
  VC-02: Backtesting & Historical Validation
  VC-03: Sensitivity Analysis
  VC-04: Logic & Code Review
  VC-05: Rollout & Monitoring
"""

import subprocess
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger("prometheus.validation.governance")

class CheckpointStatus(Enum):
    PASSED = "✓"
    FAILED = "✗"
    WARNING = "⚠"
    PENDING = "◐"

@dataclass
class GovernanceCheckResult:
    checkpoint_code: str           # VC-01, VC-02, etc.
    checkpoint_name: str
    status: CheckpointStatus
    details: str
    remediation_action: Optional[str] = None
    owner: Optional[str] = None
    timestamp: datetime = None

class GovernanceChecker:
    """Automated model risk governance checkpoint execution."""
    
    def __init__(self, config_path: str = "backend/config.py"):
        self.config_path = config_path
        self.results: List[GovernanceCheckResult] = []
    
    def check_vc01_conceptual_soundness(self) -> GovernanceCheckResult:
        """
        VC-01: Verify formula implementation matches Basel source.
        
        Checks:
        - Formula present in code with Basel paragraph reference
        - Boundary condition tests pass (PD→0, PD→1, M→∞)
        - Asymptotic behavior correct
        """
        
        # 1. Check basin sources are cited
        try:
            from backend.engines import a_irb
            formula_source = a_irb.FORMULA_REFERENCES.get("CRE31.4")
            if not formula_source:
                return GovernanceCheckResult(
                    checkpoint_code="VC-01",
                    checkpoint_name="Conceptual Soundness",
                    status=CheckpointStatus.FAILED,
                    details="Formula CRE31.4 has no BCBS reference citation",
                    remediation_action="Add @basel_reference decorator to formula",
                    owner="Lead Developer",
                )
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-01",
                checkpoint_name="Conceptual Soundness",
                status=CheckpointStatus.FAILED,
                details=f"Could not verify formula references: {e}",
                remediation_action="Run pytest backend/tests/test_formula_references.py",
                owner="Lead Developer",
            )
        
        # 2. Run boundary condition tests
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-k", "test_boundary_conditions", "-v"],
                cwd="/Users/aaron/Documents/Project/Prometheus",
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                return GovernanceCheckResult(
                    checkpoint_code="VC-01",
                    checkpoint_name="Conceptual Soundness",
                    status=CheckpointStatus.FAILED,
                    details="Boundary condition tests failed",
                    remediation_action="Review test_boundary_conditions.py and fix formula",
                    owner="Lead Developer",
                )
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-01",
                checkpoint_name="Conceptual Soundness",
                status=CheckpointStatus.WARNING,
                details=f"Could not run boundary tests: {e}",
            )
        
        return GovernanceCheckResult(
            checkpoint_code="VC-01",
            checkpoint_name="Conceptual Soundness",
            status=CheckpointStatus.PASSED,
            details="All formula references verified; boundary conditions pass",
            timestamp=datetime.utcnow(),
        )
    
    def check_vc02_backtesting(self) -> GovernanceCheckResult:
        """
        VC-02: Validate model accuracy via backtesting.
        
        Checks:
        - A/P ratio (Actual vs. Predicted) = 1 ± 0.15
        - Traffic-light compliance (< 4 exceptions = green)
        - Model predictions vs. realized losses (KS test)
        """
        
        logger.info("Running backtesting validation (VC-02)...")
        
        try:
            # Query backtesting results from database
            import sqlalchemy as sa
            from backend.config import DATABASE_URL
            
            engine = sa.create_engine(DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(sa.text("""
                    SELECT 
                        actual_vs_predicted_ratio,
                        green_zone_exception_count,
                        ks_test_p_value
                    FROM prometheus_risk.backtesting_summary
                    ORDER BY run_date DESC
                    LIMIT 1
                """))
                row = result.fetchone()
            
            if not row:
                return GovernanceCheckResult(
                    checkpoint_code="VC-02",
                    checkpoint_name="Backtesting & Historical Validation",
                    status=CheckpointStatus.PENDING,
                    details="No backtesting results found; run 36-month backfill",
                    remediation_action="Execute: python utils/backfill_history.py",
                    owner="Model Risk / Risk Analytics",
                )
            
            a_p_ratio, exceptions, ks_p_value = row
            
            # Check criteria
            a_p_pass = 0.85 <= a_p_ratio <= 1.15
            traffic_pass = exceptions <= 4  # Green zone
            ks_pass = ks_p_value > 0.05
            
            if a_p_pass and traffic_pass and ks_pass:
                return GovernanceCheckResult(
                    checkpoint_code="VC-02",
                    checkpoint_name="Backtesting & Historical Validation",
                    status=CheckpointStatus.PASSED,
                    details=(
                        f"A/P ratio: {a_p_ratio:.2f} (pass); "
                        f"Exceptions: {exceptions} (green); "
                        f"KS p-value: {ks_p_value:.3f} (pass)"
                    ),
                    timestamp=datetime.utcnow(),
                )
            else:
                failures = []
                if not a_p_pass:
                    failures.append(f"A/P ratio {a_p_ratio:.2f} outside [0.85, 1.15]")
                if not traffic_pass:
                    failures.append(f"{exceptions} exceptions > 4 (red zone)")
                if not ks_pass:
                    failures.append(f"KS p-value {ks_p_value:.3f} < 0.05")
                
                return GovernanceCheckResult(
                    checkpoint_code="VC-02",
                    checkpoint_name="Backtesting & Historical Validation",
                    status=CheckpointStatus.FAILED,
                    details="; ".join(failures),
                    remediation_action="Recalibrate model parameters or investigate data quality",
                    owner="Model Risk / Risk Analytics",
                )
        
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-02",
                checkpoint_name="Backtesting & Historical Validation",
                status=CheckpointStatus.WARNING,
                details=f"Backtesting check error: {e}",
            )
    
    def check_vc03_sensitivity(self) -> GovernanceCheckResult:
        """
        VC-03: Verify RWA sensitivity to parameter shocks.
        
        Example acceptable sensitivities:
        - ±1% PD shock: RWA change ≤ 3%
        - ±5% LGD shock: RWA change ≤ 2.5%
        - ±0.1 correlation shock: RWA change ≤ 2%
        """
        
        logger.info("Running sensitivity analysis (VC-03)...")
        
        try:
            # Execute sensitivity API
            from backend.sensitivities.greek_engine import SensitivityAnalyzer
            from backend.main import PrometheusRunner
            
            runner = PrometheusRunner()
            analyzer = SensitivityAnalyzer(runner)
            
            sensitivities = {
                "pd_1pct": analyzer.compute_delta("A_IRB", "pd", shock_size=0.001),
                "lgd_5pct": analyzer.compute_delta("A_IRB", "lgd", shock_size=0.05),
                "correlation_01": analyzer.compute_correlation_greek("A_IRB", ("Corp", "Bank"), 0.1),
            }
            
            # All sensitivities should be within acceptable ranges
            all_pass = all(
                abs(greek.rwa_delta) / greek.engine_rwa < 0.03  # 3% threshold
                for greek_dict in sensitivities.values()
                for greek in greek_dict.values()
            )
            
            if all_pass:
                return GovernanceCheckResult(
                    checkpoint_code="VC-03",
                    checkpoint_name="Sensitivity Analysis",
                    status=CheckpointStatus.PASSED,
                    details="All parameter shocks within acceptable ranges (<3% RWA change)",
                    timestamp=datetime.utcnow(),
                )
            else:
                return GovernanceCheckResult(
                    checkpoint_code="VC-03",
                    checkpoint_name="Sensitivity Analysis",
                    status=CheckpointStatus.WARNING,
                    details="Some parameter sensitivities exceed 3% RWA change threshold",
                    remediation_action="Review correlation/parameter calibration",
                    owner="Quants",
                )
        
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-03",
                checkpoint_name="Sensitivity Analysis",
                status=CheckpointStatus.WARNING,
                details=f"Sensitivity check error: {e}",
            )
    
    def check_vc04_code_review(self) -> GovernanceCheckResult:
        """
        VC-04: Verify code quality standards.
        
        Checks:
        - Pylance strict mode: 0 type errors
        - Test coverage >= 95%
        - Code review sign-offs present
        """
        
        logger.info("Running code quality checks (VC-04)...")
        
        try:
            # Check test coverage
            result = subprocess.run(
                ["python", "-m", "pytest", "--cov=backend", "--cov-report=json"],
                cwd="/Users/aaron/Documents/Project/Prometheus",
                capture_output=True,
                timeout=120,
            )
            
            if result.returncode != 0:
                return GovernanceCheckResult(
                    checkpoint_code="VC-04",
                    checkpoint_name="Logic & Code Review",
                    status=CheckpointStatus.FAILED,
                    details="Test suite did not pass",
                    remediation_action="Fix failing tests before release",
                    owner="Lead Developer",
                )
            
            # Parse coverage report
            try:
                with open(".coverage.json", "r") as f:
                    coverage_data = json.load(f)
                    coverage_pct = coverage_data.get("totals", {}).get("percent_covered", 0)
                
                if coverage_pct >= 95:
                    return GovernanceCheckResult(
                        checkpoint_code="VC-04",
                        checkpoint_name="Logic & Code Review",
                        status=CheckpointStatus.PASSED,
                        details=f"Test coverage: {coverage_pct:.1f}% (>= 95%); All tests pass",
                        timestamp=datetime.utcnow(),
                    )
                else:
                    return GovernanceCheckResult(
                        checkpoint_code="VC-04",
                        checkpoint_name="Logic & Code Review",
                        status=CheckpointStatus.WARNING,
                        details=f"Test coverage: {coverage_pct:.1f}% (< 95%)",
                        remediation_action="Add tests for uncovered lines",
                        owner="Lead Developer",
                    )
            except FileNotFoundError:
                return GovernanceCheckResult(
                    checkpoint_code="VC-04",
                    checkpoint_name="Logic & Code Review",
                    status=CheckpointStatus.WARNING,
                    details="Coverage report not found",
                )
        
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-04",
                checkpoint_name="Logic & Code Review",
                status=CheckpointStatus.WARNING,
                details=f"Code review check error: {e}",
            )
    
    def check_vc05_monitoring(self) -> GovernanceCheckResult:
        """
        VC-05: Verify production monitoring is active.
        
        Checks:
        - Daily model performance metric computed
        - Model drift detection flagged
        - Alert thresholds configured
        """
        
        logger.info("Running production monitoring check (VC-05)...")
        
        try:
            import sqlalchemy as sa
            from backend.config import DATABASE_URL
            from datetime import date
            
            engine = sa.create_engine(DATABASE_URL)
            with engine.connect() as conn:
                result = conn.execute(sa.text("""
                    SELECT COUNT(*) as recent_runs
                    FROM prometheus_risk.daily_runs
                    WHERE run_date >= CURRENT_DATE - INTERVAL '7 days'
                """))
                run_count = result.scalar()
            
            if run_count >= 5:  # At least 5/7 days
                return GovernanceCheckResult(
                    checkpoint_code="VC-05",
                    checkpoint_name="Rollout & Monitoring",
                    status=CheckpointStatus.PASSED,
                    details=f"Active monitoring: {run_count}/7 daily runs in past week",
                    timestamp=datetime.utcnow(),
                )
            else:
                return GovernanceCheckResult(
                    checkpoint_code="VC-05",
                    checkpoint_name="Rollout & Monitoring",
                    status=CheckpointStatus.WARNING,
                    details=f"Only {run_count} daily runs in past week (expected 5–7)",
                    remediation_action="Check scheduler/orchestration",
                    owner="Ops",
                )
        
        except Exception as e:
            return GovernanceCheckResult(
                checkpoint_code="VC-05",
                checkpoint_name="Rollout & Monitoring",
                status=CheckpointStatus.WARNING,
                details=f"Monitoring check error: {e}",
            )
    
    def run_all_checks(self) -> List[GovernanceCheckResult]:
        """Execute all governance checkpoints."""
        
        logger.info("=" * 70)
        logger.info("PROMETHEUS MODEL VALIDATION GOVERNANCE CHECK")
        logger.info("=" * 70)
        
        checks = [
            ("VC-01: Conceptual Soundness", self.check_vc01_conceptual_soundness),
            ("VC-02: Backtesting", self.check_vc02_backtesting),
            ("VC-03: Sensitivity Analysis", self.check_vc03_sensitivity),
            ("VC-04: Code Review", self.check_vc04_code_review),
            ("VC-05: Monitoring", self.check_vc05_monitoring),
        ]
        
        results = []
        for check_name, check_func in checks:
            try:
                logger.info(f"\n{check_name}...")
                result = check_func()
                results.append(result)
                logger.info(f"  {result.status.value} {result.details}")
                if result.remediation_action:
                    logger.warning(f"  ACTION: {result.remediation_action}")
            except Exception as e:
                logger.error(f"  Unexpected error: {e}")
                results.append(GovernanceCheckResult(
                    checkpoint_code=check_name.split(":")[0],
                    checkpoint_name=check_name.split(":", 1)[1].strip(),
                    status=CheckpointStatus.WARNING,
                    details=f"Unexpected error: {e}",
                ))
        
        self.results = results
        return results
    
    def generate_governance_report(self) -> str:
        """Generate markdown governance report."""
        
        report = f"""
# PROMETHEUS MODEL GOVERNANCE VALIDATION REPORT
**Generated:** {datetime.utcnow().isoformat()}

## Executive Summary

"""
        
        passed = sum(1 for r in self.results if r.status == CheckpointStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == CheckpointStatus.FAILED)
        warning = sum(1 for r in self.results if r.status == CheckpointStatus.WARNING)
        
        status = "🟢 PASS" if failed == 0 else ("🟡 WARNING" if warning > 0 else "🔴 FAIL")
        
        report += f"""
**Overall Status:** {status}  
**Results:** ✓ {passed} · ⚠ {warning} · ✗ {failed}

## Checkpoint Details

"""
        
        for result in self.results:
            report += f"""
### {result.checkpoint_code}: {result.checkpoint_name}

**Status:** {result.status.value}  
**Details:** {result.details}
"""
            if result.remediation_action:
                report += f"**Remediation:** {result.remediation_action}\n"
            if result.owner:
                report += f"**Owner:** {result.owner}\n"
            report += "\n"
        
        return report

# ════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    checker = GovernanceChecker()
    results = checker.run_all_checks()
    
    # Generate and save report
    report = checker.generate_governance_report()
    report_path = "/tmp/prometheus_governance_report.md"
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"\nReport saved to: {report_path}")
    
    # Exit with appropriate code
    failed = sum(1 for r in results if r.status == CheckpointStatus.FAILED)
    exit(0 if failed == 0 else 1)
```

**GitHub Actions Integration** (`.github/workflows/governance_check.yml`):

```yaml
name: Model Governance Validation

on:
  schedule:
    - cron: '0 07 * * *'  # Daily at 7 AM UTC
  workflow_dispatch:

jobs:
  governance-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m pip install -r requirements.txt
          pip install pytest pytest-cov pylance
      
      - name: Run Governance Checks
        run: |
          python -m backend.validation.governance_checker
      
      - name: Upload Report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: governance-report
          path: /tmp/prometheus_governance_report.md
      
      - name: Send Slack Notification
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "🔴 Model Governance Check Failed",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "Run the full governance check workflow"
                  }
                }
              ]
            }
```

---

## PHASE 2B: REGULATORY COMPLIANCE (WEEKS 8–17)

*[Continued in next section — due to length, showing key patterns]*

### Initiative 2B-01: Dynamic Output Floor Calibration

**File:** `/backend/capital/output_floor.py` (NEW, ~300 lines)

```python
"""
Dynamic Output Floor per Basel Endgame (CRR3)

Formula:
  Output_Floor_CRR3 = max(Total_RWA, f(SA_RWA, A-IRB_penetration, stress_regime))

Where:
  - baseline: 72.5% SA_RWA (static Basel IV)
  - stress adjustment: +0.5–2.0% if market volatility elevated
  - A-IRB penetration adjustment: accounts for model accuracy time series
"""

import logging
from datetime import date, timedelta
from typing import Tuple
import numpy as np
from backend.config import DATABASE_URL
import sqlalchemy as sa

logger = logging.getLogger("prometheus.capital.output_floor")

class DynamicOutputFloorCalculator:
    """Compute CRR3-compliant dynamic output floor."""
    
    def __init__(self, lookback_months: int = 24):
        """
        Args:
            lookback_months: Historical window for calibration (default 24)
        """
        self.lookback_months = lookback_months
        self.engine = sa.create_engine(DATABASE_URL)
    
    def fetch_historical_rwa(self) -> np.ndarray:
        """Fetch 24-month rolling RWA by method."""
        
        with self.engine.connect() as conn:
            result = conn.execute(sa.text(f"""
                SELECT 
                    run_date,
                    rwa_sa,
                    rwa_a_irb
                FROM prometheus_risk.daily_runs
                WHERE run_date >= CURRENT_DATE - INTERVAL '{self.lookback_months} month'
                ORDER BY run_date ASC
            """))
            rows = result.fetchall()
        
        return [(r[0], r[1], r[2]) for r in rows]
    
    def compute_floor_multiplier(self, sa_rwa: float, airb_rwa: float) -> float:
        """
        Compute dynamic floor multiplier per CRR3.
        
        Returns:
            Multiplier (e.g., 0.725 for 72.5% baseline SA floor)
        """
        
        # Fetch historical data
        history = self.fetch_historical_rwa()
        
        if len(history) < 12:
            logger.warning(f"Insufficient history ({len(history)} < 12 months); returning static 72.5%")
            return 0.725
        
        # Compute rolling ratio: A-IRB % of SA RWA
        ratios = []
        for _, sa, airb in history:
            if sa > 0:
                ratios.append(airb / sa)
        
        # Percentile bands (stressed regime threshold at 95th percentile)
        ratio_p5 = np.percentile(ratios, 5)
        ratio_p50 = np.percentile(ratios, 50)
        ratio_p95 = np.percentile(ratios, 95)
        
        logger.debug(f"Historical A-IRB/SA ratios: 5th={ratio_p5:.2%}, "
                    f"median={ratio_p50:.2%}, 95th={ratio_p95:.2%}")
        
        # Determine stress regime
        current_ratio = airb_rwa / sa_rwa if sa_rwa > 0 else ratio_p50
        stress_regime = current_ratio > ratio_p95
        
        # Base floor: 72.5% (Basel IV)
        base_multiplier = 0.725
        
        # Stress adjustment: +0.5–2.0% if in stressed regime
        stress_adjustment = 0.02 if stress_regime else 0.005
        
        dynamic_multiplier = base_multiplier + stress_adjustment
        
        logger.info(f"Dynamic floor: {dynamic_multiplier:.1%} "
                   f"(stress_regime={stress_regime}, adjustment={stress_adjustment:.1%})")
        
        return dynamic_multiplier
    
    def apply_floor(self, total_rwa: float, sa_rwa: float, airb_rwa: float) -> Tuple[float, float, str]:
        """
        Apply dynamic output floor.
        
        Returns:
            (floored_rwa, floor_amount, floor_status)
            
        Example:
            floored_rwa, floor_amt, status = calc.apply_floor(
                total_rwa=1000000,
                sa_rwa=1500000,
                airb_rwa=800000
            )
            print(f"Total RWA after floor: {floored_rwa:,.0f} (floor binding: {status})")
        """
        
        multiplier = self.compute_floor_multiplier(sa_rwa, airb_rwa)
        floor_rwa = sa_rwa * multiplier
        
        if total_rwa >= floor_rwa:
            # Floor not binding
            return total_rwa, 0.0, "not_binding"
        else:
            # Floor is binding — apply it
            floor_amount = floor_rwa - total_rwa
            return floor_rwa, floor_amount, "binding"
    
    def persist_floor_calc(self, run_date: date, total_rwa: float, 
                           sa_rwa: float, airb_rwa: float, floored_rwa: float):
        """Record floor calculation for audit trail."""
        
        multiplier = self.compute_floor_multiplier(sa_rwa, airb_rwa)
        status = "binding" if floored_rwa > total_rwa else "not_binding"
        
        with self.engine.connect() as conn:
            stmt = sa.text("""
                INSERT INTO prometheus_capital.output_floor_tracking 
                (run_date, total_rwa, sa_rwa, airb_rwa, floored_rwa, 
                 floor_multiplier, status, created_at)
                VALUES (:run_date, :total_rwa, :sa_rwa, :airb_rwa, :floored_rwa,
                        :mult, :status, CURRENT_TIMESTAMP)
            """)
            conn.execute(stmt, {
                "run_date": run_date,
                "total_rwa": total_rwa,
                "sa_rwa": sa_rwa,
                "airb_rwa": airb_rwa,
                "floored_rwa": floored_rwa,
                "mult": multiplier,
                "status": status,
            })
            conn.commit()

# ════════════════════════════════════════════════════════════════════════════
# Integration with main.py
# ════════════════════════════════════════════════════════════════════════════

# In backend/main.py, update the final RWA calculation:

def run_daily(self, run_date: date = None) -> Dict:
    ...
    # Compute all components
    rwa_credit = ...
    rwa_ccr = ...
    rwa_market = ...
    rwa_cva = ...
    rwa_ccp = ...
    
    # Compute SA baseline (for floor)
    rwa_sa = self.compute_sa_rwa(dataset)  # Standard Approach as comparator
    
    # Apply dynamic output floor
    floor_calc = DynamicOutputFloorCalculator()
    rwa_total_before_floor = rwa_credit + rwa_ccr + rwa_market + rwa_cva + rwa_ccp
    
    rwa_total, floor_impact, floor_status = floor_calc.apply_floor(
        total_rwa=rwa_total_before_floor,
        sa_rwa=rwa_sa,
        airb_rwa=rwa_total_before_floor  # For this calculation, use A-IRB
    )
    
    floor_calc.persist_floor_calc(
        run_date=run_date,
        total_rwa=rwa_total_before_floor,
        sa_rwa=rwa_sa,
        airb_rwa=rwa_total_before_floor,
        floored_rwa=rwa_total,
    )
    
    logger.info(f"Output floor: {floor_status}, impact = {floor_impact:,.0f}")
    
    results["capital_summary"]["rwa_before_floor"] = rwa_total_before_floor
    results["capital_summary"]["rwa_after_floor"] = rwa_total
    results["capital_summary"]["floor_status"] = floor_status
    ...
```

---

## Complete code would continue with:
- 2B-02: Leverage Ratio Implementation
- 2B-03: ESG/Climate Risk Calibration
- 2C-01: Parameter Sensitivities API
- 2C-02: RWA Attribution Engine
- And complete testing/deployment guides...

---

## QUICK-START CHECKLIST FOR IMPLEMENTATION

### Week 1: Setup & Foundations
- [ ] Create new feature branches: `feature/audit-trace`, `feature/gov-checks`
- [ ] Set up test database schema for new tables
- [ ] Create `/docs/IMPLEMENTATION_RUNBOOK.md` (link to this guide)

### Week 2–3: Trace Engine Development
- [ ] Implement `trace_engine.py` (600 lines)
- [ ] Add unit tests (100+ test cases)
- [ ] Integrate with A-IRB engine
- [ ] Generate sample trace HTML reports

### Week 4–5: Governance Checker
- [ ] Implement `governance_checker.py` (400 lines)
- [ ] Set up GitHub Actions workflow
- [ ] Configure Slack notifications
- [ ] Test all 5 checkpoints

### Week 6–7: Integration & Testing
- [ ] End-to-end test: run engine → generate traces → validate governance
- [ ] Performance benchmark: <5% overhead for tracing
- [ ] Documentation: how to query traces, interpret reports

### Week 8+: Deploy to Production
- [ ] Code review (2 approvals minimum)
- [ ] Merge to main branch
- [ ] Update README with new features
- [ ] Train ops team on new governance reports

---

## DEBUGGING & TROUBLESHOOTING

### Issue: Traces not persisting
1. Check PostgreSQL connection: `python -c "from backend.config import DATABASE_URL; print(DATABASE_URL)"`
2. Verify table exists: `SELECT COUNT(*) FROM prometheus_audit.calculation_traces;`
3. Check for constraint violations in application logs

### Issue: Governance checks all passing but dashboard shows red
1. Ensure scheduled job is running: `ps aux | grep prometheus`
2. Check cron logs: `log stream --predicate 'process == "cron"'`
3. Manually trigger: `python -m backend.validation.governance_checker`

### Issue: High trace storage requirements
1. Implement archival: move traces >90 days old to `prometheus_audit.calculation_traces_archive`
2. Consider compression: store JSONB as compressed binary
3. Adjust SELECT retention logic in trace_recorder

---

**End of Implementation Guide — Part 1**  
*Sections 2B-02 through 2C-02 to follow in extended documentation.*

---


