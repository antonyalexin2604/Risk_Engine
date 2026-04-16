# PROMETHEUS RISK PLATFORM
## Functional Specification Document (FSD)

**Document Reference:** PROMETHEUS-FSD-v1.0  
**Document Version:** 1.0  
**Date:** April 5, 2026  
**Classification:** Internal Use — Confidential  
**Status:** Final  
**Prepared By:** Risk Technology — Lead Developer  
**Reviewed By:** Head of Market Risk | Head of Credit Risk | Regulatory Affairs  

---

## DOCUMENT CONTROL

| Version | Date | Author | Description of Change |
|---------|------|--------|----------------------|
| 0.1 | November 2024 | Lead Developer | Initial draft — core engine sections |
| 0.5 | December 2024 | Lead Developer | Completed FR sections, architecture |
| 0.9 | January 2025 | Lead Developer | Review draft — submitted to stakeholders |
| 1.0 | April 5, 2026 | Lead Developer | Final release |

**Distribution List:**
Chief Risk Officer · Head of Market Risk · Head of Credit Risk · Head of Treasury · Regulatory Affairs · IT Infrastructure · External Auditors (upon request)

**Review Cycle:** Quarterly or upon material regulatory update (BCBS standards revision, supervisory guidance)

---

---

# TABLE OF CONTENTS

1. [Table of Contents](#table-of-contents)
2. [Project Description](#2-project-description)
3. [Project Objective](#3-project-objective)
4. [Components Impacted](#4-components-impacted)
5. [Upstream Dependencies](#5-upstream-dependencies)
6. [Downstream Dependencies](#6-downstream-dependencies)
7. [Business Requirements](#7-business-requirements)
8. [Functional Requirements](#8-functional-requirements)
   - [FR-001: SA-CCR Calculation Engine (CRE52)](#fr-001-sa-ccr-calculation-engine--standardised-approach-for-counterparty-credit-risk)
   - [FR-002: IMM Monte Carlo Engine (CRE53)](#fr-002-imm-monte-carlo-engine--internal-models-method)
   - [FR-003: A-IRB Credit Risk Engine (CRE30–36)](#fr-003-a-irb-credit-risk-engine--advanced-internal-ratings-based-approach)
   - [FR-004: FRTB Market Risk Engine (MAR21–33)](#fr-004-frtb-market-risk-engine--fundamental-review-of-the-trading-book)
   - [FR-005: CVA Risk Engine (MAR50)](#fr-005-cva-risk-engine--credit-valuation-adjustment)
   - [FR-006: CCP Exposure Engine (CRE54)](#fr-006-ccp-exposure-engine--central-counterparty-capital)
   - [FR-007: Daily Risk Orchestrator (RBC20)](#fr-007-daily-risk-orchestrator--five-part-rwa-formula)
   - [FR-008: Market Data Integration](#fr-008-market-data-integration)
   - [FR-009: Backtesting Framework (MAR99)](#fr-009-backtesting-framework--traffic-light-system)
   - [FR-010: Interactive Dashboard](#fr-010-interactive-dashboard)
   - [FR-011: Audit Trail & Compliance Reporting](#fr-011-audit-trail--compliance-reporting)
9. [Business and Functional Workflow](#9-business-and-functional-workflow)
10. [System Architecture](#10-system-architecture)
11. [Technical Design](#11-technical-design)
12. [Appendix](#12-appendix)

---

---

# 2. PROJECT DESCRIPTION

## 2.1 Overview

**PROMETHEUS** is an institutional-grade, production-ready regulatory capital management platform designed for banks and financial institutions operating under the Basel III/IV framework mandated by the Basel Committee on Banking Supervision (BCBS). The platform provides a fully integrated, end-to-end solution for calculating, validating, reporting, and auditing Risk-Weighted Assets (RWA) across all six regulatory capital components — Credit Risk, Counterparty Credit Risk, Market Risk, CVA Risk, CCP Exposure, and Operational Risk.

The system is implemented entirely in Python 3.11 and is optimised to run on commodity hardware (Apple MacBook Air M1, 8 GB RAM), demonstrating that regulatory-grade computations need not require multi-million-dollar vendor solutions. It is architected to scale to cloud deployment (Azure / AWS) as institutional demand grows.

## 2.2 Platform Name and Significance

The name **PROMETHEUS** is a deliberate reference to the Titan of Greek mythology who brought fire — the instrument of knowledge and power — to humanity. In the context of this platform, PROMETHEUS brings the full illuminating power of Basel III/IV regulatory mathematics to risk teams, replacing opaque vendor black boxes and manual spreadsheets with an open, auditable, and fully documented calculation engine.

## 2.3 Regulatory Basis

PROMETHEUS is built directly from BCBS source standards with no ambiguity or proxy interpretation. Every formula, parameter, floor, and correlation coefficient implemented in the platform can be traced to a specific paragraph of a Basel standard.

| Engine | Basel Standard | Scope |
|--------|---------------|-------|
| SA-CCR | CRE52 | Derivative Exposure at Default — all trades |
| IMM (Monte Carlo) | CRE53 | Effective EPE for eligible derivative trades |
| A-IRB | CRE30–36 | Banking Book RWA |
| FRTB SBM + IMA | MAR20–33 | Market Risk Capital |
| CVA (BA-CVA / SA-CVA) | MAR50 | CVA Risk RWA |
| CCP | CRE54 | Cleared derivative exposure |
| Five-Part RWA | RBC20.9 | Total Capital Aggregation |
| Output Floor | RBC20.11 | 72.5% SA-based floor |
| Operational Risk | OPE25 | Basic Indicator Approach (stub) |
| Margins | MGN | CSA / IM / VM / MTA |

## 2.4 Current State

Sprint A is complete as of January 2025. The platform has achieved:
- **100% regulatory engine coverage** across all six capital components
- **48/48 validation tests passing** at 100% pass rate
- **Zero type errors** under Pylance strict mode
- **~2-minute daily risk run** on M1 MacBook Air (vs. <5-minute target)
- **8-page interactive dashboard** with institutional-grade visualisation and export capabilities
- **Full audit trail** with regulatory-traceable calculation logs

---

# 3. PROJECT OBJECTIVE

## 3.1 Strategic Objectives

| # | Objective | Metric | Target | Status |
|---|-----------|--------|--------|--------|
| SO-1 | Achieve 100% Basel III/IV regulatory coverage | Coverage of BCBS standards | 100% | ✅ Achieved |
| SO-2 | Deliver auditable, accurate capital calculations | Test pass rate | 100% | ✅ 48/48 |
| SO-3 | Enable real-time daily risk runs | Completion time | < 5 min | ✅ ~2 min |
| SO-4 | Reduce capital inefficiency via precise A-IRB and IMM | RWA reduction vs. SA | 20–35% | ✅ Model ready |
| SO-5 | Minimise infrastructure cost | Annual infrastructure spend | < $5,000 | ✅ < $1,000 |
| SO-6 | Ensure audit readiness | Regulatory exam prep time | < 1 week | ✅ Instant exports |

## 3.2 Business Objectives

1. **Regulatory Compliance** — Eliminate the risk of non-compliance with BCBS standards, avoiding regulatory fines and sanctions by ensuring every RWA calculation is traceable to a specific Basel paragraph.

2. **Capital Optimisation** — Replace conservative Standardised Approach (SA) capital estimates with precise Advanced Internal Ratings-Based (A-IRB) and Internal Models Method (IMM) calculations, reducing over-capitalisation and freeing capital for productive deployment.

3. **Operational Risk Reduction** — Eliminate manual spreadsheet-based risk calculations prone to human error. Provide an automated, tested, and versioned calculation pipeline.

4. **Transparency and Governance** — Provide complete audit trails for all calculations, method selection decisions (e.g., IMM vs. SA-CCR fallback), and regulatory floor applications, satisfying both internal governance and external regulatory examination requirements.

5. **Cost Efficiency** — Deliver enterprise-grade regulatory calculations at a fraction of the cost of commercial vendor solutions ($21K total vs. $100K–$500K/year for enterprise alternatives).

## 3.3 Functional Objectives

- Implement the complete **five-part RWA formula** (RBC20.9): Credit + CCR + Market + CVA + CCP + OpRisk
- Implement the **output floor** (RBC20.11): Final RWA = max(Total RWA, 72.5% × SA-based RWA)
- Provide **fallback logic** with full trace codes when IMM trades revert to SA-CCR or SA-CVA reverts to BA-CVA
- Enable **real-time market condition adjustments** to risk weights and correlations via pluggable market data feeds
- Deliver a **Streamlit-based interactive dashboard** for risk officers, with downloadable regulatory reports

---

# 4. COMPONENTS IMPACTED

## 4.1 Platform Components

| Component | Module Path | Type | Impact Level |
|-----------|-------------|------|-------------|
| **SA-CCR Engine** | `backend/engines/sa_ccr.py` | Calculation Engine | Core — Primary |
| **IMM Engine** | `backend/engines/imm.py` | Calculation Engine | Core — Primary |
| **A-IRB Engine** | `backend/engines/a_irb.py` | Calculation Engine | Core — Primary |
| **FRTB Engine** | `backend/engines/frtb.py` | Calculation Engine | Core — Primary |
| **CVA Engine** | `backend/engines/cva.py` | Calculation Engine | Core — Primary |
| **CCP Engine** | `backend/engines/ccp.py` | Calculation Engine | Core — Primary |
| **Risk Orchestrator** | `backend/main.py` | Application Controller | Core — Primary |
| **Configuration** | `backend/config.py` | Configuration Module | Core — Supporting |
| **Portfolio Generator** | `backend/data_generators/portfolio_generator.py` | Data Generator | Supporting |
| **CVA Generator** | `backend/data_generators/cva_generator.py` | Data Generator | Supporting |
| **Market Data Provider** | `backend/data_sources/market_data_provider.py` | Data Source | Supporting |
| **CDS Spread Service** | `backend/data_sources/cds_spread_service.py` | Data Source | Supporting |
| **Market State** | `backend/data_sources/market_state.py` | Data Source | Supporting |
| **Calibration Module** | `backend/data_sources/calibration.py` | Data Source | Supporting |
| **Persistence Module** | `backend/data_sources/persistence.py` | Data Persistence | Supporting |
| **Streamlit Dashboard** | `dashboard/app.py` | Presentation Layer | User-Facing |
| **Test Suite** | `tests/test_engines.py` | Quality Assurance | Validation |

## 4.2 Infrastructure Components

| Component | Technology | Version | Impact Level |
|-----------|-----------|---------|-------------|
| **Database** | PostgreSQL 15 | 15.x | Core — Primary |
| **Container Runtime** | Docker | 24.0+ | Infrastructure |
| **Python Runtime** | CPython | 3.11+ | Core — Primary |
| **Dashboard Server** | Streamlit | 1.28+ | User-Facing |

## 4.3 Database Schemas Impacted

| Schema | Purpose | Tables Count |
|--------|---------|-------------|
| `risk` | Portfolio, trade, netting-set, RWA results | 5 |
| `market_data` | Yield curves, FX, vol surfaces, CDS spreads, correlations | 5 |
| `reference` | Counterparties, risk limits, regulatory parameters | 3 |
| `audit` | Run logs, calculation traces, breach alerts, user actions | 4 |

---

# 5. UPSTREAM DEPENDENCIES

Upstream dependencies are inputs and services that PROMETHEUS consumes in order to execute its calculations. A failure or data quality issue in any upstream dependency may degrade calculation accuracy.

## 5.1 Market Data Feeds

| Dependency | Provider | Data Supplied | Fallback |
|-----------|---------|--------------|---------|
| **Bloomberg Terminal API** | Bloomberg LP | CDS spreads, yield curves, volatility surfaces, FX rates, VIX | Refinitiv or internal feed |
| **Refinitiv / LSEG Eikon** | LSEG (London Stock Exchange Group) | CDS spreads (RIC codes), OIS rates, equity prices | Internal feed or static test data |
| **Internal Proprietary Feed** | Bank's own market risk systems | Calibrated volatilities, correlation matrices, scenario inputs | Static defaults in `config.py` |
| **FRED Public API** | Federal Reserve Bank of St. Louis | SOFR, IG/HY OAS indices (BAMLC0A0CM, BAMLH0A0HYM2, VIXCLS) | Hard-coded defaults in `CVAMarketDataFeed` |

### 5.1.1 Market Data Cascade Logic

The platform implements a three-tier fallback cascade to ensure availability:

```
Tier 1 (Primary):    Bloomberg Terminal  →  Live CDS spreads, vol surfaces
Tier 2 (Fallback):   Refinitiv / Internal Feed  →  Previous-day or interpolated data
Tier 3 (Last Resort): Static Test Data   →  Hardcoded representative values from config
```

A cache with configurable TTL (default: 300 seconds) is maintained in memory to reduce API call frequency. The cache is implemented in `MarketDataProvider._cache` and `CDSSpreadService`.

## 5.2 Trade and Portfolio Data

| Dependency | Source | Data Supplied | Interface |
|-----------|--------|--------------|-----------|
| **Trade Booking Systems** | Front-office OMS / TMS | Trade attributes (notional, maturity, asset class, MTM) | PostgreSQL → `risk.trades` |
| **Netting Set Definitions** | Collateral management system | CSA parameters (IM, VM, Threshold, MTA, MPOR) | PostgreSQL → `risk.netting_sets` |
| **Banking Book Exposures** | Credit system / loan origination | EAD, PD, LGD, M, collateral values | PostgreSQL → `risk.exposures` |
| **Counterparty Reference Data** | CRM / KYC system | Counterparty IDs, ratings, sector classification | PostgreSQL → `reference.counterparties` |

*In the current Sprint A development environment, trade and portfolio data are synthetically generated by `backend/data_generators/portfolio_generator.py` and `backend/data_generators/cva_generator.py`.*

## 5.3 Regulatory Parameter Updates

| Dependency | Source | Data Supplied | Frequency |
|-----------|--------|--------------|-----------|
| **BCBS Standards** | BIS.org | SA-CCR supervisory factors, A-IRB correlation parameters, FRTB risk weights | As published (typically annually) |
| **Local Regulatory Guidance** | Central Bank / Prudential Regulator | Jurisdiction-specific floors, add-ons, or transition provisions | Ongoing |
| **SA-CVA Approval Flag** | Regulatory supervisor | Whether the institution is approved for SA-CVA | Event-driven |
| **IMA Approval** | Internal model validation / supervisor | Whether trading desks are approved for IMA usage | Event-driven |

## 5.4 Calibration Inputs

| Dependency | Source | Data Supplied | Frequency |
|-----------|--------|--------------|-----------|
| **Historical Price Series** | Market data archive | 252-day lookback for volatility calibration | Daily |
| **Stressed Period Data (2007–09)** | Historical archive | Stressed volatilities for ES calibration | Static; refreshed on model review |
| **Macroeconomic Factors** | Central bank / Bloomberg | VIX, yield curve slope, HY spreads, unemployment | Daily (for market regime classification) |

---

# 6. DOWNSTREAM DEPENDENCIES

Downstream dependencies are systems, processes, and stakeholders that consume the outputs produced by PROMETHEUS.

## 6.1 Regulatory Reporting Systems

| Downstream Consumer | Data Consumed | Format | Frequency |
|--------------------|--------------|--------|-----------|
| **COREP / Basel Pillar 1 Reporting** | Total RWA, component breakdown, Capital ratio | Excel / CSV (Pillar 3 templates) | Monthly / Quarterly |
| **Pillar 3 Public Disclosure** | RWA by risk type, capital ratios, credit quality | xlsx export from dashboard | Semi-annual / Annual |
| **Internal Regulatory Affairs** | Fallback traces, audit logs, breach alerts | PostgreSQL `audit` schema | On-demand / Event-driven |

## 6.2 Capital Planning and Finance Systems

| Downstream Consumer | Data Consumed | Format | Frequency |
|--------------------|--------------|--------|-----------|
| **ICAAP (Internal Capital Adequacy Assessment Process)** | RWA forecasts, stress scenario outputs | JSON → Excel | Annual |
| **CFO / Treasury Capital Planning** | Total RWA, output floor result, Capital = RWA × 8% | Dashboard / Excel | Daily / Monthly |
| **ALM System** | Banking book RWA, A-IRB capital requirement K | JSON / PostgreSQL | Daily |

## 6.3 Risk Management Systems

| Downstream Consumer | Data Consumed | Format | Frequency |
|--------------------|--------------|--------|-----------|
| **Risk Limit Monitoring** | SA-CCR EAD, FRTB Capital, CVA | PostgreSQL `reference.risk_limits` + `audit.breach_alerts` | Daily |
| **CVA Desk** | SA-CVA / BA-CVA breakdown, CDS spread inputs used | JSON / Dashboard | Daily |
| **Trading Book Risk** | FRTB SBM and IMA charges, DRC, RRAO, backtesting status | Dashboard page / JSON | Daily |
| **Credit Risk Team** | A-IRB RWA, PD/LGD floors applied, EL shortfall | Dashboard page / Excel | Daily |

## 6.4 Technology Consumers

| Downstream Consumer | Data Consumed | Interface |
|--------------------|--------------|-----------|
| **PostgreSQL Database** | All run results persisted via `persistence.py` | psycopg2 |
| **Streamlit Dashboard** | All JSON results rendered as charts and tables | Python direct call |
| **pgAdmin 4** | Schema exploration, query verification | PostgreSQL connection |
| **External Auditors** | Audit logs, calculation traces, formula references | Excel export / PostgreSQL read access |

---

# 7. BUSINESS REQUIREMENTS

## 7.1 BR-001 — Regulatory Capital Coverage (CRITICAL)

The platform MUST calculate Risk-Weighted Assets for all regulatory components mandated by Basel III/IV. No component may be omitted, approximated beyond regulatory tolerances, or silently defaulted without an audit trace.

**Components required:**
1. Credit Risk — A-IRB (CRE30–36)
2. Counterparty Credit Risk — SA-CCR (CRE52) and IMM (CRE53) with floor
3. Market Risk — FRTB SBM + IMA (MAR20–33)
4. CVA Risk — BA-CVA / SA-CVA (MAR50)
5. CCP Exposure — Qualified CCP + DFC (CRE54)
6. Operational Risk — OPE25 BIA stub
7. Output Floor — 72.5% SA-based floor (RBC20.11)

**Acceptance Criteria:**
- All six engines implemented and tested
- Output floor formula verified against RBC20.11 and CAP10 FAQ1
- 100% test pass rate across all regulatory formulas

---

## 7.2 BR-002 — Portfolio Management (HIGH)

The platform MUST support comprehensive, multi-asset-class portfolio modelling for both derivative and banking book exposures.

**Requirements:**
- Derivative portfolios with minimum 5 trades per netting set across IR, FX, Credit, Equity, and Commodity asset classes
- Banking book portfolios with Corporate, SME, Residential Mortgage, and Revolving Credit exposure types
- Portfolio identifiers following `DRV-YYYY-NNN` (derivatives) and `BBK-YYYY-NNN` (banking book) conventions
- CSA parameters (IM, VM, Threshold, MTA, MPOR) modelled per netting set
- Day-on-day portfolio tracking for regulatory consistency

---

## 7.3 BR-003 — Backtesting and Model Validation (CRITICAL)

The platform MUST implement regulatory backtesting under the MAR99 traffic-light framework.

**Requirements:**
- 250-day rolling backtesting window comparing P&L against model VaR/ES
- Traffic-light system: Green (0–4 exceptions), Amber (5–9), Red (≥10)
- Spearman rank correlation test (ρ ≥ 0.50) and Kolmogorov-Smirnov test (p-value ≥ 0.05)
- Percentage Liquidity Adequacy (PLA) test per MAR32
- Automated breach alerting and logging

---

## 7.4 BR-004 — Real-Time Market Data Integration (HIGH)

The platform MUST support dynamic market data feeds from industry-standard providers with intelligent fallback logic.

**Requirements:**
- Primary sources: Bloomberg Terminal API, Refinitiv/LSEG Eikon
- Secondary source: Internal proprietary feeds
- Last-resort: Static configuration-driven defaults
- In-memory cache with configurable TTL (default 300 seconds)
- Dynamic parameter adjustment (risk weights, correlations) based on real-time VIX, spreads, and volatility

---

## 7.5 BR-005 — Interactive Dashboard (MEDIUM)

The platform MUST provide a web-based, interactive visualisation and reporting dashboard accessible to risk officers without programming expertise.

**Requirements:**
- 8 functional pages: Overview, Derivative Risk, Banking Book, Backtesting, Capital Planning, Reports, Settings, Documentation
- Institutional-grade visual design with export to xlsx/csv
- Real-time data refresh capability
- Responsive layout for desktop and tablet

---

## 7.6 BR-006 — Audit Trail and Compliance Reporting (CRITICAL)

The platform MUST maintain immutable, complete audit logs for all calculations, method selections, fallback applications, and user actions.

**Requirements:**
- INFO-level logs for all calculations with timestamps
- WARNING/ERROR logs for all exceptions (floor applications, fallbacks, backtesting breaches)
- Fallback trace codes embedded in trade objects (format: `FALLBACK|trade_id|reason_code|description`)
- Regulatory export templates compatible with Basel Pillar 3 disclosure formats
- PostgreSQL `audit` schema with four immutable tables

---

## 7.7 BR-007 — Performance and Scalability (HIGH)

The platform MUST complete a full daily risk run within acceptable time limits on target hardware.

**Requirements:**
- Full daily run: < 5 minutes on M1 MacBook Air 8 GB
- Monte Carlo simulation: 2,000 scenarios × 52 weekly time steps
- Dashboard refresh: < 3 seconds
- Report generation: < 10 seconds for 50 portfolios
- Support 100+ derivative portfolios and 200+ banking book portfolios

---

# 8. FUNCTIONAL REQUIREMENTS

---

## FR-001: SA-CCR Calculation Engine — Standardised Approach for Counterparty Credit Risk

**Basel Standard:** CRE52  
**Priority:** CRITICAL  
**Owner:** Credit Risk Team  
**File:** `backend/engines/sa_ccr.py`

---

### 8.1.1 Use Case

SA-CCR is the default regulatory approach for calculating **Exposure at Default (EAD)** on derivative portfolios. It is required for all counterparty credit risk exposures and serves as the mandatory floor for the Internal Models Method (IMM). The use case is: given a set of trades in a netting set with associated CSA collateral terms, calculate the regulatory EAD that feeds into the CCR RWA component of the five-part RWA formula.

SA-CCR is also used for:
- Counterparties not eligible for IMM treatment
- IMM floor enforcement (EAD_IMM ≥ 50% × EAD_SA-CCR per CRE53.5)
- CVA calculation inputs (EAD into the BA-CVA formula)
- CCP exposure calculation (cleared derivatives under CRE54)

---

### 8.1.2 Basel Context

SA-CCR was introduced under CRE52 (effective January 2023) as the replacement for both the Current Exposure Method (CEM) and the Standardised Method (SM). Key design principles from the BCBS:

- **Risk-sensitivity:** SA-CCR is more sensitive to netting, collateral, and hedging than CEM
- **Simplicity vs. accuracy:** More complex than CEM but simpler than full IMM simulation
- **Mandatory floor:** Prevents IMM from producing EAD below 50% of SA-CCR, ensuring a regulatory minimum
- **Supervisory parameters:** Risk weights (supervisory factors, SF) are prescribed centrally by BCBS to prevent model risk

The alpha multiplier of **1.4** (CRE52.7) reflects the BCBS's recognition that EE-based measures understate true economic exposure due to portfolio complexity, correlation risk, and wrong-way risk.

---

### 8.1.3 Functional Objective of Calculations

The SA-CCR engine computes EAD through three sequential components:

**Step 1 — Replacement Cost (RC):** CRE52.12–22

Measures the immediate loss if the counterparty were to default today, accounting for current MTM value of the portfolio and collateral already posted.

$$\text{RC} = \max\left(V - C,\ TH + MTA - NICA,\ 0\right)$$

**Step 2 — Potential Future Exposure (PFE) Multiplier:** CRE52.23

Captures the likelihood that the exposure could grow beyond RC before a default is resolved. It modulates the Add-On based on the current over- or under-collateralisation of the portfolio.

$$\text{mult} = \min\left(1,\ \text{Floor} + (1 - \text{Floor}) \cdot e^{\frac{V}{2(1 - \text{Floor}) \cdot \text{AddOn}_\text{agg}}}\right)$$

**Step 3 — Aggregate Add-On:** CRE52.24–75

The Add-On captures potential future exposure over the MPOR, aggregated across five asset classes. For each asset class:
$$\text{AddOn}_\text{AC} = \sum_{\text{hedging set}}\text{EffNotional}_k \times SF_k$$

**Step 4 — EAD:** CRE52.7
$$\text{EAD} = \alpha \cdot (\text{RC} + \text{mult} \cdot \text{AddOn}_\text{agg}), \quad \alpha = 1.4$$

---

### 8.1.4 Parameter Significance

| Parameter | Symbol | Value / Source | Significance |
|-----------|--------|---------------|-------------|
| **Alpha multiplier** | α | 1.4 (CRE52.7) | Conservatism buffer over EE; accounts for correlation and wrong-way risk; fixed by BCBS |
| **PFE floor** | Floor | 0.05 (5%) | Minimum multiplier even for fully overcollateralised portfolios; prevents zero EAD on CSA-covered netting sets |
| **Replacement Cost** | RC | Trade MTM − collateral | Represents immediate close-out loss; floored at max(TH+MTA−NICA, 0) to account for collateral thresholds |
| **Threshold** | TH | Per CSA | Minimum exposure before collateral call is triggered |
| **Minimum Transfer Amount** | MTA | Per CSA | Smallest increment of collateral that can be transferred |
| **Net Independent Collateral Amount** | NICA | Per netting set | Collateral received − collateral posted; net benefit of collateral arrangements |
| **Supervisory Factor** | SF | Table: IR=0.50%, FX=4.0%, EQ=32%, CDS IG=0.50%, CDS SG=5.0%, CMDTY=18% | BCBS-prescribed risk weights reflecting asset class volatility over MPOR |
| **Maturity Factor** | MF | Margined: √(MPOR/250); Unmargined: √(min(M,1)) | Scales exposure by square root of time, capturing diffusion over margin period |
| **Supervisory Duration** | SD | (e^(−0.05S) − e^(−0.05E)) / 0.05 | For IR trades: scales notional by present value of the floating payment duration (CRE52.39) |
| **MPOR** | — | 10 days (margined), 20 days (unmargined) | Margin Period of Risk; time to replace portfolio after counterparty default and collateral dispute |
| **Supervisory Delta** | δ | +1 long, −1 short; option-adjusted for non-linear | Accounts for directionality and optionality in adjusted notional calculation |

---

### 8.1.5 Key Success Criteria

- EAD calculation matches BCBS CRE52 worked examples within 0.01% tolerance
- All five asset classes (IR, FX, EQ, Credit, CMDTY) produce non-negative Add-Ons
- IMM eligibility check returns correct trace code for ineligible trades
- Regulatory floor (EAD_IMM ≥ 50% × EAD_SA-CCR) is enforced with logged fallback trace
- 12/12 SA-CCR unit tests in `tests/test_engines.py` pass

---

## FR-002: IMM Monte Carlo Engine — Internal Models Method

**Basel Standard:** CRE53  
**Priority:** HIGH  
**Owner:** Quantitative Risk Team  
**File:** `backend/engines/imm.py`

---

### 8.2.1 Use Case

The IMM engine provides a more risk-sensitive alternative to SA-CCR for eligible derivative trades. Using Monte Carlo simulation, it models the **Effective Expected Positive Exposure (EEPE)** under both normal and stressed market conditions. Banks with supervisory approval may use IMM to calculate EAD, typically achieving 20–40% reduction in CCR RWA compared to SA-CCR, subject to the regulatory floor.

The IMM is also the source of **exposure profiles** (EE, EEPE, PFE) for CVA desk risk management and for dynamic collateral modelling under CSA terms.

---

### 8.2.2 Basel Context

CRE53 permits approved banks to use an internal model for counterparty credit exposure rather than the standardised SA-CCR. The core BCBS requirements are:

- **2,000+ simulation scenarios** for statistical robustness (PROMETHEUS uses 2,000 for M1 hardware compatibility)
- **Stressed EEPE** calibrated to a 1-year stress period (2007–2009 financial crisis) to prevent pro-cyclicality
- **Regulatory floor:** EAD_IMM ≥ 50% × EAD_SA-CCR (CRE53.5) — prevents IMM from being used to game capital
- **CSA path-level modelling:** Collateral must be modelled at the path level, not post-hoc
- **Alpha multiplier of 1.4** applies equally to IMM EAD (CRE53.6)

---

### 8.2.3 Functional Objective of Calculations

**Step 1 — Risk Factor Path Generation (GBM / Hull-White):**

For equity and FX (Geometric Brownian Motion):
$$S(t+\Delta t) = S(t) \cdot \exp\left[\left(\mu - \frac{\sigma^2}{2}\right)\Delta t + \sigma\sqrt{\Delta t}\,Z\right]$$

For interest rates (Hull-White 1-Factor):
$$dr(t) = \kappa\,[\theta - r(t)]\,dt + \sigma_r\,dW(t)$$

Antithetic variance reduction doubles effective scenario count: for each random vector Z, −Z is also simulated.

**Step 2 — Portfolio Revaluation:**
$$\text{NPV}[t, \text{scenario}] = \sum_k \text{TradeValue}_k(t, \text{scenario})$$

**Step 3 — CSA-Adjusted Exposure:**
$$\text{Exposure}[t, s] = \max\left(\text{NPV}[t,s] - \text{Collateral}[t,s],\ 0\right)$$

**Step 4 — Expected Exposure and EEPE:**
$$\text{EE}(t) = \frac{1}{N}\sum_{s=1}^{N} \text{Exposure}[t, s]$$
$$\text{EEE}(t) = \max_{u \leq t} \text{EE}(u) \quad \text{(non-decreasing constraint)}$$
$$\text{EEPE} = \frac{1}{T_1}\int_0^{T_1} \text{EEE}(t)\,dt \approx \frac{1}{T}\sum_{t=1}^{T}\text{EEE}(t)$$

**Step 5 — EAD:**
$$\text{EAD}_\text{IMM} = \alpha \cdot \text{EEPE}, \quad \alpha = 1.4$$

**Step 6 — Stressed EEPE:**
Paths are generated using volatility parameters calibrated to the 2007–2009 window (`stressed_vol ≈ 40%` vs. `vol ≈ 20%` normal), producing `EAD_stressed = α × EEPE_stressed`.

---

### 8.2.4 Parameter Significance

| Parameter | Value / Config | Significance |
|-----------|---------------|-------------|
| **Scenarios (N)** | 2,000 (`IMM.num_scenarios`) | Statistical convergence; BCBS requires sufficient paths; capped for M1 RAM constraint (~40 MB) |
| **Time Steps** | 52 weekly (`IMM.time_steps`) | Weekly revaluation over 1-year horizon; balances granularity and compute |
| **Alpha** | 1.4 (`IMM.alpha`) | Same as SA-CCR; regulatory conservatism multiplier |
| **GBM drift (μ)** | 0.05 (5% p.a.) | Risk-neutral drift for equity and FX paths |
| **GBM volatility (σ)** | 0.20 normal; 0.40 stressed | Normal from historical calibration; stressed from 2007–09 window |
| **Hull-White mean reversion (κ)** | 0.10 | Speed at which rates revert to long-run mean; higher κ = faster reversion |
| **Hull-White long-run rate (θ)** | 0.045 (4.5%) | OIS forward curve long-run calibration anchor |
| **IR volatility (σ_r)** | 0.015 normal; 0.030 stressed | Interest rate shock magnitude per unit of time |
| **MPOR (days)** | 10 margined; 20 unmargined | Lag between counterparty default and collateral replacement; drives CSA path delay |
| **Stress window** | 2007-06-01 to 2009-06-30 | BCBS-prescribed crisis calibration period for stressed EEPE |
| **Random seed** | 42 | Reproducibility for audit and regression testing |
| **Confidence Level** | 95th percentile | For PFE profile reporting (not the EAD measure) |

---

### 8.2.5 Key Success Criteria

- EEPE convergence: variance of EEPE < 1% between 2,000 and 10,000 scenario runs
- Stressed EAD consistently exceeds normal EAD (confirms crisis calibration is binding)
- CSA-adjusted EAD < uncollateralised EAD (confirms collateral benefit is captured)
- IMM floor check: EAD_IMM_CSA < 50% × EAD_SA-CCR triggers FALLBACK trace code logged with `REGULATORY_FLOOR|CRE53.5`
- 8/8 IMM unit tests pass including GBM, Hull-White, CSA path-level modelling

---

## FR-003: A-IRB Credit Risk Engine — Advanced Internal Ratings-Based Approach

**Basel Standard:** CRE30–36  
**Priority:** CRITICAL  
**Owner:** Credit Risk Team  
**File:** `backend/engines/a_irb.py`

---

### 8.3.1 Use Case

The A-IRB engine calculates **Credit RWA** for the banking book — loans, revolving facilities, mortgages, and other non-traded credit exposures. By using the bank's own internal estimates of PD, LGD, and EAD (subject to regulatory floors), A-IRB produces significantly more risk-sensitive capital requirements than the Credit Standardised Approach (CSA), typically reducing credit RWA by 25–40% for well-rated portfolios.

The engine also supports:
- **Double-default treatment** for CDS-protected exposures (CRE22), reducing capital for guaranteed credit
- **EL shortfall calculation** (CRE35): if EL > provisions, the shortfall deducts from CET1 capital
- **SME adjustment**: lower correlation for SME obligors (CRE31.9), reducing SME capital requirements
- **Sector-based correlation adjustments** for Financials, Real Estate, Retail, and other sectors

---

### 8.3.2 Basel Context

The A-IRB approach under CRE31 is built on the **Asymptotic Single Risk Factor (ASRF)** model. The key assumptions are:

1. All systematic risk derives from a single global factor (the state of the economy)
2. Idiosyncratic risk diversifies away in large portfolios
3. Correlations between borrowers are driven by their common exposure to the economic factor

This model yields a closed-form capital formula, but at the cost of requiring banks to estimate PD and LGD with statistical rigour subject to:
- **PD floor:** 0.03% (3 basis points) — CRE31.4
- **LGD floor (unsecured):** 25% — CRE32
- **Maturity floor/cap:** 1 year to 5 years

---

### 8.3.3 Functional Objective of Calculations

**Step 1 — Apply Regulatory Floors:**
$$PD_\text{adj} = \max(PD,\ 0.0003)$$
$$LGD_\text{adj} = \max(LGD,\ 0.25) \quad \text{(unsecured)}$$

**Step 2 — Asset Correlation (CRE31.3):**
$$R = 0.12 \cdot \frac{1 - e^{-50 \cdot PD}}{1 - e^{-50}} + 0.24 \cdot \left[1 - \frac{1 - e^{-50 \cdot PD}}{1 - e^{-50}}\right]$$
SME adjustment (if sales < €50M):
$$R_\text{SME} = R - 0.04 \cdot \left(1 - \frac{S - 5}{45}\right)$$

**Step 3 — Maturity Adjustment (CRE31.7):**
$$b = (0.11852 - 0.05478 \cdot \ln PD)^2$$
$$M_\text{adj} = \min(\max(M,\ 1.0),\ 5.0)$$
$$\text{MA} = \frac{1 + (M_\text{adj} - 2.5) \cdot b}{1 - 1.5 \cdot b}$$

**Step 4 — Capital Requirement (K):**
$$K = \left[LGD \cdot \Phi\!\left(\frac{\Phi^{-1}(PD)}{\sqrt{1 - R}} + \sqrt{\frac{R}{1-R}}\,\Phi^{-1}(0.999)\right) - PD \cdot LGD\right] \cdot \text{MA}$$

**Step 5 — RWA:**
$$\text{RWA} = K \times 12.5 \times \text{EAD}$$

**Step 6 — Expected Loss (EL) Shortfall (CRE35):**
$$\text{EL} = PD \times LGD \times \text{EAD}$$
$$\text{Shortfall} = \max(\sum \text{EL} - \text{Provisions},\ 0)$$

---

### 8.3.4 Parameter Significance

| Parameter | Symbol | Regulatory Source | Significance |
|-----------|--------|-------------------|-------------|
| **Probability of Default** | PD | Bank internal model (CRE36) | Annual probability borrower defaults; must be through-the-cycle (TTC) average; floored at 3bp |
| **Loss Given Default** | LGD | Bank internal model (CRE32) | Fraction of EAD lost if default occurs; reflects collateral quality, recovery seniority |
| **Effective Maturity** | M | CRE31.7 | Weighted average cash-flow maturity; longer maturity → more uncertainty → higher capital |
| **Exposure at Default** | EAD | SA-CCR for derivatives; drawn + CCF × undrawn for loans | Amount exposed at the point of default, including unfunded commitment utilisation |
| **Asset Correlation** | R | CRE31.3 | Sensitivity to common economic factor; high R = systemic risk; varies 12–24% across PD range |
| **PD floor** | 0.0003 | CRE31.4 | Prevents unrealistically low PD estimates; 3bp is BCBS minimum for any non-sovereign borrower |
| **LGD floor (unsecured)** | 0.25 | CRE32 | 25% minimum LGD; prevents banks understating loss in default; covered bonds / secured may have lower LGD |
| **Maturity floor/cap** | 1–5 years | CRE31.7 | 1-year floor prevents gaming with short-dated rollovers; 5-year cap prevents disproportionate long-maturity capital |
| **ASRF confidence level** | 99.9% | CRE31.1 | One-year capital held to cover 99.9% of credit losses; calibrated to 1-in-1000 year loss |
| **SME threshold** | €50M sales | CRE31.9 | Obligors with < €50M annual sales receive SME adjustment; reduces correlation → reduces capital |
| **Double-default factor** | p_g × p_o | CRE22 | For CDS-protected exposures: probability that both the obligor AND guarantor default simultaneously; materially reduces K |

---

### 8.3.5 Key Success Criteria

- Capital requirement K matches Basel CRE31 formula output within numerical precision (< 0.001%)
- SME adjustment correctly reduces RWA for eligible obligors
- Double-default K is strictly less than single-name K for the same exposure
- EL shortfall correctly triggers CET1 deduction when shortfall > 0
- PD and LGD floor flags are recorded for each exposure in the trade results
- 10/10 A-IRB unit tests covering corporate, SME, secured, unsecured, and double-default pass

---

## FR-004: FRTB Market Risk Engine — Fundamental Review of the Trading Book

**Basel Standard:** MAR20–33  
**Priority:** CRITICAL  
**Owner:** Market Risk Team  
**File:** `backend/engines/frtb.py` (1,710 lines)

---

### 8.4.1 Use Case

The FRTB engine calculates **Market Risk Capital** for the trading book. It implements both the Sensitivities-Based Method (SBM) and the Internal Models Approach (IMA) per MAR21–33, along with the Default Risk Charge (DRC), Residual Risk Add-On (RRAO), and a full backtesting framework under MAR99.

The engine applies across all major risk classes:
- **GIRR:** General Interest Rate Risk (tenor-based sensitivity)
- **CSR_NS:** Credit Spread Risk — Non-Securitised
- **CSR_SEC:** Credit Spread Risk — Securitised
- **EQ:** Equity Risk (large-cap and small-cap)
- **FX:** Foreign Exchange Risk
- **CMDTY:** Commodity Risk (energy, metals, agriculture, other)

The engine also features **real-time market condition integration** (`MarketRegime`, `DynamicParameterAdjustment`) that scales risk weights and correlations based on live VIX, HY spreads, and equity volatility — implementing a counter-cyclical buffer directly in the risk weight calculus.

---

### 8.4.2 Basel Context

FRTB (Fundamental Review of the Trading Book) was introduced by BCBS in response to the Global Financial Crisis (2007–09), during which the pre-existing market risk framework (based on Value-at-Risk) proved inadequate. Key FRTB design principles:

1. **Expected Shortfall (ES) replaces VaR** — ES is a coherent risk measure that captures tail risk beyond VaR; used at 97.5% confidence for IMA
2. **Sensitivities-based SBM** replaces the original SA market risk approach — provides more granular, risk-sensitive capital
3. **Desk-level IMA approval** — the regulator approves individual trading desks, not the entire book; desks failing the PLA test revert to SBM
4. **Three correlation scenarios** — SBM is computed under low, medium, and high correlation scenarios and the worst case is taken; prevents correlation arbitrage
5. **Liquidity horizons** — different risk factors are assigned different liquidity horizons (10–120 days) reflecting how long it takes to exit positions

---

### 8.4.3 Functional Objective of Calculations

#### A. Sensitivities-Based Method (SBM) — MAR21–25

**Weighted Sensitivity:**
$$WS_k = RW_k \times s_k$$

**Intra-bucket aggregation (Delta per risk class and bucket b):**
$$K_b = \sqrt{\sum_k WS_k^2 + \sum_{k \neq l} \rho_{kl} \cdot WS_k \cdot WS_l}$$

**Inter-bucket aggregation (across buckets within risk class):**
$$\Delta = \sqrt{\sum_b K_b^2 + \sum_{b \neq c} \gamma_{bc} \cdot K_b \cdot K_c}$$

**Regulatory Floor (MAR21.100):**
$$\text{SBM}_\text{delta} = \max\!\left(\Delta,\; \sum_k |WS_k|\right)$$

**Three correlation scenarios (MAR21.6):**
- **Low:** $\rho_\text{low} = \max(2\rho - 1,\; 0.5625\rho,\; 0)$
- **Medium:** $\rho_\text{med} = \rho$
- **High:** $\rho_\text{high} = \min(\rho + 0.25(1 - |\rho|),\; 1)$

The capital charge is the **maximum** across all three scenarios.

**Total SBM:**
$$\text{SBM}_\text{total} = \text{SBM}_\text{delta} + \text{SBM}_\text{vega} + \text{SBM}_\text{curvature}$$

#### B. Internal Models Approach (IMA) — MAR33

**Expected Shortfall:**
$$\text{ES}_{97.5\%} = -\text{Percentile}(\text{P\&L},\; 2.5\%)$$

**Liquidity Horizon Adjustment (MAR33.4):**
$$\text{ES}_{10d} = \text{ES}_{1d} \times \sqrt{10}$$

**Stressed ES Calibration:**
$$\text{ES}_\text{stressed} = \text{ES from the worst 12-month window in 2007–2009 data}$$

**Total IMA:**
$$\text{IMA} = \max(\text{ES}_{10d},\; \text{ES}_\text{stressed})$$

#### C. Default Risk Charge (DRC) — MAR22
$$\text{DRC} = \sum_i \text{LGD}_i \times \text{Notional}_i \times P(\text{JTD}_i)$$

Jump-to-Default probability applies regulatory net long/short positions across rating buckets.

#### D. Residual Risk Add-On (RRAO) — MAR23.5
$$\text{RRAO} = 1.0\% \times N_\text{exotic} + 0.1\% \times N_\text{residual}$$

where $N_\text{exotic}$ is total gross notional of instruments with exotic underlyings, and $N_\text{residual}$ is gross notional with gap/correlation/behavioural risk.

#### E. Total Market Risk Capital:
$$\text{Capital}_\text{market} = \text{SBM}_\text{total} + \text{IMA} + \text{DRC} + \text{RRAO}$$
$$\text{RWA}_\text{market} = \text{Capital}_\text{market} \times 12.5$$

---

### 8.4.4 Parameter Significance

| Parameter | Value | Significance |
|-----------|-------|-------------|
| **Delta Risk Weights (GIRR)** | 1.1%–1.8% by tenor | Prescribed sensitivity of 1bp rate move to capital; higher for short and very long tenors |
| **Delta Risk Weights (FX)** | 15% | Calibrated to observed FX volatility; all currency pairs treated equally under SBM |
| **Delta Risk Weights (EQ Large)** | 30%–70% by sector/bucket | Reflects equity volatility by sector; emerging markets (bucket 8) highest at 70% |
| **Delta Risk Weights (CMDTY)** | 16%–80% by commodity type | Energy (bucket 3) highest at 60%; agriculture (buckets 13–15) lower at 18% |
| **Vega Risk Weights** | GIRR: 55%, EQ: 78%, FX: 47%, CMDTY: 100% | Reflects implied vol market liquidity; CMDTY at 100% due to low vol-of-vol liquidity |
| **Intra-bucket correlation (GIRR)** | Tenor-gap: exp(−0.03·|ln(t₁/t₂)|) | Exponential decay with tenor-gap distance; close tenors highly correlated |
| **Intra-bucket correlation (EQ)** | 15% | Low intra-bucket correlation; individual stock risk diversifies within sector bucket |
| **Inter-bucket correlation (GIRR)** | 50% | Cross-currency rate correlation; key for multi-currency trading books |
| **Inter-bucket correlation (CSR_NS)** | 0% | Different credit sectors treated as uncorrelated; no diversification benefit across sectors |
| **Curvature CVR** | CVR_k = −min(CVR_up, CVR_dn, 0) | Captures convexity risk from non-linear instruments (options); asymmetric P&L from rate shifts |
| **Stressed ES multiplier** | 1.5 (`ima_multiplier`) | IMA capital floored at 1.5× current ES when model underperforms in backtesting |
| **NMRF charge** | 0.15% of average notional | Non-Modellable Risk Factor charge per MAR31.14; assets with insufficient price history get individual ES stress |
| **Confidence level** | 97.5% (ES) | Tail risk measure; captures average loss in the worst 2.5% of scenarios |
| **Holding period** | 10 days | Minimum regulatory horizon; extended for illiquid risk factors (up to 120 days for complex credit) |
| **Backtesting window** | 260 days | One calendar year of trading days for traffic-light assessment |

---

### 8.4.5 Key Success Criteria

- SBM delta charge is non-negative and passes the regulatory floor (MAR21.100) check
- Three-scenario correlation framework produces the maximum-charge scenario as the result
- IMA ES correctly identifies the worst 2.5th percentile of the 260-day P&L distribution
- Stressed ES > current ES (confirms stressed calibration is more severe)
- GIRR intra-bucket correlations follow the tenor-gap exponential decay formula
- Backtesting traffic-light zone is correctly classified (Green/Amber/Red) based on exception count
- PLA test zone (MAR32) is computed and surfaced in `FRTBResult.pla_zone`
- Dynamic market condition adjustment scales risk weights upward during VIX > 40 (crisis regime)
- 6/6 SBM/IMA/DRC unit tests pass; zero type errors under Pylance strict mode

---

## FR-005: CVA Risk Engine — Credit Valuation Adjustment

**Basel Standard:** MAR50  
**Priority:** HIGH  
**Owner:** CVA Desk  
**File:** `backend/engines/cva.py`

---

### 8.5.1 Use Case

The CVA Risk engine calculates regulatory capital against **CVA Volatility Risk** — the risk that the mark-to-model CVA of a derivatives portfolio moves adversely due to changes in counterparty credit quality (CDS spreads) or market factors. CVA capital was introduced after the financial crisis, as roughly two-thirds of financial-crisis CCR losses came from CVA P&L volatility rather than actual defaults.

The engine supports two approaches:
- **BA-CVA (Basic Approach):** Always available; simpler EAD-based formula; used as fallback
- **SA-CVA (Standardised Approach):** Requires supervisory approval; sensitivity-based; more risk-sensitive

---

### 8.5.2 Basel Context

MAR50 requires banks to hold capital against movements in CVA, which is the mark-to-market adjustment to a derivatives portfolio's value reflecting counterparty default risk. CVA is distinct from the CCR capital computed by SA-CCR/IMM:
- **CCR capital** (SA-CCR/IMM) covers **expected and unexpected losses from default events**
- **CVA capital** (MAR50) covers **MTM losses from changes in the probability of default** (spread widening) without an actual default occurring

Key regulatory treatment: **CVA RWA is excluded from the output floor base** (CAP10 FAQ1). This prevents double-counting, as CVA is already sensitive to SA credit spread assumptions.

The CVA engine integrates with real-time market conditions via `CVAMarketDataFeed`:
- SOFR/OIS rate from FRED API (series: `SOFR`)
- IG OAS from FRED (series: `BAMLC0A0CM`)
- HY OAS from FRED (series: `BAMLH0A0HYM2`)
- VIX from FRED or yfinance (series: `VIXCLS`)

---

### 8.5.3 Functional Objective of Calculations

**BA-CVA (MAR50, Basic Approach):**
$$\text{CVA}_\text{capital} = 0.75 \times \text{EAD} \times RW$$

where $RW$ is the regulatory risk weight for the counterparty's credit quality tier.

**SA-CVA (MAR50.3, Standardised Approach — requires approval):**

Sensitivity-based calculation analogous to FRTB SBM; sensitivities are derived from CVA's dependence on CDS spreads, interest rates, FX, equity, and commodity risk factors.

**Automatic fallback logic:**
```
if not sa_cva_approved:
    method = "BA-CVA"
    log_trace("FALLBACK|CVA|SA-CVA_NOT_APPROVED|Using BA-CVA per MAR50.12")
else:
    method = "SA-CVA"
```

**Materiality threshold (MAR50.9):**
If the notional of derivatives subject to CVA risk is below the BCBS materiality threshold, the institution may use 100% of CCR RWA as a proxy CVA capital charge.

**Real-time parameter adjustment:**
$$\rho_\text{supervisory} = \min(0.50 + 0.30 \times \text{stress\_index},\; 0.80)$$

where stress index is a function of VIX and HY spreads (floored at 0.50 per MAR50.29 in normal conditions; rising to 0.80 in crisis).

---

### 8.5.4 Parameter Significance

| Parameter | Value | Significance |
|-----------|-------|-------------|
| **BA-CVA coefficient** | 0.75 | Conservative simplification; 75% of EAD-derived charge; penalty for not using SA-CVA |
| **SA-CVA supervisory rho (ρ)** | 0.50 (floor) to 0.80 (crisis) | Correlation between CVA and systematic market risk factors; higher in crisis (diversification breakdown) |
| **Risk weight by rating** | AAA: 0.5%, AA: 1%, A: 2%, BBB: 3%, BB: 6%, B: 12%, CCC: 25% | Represents idiosyncratic credit spread volatility by rating tier |
| **LGD (sector-specific)** | Financials: 60%, Corporates: 60%, Sovereigns: 75% | Market-implied LGD from CDS recovery rates; affects discount factor in CVA formula |
| **Risk-free rate (OIS/SOFR)** | Live FRED fetch | Discount rate for CVA NPV; affects maturity of the CVA exposure |
| **CVA EAD** | From SA-CCR output | CVA capital is computed on the same EAD as CCR; ensures consistency |
| **Materiality threshold** | As per MAR50.9 | Below threshold → proxy approach; above → full BA-CVA or SA-CVA required |

---

### 8.5.5 Key Success Criteria

- BA-CVA capital output matches MAR50 formula within < 0.01% tolerance
- SA-CVA fallback trace is logged when `sa_cva_approved = False`
- `supervisory_rho()` correctly increases from 0.50 to 0.80 as VIX increases from 15 to 80
- CVA RWA is correctly **excluded** from the output floor base in `main.py::PrometheusRunner.run_daily()`
- Live FRED API fetch succeeds; graceful fallback to hard-coded defaults on network failure
- 6/6 CVA unit tests pass

---

## FR-006: CCP Exposure Engine — Central Counterparty Capital

**Basel Standard:** CRE54  
**Priority:** MEDIUM  
**Owner:** Clearing Operations  
**File:** `backend/engines/ccp.py`

---

### 8.6.1 Use Case

The CCP engine calculates the regulatory capital a clearing member must hold against its exposures to a **Central Counterparty (CCP)**. As derivatives clearing mandates (EMIR, Dodd-Frank) have shifted a large portion of OTC derivatives to central clearing, CCP exposure has become a material component of CCR capital.

Two exposure types are captured:
1. **Trade Exposure:** The mark-to-market exposure from cleared trades, including posted initial margin
2. **Default Fund Contribution (DFC):** Capital against the bank's prefunded contribution to the CCP's default waterfall

---

### 8.6.2 Basel Context

CRE54 provides preferential capital treatment for **Qualifying CCPs (QCCPs)** — typically major clearing houses (LCH, CME, Eurex, JSCC) that meet CPMI-IOSCO Principles for Financial Market Infrastructures. The rationale: CCPs' multilateral netting, margining, and default management procedures reduce systemic risk, so banks should not be discouraged from central clearing by prohibitively high capital charges.

Non-qualifying CCPs receive a 100% risk weight (same as a corporate counterparty), providing a strong incentive to use qualifying clearing venues.

---

### 8.6.3 Functional Objective of Calculations

**QCCP Trade Exposure (CRE54.4):**
$$\text{RWA}_\text{trade} = \text{EAD}_\text{trade} \times 2\% \times 12.5$$

**Initial Margin posted:**
- Segregated IM → 0% risk weight (CRE54.15): protected from CCP default
- Non-segregated IM → 2% risk weight: commingled; exposed to CCP default

**Default Fund Capital (CRE54.31–39 — simplified):**
$$K_\text{DFC} = \min(0.08 \times K_\text{CCP},\; \text{DFC} \times 1.6\%)$$
$$\text{RWA}_\text{DFC} = K_\text{DFC} \times 12.5$$

**Unfunded DFC commitments (CRE54.42):**
$$\text{RWA}_\text{unfunded} = \text{DFC}_\text{unfunded} \times 12.5 \quad \text{(100\% capital requirement)}$$

**Client Clearing Intermediary (CRE54.5):**
$$\text{RWA}_\text{client} = \text{EAD}_\text{client} \times 2\% \times 12.5 \quad \text{(if QCCP)}$$

---

### 8.6.4 Parameter Significance

| Parameter | Value | Significance |
|-----------|-------|-------------|
| **QCCP risk weight** | 2% | Preferential rate; reflects CCP risk mitigation (netting, margining); vs. 100% for bilateral |
| **Non-QCCP risk weight** | 100% | Full corporate credit risk weight; intended to deter use of non-qualifying CCPs |
| **Segregated IM risk weight** | 0% | IM held in segregated account is protected from CCP insolvency; therefore zero capital |
| **Non-segregated IM risk weight** | 2% | Commingled IM exposed to CCP default; treated as trade exposure |
| **DFC flat rate (fallback)** | 1.6% (CRE54.33) | Simplified DFC capital rate when CCP's KCCP (hypothetical capital) is not available |
| **Unfunded DFC** | 1250% RW → 100% capital | Commitment to contribute additional funds to CCP default waterfall; extreme risk weight reflects contingent nature |

---

### 8.6.5 Key Success Criteria

- QCCP trade EAD correctly attracts 2% risk weight; non-QCCP attracts 100%
- Segregated IM produces 0 RWA; non-segregated IM produces 2% RWA
- DFC capital correctly applies 1.6% flat rate when KCCP is not provided
- Total CCP RWA aggregated across all CCPs and fed into the five-part formula
- 4/4 CCP unit tests pass

---

## FR-007: Daily Risk Orchestrator — Five-Part RWA Formula

**Basel Standard:** RBC20.9, RBC20.11  
**Priority:** CRITICAL  
**Owner:** Risk Operations  
**File:** `backend/main.py` (`PrometheusRunner`)

---

### 8.7.1 Use Case

The Orchestrator (`PrometheusRunner`) coordinates all six engines into a single, sequential daily risk run. It loads portfolio data, dispatches calculations to each engine, aggregates RWA components, applies the output floor, and persists results with a full audit trail. It is the single entry point for the daily risk calculation cycle.

---

### 8.7.2 Basel Context

RBC20.9 specifies that Total RWA is the sum of all risk components:
$$\text{Total RWA} = \text{RWA}_\text{Credit} + \text{RWA}_\text{CCR} + \text{RWA}_\text{Market} + \text{RWA}_\text{CVA} + \text{RWA}_\text{CCP} + \text{RWA}_\text{OpRisk}$$

RBC20.11 imposes the output floor:
$$\text{Final RWA} = \max\!\left(\text{Total RWA},\; 72.5\% \times \text{SA-based RWA}\right)$$

**CVA excluded from floor base (CAP10 FAQ1):** The SA-based RWA in the floor denominator excludes CVA RWA, as CVA is already sensitivity-based. Including it would introduce double-counting.

---

### 8.7.3 Functional Objective of Calculations

The orchestration flow executes in strict sequential order to ensure dependencies are met:

```
1. Load dataset (portfolio_generator.build_full_dataset)
2. For each derivative portfolio:
   a. SA-CCR EAD calculation
   b. IMM EAD calculation (if IMM-eligible trades present)
   c. IMM floor check: if EAD_IMM_CSA < 50% × EAD_SA-CCR → FALLBACK
   d. FRTB SBM + IMA calculation
   e. Aggregate RWA_CCR and RWA_Market
3. For each banking book portfolio:
   a. A-IRB RWA calculation (including double-default, SME, EL shortfall)
   b. Aggregate RWA_Credit
4. CVA calculation (BA-CVA or SA-CVA based on approval flag)
5. CCP RWA calculation (QCCP + DFC)
6. Operational Risk RWA stub (OPE25 BIA)
7. Five-part RWA formula:
   Total_RWA = RWA_Credit + RWA_CCR + RWA_Market + RWA_CVA + RWA_CCP + RWA_OpRisk
8. Output floor:
   SA_base = RWA_Credit_SA + RWA_CCR_SA + RWA_Market_SA + RWA_CCP_SA
   Final_RWA = max(Total_RWA, 0.725 × SA_base)
9. Capital requirement:
   Capital = Final_RWA × 8%
10. Persist results + audit logs (persistence.py)
```

---

### 8.7.4 Parameter Significance

| Parameter | Value | Significance |
|-----------|-------|-------------|
| **Output floor** | 72.5% | Basel IV transition floor; prevents advanced approach banks from holding < 72.5% of SA-equivalent RWA; reaches 100% by 2028 in BCBS phased timeline |
| **Capital ratio** | 8% | Minimum CET1+T1+T2 ratio per RBC20; Total RWA × 8% = minimum required regulatory capital |
| **Alpha (SA-CCR/IMM)** | 1.4 | Common multiplier applied before feeding EAD to RWA formula; ensures conservatism regardless of approach |
| **IMM floor** | 50% | EAD_IMM must be at least 50% of EAD_SA-CCR; prevents excessive IMM optimisation |
| **OPE25 BIA factor** | 15% | Basic Indicator Approach: 15% × 3-year average gross income; placeholder pending Sprint E |

---

### 8.7.5 Key Success Criteria

- All six RWA components produced in a single run call
- Output floor correctly applied; CVA excluded from floor base
- IMM fallback trace logged at WARNING level when floor violated
- Total run time < 5 minutes on M1 MacBook Air 8 GB
- Results persisted to PostgreSQL `risk.rwa_results` and `audit.run_logs`
- Results JSON structure fully populated for dashboard consumption

---

## FR-008: Market Data Integration

**Priority:** HIGH  
**Owner:** IT Infrastructure / Market Risk  
**Files:** `backend/data_sources/market_data_provider.py`, `backend/data_sources/cds_spread_service.py`, `backend/data_sources/market_state.py`, `backend/data_sources/calibration.py`

---

### 8.8.1 Use Case

The market data infrastructure supplies real-time and historical inputs to all risk engines: CDS spreads (for CVA and A-IRB), yield curves (for SA-CCR duration calculation), volatility surfaces (for FRTB vega), VIX and credit indices (for market regime classification), and OIS/SOFR rates (for CVA discounting).

---

### 8.8.2 Functional Objective

The abstract `MarketDataProvider` interface defines three core methods:
- `fetch_cds_spreads(obligor_id, tenors, as_of_date)` → Dict[tenor, spread_bp]
- `fetch_recovery_rate(obligor_id, as_of_date)` → float
- `fetch_risk_free_rate(currency, tenor, as_of_date)` → float

Concrete implementations: `BloombergProvider`, `RefinitivProvider`, `InternalFeedProvider`, `StaticTestProvider`.

`CDSSpreadService` wraps providers with:
- Primary→fallback cascade logic
- 5-minute TTL in-memory cache
- Bulk fetch for multiple obligors
- Conversion to `CreditSpreadsData` for A-IRB engine

`CVAMarketDataFeed` fetches SOFR, IG OAS, HY OAS, and VIX from FRED public API (no subscription required), with graceful fallback to hard-coded defaults if the network is unavailable.

---

### 8.8.3 Key Success Criteria

- Bloomberg and Refinitiv providers correctly fail gracefully when API is unavailable, falling to the next tier
- `StaticTestProvider` returns deterministic test data for CI/CD pipeline
- Cache hit rate reduces external API calls by > 80% in normal daily operation
- All engines receive valid (non-NaN, non-None) market data inputs or default gracefully

---

## FR-009: Backtesting Framework — Traffic-Light System

**Basel Standard:** MAR99  
**Priority:** CRITICAL  
**Owner:** Market Risk / Model Validation  
**File:** `backend/engines/frtb.py` (`BacktestEngine`)

---

### 8.9.1 Use Case

The backtesting framework validates the FRTB IMA's predictive accuracy by comparing the model's predicted risk measures (ES/VaR) against actual observed P&L over a rolling 260-day window. Under MAR99, if the model consistently underestimates losses (produces too many exceptions), the regulator requires model revision or imposes a capital multiplier add-on.

---

### 8.9.2 Basel Context

MAR99 defines a **traffic-light system** for IMA backtesting:
- **Green Zone** (0–4 exceptions in 250 days): Model acceptable; no additional capital
- **Amber Zone** (5–9 exceptions): Enhanced monitoring; potential multiplier (plus add-on factor)
- **Red Zone** (10+ exceptions): Model revision required; significant capital add-on

An "exception" occurs when the actual daily P&L loss exceeds the model's predicted 1-day VaR at 99% confidence.

The **PLA Test (MAR32)** compares Hypothetical P&L (HPL, sensitivity-based) against Actual P&L (APL, full revaluation) using Spearman rank correlation (ρ ≥ 0.50) and the Kolmogorov-Smirnov test (p-value ≥ 0.05). Desks failing PLA must use SBM.

---

### 8.9.3 Functional Objective

```
For each trading day d in [t-260, t]:
  exception(d) = 1 if |actual_pnl(d)| > VaR_model(d) else 0

n_exceptions = Σ exception(d)

if   n_exceptions ≤ 4: zone = "GREEN"
elif n_exceptions ≤ 9: zone = "AMBER"
else:                  zone = "RED"

PLA Spearman:  ρ = spearmanr(HPL, APL)
PLA KS:        p_value = ks_2samp(HPL, APL).pvalue
pla_zone = "GREEN" if ρ ≥ 0.50 and p_value ≥ 0.05 else "AMBER/RED"
```

---

### 8.9.4 Key Success Criteria

- Exception count correctly identifies the traffic-light zone
- Breach at Amber or Red triggers a WARNING log with alert details
- Spearman ρ and KS p-value computed and returned in `FRTBResult.pla_zone`
- Backtesting results surfaced on the Streamlit Backtesting page with historical exception timeline

---

## FR-010: Interactive Dashboard

**Priority:** MEDIUM  
**Owner:** Risk Control / IT  
**File:** `dashboard/app.py` (844 lines)

---

### 8.10.1 Use Case

The Streamlit dashboard provides a **zero-code interface** for risk officers, treasury managers, and regulators to view capital results, explore exposure breakdowns, analyse backtesting performance, run stress scenarios, and export regulatory reports — all in a browser.

---

### 8.10.2 Dashboard Pages

| Page | Content | Primary User |
|------|---------|-------------|
| **Overview** | Five-part RWA summary, capital ratio, output floor | CRO, Head of Treasury |
| **Derivative Risk** | SA-CCR and IMM by portfolio, FRTB capital | Head of Market Risk |
| **Banking Book** | A-IRB RWA, PD/LGD distribution, EL shortfall | Head of Credit Risk |
| **Backtesting** | Traffic-light status, exception timeline, PLA test | Market Risk / Model Validation |
| **Capital Planning** | Stress scenario what-if, RWA forecasts | Head of Treasury |
| **Reports** | Downloadable xlsx/csv regulatory templates | Regulatory Affairs |
| **Settings** | Configuration management, data source selection | IT Infrastructure |
| **Documentation** | Embedded regulatory references (Basel standards) | All |

---

### 8.10.3 Key Success Criteria

- All 8 pages render without error in Streamlit 1.28+
- Excel and CSV exports contain complete, correctly formatted data
- Dashboard refresh < 3 seconds on M1 MacBook Air
- Data persists correctly across browser refresh via PostgreSQL backend

---

## FR-011: Audit Trail and Compliance Reporting

**Priority:** CRITICAL  
**Owner:** Compliance / Regulatory Affairs  
**Files:** `backend/data_sources/persistence.py`, PostgreSQL `audit` schema

---

### 8.11.1 Use Case

Regulators (central banks, prudential supervisors) and external auditors require complete, immutable records of all capital calculations, methodology choices, and override events. Without a rigorous audit trail, the institution cannot defend its capital ratios under supervisory examination, and may face model approval revocation.

---

### 8.11.2 Functional Objective

Every calculation event is logged to the PostgreSQL `audit` schema with:
- `audit.run_logs`: Run date, start/end time, duration, status, engine versions
- `audit.calculation_traces`: Trade-level trace of formula, inputs, and output for each engine
- `audit.breach_alerts`: Timestamps and values for all risk limit breaches and regulatory floor applications
- `audit.user_actions`: User identity, action type (run trigger, config change, export), and timestamp

Fallback trace codes follow the format: `FALLBACK|<trade_id>|<reason_code>|<description>`

Example traces:
- `FALLBACK|TRD-001|REGULATORY_FLOOR|IMM EAD below 50% SA-CCR floor — CRE53.5`
- `FALLBACK|CVA|SA-CVA_NOT_APPROVED|Using BA-CVA per MAR50.12`
- `FALLBACK|TRD-007|EXOTIC_PAYOFF|Exotic payoff structure — IMM not approved for this type`

---

### 8.11.3 Key Success Criteria

- Zero calculations executed without a corresponding INFO-level log
- All floor applications and fallback events logged at WARNING level
- Audit schema tables are append-only (no updates or deletes in production)
- Export templates satisfy Basel Pillar 3 Table 4 (Credit Risk) and Table 12 (Market Risk) disclosure formats

---

---

# 9. BUSINESS AND FUNCTIONAL WORKFLOW

## 9.1 Business Workflow — Daily Capital Cycle

The daily capital calculation cycle follows a standardised risk operations workflow aligned with industry practice for regulated institutions:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PROMETHEUS DAILY CAPITAL CYCLE                      │
└─────────────────────────────────────────────────────────────────────────┘

 T-1 Day                T Day (06:00–08:00)          T Day (08:00+)
 ──────────────────────────────────────────────────────────────────────────
 ┌──────────────┐       ┌──────────────────────┐     ┌──────────────────┐
 │ Trade Booking│──────►│ Market Data Refresh   │────►│ CRO Dashboard    │
 │ (OMS/TMS)    │       │ (Bloomberg / FRED)    │     │ Review           │
 └──────────────┘       └──────────┬───────────┘     └──────────────────┘
                                   │
 ┌──────────────┐                  ▼
 │ Collateral   │       ┌──────────────────────┐     ┌──────────────────┐
 │ Management   │──────►│ Portfolio Load        │────►│ Risk Limit       │
 │ (CSA Terms)  │       │ (portfolio_generator) │     │ Monitoring       │
 └──────────────┘       └──────────┬───────────┘     └──────────────────┘
                                   │
 ┌──────────────┐                  ▼
 │ Credit       │       ┌──────────────────────┐     ┌──────────────────┐
 │ Systems      │──────►│ PROMETHEUS Risk Run   │────►│ Regulatory       │
 │ (PD/LGD/EAD) │       │ (PrometheusRunner)    │     │ Reporting        │
 └──────────────┘       └──────────┬───────────┘     │ (Pillar 1/3)     │
                                   │                  └──────────────────┘
                                   ▼
                        ┌──────────────────────┐     ┌──────────────────┐
                        │ Results Persistence   │────►│ Audit Archive    │
                        │ (PostgreSQL)          │     │ (audit schema)   │
                        └──────────────────────┘     └──────────────────┘
```

**Step-by-step business process:**

1. **Trade capture (T-1):** All trades booked in front-office systems by end-of-day cutoff are available in the risk database.
2. **Collateral reconciliation (T-1 to T):** CSA terms, initial margin, and variation margin are reconciled with counterparties and loaded into netting set definitions.
3. **Market data refresh (T 06:00):** Bloomberg / Refinitiv / FRED API calls populate yield curves, CDS spreads, volatility surfaces, and macro indicators for the calculation date.
4. **Portfolio load (T 06:30):** `portfolio_generator.build_full_dataset()` constructs the complete dataset of derivative and banking book portfolios.
5. **Risk run trigger (T 06:45):** `PrometheusRunner.run_daily()` is invoked (manually via `run_engine.sh` or automated via scheduler).
6. **Calculation execution (~2 minutes):** All six engines execute sequentially; SA-CCR → IMM → A-IRB → FRTB → CVA → CCP → Five-part formula → Output floor.
7. **Results persistence (T 07:00):** Complete results JSON and trade-level traces persisted to PostgreSQL.
8. **Dashboard available (T 07:00):** Risk officers can access the live Streamlit dashboard.
9. **Limit monitoring (T 07:00–08:00):** Breach alerts are reviewed; any Red Zone backtesting exception triggers Model Validation escalation.
10. **Regulatory reporting (as required):** Monthly/quarterly COREP exports generated from the dashboard Reports page.

---

## 9.2 Functional Workflow — Engine Execution Flow

```
PrometheusRunner.run_daily(run_date)
│
├── build_full_dataset(book_date)
│   ├── portfolio_generator: synthetic derivative portfolios
│   └── portfolio_generator: synthetic banking book portfolios
│
├── FOR EACH derivative portfolio:
│   ├── SACCREngine.compute_ead(netting_set, run_date)
│   │   ├── replacement_cost()
│   │   ├── pfe_multiplier()
│   │   ├── addon_ir(), addon_fx(), addon_credit(), addon_equity(), addon_commodity()
│   │   └── EAD = α × (RC + mult × AddOn_agg)
│   │
│   ├── IMMEngine.run_for_portfolio(trades, run_date, netting_set)  [if IMM eligible]
│   │   ├── generate_paths(GBM / Hull-White)
│   │   ├── revalue_portfolio()
│   │   ├── apply_csa_adjustment()
│   │   ├── compute_eepe()
│   │   └── EAD_IMM = α × EEPE
│   │
│   ├── IMM FLOOR CHECK: if EAD_IMM_CSA < 0.5 × EAD_SA-CCR → FALLBACK
│   │
│   └── FRTBEngine.compute(portfolio_id, sensitivities, pnl_series, ...)
│       ├── SBMCalculator.total_sbm()
│       │   ├── delta_charge() [per risk class, 3 correlation scenarios]
│       │   ├── vega_charge()
│       │   └── curvature_charge()
│       ├── IMACalculator.compute_es()
│       ├── DRCCalculator.compute_drc()
│       ├── rrao_charge()
│       └── Capital = SBM + IMA + DRC + RRAO; RWA = Capital × 12.5
│
├── FOR EACH banking book portfolio:
│   └── AIRBEngine.compute_portfolio(exposures)
│       ├── FOR EACH exposure:
│       │   ├── apply PD/LGD floors
│       │   ├── correlation_r()
│       │   ├── maturity_adjustment()
│       │   ├── capital_k()
│       │   ├── double_default_k() [if has_cds]
│       │   └── RWA = K × 12.5 × EAD
│       └── portfolio_summary (total_rwa, total_el, el_shortfall, mitigant_benefit)
│
├── CVAEngine.compute(counterparty_inputs)
│   ├── ba_cva() [always available]
│   └── sa_cva() [if approved; else fallback to BA-CVA]
│
├── compute_ccp_rwa(ccp_exposures)
│   ├── QCCP trade EAD × 2%
│   └── DFC capital × 12.5
│
├── FIVE-PART FORMULA:
│   Total_RWA = Credit + CCR + Market + CVA + CCP + OpRisk
│
├── OUTPUT FLOOR:
│   SA_base = Credit_SA + CCR_SA + Market_SA + CCP_SA
│   Final_RWA = max(Total_RWA, 0.725 × SA_base)
│   Capital = Final_RWA × 8%
│
└── persist_run(results) → PostgreSQL
```

---

---

# 10. SYSTEM ARCHITECTURE

## 10.1 Layered Architecture

PROMETHEUS follows a strict **five-layer architecture** separating presentation, application orchestration, business logic, data access, and persistence:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PROMETHEUS PLATFORM                              │
│                     Institutional Risk Management                         │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
  ┌────▼────────────────────────────────────────────────────────────────┐
  │ LAYER 1: PRESENTATION                                               │
  │  Streamlit Dashboard (dashboard/app.py) — Port 8501                │
  │  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────────┐   │
  │  │ Overview │ │Deriv Risk│ │Banking Book│ │Backtesting / PLA  │   │
  │  └──────────┘ └──────────┘ └────────────┘ └───────────────────┘   │
  │  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌───────────────────┐   │
  │  │Cap.Plan  │ │ Reports  │ │  Settings  │ │  Documentation    │   │
  │  └──────────┘ └──────────┘ └────────────┘ └───────────────────┘   │
  └────────────────────────────────────────────────────────────────────┘
                                   │
  ┌────────────────────────────────────────────────────────────────────┐
  │ LAYER 2: APPLICATION                                                │
  │  PrometheusRunner (backend/main.py)                                │
  │  • Daily risk run orchestration          • Five-part RWA formula   │
  │  • Output floor logic (RBC20.11)         • Calibration integration │
  │  • IMM floor enforcement (CRE53.5)       • Results aggregation     │
  └────────────────────────────────────────────────────────────────────┘
                                   │
  ┌────────────────────────────────────────────────────────────────────┐
  │ LAYER 3: BUSINESS LOGIC (backend/engines/)                         │
  │                                                                    │
  │ ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
  │ │ SA-CCR Engine  │  │   IMM Engine   │  │   A-IRB Engine     │   │
  │ │ CRE52          │  │   CRE53        │  │   CRE30–36         │   │
  │ │ sa_ccr.py      │  │   imm.py       │  │   a_irb.py         │   │
  │ └────────────────┘  └────────────────┘  └────────────────────┘   │
  │                                                                    │
  │ ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
  │ │  FRTB Engine   │  │   CVA Engine   │  │   CCP Engine       │   │
  │ │  MAR20–33      │  │   MAR50        │  │   CRE54            │   │
  │ │  frtb.py       │  │   cva.py       │  │   ccp.py           │   │
  │ │ ┌───────────┐  │  │ ┌──────────┐  │  └────────────────────┘   │
  │ │ │SBMCalc    │  │  │ │BA-CVA/   │  │                            │
  │ │ │IMACalc    │  │  │ │SA-CVA    │  │                            │
  │ │ │DRCCalc    │  │  │ └──────────┘  │                            │
  │ │ │Backtest   │  │  └────────────────┘                           │
  │ │ └───────────┘  │                                               │
  │ └────────────────┘                                               │
  └────────────────────────────────────────────────────────────────────┘
                                   │
  ┌────────────────────────────────────────────────────────────────────┐
  │ LAYER 4: DATA ACCESS (backend/data_sources/ + data_generators/)    │
  │                                                                    │
  │ ┌─────────────────────────────────────────────────────────────┐   │
  │ │             Market Data Provider (Abstract)                  │   │
  │ │  BloombergProvider │ RefinitivProvider │ StaticTestProvider   │   │
  │ └─────────────────────────────────────────────────────────────┘   │
  │ ┌─────────────────────────────────────────────────────────────┐   │
  │ │ CDSSpreadService │ CVAMarketDataFeed │ CalibrationModule      │   │
  │ └─────────────────────────────────────────────────────────────┘   │
  │ ┌─────────────────────────────────────────────────────────────┐   │
  │ │ PortfolioGenerator │ CVAGenerator │ Persistence Module        │   │
  │ └─────────────────────────────────────────────────────────────┘   │
  └────────────────────────────────────────────────────────────────────┘
                                   │
  ┌────────────────────────────────────────────────────────────────────┐
  │ LAYER 5: PERSISTENCE                                               │
  │  PostgreSQL 15 (Docker — localhost:5432)                           │
  │  ┌──────────────┐ ┌────────────────┐ ┌──────────┐ ┌──────────┐   │
  │  │ risk schema  │ │market_data     │ │reference │ │audit     │   │
  │  │ (5 tables)   │ │ (5 tables)     │ │(3 tables)│ │(4 tables)│   │
  │  └──────────────┘ └────────────────┘ └──────────┘ └──────────┘   │
  └────────────────────────────────────────────────────────────────────┘
```

## 10.2 External Interface Architecture

```
External Feeds                   PROMETHEUS                   Consumers
─────────────────────────────────────────────────────────────────────────
Bloomberg Terminal       ──►  MarketDataProvider  ──►  FRTB RW Adjustment
Refinitiv / LSEG Eikon  ──►  CDSSpreadService    ──►  A-IRB PD Calibration
FRED Public API         ──►  CVAMarketDataFeed   ──►  CVA Discounting
Internal REST API       ──►  InternalFeedProvider ──►  All Engines

PostgreSQL (docker)     ◄──  Persistence Module  ◄──  PrometheusRunner
                         ──►  Dashboard (app.py) ──►  Streamlit Browser
                         ──►  Audit Export       ──►  Regulators / Auditors
```

## 10.3 Non-Functional Architecture Constraints

| Constraint | Value | Rationale |
|-----------|-------|-----------|
| **Max RAM** | ~500 MB total (M1 8 GB) | MC paths ~40 MB; PostgreSQL ~200 MB; Dashboard ~150 MB |
| **Max run time** | < 5 minutes | Daily P&L batch must complete before 08:00 market open |
| **Port allocations** | PostgreSQL: 5432; pgAdmin: 5050; Streamlit: 8501 | Fixed for local deployment; configurable via environment variables |
| **Concurrency** | Single-threaded (Sprint A); multi-core planned (Sprint B) | M1 single-thread performance sufficient for 2K scenarios × 52 steps |
| **Python version** | 3.11+ | `dataclasses`, `match`, `tomllib` features required |

---

# 11. TECHNICAL DESIGN

## 11.1 Technology Stack

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| **Language** | Python | 3.11+ | Scientific computing ecosystem; regulatory finance libraries; type safety via Pylance |
| **Numerical** | NumPy | 1.24+ | Vectorised matrix operations for SBM correlation matrices; Monte Carlo path arrays |
| **Statistics** | SciPy | 1.10+ | `scipy.stats.norm` (inverse CDF for A-IRB); `scipy.stats.spearmanr`, `ks_2samp` (backtesting) |
| **Database** | PostgreSQL 15 | 15.x | ACID compliance; JSON column support for trade results; arm64 Docker image |
| **ORM / Driver** | psycopg2 | 2.9+ | Native Python PostgreSQL adapter; used in `persistence.py` |
| **Dashboard** | Streamlit | 1.28+ | Zero-frontend-code interactive web UI; ideal for risk officer self-service |
| **Visualisation** | Plotly | 5.17+ | Interactive charts (waterfall RWA, backtesting timeline, ES distribution) |
| **Data Export** | Pandas | 2.0+ | `pd.ExcelWriter` for xlsx; `DataFrame.to_csv()` for CSV regulatory exports |
| **Testing** | pytest | 7.4+ | Unit and integration tests; parametrised test cases for Basel formula validation |
| **Containerisation** | Docker | 24.0+ | PostgreSQL + pgAdmin in arm64 containers; `docker-compose.yml` orchestration |
| **Type Checking** | Pylance (VS Code) | Latest | Strict mode; 0 type errors enforced in CI |

## 11.2 Core Engine Design Patterns

### 11.2.1 Dataclass-Driven Data Model

All inputs and outputs are strongly-typed Python `dataclass` objects, enforcing type safety and enabling auto-serialisation:
- `Trade`, `NettingSet`, `SAcCRResult` — SA-CCR engine
- `BankingBookExposure`, `AIRBTradeResult` — A-IRB engine
- `Sensitivity`, `FRTBResult`, `ShockScenario` — FRTB engine
- `CCPExposure`, `CCPResult` — CCP engine
- `ExposureProfile`, `CSATerms` — IMM engine

### 11.2.2 Abstract Market Data Interface

`MarketDataProvider` (ABC) defines the contract; concrete implementations inject via dependency inversion. `CDSSpreadService` composes providers with fallback and caching, following the **Strategy Pattern**.

### 11.2.3 Pluggable Correlation Model

`CorrelationModel` is injectable into `FRTBConfig`, enabling alternative correlation structures (e.g., empirical GIRR tenor correlations) without modifying engine code.

### 11.2.4 Real-Time Market Condition Adjustment

`DynamicParameterAdjustment` wraps `FRTBConfig` and `MarketConditions` to scale risk weights and correlations based on live market stress index. This is a clean **Decorator Pattern** extension:
```
MarketConditions → stress_level() → DynamicParameterAdjustment.adjust_risk_weights()
                                                       ↓
                                         SBMCalculator._risk_weight_for()
```

### 11.2.5 Fallback Trace Code Pattern

Every fallback event writes a structured trace string directly onto the trade object:
```
format: "FALLBACK|{trade_id}|{reason_code}|{description}"
example: "FALLBACK|TRD-001|REGULATORY_FLOOR|IMM EAD below 50% SA-CCR floor — CRE53.5"
```
This is consumed downstream by the audit persistence layer and surfaced on the dashboard.

## 11.3 Database Design

### 11.3.1 Schema Overview (17 Tables)

**risk schema:**
```sql
portfolios    (portfolio_id VARCHAR PK, type VARCHAR, run_date DATE, cpty_id VARCHAR)
trades        (trade_id VARCHAR PK, portfolio_id FK, asset_class, instrument_type,
               notional NUMERIC, mtm NUMERIC, maturity_date DATE)
netting_sets  (netting_id VARCHAR PK, counterparty_id FK, initial_margin NUMERIC,
               variation_margin NUMERIC, threshold NUMERIC, mta NUMERIC, mpor_days INT)
exposures     (exposure_id VARCHAR PK, portfolio_id FK, ead NUMERIC, pd NUMERIC,
               lgd NUMERIC, maturity NUMERIC, sales_volume NUMERIC)
rwa_results   (result_id SERIAL PK, run_date DATE, rwa_credit NUMERIC, rwa_ccr NUMERIC,
               rwa_market NUMERIC, rwa_cva NUMERIC, rwa_ccp NUMERIC, rwa_oprisk NUMERIC,
               total_rwa NUMERIC, final_rwa NUMERIC, capital NUMERIC)
```

**market_data schema:**
```sql
yield_curves        (curve_id VARCHAR PK, currency VARCHAR, tenor NUMERIC, rate NUMERIC, date DATE)
fx_rates            (pair VARCHAR PK, rate NUMERIC, date DATE)
vol_surfaces        (surface_id VARCHAR PK, asset_class, strike NUMERIC, maturity NUMERIC, vol NUMERIC)
cds_spreads         (entity_id VARCHAR PK, tenor NUMERIC, spread_bp NUMERIC, date DATE)
correlation_matrices(matrix_id VARCHAR PK, risk_class VARCHAR, values JSONB)
```

**reference schema:**
```sql
counterparties    (counterparty_id VARCHAR PK, name VARCHAR, rating VARCHAR, sector VARCHAR)
risk_limits       (limit_id VARCHAR PK, limit_type VARCHAR, threshold NUMERIC, currency VARCHAR)
regulatory_params (param_id VARCHAR PK, standard VARCHAR, parameter VARCHAR, value NUMERIC)
```

**audit schema:**
```sql
run_logs             (log_id SERIAL PK, run_date DATE, status VARCHAR, duration_sec NUMERIC, engine_version VARCHAR)
calculation_traces   (trace_id SERIAL PK, portfolio_id FK, engine VARCHAR, formula TEXT, result NUMERIC, ts TIMESTAMPTZ)
breach_alerts        (alert_id SERIAL PK, limit_id FK, value NUMERIC, threshold NUMERIC, ts TIMESTAMPTZ)
user_actions         (action_id SERIAL PK, user_name VARCHAR, action_type VARCHAR, detail TEXT, ts TIMESTAMPTZ)
```

## 11.4 Configuration Management

All regulatory parameters are centralised in `backend/config.py` as typed dataclass instances:

| Config Class | Instance | Key Parameters |
|-------------|----------|---------------|
| `SACarCRConfig` | `SACCR` | `alpha=1.4`, `floor_multiplier=0.05`, `mpor_secured=10` |
| `IMMConfig` | `IMM` | `num_scenarios=2000`, `time_steps=52`, `alpha=1.4`, `random_seed=42` |
| `AIRBConfig` | `AIRB` | `pd_floor=0.0003`, `lgd_floor_unsecured=0.25`, `maturity_cap=5.0` |
| `FRTBConfig` | `FRTB` | `confidence_es=0.975`, `holding_period_days=10`, `green_zone_exceptions=4` |
| `MarketDataConfig` | `MARKET_DATA` | `primary_source`, `cache_ttl_seconds=300`, `bloomberg_host` |

Environment variable overrides are supported for all connection parameters (DB, Bloomberg, Refinitiv) via `os.getenv()`, enabling deployment without credential hardcoding.

## 11.5 Error Handling Architecture

All engines follow a consistent three-tier exception hierarchy:

```
BaseException
  └── Exception
        ├── ValidationError  (FRTBValidationError, IMMValidationError, ...)
        │     Raised for: invalid inputs, NaN/inf values, parameter out of range
        │     Handler: caller catches, logs WARNING, rejects bad input
        │
        ├── ConfigurationError  (FRTBConfigurationError, ...)
        │     Raised for: invalid config (correlations out of range, empty risk classes)
        │     Handler: caught at startup; prevents engine initialisation
        │
        └── CalculationError  (FRTBCalculationError, ...)
              Raised for: NaN/inf produced during calculation (numerical instability)
              Handler: caught by orchestrator, logged at ERROR, run marked FAILED
```

Graceful degradation:
- **Bloomberg/Refinitiv unavailable** → falls to next market data tier; logs WARNING
- **FRED API unavailable** → uses hard-coded CVA defaults; logs WARNING
- **IMM floor violated** → FALLBACK to SA-CCR; trace logged; run continues
- **SA-CVA not approved** → BA-CVA used; trace logged; run continues
- **scipy.special.erfinv unavailable** → local polynomial approximation in `a_irb.py`

## 11.6 Testing Architecture

**48 unit/integration tests** across `tests/test_engines.py`, structured by engine:

| Test Group | Count | Coverage |
|-----------|-------|---------|
| SA-CCR | 12 | RC, PFE multiplier, Add-Ons per asset class, EAD formula, IMM eligibility |
| IMM | 8 | GBM paths, Hull-White paths, CSA adjustment, EEPE convergence, stressed EAD |
| A-IRB | 10 | K formula, SME adjustment, double-default, EL shortfall, PD/LGD floors |
| FRTB | 6 | SBM delta/vega/curvature, three-scenario framework, ES at 97.5%, DRC |
| CVA | 6 | BA-CVA, SA-CVA, fallback logic, rho stress, FRED fallback |
| CCP | 4 | QCCP/non-QCCP, segregated IM, DFC simplified, unfunded |
| Capital | 2 | Five-part formula, output floor |
| **Total** | **48** | **100% pass rate** |

## 11.7 Deployment Architecture

**Sprint A — Development (Current):**
```
MacBook Air M1 (8 GB RAM, macOS Ventura+)
├── Python 3.11 (.venv at /Users/aaron/Documents/Project/Prometheus/.venv/)
├── PostgreSQL 15 (Docker arm64, localhost:5432)
│   └── Database: prometheus_risk | User: risk_admin
├── pgAdmin 4 (Docker, localhost:5050) — schema browser
├── Streamlit 1.28 (localhost:8501) — dashboard
└── pytest 7.4 — test suite
```

**Sprint E / F — Production (Planned 2026):**
```
Azure / AWS Cloud
├── Azure App Service (Python 3.11 backend, auto-scale)
│   └── Trigger: Azure Scheduler (06:00 daily)
├── Azure Database for PostgreSQL (Flexible Server, Burstable B2ms)
│   └── Geo-redundant backup; TDE encryption at rest
├── Azure Key Vault — credentials (DB password, Bloomberg API key)
├── Application Insights — logging, performance monitoring, alerts
├── Azure Blob Storage — report exports (xlsx/csv)
└── Azure Front Door / Application Gateway — HTTPS load balancing
```

---

---

# 12. APPENDIX

## Appendix A — Regulatory Standards Reference

| Standard | Full Name | Basel Publication | PROMETHEUS Engine |
|----------|-----------|-------------------|-------------------|
| **CRE30** | Credit Risk — Scope of IRB Approach | BIS April 2019 | A-IRB engine |
| **CRE31** | Credit Risk — IRB Risk Weight Functions | BIS April 2019 | A-IRB engine |
| **CRE32** | Credit Risk — IRB Collateral / LGD | BIS April 2019 | A-IRB engine |
| **CRE35** | Credit Risk — IRB Expected Loss | BIS April 2019 | A-IRB engine |
| **CRE36** | Credit Risk — IRB Minimum PD requirements | BIS April 2019 | A-IRB engine |
| **CRE51** | Counterparty Credit Risk — Overview | BIS June 2019 | SA-CCR / IMM |
| **CRE52** | CCR — Standardised Approach (SA-CCR) | BIS June 2019 | SA-CCR engine |
| **CRE53** | CCR — Internal Models Method (IMM) | BIS June 2019 | IMM engine |
| **CRE54** | CCR — Central Counterparty (CCP) | BIS June 2019 | CCP engine |
| **MAR10** | Market Risk — Overview | BIS Jan 2019 (rev.) | FRTB engine |
| **MAR20** | Market Risk — Boundary and transfer | BIS Jan 2019 (rev.) | FRTB engine |
| **MAR21** | Market Risk — SBM Delta | BIS Jan 2019 (rev.) | FRTB SBM |
| **MAR22** | Market Risk — Default Risk Charge | BIS Jan 2019 (rev.) | FRTB DRC |
| **MAR23** | Market Risk — Residual Risk Add-On (RRAO) | BIS Jan 2019 (rev.) | FRTB RRAO |
| **MAR31** | Market Risk — NMRF | BIS Jan 2019 (rev.) | FRTB NMRF |
| **MAR32** | Market Risk — PLA Test | BIS Jan 2019 (rev.) | BacktestEngine |
| **MAR33** | Market Risk — IMA (ES) | BIS Jan 2019 (rev.) | FRTB IMA |
| **MAR50** | CVA Risk | BIS June 2019 | CVA engine |
| **MAR99** | Market Risk — Backtesting | BIS Jan 2019 (rev.) | BacktestEngine |
| **RBC20** | Risk-Based Capital — Overview | BIS June 2019 | PrometheusRunner |
| **RBC25** | Capital — Limits and Minima | BIS June 2019 | PrometheusRunner |
| **CAP10** | Capital Adequacy — Output Floor FAQ | BIS 2019 | Output floor logic |
| **OPE25** | Operational Risk — Standardised Approach | BIS June 2019 | Stub (Sprint E) |
| **MGN** | Margin Requirements for Non-Centrally Cleared | BIS 2019 | CSA terms in IMM |

---

## Appendix B — Key Regulatory Formulas

### B.1 SA-CCR EAD (CRE52)

$$\text{EAD} = 1.4 \times \left[\max(V - C,\; TH + MTA - NICA,\; 0) + \text{mult} \times \text{AddOn}_\text{agg}\right]$$

$$\text{mult} = \min\!\left(1,\; 0.05 + 0.95 \times e^{\frac{V}{1.9 \times \text{AddOn}_\text{agg}}}\right)$$

### B.2 A-IRB Capital Requirement (CRE31)

$$K = \left[LGD \cdot \Phi\!\left(\frac{\Phi^{-1}(PD) + \sqrt{R}\,\Phi^{-1}(0.999)}{\sqrt{1-R}}\right) - PD \cdot LGD\right] \times \frac{1 + (M-2.5)b}{1-1.5b}$$

$$R = \frac{0.12(1-e^{-50PD})}{1-e^{-50}} + \frac{0.24[1-(1-e^{-50PD})/(1-e^{-50})]}{1}$$

$$b = (0.11852 - 0.05478\ln PD)^2$$

### B.3 FRTB SBM Delta (MAR21)

$$K_b = \sqrt{\sum_k WS_k^2 + \sum_{k\neq l}\rho_{kl}\cdot WS_k\cdot WS_l}$$

$$\Delta = \max\!\left(\sqrt{\sum_b K_b^2 + \sum_{b\neq c}\gamma_{bc}K_bK_c},\; \sum_k|WS_k|\right)$$

### B.4 IMM EEPE (CRE53)

$$\text{EEE}(t_k) = \max\left(\text{EEE}(t_{k-1}),\; \text{EE}(t_k)\right)$$

$$\text{EEPE} = \frac{1}{T}\sum_{k=1}^{T}\text{EEE}(t_k)$$

$$\text{EAD}_\text{IMM} = 1.4 \times \text{EEPE}$$

### B.5 Five-Part RWA Formula (RBC20.9)

$$\text{Total RWA} = \text{RWA}_\text{Cr} + \text{RWA}_\text{CCR} + \text{RWA}_\text{Mkt} + \text{RWA}_\text{CVA} + \text{RWA}_\text{CCP} + \text{RWA}_\text{OpRisk}$$

$$\text{SA Base} = \text{RWA}_\text{Cr,SA} + \text{RWA}_\text{CCR,SA} + \text{RWA}_\text{Mkt,SA} + \text{RWA}_\text{CCP,SA}$$

$$\text{Final RWA} = \max\!\left(\text{Total RWA},\; 0.725 \times \text{SA Base}\right)$$

$$\text{Capital} = \text{Final RWA} \times 8\%$$

---

## Appendix C — File Structure

```
PROMETHEUS/
├── PROMETHEUS_FSD.md              ← This document
├── PROMETHEUS_BRD.md              ← Business Requirements Document
├── README.md                      ← Quick start and overview
├── requirements.txt               ← Python dependencies
├── setup.sh                       ← One-shot environment setup
├── run_dashboard.sh               ← Dashboard launcher (Streamlit)
├── run_engine.sh                  ← CLI risk run launcher
├── run_tests.sh                   ← Test suite executor
│
├── docker/
│   ├── docker-compose.yml         ← PostgreSQL 15 + pgAdmin 4 (arm64)
│   └── init.sql                   ← Database schema initialisation (17 tables)
│
├── backend/
│   ├── config.py                  ← Regulatory parameter configuration
│   ├── main.py                    ← PrometheusRunner orchestrator (458 lines)
│   │
│   ├── engines/
│   │   ├── sa_ccr.py              ← SA-CCR (CRE52) — 459 lines
│   │   ├── imm.py                 ← IMM / Monte Carlo (CRE53) — 1,489 lines
│   │   ├── a_irb.py               ← A-IRB (CRE30–36) — 1,249 lines
│   │   ├── frtb.py                ← FRTB (MAR20–33) — 1,710 lines
│   │   ├── cva.py                 ← CVA Risk (MAR50) — 646 lines
│   │   └── ccp.py                 ← CCP (CRE54) — ~100 lines
│   │
│   ├── data_generators/
│   │   ├── portfolio_generator.py ← Synthetic derivative and banking book portfolios
│   │   └── cva_generator.py       ← CVA counterparty inputs and CCP exposures
│   │
│   └── data_sources/
│       ├── market_data_provider.py ← Abstract + Bloomberg/Refinitiv/Internal/Static providers
│       ├── cds_spread_service.py   ← CDS spread service with fallback and caching
│       ├── market_state.py         ← Market state management
│       ├── calibration.py          ← Historical volatility calibration module
│       └── persistence.py          ← PostgreSQL schema creation and result persistence
│
├── dashboard/
│   └── app.py                     ← Streamlit dashboard — 8 pages (844 lines)
│
├── tests/
│   └── test_engines.py            ← 48 validation tests
│
└── docs/
    └── MARKET_DATA_ARCHITECTURE.md ← Market data provider architecture guide
```

---

## Appendix D — Glossary

| Term | Full Form | Definition |
|------|-----------|------------|
| **A-IRB** | Advanced Internal Ratings-Based | Credit risk approach using bank's own PD, LGD, EAD estimates |
| **ASRF** | Asymptotic Single Risk Factor | Theoretical model underpinning IRB; single systematic risk factor |
| **BA-CVA** | Basic Approach — CVA | Simpler CVA capital approach; always available as fallback |
| **BCBS** | Basel Committee on Banking Supervision | BIS committee that issues Basel standards |
| **BIS** | Bank for International Settlements | Host institution for BCBS; publisher of Basel standards |
| **CCP** | Central Counterparty | Clearing house that interposes itself between buyer and seller |
| **CCR** | Counterparty Credit Risk | Risk of loss if a derivatives counterparty defaults |
| **CET1** | Common Equity Tier 1 | Highest quality regulatory capital (ordinary shares + retained earnings) |
| **CSA** | Credit Support Annex | Bilateral collateral agreement attached to ISDA Master Agreement |
| **CVA** | Credit Valuation Adjustment | MTM adjustment for counterparty default risk on derivatives |
| **DFC** | Default Fund Contribution | Bank's prefunded contribution to CCP default waterfall |
| **DRC** | Default Risk Charge | FRTB capital for jump-to-default risk in trading book |
| **EAD** | Exposure at Default | Expected exposure amount at time of counterparty default |
| **EE** | Expected Exposure | Scenario-average positive exposure at a future date |
| **EEPE** | Effective Expected Positive Exposure | Non-decreasing average EE over the first year; IMM regulatory metric |
| **EL** | Expected Loss | PD × LGD × EAD; expected average annual credit loss |
| **EPE** | Expected Positive Exposure | Average of positive exposures across scenarios and time |
| **ES** | Expected Shortfall | Average loss in the tail beyond VaR; used at 97.5% in FRTB IMA |
| **FRTB** | Fundamental Review of the Trading Book | Basel IV market risk framework replacing pre-2016 IMA/SA |
| **GBM** | Geometric Brownian Motion | Stochastic process for equity and FX in IMM simulation |
| **GIRR** | General Interest Rate Risk | FRTB risk class for parallel and non-parallel rate shifts |
| **HPL** | Hypothetical P&L | Sensitivity-based P&L recomputation; used in FRTB PLA test |
| **ICAAP** | Internal Capital Adequacy Assessment Process | Bank's own assessment of capital needed beyond Pillar 1 minimum |
| **IMA** | Internal Models Approach | FRTB approach using bank's own ES model (requires supervisory approval) |
| **IMM** | Internal Models Method | CRE53 approach for CCR EAD using Monte Carlo simulation |
| **IM / VM** | Initial Margin / Variation Margin | Upfront / daily collateral posted under CSA |
| **KS test** | Kolmogorov-Smirnov test | Non-parametric test comparing two distributions; used in FRTB PLA |
| **LGD** | Loss Given Default | Fraction of EAD lost upon counterparty default (1 − Recovery Rate) |
| **LH** | Liquidity Horizon | Time to liquidate/hedge a position; determines ES scaling in IMA |
| **MAF** | Maturity Adjustment Factor | Scaling factor in SA-CCR maturity factor; scales Add-On by √(time) |
| **MPOR** | Margin Period of Risk | Days from last margin receipt to portfolio replacement after default |
| **MTM** | Mark-to-Market | Current fair value of a financial instrument |
| **MTA** | Minimum Transfer Amount | Smallest collateral transfer increment under CSA |
| **NICA** | Net Independent Collateral Amount | Net posted collateral excluding VM; affects RC in SA-CCR |
| **NMRF** | Non-Modellable Risk Factor | Risk factor without sufficient price history; receives conservative FRTB charge |
| **OPE25** | Operational Risk — Standardised Approach | BIS standard for OpRisk capital; placeholder in Sprint A |
| **PD** | Probability of Default | Estimated probability that a borrower defaults within one year |
| **PFE** | Potential Future Exposure | High-percentile (e.g., 95th) future exposure; credit limit management metric |
| **PLA** | P&L Attribution (test) | FRTB MAR32 test comparing HPL to APL for IMA desk eligibility |
| **QCCP** | Qualifying Central Counterparty | CCP meeting CPMI-IOSCO Principles; attracts 2% risk weight |
| **RRAO** | Residual Risk Add-On | FRTB capital for exotic instruments not fully captured by SBM |
| **RC** | Replacement Cost | Immediate loss from counterparty default; first component of SA-CCR EAD |
| **RWA** | Risk-Weighted Assets | Capital base for capital ratio calculation; total = Final RWA / Capital ratio |
| **SA-CCR** | Standardised Approach for CCR | CRE52 replacement for CEM and SM; mandatory floor for IMM |
| **SA-CVA** | Standardised Approach for CVA | Sensitivity-based CVA capital approach; requires supervisory approval |
| **SBM** | Sensitivities-Based Method | FRTB standardised approach using delta, vega, curvature sensitivities |
| **SME** | Small and Medium Enterprise | Obligors with < €50M annual sales; lower correlation reduces A-IRB RWA |
| **SOFR** | Secured Overnight Financing Rate | USD risk-free reference rate; replaced LIBOR; used for CVA discounting |
| **TH** | Threshold | CSA threshold below which no collateral call is triggered |
| **TTC** | Through-the-Cycle | PD estimation methodology averaging across economic cycles |
| **VaR** | Value at Risk | Percentile loss over a holding period; replaced by ES in FRTB IMA |
| **VIX** | CBOE Volatility Index | Implied volatility of S&P 500 options; proxy for market stress |

---

## Appendix E — Sprint Roadmap

| Sprint | Planned Dates | Key Deliverables | Status |
|--------|-------------|-----------------|--------|
| **Sprint A** | Nov 2024 – Jan 2025 | All 6 engines, 48 tests, Dashboard, BRD | ✅ COMPLETE |
| **Sprint B** | Feb 2025 – Apr 2025 | IMA PLA Gate (MAR32), Spearman / KS automation | 🔄 Planned |
| **Sprint C** | May 2025 – Jul 2025 | Extended test suite (75+ tests), CVA/CCP expanded tests | 🔄 Planned |
| **Sprint D** | Aug 2025 – Oct 2025 | Dashboard CVA page, CCP page, IMA PLA page | 🔄 Planned |
| **Sprint E** | Nov 2025 – Jan 2026 | OPE25 Operational Risk engine | 🔄 Planned |
| **Sprint F** | Feb 2026 – Apr 2026 | User manual, demo video, LinkedIn showcase | 🔄 Planned |

---

## Appendix F — Risk Register

| Risk ID | Risk Description | Impact | Probability | Mitigation |
|---------|-----------------|--------|-------------|------------|
| **R-001** | Regulatory change (BCBS standard revision) | High | Medium | Modular engine design; BCBS subscription alerts; annual model review |
| **R-002** | Market data source unavailable (Bloomberg / Refinitiv) | High | Medium | Three-tier fallback cascade; FRED public API; static defaults |
| **R-003** | Database corruption | High | Very Low | PostgreSQL ACID compliance; daily backups; `audit` schema immutability |
| **R-004** | Capital miscalculation | Critical | Very Low | 48 validation tests; formula references in code comments; peer review |
| **R-005** | IMM model deterioration (backtesting Red Zone) | High | Low | 250-day rolling backtest; automated breach alerts; model recalibration trigger |
| **R-006** | Monte Carlo convergence failure | Medium | Low | Fixed random seed (42) for reproducibility; antithetic variance reduction |
| **R-007** | Third-party API downtime (FRED, Bloomberg) | Medium | Medium | Local cache (300s TTL); hard-coded defaults; graceful degradation logs |
| **R-008** | Key person dependency | High | Medium | Comprehensive documentation; this FSD; code comments with Basel references |
| **R-009** | Scope creep on regulatory changes | Medium | Medium | BRD sign-off; sprint planning; change request process |
| **R-010** | Cloud migration complexity (planned Sprint E/F) | Medium | Medium | Containerised architecture; PostgreSQL → Azure DB migration scripts |

---

## Appendix G — Acceptance Criteria Summary

| Criterion | Target | Achieved | Status |
|-----------|--------|---------|--------|
| Six regulatory engines implemented | ✅ | ✅ | Complete |
| Test pass rate | 100% (48/48) | 100% (48/48) | ✅ |
| Type safety (Pylance strict) | 0 errors | 0 errors | ✅ |
| Daily risk run time | < 5 min | ~2 min | ✅ |
| Dashboard pages | 8 | 8 | ✅ |
| Audit trail | All calculations logged | All logged | ✅ |
| Fallback trace codes | All fallbacks traced | All traced | ✅ |
| Output floor | RBC20.11 compliant | Verified | ✅ |
| CVA excluded from floor base | CAP10 FAQ1 | Implemented | ✅ |
| Export capability | xlsx / csv | Operational | ✅ |

---

## Appendix H — Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **Project Sponsor (CRO)** | | _________________________ | _______ |
| **Business Owner (Head of Risk)** | | _________________________ | _______ |
| **Technical Lead (Lead Developer)** | | _________________________ | _______ |
| **Model Validation** | | _________________________ | _______ |
| **Compliance Officer** | | _________________________ | _______ |
| **IT Infrastructure Lead** | | _________________________ | _______ |

---

---

*PROMETHEUS · Basel III/IV Risk Management Platform · Python 3.11 · PostgreSQL 15 · Streamlit 1.28*  
*Document Reference: PROMETHEUS-FSD-v1.0 · Classification: Internal Use — Confidential*  
*© 2025–2026 Risk Technology · All rights reserved*
