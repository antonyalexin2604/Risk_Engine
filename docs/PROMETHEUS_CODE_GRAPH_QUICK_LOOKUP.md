# PROMETHEUS CODE GRAPH — QUICK LOOKUP (Ultra-Compact Reference)
**Purpose:** Maximum token efficiency — one-liners only

---

## 🎯 COPY-PASTE PROMPT TEMPLATES

### Template 1: "Show me the function"
```
From PROMETHEUS_CODE_GRAPH, show me:
backend/engines/a_irb.py :: AIRBEngine.compute_portfolio(exposures)
Regulatory: CRE31
```

### Template 2: "How does it connect"
```
Data flow in PROMETHEUS_CODE_GRAPH:
main.py → build_full_dataset() 
      → banking_portfolios[].exposures 
      → AIRBEngine.compute_portfolio()
      ← credit_calibration.py (PD/LGD params)
```

### Template 3: "Show the dependency"
```
In PROMETHEUS_CODE_GRAPH, trace:
backend/engines/[any].py imports from:
  • backend/data_sources/calibration.py
  • backend/data_sources/market_data_provider.py
  • backend/config.py
```

---

## 🔤 MODULE ABBREVIATIONS (Use in prompts)

```
MN = main.py
AIB = a_irb.py
SC = sa_ccr.py
IM = imm.py
FX = frtb.py
CV = cva.py
CC = ccp.py
GS = gsib_capital.py
OP = operational_risk.py

OF = output_floor.py (Phase 2A)
ESG = esg_framework.py (Phase 2A)
DQ = dqms.py (Phase 2A)
TR = trace_engine.py (Phase 2A)
GV = governance_checker.py (Phase 2A)

SC_LIB = scenarios/library.py
SC_ENG = scenarios/engine.py
SNS = sensitivities/__init__.py

CAL = calibration.py
CCR_CAL = credit_calibration.py
MD = market_data_provider.py
MS = market_state.py
PER = persistence.py

PG = portfolio_generator.py
CVA_GEN = cva_generator.py
```

**Usage:** "In PG (portfolio_generator.py), show me build_full_dataset()"

---

## 🏛️ REGULATORY STANDARD QUICK MAP

```
CRE30 → AIB
CRE31 → AIB (A-IRB formula)
CRE32 → AIB (LGD)
CRE36 → AIB (SME treatment)
CRE51 → SC (CCR counterparty)
CRE52 → SC (SA-CCR)
CRE53 → IM (IMM)
CRE54 → CC (CCP)

MAR20 → FX (FRTB overview)
MAR21 → FX (Sensitivities)
MAR33 → FX (ES)
MAR50 → CV (CVA)
MAR51 → FX (Backtesting)

CAP10 → GS (Capital adequacy)
CAP50 → GS (GSIB surcharge)

RBC20 → MN (Output floor)
RBC20.11 → OF (Dynamic floor)

CRR3 Art. 12a → OF (Dynamic floor)
CRR3 Art. 87a → ESG (ESG risk)

SR 11-7 → GV (Model governance)
OPE25 → OP (Op risk stub)
```

---

## 🎲 FUNCTION SIGNATURES (Ctrl+F find these)

```
CLASS/FUNCTION                          | FILE | RETURNS
────────────────────────────────────────┼──────┼─────────────────────
AIRBEngine()                            | AIB  | self
AIRBEngine.compute_portfolio(exposures) | AIB  | Dict (rwa, el, etc)
SACCREngine()                           | SC   | self
SACCREngine.compute_ead(netting, date)  | SC   | SACCRResult
IMMEngine()                             | IM   | self
IMMEngine.run_for_portfolio(trades)     | IM   | Dict (ead_imm, ead_csa)
FRTBEngine()                            | FX   | self
FRTBEngine.compute(...)                 | FX   | FRTBResult
CVAEngine()                             | CV   | self
CVAEngine.compute_portfolio_cva(...)    | CV   | Dict (total_rwa_cva)
compute_ccp_rwa(exposures)              | CC   | Dict (total_rwa_ccp)
compute_capital_adequacy(rwa_total)     | GS   | Dict (ratios, etc)
DynamicOutputFloorCalculator()          | OF   | self
DynamicOutputFloorCalculator.apply_floor() | OF | (floored_rwa, impact, status)
ESGRiskCalculator()                     | ESG  | self
ESGRiskCalculator.compute_esg_uplift()  | ESG  | (pd_adjusted, rationale)
DataQualityManager()                    | DQ   | self
DataQualityManager.compute_dq_scorecard() | DQ | Dict (score 0-100)
GovernanceChecker()                     | GV   | self
GovernanceChecker.check_sr117_compliance() | GV | Dict (5 checks)
TraceEngine()                           | TR   | self
TraceEngine.generate_trace_report()     | TR   | str (HTML)
PrometheusRunner()                      | MN   | self
PrometheusRunner.run_daily(run_date)    | MN   | Dict (5-part RWA summary)
build_full_dataset(book_date)           | PG   | Dict (portfolios)
build_cva_inputs(derivative_results)    | CVA_GEN | (List[CVAInput], rating_map)
CalibratedParams                        | CAL  | dataclass
calibrate_and_apply(market_params)      | CAL  | CalibratedParams
ensure_schema()                         | PER  | bool
persist_run(run_date, results)          | PER  | None
```

---

## 📍 KEY LOOKUP POINTS (By Question)

### "Where is the PD calculation?"
→ `AIB (a_irb.py)` → `AIRBEngine.compute_portfolio()` → Calls `CAL (calibration.py)`

### "Where is the floor logic?"
→ `OF (output_floor.py)` → `DynamicOutputFloorCalculator.apply_floor()`

### "Where is ESG?"
→ `ESG (esg_framework.py)` → `ESGRiskCalculator.compute_esg_uplift()` (9 sectors)

### "Where is data quality checking?"
→ `DQ (dqms.py)` → `DataQualityManager.compute_dq_scorecard()` (5 dimensions)

### "Where is governance?"
→ `GV (governance_checker.py)` → `GovernanceChecker.check_sr117_compliance()` (5 checks)

### "Where is tracing?"
→ `TR (trace_engine.py)` → `TraceEngine.generate_trace_report()` (3-level detail)

### "Where is market data?"
→ `MD (market_data_provider.py)` → `MarketDataProvider.fetch_*()` (Bloomberg/Refinitiv)

### "Where is persistence?"
→ `PER (persistence.py)` → `persist_run()` → PostgreSQL tables

### "Where does it all start?"
→ `MN (main.py)` → `PrometheusRunner.run_daily()` (orchestrator)

---

## 🔧 DATABASE TABLES (For persistence queries)

```
TABLE NAME                          | PURPOSE
────────────────────────────────────┼──────────────────────────
prometheus_risk_runs                | Daily RWA snapshots
prometheus_trade_details            | Trade-level results
prometheus_rwa_components           | RWA breakdown (6 parts)
prometheus_capital_tracking         | Historical capital ratios
output_floor_tracking               | Dynamic floor history
esg_risk_tracking                   | ESG impact log
data_quality_scorecard              | DQ scores (daily)
governance_check_results            | SR 11-7 checks (daily)
calculation_trace_log               | Hierarchical traces
```

---

## 📊 FORMULA QUICK REFERENCE

```
A-IRB RWA:
  K = [PD floor + MA uplift + SME uplift] × LGD × MA × N(...) × EAD × 12.5
  Where N(...) = normalization, MA = maturity adjustment

Output Floor:
  Floored_RWA = max(Total_RWA, SA_RWA × [72.5% + stress_adj])

SA-CCR EAD:
  EAD = 1.4 × (RC + Floor_Mult × Addon_Total)

CVA RWA:
  RWA_CVA = 2.33 × K × M × (Spread × V) × EAD

ESG PD Uplift:
  PD_adjusted = PD_base × (1 + transition_risk_bps / 10000)
```

---

## 🎯 TOKEN-SAVING PATTERNS

### Pattern A: Minimal reference
Instead of:
```
Please look at the AIRBEngine in backend/engines/a_irb.py
and explain the full compute_portfolio method...
```

Use:
```
PROMETHEUS_CODE_GRAPH: AIB.compute_portfolio()
Show PD floor enforcement (CRE31.4).
```

**Saves:** 50+ tokens per query

---

### Pattern B: Dependency query
Instead of:
```
I need to understand how the A-IRB engine gets its
calibration parameters from the credit_calibration module...
```

Use:
```
PROMETHEUS_CODE_GRAPH import graph:
AIB imports CAL
Show: CAL.calibrate_pd_by_sector() flow
```

**Saves:** 80+ tokens per query

---

### Pattern C: Data flow
Instead of:
```
Walk me through the entire data flow from
PrometheusRunner to the final RWA calculation...
```

Use:
```
PROMETHEUS_CODE_GRAPH data flow:
MN.run_daily() → dataset → AIRB.compute_portfolio() → PER.persist_run()
Show each step.
```

**Saves:** 120+ tokens per query

---

## ✅ ESTIMATED TOKEN SAVINGS PER SESSION

| Activity | Without Graph | With Graph | Savings |
|----------|---------------|-----------|---------|
| Code review (5 questions) | 8,000 | 2,500 | 69% |
| Bug fix investigation | 6,000 | 1,800 | 70% |
| Integration work | 10,000 | 3,000 | 70% |
| Phase 2 implementation | 15,000 | 4,500 | 70% |

**Average savings: 70% of tokens/session**

---

## 🚀 QUICK START: FIRST CLAUDE PROMPT

```
I have PROMETHEUS_CODE_GRAPH.md in my project.

1. When I say "AIB", resolve to: backend/engines/a_irb.py
2. When I say "CAL", resolve to: backend/data_sources/calibration.py
3. When I reference CRE31, search the graph for regulatory basis mapping

Now, show me how PD floor enforcement works in AIB given
that CAL provides the floor parameter (3bp default).
```

---

## 📎 COMPANION DOCUMENTS

- `PROMETHEUS_CODE_GRAPH.md` — Full graph (this is the quick lookup)
- `PROMETHEUS_TECHNICAL_ARCHITECTURE.md` — System design (7-layer)
- `PHASE2A_INTEGRATION_GUIDE.md` — Implementation details
- `IMPLEMENTATION_SCENARIOS_SENSITIVITIES.md` — Greeks API

---

**Usage:** Reference this document in every Claude prompt to cut tokens by 60–90%.

**Keep this open** while working on PROMETHEUS development.

---

**Date:** April 29, 2026  
**Format:** Ultra-compact reference — use Ctrl+F to search

