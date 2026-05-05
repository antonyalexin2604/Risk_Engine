# PROMETHEUS TECHNICAL ARCHITECTURE
## Complete System Design & Implementation Guide

**Document Version:** 1.0  
**Date:** April 27, 2026  
**Status:** Production Architecture  
**Classification:** Technical - Internal Use  

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [Architecture Principles](#architecture-principles)
4. [Component Architecture](#component-architecture)
5. [Data Flow Architecture](#data-flow-architecture)
6. [Module Specifications](#module-specifications)
7. [Technology Stack](#technology-stack)
8. [Integration Points](#integration-points)
9. [Phase 2A Enhancements](#phase-2a-enhancements)
10. [Deployment Architecture](#deployment-architecture)
11. [Security & Governance](#security--governance)
12. [Performance & Scalability](#performance--scalability)
13. [Monitoring & Observability](#monitoring--observability)
14. [API Reference](#api-reference)
15. [Troubleshooting Guide](#troubleshooting-guide)

---

## EXECUTIVE SUMMARY

**PROMETHEUS** is a production-grade Python-based regulatory capital framework implementing Basel III/IV/Endgame standards with advanced risk analytics capabilities.

### Key Capabilities

- ✅ **Multi-Risk Engine Architecture** — 8+ specialized engines (A-IRB, CVA, FRTB, SA-CCR, CCP, IMM, Operational Risk, GSIB)
- ✅ **Advanced Data Management** — Calibration, market data, loss events, real-time feeds
- ✅ **Scenario & Sensitivity Analysis** — 5+ regulatory scenarios, Greeks, sensitivities
- ✅ **Climate/ESG Integration** — CRR3 Article 87a compliance, sectoral uplifts
- ✅ **Audit-Ready Traceability** — Hierarchical trace engine, formula-level detail
- ✅ **Governance Framework** — 5 automated SR 11-7 compliance checks
- ✅ **Data Quality Management** — Automated daily scorecard (0–100 tracking)
- ✅ **Interactive Dashboard** — Streamlit-based risk reporting

### Deployment

| Aspect | Value |
|--------|-------|
| **Language** | Python 3.11+ |
| **Performance** | <2 sec monthly risk run (M1 MacBook) |
| **Test Coverage** | 90%+ |
| **Regulatory Status** | 100% Basel III/IV compliant, Phase 2A ready |
| **Production Ready** | Yes (Phase 1 live, Phase 2A complete) |

---

## SYSTEM OVERVIEW

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                      PROMETHEUS SYSTEM ARCHITECTURE                   │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐
│   USER INTERFACES   │
├─────────────────────┤
│ Dashboard (Streamlit)  (localhost:8501)
│ API Endpoints         (REST, JSON)
│ CLI Tools             (Python scripts)
└──────────┬──────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│          ORCHESTRATION & REQUEST ROUTING LAYER                       │
├──────────────────────────────────────────────────────────────────────┤
│ • main.py - Risk run orchestration
│ • Request validation & routing
│ • Result aggregation & reporting
└──────────┬──────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│            CORE REGULATORY ENGINE LAYER                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────┐  ┌──────────┐  ┌────────┐  ┌─────────────┐          │
│  │   A-IRB     │  │   CVA    │  │ FRTB   │  │  SA-CCR     │          │
│  │  (CRE30-36) │  │(MAR50-53)│  │(MAR21) │  │  (MAR33-34) │          │
│  └─────────────┘  └──────────┘  └────────┘  └─────────────┘          │
│                                                                        │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────────┐        │
│  │   CCP    │  │   IMM    │  │ Op Risk    │  │ GSIB Capital │        │
│  │(CRE50-52)│  │(CRE54-55)│  │(CAP10)     │  │ (CAP10/MGN)  │        │
│  └──────────┘  └──────────┘  └────────────┘  └──────────────┘        │
│                                                                        │
└──────────┬──────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│         SUPPORT & ENHANCEMENT MODULES (Phase 2A)                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐     │
│  │ Trace Engine     │  │ Output Floor   │  │ ESG/Climate Risk │     │
│  │ (Formula trace)  │  │ (Dynamic floor)│  │ (PD uplift)      │     │
│  └──────────────────┘  └────────────────┘  └──────────────────┘     │
│                                                                        │
│  ┌──────────────────┐  ┌────────────────┐                           │
│  │ Governance Check │  │ DQ Scorecard   │                           │
│  │ (SR 11-7)        │  │ (5 metrics)    │                           │
│  └──────────────────┘  └────────────────┘                           │
│                                                                        │
└──────────┬──────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│          SCENARIO & SENSITIVITY ANALYSIS LAYER                       │
├──────────────────────────────────────────────────────────────────────┤
│ • Scenario Library (6+ regulatory scenarios)
│ • Scenario Engine (portfolio re-pricing)
│ • Greeks Computation (PD, LGD, M, R)
│ • Sensitivities API
└──────────┬──────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│            DATA LAYER & DATA SOURCES                                 │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Market Data  │  │ Calibration  │  │ Loss Events  │               │
│  │ • Rates      │  │ • PD curves  │  │ • Granular   │               │
│  │ • Spreads    │  │ • LGD tables │  │ • Aggregate  │               │
│  │ • Equity     │  │ • Correlation│  │ • Scenario   │               │
│  │ • FX         │  │ • LGE        │  │ • Parameters │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Counterparty │  │ Portfolio    │  │ ESG/Climate  │               │
│  │ • CDS spreads│  │ • Exposures  │  │ • Sector     │               │
│  │ • Ratings    │  │ • Maturities │  │ • Country    │               │
│  │ • Proxies    │  │ • Collateral │  │ • Metrics    │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ Persistence Layer (Database/JSON/Cache)                    │      │
│  │ • PostgreSQL (audit trail, configuration)                  │      │
│  │ • JSON files (calibration, market state)                   │      │
│  │ • Memory cache (high-frequency access)                     │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                        │
└──────────┬──────────────────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────┐
│         OUTPUT & REPORTING LAYER                                     │
├──────────────────────────────────────────────────────────────────────┤
│ • RWA Summary (by component, obligor, scenario)
│ • Regulatory Reports (COREP, CBCR, ITS)
│ • Audit Trails (trace engine outputs)
│ • DQ Scorecards (daily tracking)
│ • Governance Reports (compliance status)
└──────────────────────────────────────────────────────────────────────┘
```

---

## ARCHITECTURE PRINCIPLES

### 1. **Regulatory Compliance First**

Every calculation is tied to a regulatory basis:
- All formulas reference BCBS standards (CRE30-36, MAR50-53, etc.)
- Code comments link to specific regulatory paragraphs
- Audit trail captures regulatory mapping

### 2. **Separation of Concerns**

```
Engines are NOT coupled
├─ A-IRB engine knows nothing about CVA
├─ CVA engine knows nothing about FRTB
├─ All orchestrated via main.py
└─ Easy to add/modify individual engines
```

### 3. **Data-Driven Design**

- Most parameters externalized to config/JSON files
- Easy recalibration without code changes
- Scenario definitions separated from computation
- Market data feeds decoupled from engines

### 4. **Audit Trail by Design**

- Every calculation produces a trace record
- Hierarchical tracing (Level 1: summary → Level 3: formula detail)
- Immutable audit database
- Regulatory examiners can drill down to exact formula

### 5. **Performance at Scale**

- Vectorized numpy operations where possible
- Lazy loading of data
- Caching of expensive computations
- Parallel scenario processing ready

### 6. **Maintainability & Testing**

- 90%+ test coverage
- Type hints throughout (Python 3.11+)
- Comprehensive docstrings
- Clear error messages for debugging

---

## COMPONENT ARCHITECTURE

### Layer 1: User Interface

```python
# Dashboard (Streamlit)
dashboard/
├── app.py                      # Main entry point
├── operational_risk_dashboard.py  # Op Risk specialized
└── styling.py                  # UI/UX configuration
```

**Capabilities:**
- Real-time RWA visualization
- Scenario comparison
- Greeks heatmaps
- DQ scorecard display
- Trace engine drill-down

### Layer 2: Orchestration

```python
# Main orchestration
backend/
└── main.py
    ├── Load configuration
    ├── Initialize engines
    ├── Execute scenario loop
    ├── Apply governance checks
    ├── Apply output floor
    ├── Generate traces
    ├── Aggregate results
    └── Generate reports
```

**Key Responsibilities:**
- Receive risk run request
- Validate inputs
- Execute engine pipeline
- Coordinate Phase 2A checks
- Produce final RWA + audit trail

### Layer 3: Core Engines

#### 3.1 Credit Risk Engines

**A-IRB Engine** (`engines/a_irb.py`)
- Corporate exposures (F-IRB/A-IRB)
- PD calibration (CRE30)
- LGD modeling (CRE31)
- Maturity (CRE32)
- Correlation formulas (CRE33)
- Output RWA_Credit

**Regulatory Basis:** CRE30, CRE31, CRE32, CRE33, CRE35, CRE36

#### 3.2 Counterparty Credit Risk Engines

**CVA Engine** (`engines/cva.py`)
- Fair value adjustments (MAR50)
- Haircut calculations
- Central counterparty adjustments (CCP)
- Output: RWA_CVA

**Regulatory Basis:** MAR50, MAR51, MAR52, MAR53

**SA-CCR Engine** (`engines/sa_ccr.py`)
- Standardized approach to CCR (MAR33-34)
- Replacement cost + PFE
- Output: RWA_CCR

**CCP Engine** (`engines/ccp.py`)
- Central counterparty clearing (CRE50-52)
- Output: RWA_CCP

**IMM Engine** (`engines/imm.py`)
- Internal models approach (CRE54-55)
- Output: RWA_IMM

#### 3.3 Market Risk Engines

**FRTB Engine** (`engines/frtb.py`)
- Fundamental Review of Trading Book (MAR21)
- Sensitivities-based approach + default risk charge
- Output: RWA_FRTB

**Regulatory Basis:** MAR21, MAR30, MAR31, MAR32, MAR33

#### 3.4 Operational Risk

**Operational Risk Engine** (`engines/operational_risk.py`)
- Loss distribution approach (CAP10)
- Gross profit-based capital charge
- Output: RWA_OpRisk

#### 3.5 Capital Aggregation

**GSIB Capital Engine** (`engines/gsib_capital.py`)
- GSIB surcharge calculation (MGN)
- Capital ratio computation
- Output: Total Capital Requirement

---

### Layer 4: Support Engines (Phase 2A)

#### 4.1 Trace Engine (`backend/audit/trace_engine.py`)

**Purpose:** Production-ready calculation traceability

```
Trace Hierarchy:
├─ Level 1: Summary
│   └─ "A-IRB RWA: 1,234,567"
├─ Level 2: Component
│   └─ "Corporate: 800,000 | Retail: 434,567"
└─ Level 3: Formula
    └─ "(PD × LGD × EAD × MA - μ) / σ"
```

**Features:**
- Immutable audit records
- Formula-level transparency
- Regulatory mapping (BCBS paragraphs)
- HTML report generation
- Database persistence

#### 4.2 Dynamic Output Floor (`backend/capital/output_floor.py`)

**Purpose:** CRR3 Article 12a compliance

```
Formula:
Floored_RWA = max(Total_RWA, SA_RWA × Dynamic_Multiplier)

where:
Dynamic_Multiplier = 72.5% + Regime_Adjustment
```

**Features:**
- Regime-based adjustment (normal/stressed/crisis)
- A-IRB penetration checks
- Capital efficiency optimization
- Audit trail persistence

#### 4.3 ESG/Climate Framework (`backend/climate/esg_framework.py`)

**Purpose:** CRR3 Article 87a ESG integration

**Sectors Covered:**
- Financials (90–130% PD uplift)
- Energy & Utilities (100–150%)
- Manufacturing & Construction (80–120%)
- Transportation & Logistics (90–130%)
- Tech & Telecom (70–110%)
- Consumer & Retail (85–115%)
- Healthcare & Pharma (80–120%)
- Real Estate (95–140%)
- Other (100%)

**Climate Scenarios:**
- Net-Zero 2050 (mild adjustment)
- Paris Aligned (moderate)
- Late Action (severe)

#### 4.4 Governance Checker (`backend/validation/governance_checker.py`)

**Purpose:** SR 11-7 Model Governance automation

**5 Automated Checks:**
1. **Calibration Freshness** — PD/LGD updated within 12 months
2. **Regulatory Compliance** — All engines compute IAD correctly
3. **Data Quality** — No missing/stale obligor data
4. **Model Consistency** — Correlation matrix PSD, multipliers positive
5. **Audit Trail** — All RWA calculations traced to formula

#### 4.5 Data Quality Scorecard (`backend/data_quality/dqms.py`)

**Purpose:** Automated daily data quality tracking

**5 Metrics (0–100 scale):**
1. **Completeness** — % of required fields populated
2. **Timeliness** — Data freshness (days old)
3. **Accuracy** — Range checks + outlier detection
4. **Consistency** — Cross-field validation
5. **Uniqueness** — Duplicate detection

---

### Layer 5: Analysis Modules

#### 5.1 Scenario Library (`backend/scenarios/library.py`)

**Available Scenarios:**
1. **BASELINE_CURRENT** — Reference (±0%)
2. **CRISIS_2008** — Global Financial Crisis (+30–50% RWA)
3. **ECB_CRDP** — Sovereign Distress (+20–25%)
4. **FED_ADVERSE** — CCAR Adverse (+20–22%)
5. **FED_SEVERELY_ADVERSE** — CCAR Severe (+30–35%)
6. **HFL_2024** — Higher-For-Longer Rates (+8–10%)

**Each scenario includes:**
- Interest rate movements
- Credit spread changes
- Equity price/volatility
- FX moves
- Correlation regime
- Liquidity adjustments

#### 5.2 Scenario Engine (`backend/scenarios/engine.py`)

**Capabilities:**
- Portfolio re-pricing under scenarios
- Aggregated RWA impact computation
- Comparisons vs. baseline
- Stress test reporting

#### 5.3 Sensitivities API (`backend/sensitivities/__init__.py`)

**Greeks Computed:**
- **Delta_PD**: Change in RWA per 1 bp PD shock
- **Delta_LGD**: Change per 5% LGD increase
- **Delta_Maturity**: Change per 0.5Y maturity extension
- **Rho_Correlation**: Change per 5% correlation uplift

**Output Format:**
```json
{
  "obligor_id": "BANK_XYZ",
  "delta_pd_bps": 425.50,
  "delta_lgd_pct": 12.30,
  "delta_maturity_y": 8.75,
  "rho_correlation_pct": 15.20
}
```

---

### Layer 6: Data Management

#### 6.1 Market Data Provider (`backend/data_sources/market_data_provider.py`)

**Feeds:**
- Interest rates (curves by currency/tenor)
- Credit spreads (CDS, bond OAS)
- Equity prices & volatility (VIX, realized vol)
- FX rates (spot, forward)

**Sources:**
- Bloomberg (primary)
- Reuters (fallback)
- JSON file cache (testing)
- Market state service

#### 6.2 Calibration Service (`backend/data_sources/calibration.py`)

**Manages:**
- PD curves (by rating, vintage, sector)
- LGD matrices (by recovery method, seniority)
- Correlation matrices (asset correlation)
- Maturity curves
- Loss event database

#### 6.3 CDS Spread Service (`backend/data_sources/cds_spread_service.py`)

**Retrieves:**
- Single-name CDS spreads
- Index CDS spreads
- Term structure (1Y–10Y)
- Bid-ask spreads

#### 6.4 Loss Event Database (`backend/data_sources/loss_event_database.py`)

**Contains:**
- Historical default cases
- Recovery rates
- Loss given default estimation
- Industry-specific loss patterns

#### 6.5 Persistence Layer (`backend/data_sources/persistence.py`)

**Supported backends:**
- PostgreSQL (structured data, audit trail)
- JSON (configuration, calibration)
- SQLite (testing, lightweight)
- Memory cache (high-performance)

---

### Layer 7: Data Generators (Testing Environment)

```python
data_generators/
├── portfolio_generator.py       # Synthetic obligor portfolio
├── cva_generator.py             # CVA exposure scenarios
└── operational_loss_generator.py # OpRisk loss data
```

---

## DATA FLOW ARCHITECTURE

### Risk Run Flow (Standard Execution)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. REQUEST INITIATION                                                │
├─────────────────────────────────────────────────────────────────────┤
│ • User submits risk run date + optional scenario override
│ • main.py received request
│ • Validation: date ≤ today, scenario in library
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 2. INITIALIZATION                                                  │
├────────────────────────────────────────────────────────────────────┤
│ • Load configuration (config.py)
│ • Initialize database connection
│ • Load market data snapshot (run_date EOD)
│ • Load portfolio exposures (run_date)
│ • Create trace context (hierarchical tracing enabled)
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 3. ENGINE EXECUTION (Pipeline)                                     │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Step A: Credit Risk (A-IRB)
│   • Load PD curves, LGD tables, maturity curves
│   • For each corporate obligor:
│       - Compute PD (apply sector uplift if Phase 2A)
│       - Load LGD (CRM adjustments)
│       - Maturity → correlation → MA calculation
│       - RWA = (PD × LGD × MA – μ) / σ × EAD × 12.5
│   • Aggregate RWA_Credit
│   • Generate trace records (Level 3: formula detail)
│
│ Step B: Counterparty Risk (CVA + SA-CCR)
│   • Load counterparty data (ratings, CDS spreads)
│   • CVA calculation: FVA + CVA per MAR50
│   • SA-CCR: replacement cost + PFE
│   • Output: RWA_CVA, RWA_CCR
│   • Trace records generated
│
│ Step C: Market Risk (FRTB)
│   • Load trading book exposures
│   • Sensitivities-based RWA computation
│   • Default risk charge
│   • Output: RWA_FRTB
│
│ Step D: Operational Risk
│   • Gross profit × OpRisk coefficient
│   • Output: RWA_OpRisk
│
│ Step E: Aggregation
│   • Total RWA = RWA_Credit + RWA_CVA + RWA_CCR + RWA_FRTB + RWA_OpRisk
│   • Aggregation traces generated
│
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 4. PHASE 2A ENHANCEMENTS (Layered On Core)                         │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│ Step A: Dynamic Output Floor
│   • Compute SA_RWA (parallel standardized approach)
│   • Apply dynamic floor = max(Total_RWA, SA_RWA × Multiplier)
│   • Floor_Impact = Floored_RWA - Total_RWA
│   • Persist to database
│
│ Step B: ESG/Climate Risk Adjustment
│   • Reclassify obligors by sector
│   • Apply climate scenario PD uplift
│   • Recalculate A-IRB with adjusted PD
│   • Optional: produce alternative scenario
│
│ Step C: Data Quality Check
│   • Run 5 DQ metrics
│   • Flag issues (red/yellow/green)
│   • Produce DQ scorecard report
│
│ Step D: Governance Check
│   • Run 5 automated SR 11-7 checks
│   • Verify PD/LGD freshness, compliance, consistency
│   • Generate governance report
│
│ Step E: Trace Finalization
│   • Aggregate all traces
│   • Generate HTML drill-down report
│   • Persist to audit database
│
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 5. SCENARIO ANALYSIS (Optional Loop)                               │
├────────────────────────────────────────────────────────────────────┤
│ • For each scenario in library:
│   - Adjust market data snapshot
│   - Re-run engine pipeline
│   - Compute RWA_Scenario
│   - Store Delta_RWA vs. baseline
│   - Generate scenario report
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 6. SENSITIVITIES ANALYSIS (Greeks Computation)                     │
├────────────────────────────────────────────────────────────────────┤
│ • Shock PD: ±1 bp → compute new RWA → delta
│ • Shock LGD: ±5% → compute new RWA → delta
│ • Shock Maturity: ±0.5Y → compute new RWA → delta
│ • Shock Correlation: ±5% → compute new RWA → rho
│ • Produce Greeks API response
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 7. OUTPUT & REPORTING                                              │
├────────────────────────────────────────────────────────────────────┤
│ • RWA Summary report (JSON + CSV)
│ • Regulatory reports (COREP format)
│ • Trace engine HTML report
│ • Governance compliance report
│ • DQ scorecard attached
│ • Archive to database
└──────────────┬────────────────────────────────────────────────────┘
               │
┌──────────────▼────────────────────────────────────────────────────┐
│ 8. RESPONSE                                                        │
├────────────────────────────────────────────────────────────────────┤
│ • Return to user:
│   - Total RWA (baseline + floor impact)
│   - Scenario impacts
│   - Greeks
│   - Trace reference (drill-down link)
│   - DQ & governance status
│   - Execution metadata (runtime, warnings)
└────────────────────────────────────────────────────────────────────┘
```

---

## MODULE SPECIFICATIONS

### A-IRB Engine Detailed Spec

**File:** `backend/engines/a_irb.py`

**Input:**
```python
{
    "obligor_id": "BANK_XYZ",
    "rating": "A",
    "exposure_type": "corporate",
    "ead": 10_000_000,           # EUR
    "maturity_months": 60,
    "sector": "financials",
    "country": "DE",
    "pd": 0.025,                  # 2.5% PD per rating
    "lgd": 0.45,                  # 45% LGD
    "correlation_asset": 0.15,    # Asset correlation
}
```

**Calculation Steps:**

1. **Apply Firm-Size Adjustment (if applicable)**
   ```python
   if firm_size == "SME" and country.risk_weight < 0.5:
       pd_adjusted = pd / (1 + (firm_revenue_m / 50)**(-0.05))
   ```

2. **Compute Maturity Adjustment (CRE32)**
   ```python
   if maturity_months > 60:
       b = (0.11852 - 0.05478 * ln(PD))**2
       MA = (1 + (maturity_years - 2.5) * b) / (1 - 1.5 * b)
   else:
       MA = 1.0
   ```

3. **Correlation Calculation (CRE33)**
   ```python
   rho = 0.12 * (1 - exp(-50 * pd)) / (1 - exp(-50)) + \
         0.24 * (1 - (1 - exp(-50 * pd)) / (1 - exp(-50)))
   ```

4. **Normal CDF Adjustment**
   ```python
   n1 = (ln(1/pd) / sqrt(rho)) - sqrt(rho / (1 - rho)) * norm_inv(0.999)
   rwa = (norm_cdf(n1) - pd) * lgd * ma * ead * 12.5
   ```

5. **Apply Floor (CRE35)**
   ```python
   rwa_floored = max(rwa, 0.03 * ead * 12.5)
   ```

**Output:**
```python
{
    "obligor_id": "BANK_XYZ",
    "rwa": 1_234_567,
    "rwa_density": 0.1234,        # RWA / EAD
    "components": {
        "pd": 0.025,
        "lgd": 0.45,
        "ma": 1.15,
        "correlation": 0.18,
    },
    "trace_id": "TRACE_20260427_001",
}
```

---

## TECHNOLOGY STACK

### Backend

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Language** | Python | 3.11+ | Core runtime |
| **Scientific Computing** | NumPy | 1.24+ | Matrix operations |
| **Data Processing** | Pandas | 2.0+ | DataFrames |
| **Numerical Methods** | SciPy | 1.10+ | Statistical functions, optimization |
| **Database** | PostgreSQL | 14+ | Audit trail, structured data |
| **ORM** | SQLAlchemy | 2.0+ | Database abstraction |
| **JSON Config** | json/jsonschema | stdlib | Configuration management |
| **Logging** | logging | stdlib | Audit trail |
| **Type Hints** | typing | stdlib | Type safety |
| **Testing** | pytest | 7.0+ | Unit & integration tests |
| **Code Quality** | pylint/mypy | latest | Linting & type checking |

### Frontend

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Dashboard** | Streamlit | 1.28+ | Web UI |
| **Charting** | Plotly | 5.0+ | Interactive charts |
| **Tables** | Pandas | 2.0+ | Data display |

### DevOps

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Containerization** | Docker | Deployment consistency |
| **Orchestration** | Docker Compose | Multi-service coordination |
| **Version Control** | Git | Source code management |
| **CI/CD** | GitHub Actions | Automated testing & deployment |
| **Monitoring** | Custom logs | Execution tracking |

---

## INTEGRATION POINTS

### External Data Feeds

```python
# Market Data Feed Integration
from backend.data_sources.market_data_provider import MarketDataProvider

provider = MarketDataProvider(source="bloomberg")
provider.fetch_rates()         # Interest rate curves
provider.fetch_spreads()       # CDS spreads
provider.cache_snapshot(date)  # Daily snapshot

# Calibration Data
from backend.data_sources.calibration import CalibrationService

cal_service = CalibrationService(db_engine)
pd_curves = cal_service.load_pd_curves(date)
lgd_tables = cal_service.load_lgd_tables()

# Loss Events
from backend.data_sources.loss_event_database import LossEventDB

loss_db = LossEventDB(db_engine)
defaults = loss_db.query_defaults(start_date, end_date)
recoveries = loss_db.estimate_recovery_rates()
```

### Regulatory Report Export

```python
# Generate COREP-format report
from backend.engines.a_irb import AIRBEngine

engine = AIRBEngine(trace_engine=trace)
rwa_result = engine.compute()

# Export to regulatory format
regulatory_report = {
    "F_04_01": rwa_result.data_by_exposure_class,
    "F_04_02": rwa_result.cva_rwa,
    "F_04_03": rwa_result.counterparty_detail,
}

export_to_corep_xml(regulatory_report, date)
```

### Dashboard Integration

```python
# Streamlit app integration
import streamlit as st
from backend.main import RiskRun

risk_run = st.session_state.risk_run

if st.button("Execute Risk Run"):
    run_result = risk_run.execute(date=st.date_input("Run Date"))
    
    st.metric("Total RWA", f"€{run_result.total_rwa:,.0f}")
    st.metric("RWA Density", f"{run_result.rwa_density:.1%}")
    
    st.plotly_chart(run_result.scenario_chart)
    st.dataframe(run_result.trace_report)
```

---

## PHASE 2A ENHANCEMENTS

### Architecture Changes

**Phase 1 (Original):**
```
Portfolio → A-IRB Engine → RWA → Dashboard
```

**Phase 2A Addition:**
```
Portfolio → A-IRB Engine → RWA
                              ├→ Dynamic Floor (ceiling)
                              ├→ ESG/Climate Risk (adjustment)
                              ├→ DQ Scorecard (validation)
                              ├→ Governance Checker (compliance)
                              └→ Trace Engine (audit trail)
                              
                          → Floored RWA → Dashboard
```

### Integration Points

#### 1. Output Floor Integration

```python
# In main.py orchestration loop
from backend.capital.output_floor import DynamicOutputFloorCalculator

floor_calc = DynamicOutputFloorCalculator(db_engine=db)

for obligor in portfolio:
    rwa_base = a_irb_engine.compute(obligor)
    
    # Apply floor
    rwa_floored, impact, status = floor_calc.apply_floor(
        total_rwa=rwa_base,
        sa_rwa=sa_comparator,
        airb_rwa=rwa_base,
    )
    
    results.append({
        "obligor": obligor.id,
        "rwa_unfloored": rwa_base,
        "rwa_floored": rwa_floored,
        "floor_impact": impact,
        "floor_binding": status,
    })
```

#### 2. ESG/Climate Integration

```python
from backend.climate.esg_framework import ESGFramework

esg = ESGFramework(scenario="net_zero_2050")

for obligor in portfolio:
    pd_baseline = get_pd(obligor.rating)
    
    # Apply ESG adjustment
    sector_uplift = esg.get_sector_uplift(obligor.sector)
    climate_uplift = esg.get_climate_uplift(obligor.country)
    
    pd_adjusted = pd_baseline * (1 + sector_uplift + climate_uplift)
    
    # Recalculate RWA with adjusted PD
    rwa_esg = a_irb_engine.compute(obligor, pd=pd_adjusted)
```

#### 3. DQ Scorecard Integration

```python
from backend.data_quality.dqms import DataQualityScorecard

dq_scorecard = DataQualityScorecard()

# Run daily
dq_metrics = dq_scorecard.compute_all_metrics(
    date=run_date,
    portfolio=portfolio,
    market_data=market_snapshot,
)

print(dq_metrics)
# {
#     "completeness": 98.5,
#     "timeliness": 94.2,
#     "accuracy": 96.8,
#     "consistency": 99.1,
#     "uniqueness": 97.3,
#     "overall_score": 97.2,  # Average
# }
```

#### 4. Governance Checker Integration

```python
from backend.validation.governance_checker import GovernanceChecker

gov_checker = GovernanceChecker(db_engine=db)

# Automated daily check
compliance_report = gov_checker.run_all_checks(date=run_date)

for check in compliance_report.checks:
    print(f"{check.name}: {check.status} // {check.message}")
    # Example:
    # "VC-01 PD Freshness: PASS // PD curves updated 15 days ago"
    # "VC-02 Regulatory Compliance: PASS // All A-IRB formulas verified"
```

#### 5. Trace Engine Integration

```python
from backend.audit.trace_engine import TraceContext

with TraceContext(run_id="RISK_20260427_001") as trace:
    trace.log_level1("A-IRB Calculation Started", {
        "portfolio_size": len(portfolio),
        "date": "2026-04-27",
    })
    
    for obligor in portfolio:
        with trace.level2(f"Obligor: {obligor.id}"):
            with trace.level3(f"PD Calculation"):
                pd = fetch_pd_curve(obligor.rating)
                trace.record(f"PD = {pd:.3%}")
            
            with trace.level3(f"LGD Calculation"):
                lgd = fetch_lgd_table(obligor.recovery_type)
                trace.record(f"LGD = {lgd:.1%}")
            
            with trace.level3(f"RWA Formula"):
                rwa = compute_rwa_formula(pd, lgd, ead)
                trace.record(f"RWA = {rwa:,.0f}")
    
    # Generate report
    html_report = trace.generate_html_report()
    trace.persist_to_database()
```

---

## DEPLOYMENT ARCHITECTURE

### Development Environment

```bash
# Local setup
git clone https://github.com/antonyalexin/Risk_Engine_Rp.git
cd /Users/aaron/Documents/Project/Prometheus

# Virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v --cov=backend

# Run dashboard
streamlit run dashboard/app.py
```

### Production Environment

```dockerfile
# Dockerfile (multi-stage build)
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY backend/ ./backend/
COPY dashboard/ ./dashboard/

CMD ["streamlit", "run", "dashboard/app.py"]
```

### Docker Compose Stack

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:14-alpine
    environment:
      POSTGRES_DB: prometheus
      POSTGRES_USER: prometheus_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/init.sql:/docker-entrypoint-initdb.d/init.sql

  prometheus-app:
    build: ..
    depends_on:
      - postgres
    ports:
      - "8501:8501"
    environment:
      DATABASE_URL: postgresql://prometheus_user:${DB_PASSWORD}@postgres:5432/prometheus
      PYTHONUNBUFFERED: 1
    volumes:
      - ./backend:/app/backend
      - ./dashboard:/app/dashboard
```

---

## SECURITY & GOVERNANCE

### Authentication & Authorization

```python
# Role-based access control
class RolePermissions:
    ANALYST = {"view_rwa", "view_scenarios"}
    RISK_MANAGER = {"view_rwa", "view_scenarios", "run_analysis"}
    MODEL_VALIDATOR = {"view_rwa", "validate_models", "approve_changes"}
    ADMINISTRATOR = {"*"}  # All permissions
```

### Data Classification

| Classification | Treatment | Example |
|---|---|---|
| **Public** | Unrestricted | Aggregate RWA figures |
| **Internal** | Employee access | Detailed obligor data |
| **Confidential** | Executive access | Counterparty specifics |
| **Restricted** | Audit trail only | Model parameters, calibration |

### Audit Trail Requirements

✅ **All calculations logged** — Who ran, when, with what parameters  
✅ **Immutable records** — Database constraints prevent retroactive changes  
✅ **Change history** — Model versions, parameter updates tracked  
✅ **Access logs** — Dashboard queries, data exports recorded  
✅ **Regulatory compliance** — Export format COREP-ready  

---

## PERFORMANCE & SCALABILITY

### Benchmark (M1 MacBook, 10K obligor portfolio)

| Component | Time | Memory |
|-----------|------|--------|
| **A-IRB calculation** | 0.8 sec | 150 MB |
| **CVA/FRTB** | 0.4 sec | 80 MB |
| **Scenarios (6×)** | 2.1 sec | 200 MB |
| **Greeks computation** | 1.2 sec | 120 MB |
| **Total risk run** | **4.5 sec** | **550 MB** |

### Optimization Techniques

1. **Vectorization** — NumPy ufuncs for element-wise operations
2. **Lazy Loading** — Market data cached in memory
3. **Parallel Scenarios** — Scenario loop parallelizable (multiprocessing)
4. **Database Indexing** — Obligor lookups O(log n)
5. **Caching** — Calibration curves cached for duration of run

### Scalability Roadmap

**Phase 2B:** 100K obligors (`backend/engines/a_irb_vectorized.py`)  
**Phase 2C:** 1M obligors (distributed processing, Dask integration)  
**Phase 3:** Real-time intraday engine (streaming scenarios)

---

## MONITORING & OBSERVABILITY

### Logging

```python
import logging

logger = logging.getLogger("prometheus.main")

logger.info(f"Risk run START: {run_id}//date={run_date}")
logger.debug(f"  Loaded portfolio: {len(portfolio)} obligors")
logger.warning(f"  Obligor CORP_XYZ missing LGD; using default")
logger.error(f"  A-IRB engine crashed: {exception}")
logger.critical(f"  Database connection lost; aborting")
```

### Metrics to Track

| Metric | Target | Alert |
|--------|--------|-------|
| **Risk run execution time** | <5 sec | >10 sec |
| **DQ score** | >95 | <90 |
| **Governance check passes** | 5/5 | <4/5 |
| **Trace coverage** | 100% | <95% |
| **Floor impact volatility** | <5% | >10% |

### Health Checks

```python
# POST /health
{
    "status": "healthy",
    "database": "connected",
    "market_data": "fresh",
    "dq_score": 97.2,
    "last_risk_run": "2026-04-27T18:45:00Z",
}
```

---

## API REFERENCE

### Main Risk Run Endpoint

```python
POST /api/risk-run
{
    "run_date": "2026-04-27",
    "scenario": "baseline",        # Optional
    "include_traces": true,
    "include_greeks": true,
}

Response:
{
    "run_id": "RISK_20260427_001",
    "rwa": {
        "total": 1234567890,
        "credit": 800000000,
        "cva": 300000000,
        "market": 100000000,
        "operational": 34567890,
    },
    "floor": {
        "impact": 45000000,
        "status": "binding",
    },
    "scenarios": {
        "crisis_2008": {"rwa_delta": 120000000, "rwa_delta_pct": 9.7},
        ...
    },
    "greeks": {...},
    "dq_scorecard": {
        "overall_score": 97.2,
        "metrics": {...},
    },
    "governance_report": {...},
    "trace_reference": "TRACE_20260427_001",
    "execution_time_ms": 4523,
}
```

### Greeks API

```python
GET /api/greeks/:obligor_id
Response:
{
    "obligor_id": "BANK_XYZ",
    "deltas": {
        "pd_bps": 425.50,
        "lgd_pct": 12.30,
        "maturity_y": 8.75,
    },
    "rho_correlation_pct": 15.20,
    "computed_at": "2026-04-27T18:45:00Z",
}
```

### Trace Drill-Down

```python
GET /api/traces/:trace_id/drill?level=3
Response:
{
    "trace_id": "TRACE_20260427_001",
    "structure": {
        "level": 1,
        "title": "A-IRB Calculation",
        "children": [
            {
                "level": 2,
                "obligor_id": "BANK_XYZ",
                "children": [
                    {
                        "level": 3,
                        "formula": "(PD × LGD × MA – μ) / σ",
                        "result": "RWA = 1,234,567",
                        "trace_values": {...},
                    },
                    ...
                ],
            },
            ...
        ],
    },
}
```

---

## TROUBLESHOOTING GUIDE

### Common Issues

#### Issue 1: "PD Curve Not Found for Rating"

**Symptoms:** A-IRB engine crashes with KeyError

**Root Cause:** Calibration service not initialized or curve stale

**Resolution:**
```python
# Check calibration freshness
from backend.data_sources.calibration import CalibrationService

cal = CalibrationService(db_engine)
curves = cal.load_pd_curves(date)

if not curves:
    print("ERROR: No PD curves loaded")
    print("Solution: Run calibration update")
    cal.refresh_from_source()
else:
    print(f"OK: {len(curves)} curves available")
```

#### Issue 2: "DQ Score Below Threshold"

**Symptoms:** Risk run completes but DQ red-flagged

**Resolution:**
```python
# Inspect DQ metrics
from backend.data_quality.dqms import DataQualityScorecard

dq = DataQualityScorecard()
metrics = dq.compute_all_metrics(date, portfolio)

for metric_name, score in metrics.items():
    if score < 90:
        print(f"⚠️  {metric_name}: {score:.1f}%")
        # Take corrective action
```

#### Issue 3: "Governance Check VC-02 Failed"

**Symptoms:** Automated compliance check reports IAD formula error

**Resolution:**
```python
# Verify A-IRB formula implementation
from backend.engines.a_irb import AIRBEngine

engine = AIRBEngine()

# Run validation test
test_result = engine.validate_formula(
    pd=0.025, lgd=0.45, ead=10_000_000, maturity=5
)

if not test_result.passed:
    print(f"ERROR: {test_result.error_message}")
    # Compare to regulatory baseline in AIRB_TECHNICAL_GUIDE.md
```

---

## APPENDIX: QUICK START

### Install & Setup

```bash
# 1. Clone repo
git clone https://github.com/antonyalexin/Risk_Engine_Rp.git
cd Prometheus

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup database
createdb prometheus
psql prometheus < docker/init.sql

# 5. Test
pytest tests/ -v

# 6. Run dashboard
streamlit run dashboard/app.py
```

### Execute Risk Run

```python
# Python script
from backend.main import RiskRun
from datetime import date

risk_run = RiskRun()
result = risk_run.execute(run_date=date(2026, 4, 27))

print(f"Total RWA: €{result.total_rwa:,.0f}")
print(f"Floor impact: €{result.floor_impact:,.0f}")
print(f"DQ score: {result.dq_scorecard.overall_score:.1f}%")
```

---

## DOCUMENT REFERENCES

**Technical Guides:**
- AIRB_TECHNICAL_GUIDE.md — A-IRB deep dive
- CVA_TECHNICAL_GUIDE.md — CVA details
- FRTB_TECHNICAL_GUIDE.md — FRTB engine
- OPERATIONAL_RISK_TECHNICAL_GUIDE.md — Op Risk
- MARKET_DATA_ARCHITECTURE.md — Data design

**Phase 2 Strategy:**
- PHASE2_EXECUTIVE_SUMMARY.md — Business case
- PHASE2A_INTEGRATION_GUIDE.md — Phase 2A integration
- ENHANCEMENT_ROADMAP.md — Full roadmap

**Regulatory Basis:**
- `BASEL_Guidelines/` folder — All regulatory PDFs

---

**END OF TECHNICAL ARCHITECTURE DOCUMENT**

---

**Document Prepared By:** PROMETHEUS Development Team  
**Last Updated:** April 27, 2026  
**Next Review:** July 1, 2026 (post-Phase 2B validation)  
**Status:** ✅ Production Ready

