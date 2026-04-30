# PROMETHEUS CODE GRAPH — VISUAL INDEX (One-Page Reference)
**Print this page and keep by your desk**

```
╔════════════════════════════════════════════════════════════════════════════╗
║                    PROMETHEUS RISK PLATFORM MODULES                        ║
║                   (Use Ctrl+F to jump to sections)                         ║
╚════════════════════════════════════════════════════════════════════════════╝

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 1: ORCHESTRATION (Entry points)                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 backend/main.py (MN)
     └─ PrometheusRunner.run_daily(run_date)
        Main entry point [RWA orchestrator]


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 2: CORE RISK ENGINES (Regulatory calculations)                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 CRE30-36: Credit Risk (Advanced IRB)
     └─ backend/engines/a_irb.py (AIB)
        ├─ AIRBEngine.compute_portfolio(exposures)
        └─ Calls: CAL (PD/LGD calibration)

  📍 CRE51-53: Counterparty Credit Risk
     ├─ backend/engines/sa_ccr.py (SC)
     │  ├─ SACCREngine.compute_ead(netting_set, run_date)
     │  └─ Regulatory: CRE52.7—52.23
     │
     └─ backend/engines/imm.py (IM)
        ├─ IMMEngine.run_for_portfolio(trades, netting_set)
        └─ Monte Carlo (2K scenarios)

  📍 CNE54: CCP Valuation Adjustments
     └─ backend/engines/ccp.py (CC)
        └─ compute_ccp_rwa(exposures)

  📍 MAR20-33: Market Risk (FRTB SBM)
     └─ backend/engines/frtb.py (FX)
        ├─ FRTBEngine.compute(portfolio_id, sensitivities, pnl_series)
        ├─ Risk classes: GIRR, FX, EQ_LARGE, EQ_SMALL, CSR_NS, CMDTY
        └─ BacktestEngine.evaluate(predicted_var, actual_pnl)

  📍 MAR50: CVA Risk
     └─ backend/engines/cva.py (CV)
        └─ CVAEngine.compute_portfolio_cva(inputs, ccr_rwa, ratings, date)
           Methods: SA_CVA, BA_CVA, CCR_PROXY (fallback)

  📍 CAP10-50: Capital Adequacy & GSIB
     └─ backend/engines/gsib_capital.py (GS)
        └─ compute_capital_adequacy(rwa_total, gsib)
           Returns: CET1, Tier1, Total ratios + surcharges


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 3: PHASE 2A ENHANCEMENTS (Post-processing)                         ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 CRR3 Art. 12a: Dynamic Output Floor
     └─ backend/capital/output_floor.py (OF)
        ├─ DynamicOutputFloorCalculator()
        ├─ apply_floor(total_rwa, sa_rwa, airb_rwa, regime)
        └─ Regime: normal (0.5%), stressed (1.5%), crisis (2.0%)

  📍 CRR3 Art. 87a: ESG/Climate Risk
     └─ backend/climate/esg_framework.py (ESG)
        ├─ ESGRiskCalculator()
        ├─ compute_esg_uplift(sector, risk_level, pd_base)
        └─ 9 sectors: Energy, Utilities, Transport, Materials, Tech, etc.

  📍 SR 11-7: Model Governance
     └─ backend/validation/governance_checker.py (GV)
        ├─ GovernanceChecker()
        └─ check_sr117_compliance(run_date) [5 checks: validation, calibration, 
           output reasonableness, regulatory compliance, DQ]

  📍 Audit Trail: Calculation Traceability
     └─ backend/audit/trace_engine.py (TR)
        ├─ TraceEngine()
        ├─ Level 1: RWA total
        ├─ Level 2: Component (Credit, CCR, Market, CVA, CCP, Op)
        └─ Level 3: Formula (PD × LGD × MA × N(...))

  📍 Data Quality Framework
     └─ backend/data_quality/dqms.py (DQ)
        ├─ DataQualityManager()
        ├─ Dimensions: Completeness, Accuracy, Consistency, Timeliness, Uniqueness
        └─ Returns: Score 0–100 + status


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 4: SCENARIO & SENSITIVITY ANALYSIS                                 ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 Scenario Analysis (5+ regulatory scenarios)
     ├─ backend/scenarios/library.py (SC_LIB)
     │  └─ get_all_scenarios() returns:
     │     BASELINE_CURRENT, CRISIS_2008, ECB_CRDP, FED_ADVERSE,
     │     FED_SEVERELY_ADVERSE, HFL_2024
     │
     └─ backend/scenarios/engine.py (SC_ENG)
        └─ compute_scenario_rwa(portfolio, scenario)

  📍 Greeks & Sensitivities (A-IRB parameters)
     └─ backend/sensitivities/__init__.py (SNS)
        ├─ compute_greeks(portfolio, base_rwa)
        │  Returns: delta_pd, delta_lgd, delta_maturity, rho_correlation
        └─ Shocks: 1bp PD, 5% LGD, 0.5Y maturity, 5% correlation


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 5: DATA MANAGEMENT & CALIBRATION                                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 Master Calibration Module
     └─ backend/data_sources/calibration.py (CAL)
        ├─ CalibratedParams dataclass
        ├─ calibrate_and_apply(market_params, lookback_days)
        └─ Provides: PD, LGD, correlation, market curves

  📍 Credit Calibration (by sector)
     └─ backend/data_sources/credit_calibration.py (CCR_CAL)
        ├─ calibrate_pd_by_sector(historical_defaults, lookback_years)
        ├─ calibrate_lgd(recovery_data, cured_rates)
        └─ calibrate_correlation_matrix(returns_data, periods)

  📍 Market Data Provider (Bloomberg | Refinitiv | Internal)
     └─ backend/data_sources/market_data_provider.py (MD)
        ├─ fetch_yield_curve(as_of_date)
        ├─ fetch_credit_spreads(issuer_ids, as_of_date)
        └─ fetch_equity_data(underlyings, as_of_date)

  📍 Market Regime Classification
     └─ backend/data_sources/market_state.py (MS)
        └─ infer_market_regime(market_data) → "normal" | "stressed" | "crisis"

  📍 CDS Spread Service
     └─ backend/data_sources/cds_spread_service.py
        └─ Used by: CVA engine for counterparty spreads

  📍 Loss Event Database (Operational Risk)
     └─ backend/data_sources/loss_event_database.py
        └─ Historical loss events (for OPE25 calibration)

  📍 PostgreSQL Persistence Layer
     └─ backend/data_sources/persistence.py (PER)
        ├─ ensure_schema() → create tables if needed
        ├─ persist_run(run_date, results) → INSERT
        └─ Tables: prometheus_risk_runs, prometheus_trade_details,
           prometheus_rwa_components, output_floor_tracking, esg_risk_tracking,
           data_quality_scorecard, governance_check_results, calculation_trace_log


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 6: DATA GENERATORS (Portfolio builder)                             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 Portfolio Generation
     └─ backend/data_generators/portfolio_generator.py (PG)
        └─ build_full_dataset(book_date) → derivative_portfolios + banking_portfolios

  📍 CVA & CCP Input Generation
     └─ backend/data_generators/cva_generator.py (CVA_GEN)
        ├─ build_cva_inputs(derivative_results, seed)
        └─ build_ccp_exposures(seed)

  📍 Operational Loss Generation
     └─ backend/data_generators/operational_loss_generator.py
        └─ For OPE25 scenario testing


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ LAYER 7: INFRASTRUCTURE & UI                                             ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  📍 Configuration
     └─ backend/config.py
        ├─ DB_CONFIG: PostgreSQL connection
        ├─ SACCR, IMM, AIRB, FRTB, MARKET_DATA: regulatory params
        └─ OPERATIONAL_RISK_ENABLED: OPE25 flag

  📍 Dashboard UI (Streamlit)
     └─ dashboard/app.py
        ├─ Portfolio overview
        ├─ RWA drill-down
        ├─ Capital ratio trends
        ├─ Scenario analysis
        ├─ Backtesting results
        └─ Phase 2A monitoring (DQ, floor, governance)

  📍 Dashboard Styling
     └─ dashboard/styling.py

  📍 Docker Deployment
     └─ docker/
        ├─ docker-compose.yml
        └─ init.sql


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ KEY LOOKUP: "I need to find..."                                          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

  → "PD calculation"
    └─ AIB (a_irb.py) → compute_portfolio() → calls CAL (calibration.py)

  → "LGD adjustment"
    └─ AIB → CCR_CAL → calibrate_lgd() → LGD floors by collateral type

  → "Floor application"
    └─ OF (output_floor.py) → apply_floor() → regime-based multiplier

  → "ESG risk impact"
    └─ ESG (esg_framework.py) → compute_esg_uplift() → sector-specific

  → "Audit trail"
    └─ TR (trace_engine.py) → generate_trace_report() → 3-level detail

  → "Data quality check"
    └─ DQ (dqms.py) → compute_dq_scorecard() → 5 dimensions

  → "Governance compliance"
    └─ GV (governance_checker.py) → check_sr117_compliance() → 5 checks

  → "Market data"
    └─ MD (market_data_provider.py) → fetch_* methods → Bloomberg/Refinitiv

  → "Scenario analysis"
    └─ SC_LIB (scenarios/library.py) → 6 scenarios → re-pricing

  → "Greeks/sensitivities"
    └─ SNS (sensitivities/__init__.py) → 4 Greeks (PD, LGD, M, R)

  → "Historical data"
    └─ PER (persistence.py) → retrieve_run() → PostgreSQL


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ REGULATORY STANDARDS CROSS-REFERENCE                                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

CRE30 ──→ AIB        CRE51 ──→ SC          MAR20 ──→ FX
CRE31 ──→ AIB        CRE52 ──→ SC          MAR21 ──→ FX
CRE32 ──→ AIB        CRE53 ──→ IM          MAR33 ──→ FX
CRE36 ──→ AIB        CRE54 ──→ CC          MAR50 ──→ CV

RBC20.11 → OF        CAP10 ──→ GS          SR 11-7 ──→ GV
CRR3 Art.12a → OF    CAP50 ──→ GS          OPE25 ──→ OP
CRR3 Art.87a → ESG   ECB ──────→ ESG


┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ PIN THIS TO YOUR WALL / KEEP AT YOUR DESK                                ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

📄 Full documentation:
  • PROMETHEUS_CODE_GRAPH.md ← Full module inventory + dependencies
  • PROMETHEUS_CODE_GRAPH_QUICK_LOOKUP.md ← Token-efficient patterns
  • PROMETHEUS_TECHNICAL_ARCHITECTURE.md ← 7-layer system design
  • PROMETHEUS_FSD.md ← Functional specification

🚀 Phase 2 implementation:
  • PHASE2A_INTEGRATION_GUIDE.md ← How all 5 modules integrate
  • ENHANCEMENT_ROADMAP.md ← Strategic priorities

💻 Running the system:
  • backend/main.py ← Run: python backend/main.py
  • dashboard/app.py ← Run: streamlit run dashboard/app.py
  • docker/docker-compose.yml ← Run: docker-compose up

🧪 Testing:
  • tests/test_engines.py ← Core engine tests
  • tests/test_phase2a.py ← Phase 2A tests
  • All 48+ tests pass: pytest tests/ -v


═══════════════════════════════════════════════════════════════════════════════

Use this map to cut your Claude prompt tokens by 60–90%.

Reference structure: "In PROMETHEUS_CODE_GRAPH [LAYER X: name], locate:"
Example: "In PROMETHEUS_CODE_GRAPH [LAYER 2: Core Risk Engines], show me AIB.compute_portfolio()"

═══════════════════════════════════════════════════════════════════════════════
```

---

## 🎯 PRINT-FRIENDLY QUICK KEYS (Memorize these)

```
Quick reference:     What it contains:
─────────────────────────────────────
MN                → Main orchestrator (entry point)
AIB, SC, IM, FX, CV, CC, GS → 7 core engines
OF, ESG, DQ, TR, GV → Phase 2A (5 enhancements)
CAL, MD, PER      → Data sources
PG, CVA_GEN       → Portfolio builders
```

**Usage in prompts:**
- Instead of: "Show me the A-IRB engine file and explain the compute_portfolio method..."
- Use: "PROMETHEUS_CODE_GRAPH: In AIB, show compute_portfolio() and how it calls CAL."

---

## ✅ THIS ONE-PAGE REFERENCE SAVES

- **Per question:** 100–300 tokens
- **Per session:** 2,000–5,000 tokens
- **Across project:** 50,000+ tokens annually

**Keep this open while coding.**

---

**Format:** ASCII visual index [Print-friendly, no images]  
**Last Updated:** April 29, 2026

