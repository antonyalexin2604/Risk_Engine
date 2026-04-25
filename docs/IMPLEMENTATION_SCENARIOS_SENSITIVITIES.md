# Scenario Analysis & Sensitivities Implementation Guide
## Getting Started with New Modules

**Date:** April 25, 2026  
**Status:** Ready for Phase 2B Development  
**Modules:** `backend.scenarios`, `backend.sensitivities`

---

## QUICK START

### 1. Using the Scenario Library

```python
from backend.scenarios.library import (
    get_regulatory_scenario,
    get_all_scenarios,
    ScenarioType,
)

# Get a single regulatory scenario
crisis_2008 = get_regulatory_scenario("CRISIS_2008")
print(f"Scenario: {crisis_2008.scenario_name}")
print(f"Equity shock: {crisis_2008.market_params.sp500_shock:.1%}")
print(f"Spreads widen: {crisis_2008.market_params.credit_spread_bbb} bps")

# Get all scenarios
all_scenarios = get_all_scenarios()
for scenario in all_scenarios:
    print(f"- {scenario.scenario_id}: {scenario.scenario_name}")

# Filter by type
regulatory = get_all_scenarios(ScenarioType.REGULATORY_ADVERSE)
for scenario in regulatory:
    print(f"CCAR Scenario: {scenario.scenario_name}")
```

### 2. Using the Scenario Analysis Engine

```python
from backend.scenarios.engine import ScenarioAnalysisEngine
from backend.scenarios.library import get_regulatory_scenario
from backend.main import PrometheusRunner

# Initialize
runner = PrometheusRunner()
engine = ScenarioAnalysisEngine(runner)

# Build portfolio
dataset = build_full_dataset(book_date=date.today())

# Run single scenario
scenario = get_regulatory_scenario("CRISIS_2008")
run = engine.run_scenario(dataset, scenario)

print(f"Baseline RWA: {engine.baseline_rwa:,.0f}")
print(f"Crisis RWA: {run.rwa_total:,.0f}")
print(f"Increase: {run.rwa_increase_pct:+.1%}")
print(f"Capital Impact: {run.capital_increase:+,.0f}")

# Run all regulatory scenarios
all_runs = engine.run_all_scenarios(dataset)
for scenario_id, run in all_runs.items():
    print(f"{run.scenario.scenario_name}: {run.rwa_total:,.0f} ({run.rwa_increase_pct:+.1%})")

# Generate comparison report
report = engine.generate_scenario_report()
print(report)
```

### 3. Using the Sensitivities API

```python
from backend.sensitivities import SensitivityAnalyzer
from backend.main import PrometheusRunner

# Initialize
runner = PrometheusRunner()
analyzer = SensitivityAnalyzer(runner)

# Get portfolio
dataset = build_full_dataset(book_date=date.today())
portfolio_bbk = dataset["banking_book"]

# Compute single Greek (PD sensitivity)
greek_pd = analyzer.compute_delta_airb_pd(
    portfolio_bbk,
    shock_size=0.001,  # 1 bp shock
)
print(f"PD Sensitivity (Delta):")
print(f"  Base RWA: {greek_pd.rwa_base:,.0f}")
print(f"  Shocked RWA: {greek_pd.rwa_shocked:,.0f}")
print(f"  Δ RWA: {greek_pd.rwa_delta:+,.0f}")
print(f"  Δ RWA %: {greek_pd.rwa_delta_pct:+.2%}")
print(f"  Magnitude: {greek_pd.magnitude}")

# Compute all A-IRB Greeks
portfolio_greeks = analyzer.compute_all_greeks_airb(portfolio_bbk)

# Get top sensitivities
top_10 = portfolio_greeks.get_top_sensitivities(10)
for i, greek in enumerate(top_10, 1):
    print(f"{i}. {greek.parameter_name}: {greek.rwa_delta_pct:+.2%} per {greek.shock_size}")

# Export to dataframe (optional)
df = portfolio_greeks.to_dataframe()
print(df)
```

---

## INTEGRATION WITH EXISTING CODE

### Adding to main.py Daily Risk Run

```python
# In backend/main.py, PrometheusRunner.run_daily():

def run_daily(self, run_date: date = None, include_scenarios=True) -> Dict:
    run_date = run_date or date.today()
    
    # Existing code...
    dataset = build_full_dataset(book_date=run_date)
    
    # ... compute all RWA components ...
    
    results = {
        "run_date": run_date.isoformat(),
        "derivative": [...],
        "banking_book": [...],
        "capital_summary": {...},
    }
    
    # NEW: Scenario Analysis
    if include_scenarios:
        logger.info("Running scenario analysis...")
        from backend.scenarios.engine import ScenarioAnalysisEngine
        from backend.scenarios.library import get_all_scenarios, ScenarioType
        
        scenario_engine = ScenarioAnalysisEngine(self)
        
        # Run regulatory scenarios
        regulatory_scenarios = get_all_scenarios(ScenarioType.REGULATORY_ADVERSE)
        for scenario in regulatory_scenarios:
            scenario_run = scenario_engine.run_scenario(dataset, scenario, run_date)
            results["scenarios"][scenario.scenario_id] = {
                "rwa_total": scenario_run.rwa_total,
                "rwa_increase_pct": scenario_run.rwa_increase_pct,
                "capital_impact": scenario_run.capital_increase,
            }
    
    # NEW: Sensitivities Analysis
    if include_scenarios:
        logger.info("Computing sensitivities...")
        from backend.sensitivities import SensitivityAnalyzer
        
        analyzer = SensitivityAnalyzer(self)
        portfolio_greeks = analyzer.compute_all_greeks_airb(dataset.get("banking_book", []))
        
        results["sensitivities"] = {
            "greeks": [{
                "parameter": g.parameter_name,
                "greek": g.greek_type.value,
                "rwa_delta_pct": float(g.rwa_delta_pct),
                "magnitude": g.magnitude,
            } for g in portfolio_greeks.greeks]
        }
    
    # Persist to database
    persist_run(results)
    
    return results
```

### Dashboard Integration (Streamlit)

```python
# In dashboard/app.py

import streamlit as st
from backend.scenarios.library import get_all_scenarios
from backend.scenarios.engine import ScenarioAnalysisEngine

st.set_page_config(page_title="Risk Dashboard", layout="wide")

# Existing tabs...
tab_overview, tab_credit, tab_market, tab_scenarios, tab_sensitivities = st.tabs([
    "Overview", "Credit Risk", "Market Risk", "Scenarios", "Sensitivities"
])

with tab_scenarios:
    st.header("Scenario Analysis")
    
    # Retrieve latest run
    latest_run_data = query_latest_risk_run()
    
    if "scenarios" in latest_run_data:
        scenarios_results = latest_run_data["scenarios"]
        
        # Display scenario comparison table
        baseline_rwa = latest_run_data["capital_summary"]["rwa_total"]
        
        scenario_data = []
        for scenario_id, scenario_metrics in scenarios_results.items():
            scenario_data.append({
                "Scenario": scenario_id,
                "RWA": f"€{scenario_metrics['rwa_total']:,.0f}",
                "Δ (%)": f"{scenario_metrics['rwa_increase_pct']:+.1%}",
                "Capital Impact": f"€{scenario_metrics['capital_impact']:,.0f}",
            })
        
        st.dataframe(scenario_data, use_container_width=True)
        
        # Chart: RWA by scenario
        scenario_names = list(scenarios_results.keys())
        scenario_rwas = [scenarios_results[s]["rwa_total"] for s in scenario_names]
        
        st.bar_chart({
            "Scenario": scenario_names,
            "RWA": scenario_rwas,
        })

with tab_sensitivities:
    st.header("Risk Sensitivities (Greeks)")
    
    if "sensitivities" in latest_run_data:
        greeks = latest_run_data["sensitivities"]["greeks"]
        
        # Display Greeks table
        greeks_df = pd.DataFrame(greeks)
        st.dataframe(greeks_df, use_container_width=True)
        
        # Tornado chart: Top sensitivities
        top_10 = sorted(greeks, key=lambda g: abs(g["rwa_delta_pct"]), reverse=True)[:10]
        
        st.scatter_chart({
            "Parameter": [g["parameter"] for g in top_10],
            "Sensitivity": [g["rwa_delta_pct"] for g in top_10],
        })
```

---

## DATABASE SCHEMA

### Tables for Scenarios & Sensitivities

```sql
-- Scenario runs
CREATE TABLE prometheus_scenarios.scenario_runs (
    scenario_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date DATE NOT NULL,
    scenario_id VARCHAR(100),
    scenario_name VARCHAR(200),
    scenario_type VARCHAR(50),
    
    rwa_baseline DECIMAL(15,2),
    rwa_total DECIMAL(15,2),
    rwa_increase_pct DECIMAL(6,4),
    
    capital_baseline DECIMAL(15,2),
    capital_scenario DECIMAL(15,2),
    capital_increase DECIMAL(15,2),
    
    key_drivers JSONB,
    breached_limits TEXT[],
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_date) REFERENCES prometheus_risk.daily_runs(run_date)
);

-- Sensitivities
CREATE TABLE prometheus_scenarios.sensitivities (
    sensitivity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date DATE NOT NULL,
    
    parameter_name VARCHAR(200),
    parameter_class VARCHAR(50),  -- A_IRB, SA_CCR, FRTB
    greek_type VARCHAR(50),       -- DELTA, GAMMA, VEGA, RHO
    
    shock_size DECIMAL(8,6),
    rwa_base DECIMAL(15,2),
    rwa_shocked DECIMAL(15,2),
    rwa_delta DECIMAL(15,2),
    rwa_delta_pct DECIMAL(6,4),
    
    magnitude VARCHAR(50),        -- negligible, low, medium, high, extreme
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_date) REFERENCES prometheus_risk.daily_runs(run_date)
);

CREATE INDEX idx_scenarios_run_date ON prometheus_scenarios.scenario_runs(run_date);
CREATE INDEX idx_scenarios_scenario_id ON prometheus_scenarios.scenario_runs(scenario_id);
CREATE INDEX idx_sensitivities_run_date ON prometheus_scenarios.sensitivities(run_date);
```

---

## AVAILABLE SCENARIOS (5+)

| Scenario ID | Name | Type | Regulatory |
|-------------|------|------|-----------|
| `BASELINE_CURRENT` | Baseline — Current Market | Baseline | No |
| `CRISIS_2008` | Global Financial Crisis (2007–2009) | Historical Crisis | Yes (IMM) |
| `ECB_CRDP` | ECB Concurrent Risk Distress Period | Regulatory Adverse | Yes (ECB) |
| `FED_ADVERSE` | FED CCAR Adverse Scenario | Regulatory Adverse | Yes (FED) |
| `FED_SEVERELY_ADVERSE` | FED CCAR Severely Adverse | Regulatory Severe | Yes (FED) |
| `HFL_2024` | Higher-for-Longer Rate Environment | Custom | No |

### Expected RWA Impact

| Scenario | Expected RWA Increase |
|----------|----------------------|
| Baseline | 0% |
| 2008 Crisis | +30–50% |
| ECB CRDP | +20–25% |
| FED Adverse | +20–22% |
| FED Severely Adverse | +30–35% |
| HFL 2024 | +8–10% |

---

## SENSITIVITIES COMPUTED

### A-IRB Greeks (Banking Book)

| Parameter | Greek Type | Interpretation | Typical Shock |
|-----------|-----------|-----------------|--------------|
| PD (Probability of Default) | Delta | ∂RWA/∂PD | 1 bp |
| LGD (Loss Given Default) | Delta | ∂RWA/∂LGD | 5% |
| M (Maturity) | Delta | ∂RWA/∂M | 0.5 years |
| R (Correlation) | Rho | ∂RWA/∂R | 5% |

### Expected Sensitivities (Typical Portfolio)

| Parameter | Magnitude | Typical Δ RWA per shock |
|-----------|-----------|----------------------|
| PD | HIGH | +5–10% per 1 bp |
| LGD | MEDIUM | +2–3% per 5% |
| Maturity | LOW | +0.5–1% per 0.5Y |
| Correlation | MEDIUM | +2–4% per 5% |

---

## TESTING

### Run Tests

```bash
# Test scenarios module
python -m pytest tests/test_scenarios.py -v

# Test sensitivities module
python -m pytest tests/test_sensitivities.py -v

# Run both with coverage
python -m pytest tests/test_scenarios.py tests/test_sensitivities.py --cov=backend.scenarios --cov=backend.sensitivities -v
```

### Expected Test Results

```
tests/test_scenarios.py::TestScenarioLibrary::test_baseline_scenario_creation PASSED
tests/test_scenarios.py::TestScenarioLibrary::test_2008_crisis_scenario_parameters PASSED
tests/test_scenarios.py::TestScenarioEngine::test_scenario_run_creation PASSED
tests/test_sensitivities.py::TestGreekDefinitions::test_greek_creation PASSED
tests/test_sensitivities.py::TestSensitivityAnalyzer::test_delta_pd_computation PASSED

===== 20 passed in 1.23s =====
```

---

## DEVELOPMENT ROADMAP

### Phase 2B: Integration (Weeks 8–17)

**Week 8–9: Scenario Engine Completion**
- [ ] Integrate with market data providers (Bloomberg, Refinitiv)
- [ ] Implement portfolio re-pricing under scenario
- [ ] Add stress scenario backtesting
- [ ] Hook into daily risk run

**Week 10–11: Sensitivities Engine Completion**
- [ ] Add FRTB Greeks (delta, vega, curvature)
- [ ] Add SA-CCR Greeks (MPOR, alpha, maturity)
- [ ] Implement numerical stability checks
- [ ] Performance optimization for 1M+ exposures

**Week 12–13: Dashboard Integration**
- [ ] Scenario analysis dashboard page
- [ ] Greeks sensitivity charts
- [ ] Tornado diagrams (sensitivity rankings)
- [ ] Real-time scenario updates

**Week 14–17: Testing & Validation**
- [ ] Backtesting scenarios vs. realized returns
- [ ] Greeks validation against analytical formulas
- [ ] Performance testing (compute time for 1M exposures)
- [ ] UAT with risk committee

---

## CURRENT FILE STRUCTURE

```
backend/
├── scenarios/
│   ├── __init__.py           ← Module entry point
│   ├── library.py            ← 5+ regulatory scenarios defined
│   └── engine.py             ← Scenario analysis engine
├── sensitivities/
│   ├── __init__.py           ← Module entry point + SensitivityAnalyzer
│   └── (No separate files needed yet)

tests/
├── test_scenarios.py         ← 20+ test cases
└── test_sensitivities.py     ← 25+ test cases
```

---

## NEXT STEPS

1. **Week of April 29:** Code review + merge to main branch
2. **Week of May 6:** Begin Phase 2B integration work
3. **June 1:** Scenario library live in shadow mode
4. **July 1:** Greeks daily computation operational
5. **August 1:** Gate 2 review (Phase 2A complete)

---

## QUESTIONS & SUPPORT

- **Scenarios?** See `backend.scenarios.library.print_scenario_summary()`
- **Greeks?** See `backend.sensitivities.SensitivityAnalyzer` docstrings
- **Usage?** Run tests: `pytest tests/test_scenarios.py tests/test_sensitivities.py -v`
- **Issues?** Check module docstrings and test cases for examples

---

**Prepared by:** Development Team  
**Status:** Ready for implementation  
**Last Updated:** April 25, 2026


