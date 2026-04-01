# FRTB Engine Enhancements

## Overview
The FRTB engine has been refactored to improve robustness, maintainability, and regulatory compliance. Four key areas were enhanced:

---

## 1. Input Validation (Prevents Silent Errors)

### Custom Exceptions
Three new exception classes provide clear error semantics:
- **`FRTBValidationError`**: Invalid input data (sensitivities, PnL series)
- **`FRTBConfigurationError`**: Invalid regulatory configuration
- **`FRTBCalculationError`**: Numerical errors (NaN, inf) during computation

### Validation Functions
- **`validate_sensitivity(s)`**: Checks individual sensitivity for:
  - Valid trade_id, risk_class, bucket (non-empty strings)
  - Delta, vega, curvature values (no NaN/inf)
  
- **`validate_sensitivities(sensitivities, config)`**: Portfolio-level validation
  - Ensures all risk classes are recognized
  - Validates entire portfolio before computation starts
  
- **`validate_pnl_series(pnl_series)`**: PnL data quality checks
  - Minimum length (10 observations)
  - No NaN or inf values
  - Type checking (numpy array)

### Error Handling
All calculator methods now:
- Wrap computations in try-catch blocks
- Validate intermediate results (NaN/inf detection)
- Log detailed errors for debugging
- Raise meaningful exceptions with context

**Example**:
```python
try:
    validate_sensitivities(sensitivities, self.config)
except FRTBValidationError as e:
    logger.error(f"Sensitivity validation failed: {e}")
    raise
```

---

## 2. Configuration Management (Replaces Hard-Coded Values)

### FRTBConfig Dataclass
Centralized configuration object containing all regulatory parameters:

```python
@dataclass
class FRTBConfig:
    risk_classes: List[str]              # ["GIRR", "CSR_NS", ...]
    delta_rw: Dict[str, Sequence[float]] # Risk weights by class/bucket
    intra_corr: Dict[str, float]         # Intra-bucket correlations
    inter_corr: Dict[str, float]         # Inter-bucket correlations
    vega_rw: Dict[str, float]            # Vega weights per class
    confidence_level: float = 0.975      # ES confidence (97.5%)
    holding_period_days: int = 10        # 10-day horizon
    backtesting_window: int = 260        # 1-year observation window
    green_zone_max: int = 4              # MAR99 green threshold
    amber_zone_max: int = 9              # MAR99 amber threshold
    ima_multiplier: float = 1.5          # Backtesting m_c multiplier
    nmrf_charge_bp: float = 0.0015       # 15bp per NMRF factor
    stressed_es_multiplier: float = 1.5  # Stressed scenario multiplier
```

### Benefits
✅ **Single source of truth** for all regulatory parameters  
✅ **Easy override** for stress testing or alternative scenarios  
✅ **Validation** ensures parameters stay within regulatory bounds  
✅ **Type safety** with proper type hints  

### Usage
```python
# Default configuration
config = FRTBConfig()
engine = FRTBEngine(config)

# Custom configuration
custom_config = FRTBConfig(
    confidence_level=0.99,
    ima_multiplier=2.0
)
engine = FRTBEngine(custom_config)
```

---

## 3. Enhanced Type Hints (Better IDE Support)

### Improved Imports
```python
from typing import List, Dict, Optional, Tuple, Mapping, Sequence, Union
```

### Type Safety Improvements
| Before | After |
|--------|-------|
| `List[Sensitivity]` | `Sequence[Sensitivity]` (more flexible) |
| `Dict[str, float]` | `Dict[str, Sequence[float]]` (clearer structure) |
| `None` in date parameter | `Optional[date]` (explicit nullable) |
| Missing docstrings | Rich dataclass docstrings with `Attributes:` sections |

### Enhanced Dataclass Docstrings
```python
@dataclass
class Sensitivity:
    """
    Single risk factor sensitivity per MAR21.6.
    
    Attributes:
        trade_id: Unique trade identifier.
        risk_class: One of GIRR, CSR_NS, CSR_SEC, EQ, CMDTY, FX.
        bucket: Regulatory bucket (e.g., "1", "2", or risk name).
        delta: Delta sensitivity ∂V/∂S (dV per 1bp move).
        vega: Vega sensitivity ∂V/∂σ (dV per 1% IV move).
        curvature_up: P&L change if scenario rates shift +1bp.
        curvature_dn: P&L change if scenario rates shift -1bp.
    """
```

### IDE Benefits
✅ Auto-completion for all parameters  
✅ Type checking with Pylance/mypy  
✅ Inline documentation on hover  
✅ Refactoring support  

---

## 4. Error Handling & Graceful Degradation

### Calculator Error Handling
Each calculator method (`delta_charge`, `vega_charge`, `compute_es`, etc.) now:

1. **Validates input** before computation
2. **Catches numerical errors** (NaN/inf)
3. **Logs with context** (risk class, trade ID, operation)
4. **Raises typed exceptions** for proper error handling
5. **Provides recovery information** in error messages

**Example - SBMCalculator.delta_charge**:
```python
def delta_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
    try:
        # ... computation logic ...
        result = math.sqrt(max(charge_sq, 0.0))
        if math.isnan(result) or math.isinf(result):
            raise FRTBCalculationError(f"Delta charge produced NaN/inf for {risk_class}")
        return result
    except (ValueError, TypeError) as e:
        raise FRTBCalculationError(f"Delta charge calculation failed for {risk_class}: {e}")
```

### FRTBEngine Error Handling
Master compute method with comprehensive exception handling:
```python
def compute(...) -> FRTBResult:
    try:
        # Validate all inputs upfront
        validate_sensitivities(sensitivities, self.config)
        if pnl_series is not None:
            validate_pnl_series(pnl_series)
        
        # Proceed with calculation
        # ...
        
    except (FRTBValidationError, FRTBCalculationError) as e:
        logger.error(f"FRTB computation failed for {portfolio_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in FRTB computation: {e}")
        raise FRTBCalculationError(f"Unexpected error: {e}")
```

### BacktestEngine Error Handling
```python
def evaluate(self, predicted: np.ndarray, actual_pnl: np.ndarray) -> Dict:
    try:
        # Validate input arrays
        if len(predicted) != len(actual_pnl):
            raise FRTBValidationError("Length mismatch: predicted vs actual_pnl")
        if np.any(np.isnan(predicted)) or np.any(np.isnan(actual_pnl)):
            raise FRTBValidationError("Predicted or actual_pnl contains NaN")
        # ... evaluation logic ...
    except FRTBValidationError:
        raise
    except Exception as e:
        raise FRTBCalculationError(f"Backtesting evaluation failed: {e}")
```

---

## Usage Examples

### Basic Usage with Validation
```python
from backend.engines.frtb import (
    FRTBEngine, FRTBConfig, Sensitivity, 
    FRTBValidationError, FRTBCalculationError
)
import numpy as np
from datetime import date

# Create engine with default config
engine = FRTBEngine()

# Create sensitivities
sensitivities = [
    Sensitivity(
        trade_id="TRD001",
        risk_class="GIRR",
        bucket="1",
        risk_factor="USD_2Y",
        delta=1_000_000,
        vega=50_000
    ),
    Sensitivity(
        trade_id="TRD002",
        risk_class="CSR_NS",
        bucket="1",
        risk_factor="ACME",
        delta=-500_000
    ),
]

# Compute capital charge (with automatic validation)
try:
    result = engine.compute(
        portfolio_id="PORT001",
        sensitivities=sensitivities,
        pnl_series=np.random.normal(0, 10000, 260),
        n_nmrf=2,
        avg_notional=50_000_000
    )
    print(f"SBM: ${result.sbm_total:,.0f}")
    print(f"IMA: ${result.ima_total:,.0f}")
    print(f"Capital: ${result.capital_market_risk:,.0f}")
    print(f"RWA: ${result.rwa_market:,.0f}")
except (FRTBValidationError, FRTBCalculationError) as e:
    print(f"Error: {e}")
```

### Custom Configuration
```python
# Stress test with higher confidence level
stress_config = FRTBConfig(
    confidence_level=0.99,           # 99% instead of 97.5%
    ima_multiplier=2.0,              # 2x multiplier instead of 1.5x
    nmrf_charge_bp=0.003             # 30bp instead of 15bp
)
stress_config.validate()  # Ensure config is valid

stress_engine = FRTBEngine(stress_config)
stress_result = stress_engine.compute(...)
```

### Backtesting
```python
from backend.engines.frtb import BacktestEngine

backtest = BacktestEngine(engine.config)

predicted_var = np.array([100_000] * 252)  # Daily VaR predictions
actual_pnl = np.random.normal(-50_000, 150_000, 252)  # Actual daily P&L

try:
    bt_result = backtest.evaluate(predicted_var, actual_pnl)
    print(f"Traffic Light: {bt_result['traffic_light']}")  # GREEN/AMBER/RED
    print(f"Exceptions: {bt_result['exceptions']}/{bt_result['window_days']}")
except FRTBValidationError as e:
    print(f"Backtesting failed: {e}")
```

---

## Summary of Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Configuration** | Hard-coded global dicts | Centralized FRTBConfig class with validation |
| **Type Hints** | Basic (List, Dict) | Rich (Sequence, Mapping, Optional, Union) |
| **Validation** | None | Pre-computation validation on all inputs |
| **Error Handling** | Generic ValueError | Typed exceptions (3 custom classes) |
| **Docstrings** | Sparse comments | Comprehensive dataclass docstrings |
| **Numerical Safety** | Silent NaN/inf | Explicit NaN/inf detection & error raising |
| **Testability** | Monolithic | Dependency-injected config, testable methods |
| **Observability** | Basic logging | Context-rich error logs with trade/class info |

---

## Benefits

✅ **Prevents Silent Errors**: All invalid inputs caught early with clear exceptions  
✅ **Configuration Flexibility**: Easy scenario testing, stress testing, regulatory changes  
✅ **Type Safety**: IDE auto-completion, type checking, self-documenting code  
✅ **Maintainability**: Single source of truth for regulatory parameters  
✅ **Debuggability**: Rich error messages with full context  
✅ **Regulatory Compliance**: Explicit validation of all regulatory bounds  
✅ **Testability**: Dependency-injected components, mockable configuration  

---

## Migration Notes

Existing code using `FRTBEngine()` should be updated:

```python
# Old (still works but no config override)
engine = FRTBEngine()

# New (recommended)
config = FRTBConfig()
config.validate()
engine = FRTBEngine(config)

# Or with custom config
custom_config = FRTBConfig(confidence_level=0.99)
custom_config.validate()
engine = FRTBEngine(custom_config)
```

The BacktestEngine also now requires config:
```python
# Old
backtest = BacktestEngine()

# New
backtest = BacktestEngine(engine.config)
```

All validation exceptions should be caught and handled appropriately in calling code.
