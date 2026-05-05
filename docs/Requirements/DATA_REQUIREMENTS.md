# PROMETHEUS Data Requirements Document
## Phase 2A: Data Architecture, Quality, & Lineage

**Version:** 2.1  
**Date:** May 1, 2026  
**Status:** ✅ APPROVED FOR IMPLEMENTATION  
**Prepared By:** Data Architecture & Governance Teams

---

## Executive Summary

This document defines all data requirements for PROMETHEUS Phase 2A, including input data sources, data quality standards, data lineage/governance, and the daily DQ scorecard framework (FR-016).

---

## 1. Input Data Sources

### 1.1 Portfolio Data (Daily, T+0)

| Source | Refresh Frequency | SLA | Format | Volume |
|--------|------------------|-----|--------|--------|
| Core Banking System | Daily (6:00 AM PT) | T+0 | CSV/Parquet | 500M+ rows |
| CIB Risk System | Daily (6:15 AM PT) | T+0 | SQL dump | 10M positions |
| Operations DB | Daily (6:30 AM PT) | T+0 | Delta table | 50M records |

**Key Portfolio Fields:**
```
position_id (PK)
obligor_id (FK)
counterparty_id
asset_class (CORP, RETAIL_MORT, BANK, SOVEREIGN, HVCRE, RETAIL_REV)
sector (Industrials, Financials, Energy, Healthcare, etc.)
ead (Exposure at Default in USD)
pd (Probability of Default, 0.03%–100%)
lgd (Loss Given Default, 0–100%)
maturity_years (1–5 years, per CRE31.7)
collateral_type (FINANCIAL, RECEIVABLES, RE_RES, RE_COM, etc.)
collateral_value
guarantee_id (if applicable)
cds_hedge_id (if applicable)
climate_brown_factor (0–1, Phase 2A new)
esg_score (0–100, Phase 2A new)
valuation_date
entry_date
```

**Data Quality Targets:**
- **Completeness:** >99% of rows have all required fields
- **Timeliness:** Received by 6:00 AM PT, processed by 6:30 AM PT
- **Accuracy:** Reconciliation <0.1% variance to source system

---

### 1.2 Market Data (Intra-day)

| Data Point | Source | Frequency | Fallback | Use Case |
|------------|--------|-----------|----------|----------|
| **SOFR** | FRED SOFR | Hourly | Previous close | Risk-free rate for discounting |
| **Credit Spreads (IG)** | Bloomberg CDX IG / FRED BAMLC0A0CM | Hourly | Previous close | BA-CVA spread |
| **Credit Spreads (HY)** | Bloomberg CDX HY / FRED BAMLH0A0HYM2 | Hourly | Previous close | BA-CVA spread |
| **VIX** | CBOE / yfinance | 15-min delayed | 20 (static) | Macro overlay |
| **Unemployment** | FRED UNRATE | Monthly | Previous month | Macro overlay |
| **Treasury Yields** | FRED T10Y2Y | Hourly | Previous close | Stress indicators |

**DQ Requirements:**
- **Latency:** SOFR/spreads updated within 1 hour of release
- **Completeness:** 100% coverage of required rates
- **Consistency:** Cross-validate Bloomberg vs FRED (tolerance: ±5 bps for spreads)

---

### 1.3 ESG/Climate Data (Monthly)

| ESG Dimension | Source | Frequency | Lag | Compliance Link |
|---------------|--------|-----------|-----|-----------------|
| **Emissions** | MSCI ESG DB / internal scoring | Monthly | 2 months | CRR3 Art. 87a |
| **Governance** | S&P CreditWise / internal | Quarterly | 1 quarter | Governance standard |
| **Board Composition** | BoardEx / internal | Annually | Annual | Governance standard |
| **Climate Taxonomy** | TCFD / internal mapping | Monthly | 30 days | Climate risk framework |

**ESG Scoring:** 0–100 scale
- 0–25: BROWN (high climate risk, weak governance)
- 26–50: AMBER (moderate climate risk)
- 51–75: NEUTRAL (transitioning)
- 76–100: GREEN (low climate risk, strong ESG)

**Climate PD Uplift (Fr-013):**
```
PD_uplift = brown_factor × max_uplift[asset_class]

Where brown_factor = (100 - esg_score) / 100
  (0 = green, 1 = brown)

And max_uplift[asset_class]:
  CORP: 50 bps
  RETAIL_MORT: 30 bps (flood risk)
  HVCRE: 80 bps (stranded asset risk)
  [etc.]
```

---

### 1.4 Regulatory Parameters (Quarterly Update)

| Parameter | Value (Current) | Source | Update Frequency |
|-----------|-----------------|--------|------------------|
| **Output Floor Ratio** | 0.725 (72.5%) | CRR3 Art. 12a | Per regulation |
| **Dynamic Relief Range** | 50–100 bps | Internal calibration | Quarterly review |
| **N⁻¹(0.999)** | 3.0902 | Basel III formula | Static |
| **PD Floor** | 0.03% | CRE31.5 | Static |
| **Supervisory ρ (BA-CVA)** | 0.50 | MAR50.29 | Static |
| **Stress Scenarios** | 6 defined (BASE + STRESS_1–5) | BCBS framework | Quarterly review |

---

## 2. Data Quality Standards (FR-016)

### 2.1 Four Dimensions Framework

#### Dimension 1: Completeness (25% weight)

**Definition:** % of required data fields populated (not NULL/missing)

**Calculation:**
```
Completeness = 1.0 - (Total Missing / (Total Records × Required Fields))

Target: >99%
Yellow Alert: <95%
Red Alert: <90%
```

**Root Cause Analysis for Missing Data:**
- Late source system delivery → escalate to ops
- Network failure → retry with exponential backoff
- Data format error → data engineering review
- Calculation failure → technical investigation

---

#### Dimension 2: Accuracy (25% weight)

**Definition:** % of data passing business validation rules

**Validation Rules (>150 total):**
```python
# Range validations
if pd < 0.03% or pd > 100%: flag as inaccurate
if lgd < 0% or lgd > 100%: flag
if ead < 0: flag
if maturity < 1 or maturity > 5: flag  # CRE31.7

# Cross-field validations
if asset_class == 'RETAIL_MORT' and maturity > 1:
    # Retail maturity floored at 1 year
    flag as inaccurate
    
if collateral_value > 0 and collateral_type is NULL:
    flag: missing collateral type

if cds_hedge_id is not NULL and cds_notional <= 0:
    flag: invalid hedge notional

# Reconciliation validations
obligor_id must exist in master obligor database
counterparty_id must exist in CDS/CVA pricing database
```

**Calculation:**
```
Accuracy = Validation Passes / Total Validation Checks × 100

Target: >98%
Yellow Alert: <90%
Red Alert: <80%
```

---

#### Dimension 3: Timeliness (25% weight)

**Definition:** % of data received/processed within SLA window

**SLA by Data Source:**
| Source | SLA Target | Latency Alert |
|--------|------------|---------------|
| Portfolio data | 6:30 AM PT | +15 min = YELLOW, +30 min = RED |
| Market data | Hourly | +60 min = YELLOW, +90 min = RED |
| ESG data | Monthly (5th of month) | +7 days = YELLOW, +14 days = RED |

**Calculation:**
```
Timeliness = On-Time Records / Total Records × 100

Target: 95%
Yellow Alert: Avg latency >30 min
Red Alert: Avg latency >60 min
```

---

#### Dimension 4: Consistency (25% weight)

**Definition:** % of successful cross-system reconciliations

**Key Reconciliations:**
```
Core Banking System   ←→ CIB Risk System
  Total EAD match: ±0.1%
  Position count match: ±0.5%
  Top 20 obligors: 100% match

Portfolio Data        ←→ Operations DB
  PD distribution match: ±2%
  LGD distribution match: ±1%

Market Data (Bloomberg) ←→ Market Data (FRED)
  SOFR rate: exact match
  Credit spreads: ±5 bps
  Implied volatility: ±2%
```

**Calculation:**
```
Consistency = Reconciled Records / Total Cross-System Records

Target: >97%
Yellow Alert: <90%
Red Alert: <80%
```

---

### 2.2 DQ Scorecard (FR-016)

**Daily Execution:** 7:00 AM PT (post-calculation)

**Output:**
```json
{
  "date": "2026-05-01",
  "overall_score": 94.2,
  "status": "GREEN",  // GREEN (≥90), YELLOW (75–89), RED (<75)
  "dimensions": {
    "completeness": {"score": 96.5, "pct": 99.5},
    "accuracy": {"score": 93.8, "pct": 98.2},
    "timeliness": {"score": 95.0, "pct": 97.3},
    "consistency": {"score": 91.2, "pct": 96.1}
  },
  "alerts": [
    {
      "dimension": "accuracy",
      "severity": "MEDIUM",
      "message": "Equity sector volatility outliers detected (10 exceptions)",
      "action": "Data engineering review Friday EOD"
    }
  ],
  "trend": "IMPROVING",  // IMPROVING / STABLE / DETERIORATING
  "year_to_date_avg": 92.1,
  "previous_30_days_avg": 91.8
}
```

**Alert Escalation:**
- **GREEN Status:** Normal, no action required
- **YELLOW Status:** Monitor closely; risk committee notified; root cause analysis by EOD
- **RED Status:** Risk run BLOCKED; investigation immediate; governance exception required for override

---

## 3. Data Lineage & Governance

### 3.1 Lineage Tracking (FR-014)

**Data Flow:**
```
SOURCE → INGESTION → VALIDATION → TRANSFORMATION → CALCULATION → OUTPUT → REPORTING

E.g., Portfolio Position:
  Core Banking System (source)
    ↓ CSV dump 6:00 AM PT (ingestion)
    ↓ Schema validation + range check (validation layer 1)
    ↓ Completeness check (validation layer 2 = FR-016 Dim 1)
    ↓ Normalization (PD scaling, FX conversion) (transformation)
    ↓ A-IRB capital calculation (calculation layer)
    ↓ Trace tree recording (trace engine = FR-014)
    ↓ Export to regulatory reports (output)
    ↓ Dashboard visualization (reporting)
```

**Trace Node Structure (FR-014 Integration):**
- **Input:** Portfolio position + market data
- **Intermediate Steps:** 
  - PD floor check
  - Maturity adjustment b(PD)
  - Asset correlation R calculation
  - Collateral LGD* calculation (if applicable)
  - K formula (capital per unit EAD)
  - RWA calculation
  - Dynamic floor check
  - ESG/Climate uplift
- **Output:** Final RWA + trace tree

**Auditability:**
- ✅ Every RWA number traceable to source position data
- ✅ Every formula step logged with intermediate values + timestamps
- ✅ Able to reproduce exact RWA calculation 7 years post-valuation (retention requirement)

---

### 3.2 Data Governance

**Data Ownership:**
| Data Category | Owner | SLA | Escalation |
|---------------|-------|-----|-----------|
| Portfolio data | Chief Risk Officer | T+0 | COO |
| Market data | Treasury | Hourly | CFO |
| ESG/Climate | Sustainability Officer | Monthly | CRO |
| Regulatory parameters | Compliance | Regulatory update | CEO |

**Data Quality Review Process:**
```
Daily (7:45 AM PT): Risk committee reviews DQ scorecard status
  - GREEN: Approve risk run, lock capital numbers
  - YELLOW: Review root cause, may approve with exception notation
  - RED: Halt risk run, investigate before rerun

Weekly (Monday 10 AM): Data governance meeting
  - Review previous week DQ trend (improving/stable/deteriorating)
  - Discuss root causes of any YELLOW/RED events
  - Plan remediation actions

Monthly (1st Friday): Data quality steering committee
  - Review YTD trends across all 4 dimensions
  - Adjust DQ targets/alerts if needed
  - Validate data governance controls
```

---

## 4. Data Dictionary

### 4.1 Portfolio Data

| Field | Type | Format | Validation Rule |
|-------|------|--------|-----------------|
| position_id | String | UUID-v4 | NOT NULL |
| obligor_id | String | MAX-50 | NOT NULL, foreign key to obligor_master |
| counterparty_id | String | MAX-50 | Foreign key if OTC derivative |
| asset_class | String | Enum | CORP \| RETAIL_MORT \| BANK \| SOVEREIGN \| HVCRE \| RETAIL_REV \| CCP |
| sector | String | MAX-50 | Industrials \| Financials \| Energy \| Healthcare \| Utilities \| Technology \| Telecom \| Consumer \| Comm_RE \| Res_RE \| Other |
| ead | Float | USD | 0 to 999,999,999,999 |
| pd | Float | Decimal | 0.0003 to 1.0 (0.03% to 100%) |
| lgd | Float | Decimal | 0.0 to 1.0 (0% to 100%) |
| maturity_years | Float | Decimal | 1.0 to 5.0 (enforce CRE31.7) |
| collateral_type | String | Enum (nullable) | FINANCIAL \| RECEIVABLES \| RE_RESIDENTIAL \| RE_COMMERCIAL \| OTHER_PHYSICAL |
| collateral_value | Float | USD | 0 to 999,999,999,999 |
| esg_score | Float | 0–100 | 0 to 100 (Month-end; nullable until Phase 2A) |
| climate_brown_factor | Float | 0–1 | 0 to 1 (Month-end; nullable until Phase 2A) |
| valuation_date | Date | ISO 8601 | YYYY-MM-DD, must be most recent business day |

---

## 5. Data Architecture

### 5.1 Storage Tiers

```
HOT LAYER (0–90 days)
├─ PostgreSQL (operational)
├─ Redis (cache, 1-hour TTL)
└─ Refresh: Real-time (portfolio, market data)

WARM LAYER (91 days – 2 years)
├─ DuckDB (analytical)
├─ Delta Lake (time-series)
└─ Refresh: Daily snapshot

COLD LAYER (2+ years)
├─ S3 (archive, compressed)
├─ Glacier tier (long-term retention)
└─ Access: Quarterly audits, exam requests
```

### 5.2 Backup & Recovery

| Objective | Target | Method | Frequency |
|-----------|--------|--------|-----------|
| RTO (Recovery Time Objective) | 4 hours | Automated failover to standby | N/A (automatic) |
| RPO (Recovery Point Objective) | <1 hour | Transaction log replication | Continuous |
| Backup Retention | 7 years | Immutable archive | Nightly after calculation |
| Disaster Recovery Test | Quarterly | Full recovery drill | Q1/Q2/Q3/Q4 |

---

## 6. Metadata Management

### 6.1 Data Catalog

**Schema Documentation:**
```
Table: portfolio_positions
├─ Business Description: All banking book exposures valued daily
├─ Owner: Chief Risk Officer
├─ Update Frequency: Daily (T+0)
├─ Columns: [position_id, obligor_id, asset_class, ..., esg_score, climate_brown_factor]
├─ Quality Dimensions: Completeness, Accuracy, Timeliness, Consistency
├─ Last Validated: 2026-05-01 07:35 AM PT
└─ SLA: ≥99% completeness, >98% accuracy, 100% timeliness

Field: esg_score
├─ Data Type: Float (0–100)
├─ Updated: Monthly (5th of month)
├─ Source: MSCI ESG Database
├─ Calculation: 30% governance + 35% environmental + 20% social + 15% economic
├─ Phase 2A Addition: Yes
└─ Regulatory Link: CRR3 Art. 87a
```

---

## 7. Compliance & Audit

### 7.1 Data Retention Policy

| Category | Retention Period | Justification |
|----------|------------------|-------------|
| Trace logs (FR-014) | 7 years | Regulatory exam requirement |
| Calculation results | 5 years | SOX/audit trail requirement |
| Raw market data | 2 years | Backup + compliance investigation |
| DQ scorecard archives | Permanent | Governance metric history |

### 7.2 GDPR/Privacy Compliance

- **PII Masking:** Obligor names masked in all logs/queries except authorized roles
- **Data Subject Rights:** Archive query protocol for data access requests
- **Data Minimization:** Only fields needed for capital calculation retained
- **Breach Protocol:** Notification within 72 hours to privacy officer

---

## Document Control

| Item | Value |
|------|-------|
| **Classification** | Internal Use — Confidential |
| **Owner** | Chief Data Officer |
| **Reviewer** | Data Governance, Operations, Compliance |
| **Distribution** | Data Team, Risk Committee, Model Risk |
| **Review Cycle** | Quarterly |

---

**END OF DATA REQUIREMENTS DOCUMENT**

**Prepared By:** Data Architecture & Governance Teams  
**Date:** May 1, 2026  
**Status:** ✅ APPROVED FOR IMPLEMENTATION

