# Prometheus — Database Quick Reference

**Database:** PostgreSQL 15  
**Regulatory Basis:** Basel III/IV (CRE30-55, MAR10-99, MGN, RBC20-25, CAP10)

---

## Schemas

| Schema | Purpose |
|---|---|
| `ref` | Reference / static data |
| `trading` | Portfolios & trades |
| `risk` | Risk results (daily snapshots) |
| `audit` | Audit trail |

---

## `ref` — Reference Data

### `ref.counterparties`
Counterparty master — obligor classification, ratings, PD/LGD inputs (CRE30).

| Column | Type | Description |
|---|---|---|
| `counterparty_id` | SERIAL PK | Auto-generated ID |
| `counterparty_code` | VARCHAR(20) | Unique code, e.g. `CPTY-0001` |
| `legal_name` | VARCHAR(200) | Full legal entity name |
| `country_iso2` | CHAR(2) | ISO 2-letter country code |
| `sector` | VARCHAR(50) | `Bank`, `Corp`, `Sovereign`, `SSE` |
| `rating_agency` | VARCHAR(20) | `Moody`, `S&P`, `Fitch` |
| `external_rating` | VARCHAR(10) | e.g. `AAA`, `BB+` |
| `pd_1yr` | NUMERIC(12,8) | 1-year PD (A-IRB input) |
| `lgd_unsecured` | NUMERIC(6,4) | LGD floor per CRE32 (default 0.45) |
| `maturity_years` | NUMERIC(6,2) | Effective maturity M (default 2.5) |
| `is_financial` | BOOLEAN | Financial institution flag |
| `is_nfc_plus` | BOOLEAN | Non-Financial Corporate above threshold |
| `extra` | JSONB | Extensible metadata |

---

### `ref.asset_classes`
Asset class lookup used across SA-CCR and FRTB. Pre-seeded with 5 rows.

| Column | Type | Description |
|---|---|---|
| `asset_class_code` | VARCHAR(20) PK | `IR`, `FX`, `EQ`, `CR`, `CMDTY` |
| `asset_class_name` | VARCHAR(100) | Full name |
| `supervisory_factor` | NUMERIC(8,4) | CRE52 supervisory factor (SF) |
| `supervisory_delta` | NUMERIC(8,4) | Default 1.0 |
| `correlation_rho` | NUMERIC(8,4) | Intra-bucket correlation |
| `description` | TEXT | Basel reference, e.g. `CRE52 Table 2` |

**Seeded values:**

| Code | Name | SF | Rho |
|---|---|---|---|
| `IR` | Interest Rate | 0.0050 | 0.50 |
| `FX` | Foreign Exchange | 0.0400 | 1.00 |
| `EQ` | Equity | 0.3200 | 0.50 |
| `CR` | Credit (SN) | 0.0500 | 0.50 |
| `CMDTY` | Commodity | 0.1800 | 0.40 |

---

### `ref.frtb_buckets`
FRTB risk-factor bucket definitions (MAR21) — delta/vega risk weights and intra-bucket correlations.

| Column | Type | Description |
|---|---|---|
| `bucket_id` | SERIAL PK | Auto-generated ID |
| `risk_class` | VARCHAR(20) | `GIRR`, `CSR_NS`, `EQ`, `FX`, `CMDTY` |
| `bucket_number` | SMALLINT | Bucket number per MAR21 tables |
| `bucket_label` | VARCHAR(100) | Human-readable label |
| `risk_weight` | NUMERIC(8,4) | Prescribed risk weight |
| `intra_corr_rho` | NUMERIC(8,4) | Intra-bucket correlation ρ |

---

### `ref.saccr_params`
SA-CCR supervisory parameters by asset class and subtype (CRE52 Table 2).

| Column | Type | Description |
|---|---|---|
| `param_id` | SERIAL PK | Auto-generated ID |
| `asset_class` | VARCHAR(20) FK | References `ref.asset_classes` |
| `subtype` | VARCHAR(50) | e.g. `IRS_TENOR_5Y`, `FX_SPOT` |
| `supervisory_factor` | NUMERIC(8,4) | SF for the specific subtype |
| `supervisory_duration` | NUMERIC(8,4) | IR trade supervisory duration (SD) |

---

## `trading` — Portfolios & Trades

### `trading.netting_agreements`
ISDA Master Agreement / CSA netting sets.

| Column | Type | Description |
|---|---|---|
| `netting_id` | SERIAL PK | Auto-generated ID |
| `netting_code` | VARCHAR(30) | Unique code, e.g. `NET-CPTY0001-001` |
| `counterparty_id` | INT FK | References `ref.counterparties` |
| `agreement_type` | VARCHAR(30) | Default `ISDA_2002` |
| `has_csa` | BOOLEAN | Whether a CSA is in place |
| `initial_margin` | NUMERIC(20,2) | IM posted (USD) |
| `variation_margin` | NUMERIC(20,2) | VM received (USD) |
| `threshold_amount` | NUMERIC(20,2) | MTA/Threshold (USD) |
| `mta` | NUMERIC(20,2) | Minimum Transfer Amount (default 500,000) |
| `independent_amount` | NUMERIC(20,2) | Independent Amount |
| `margining_freq_days` | SMALLINT | Margining frequency (default 1 = daily) |
| `mpor_days` | SMALLINT | Margin Period of Risk (default 10) |
| `ccy` | CHAR(3) | Base currency (default `USD`) |
| `start_date` | DATE | Agreement start date |
| `end_date` | DATE | Agreement end date (nullable) |

---

### `trading.portfolios`
Portfolio headers — separates Derivative and Banking Book books.

| Column | Type | Description |
|---|---|---|
| `portfolio_id` | VARCHAR(20) PK | e.g. `DRV-2024-001`, `BBK-2024-001` |
| `portfolio_type` | VARCHAR(15) | `DERIVATIVE` or `BANKING_BOOK` |
| `portfolio_name` | VARCHAR(200) | Descriptive name |
| `counterparty_id` | INT FK | References `ref.counterparties` |
| `netting_id` | INT FK | References `trading.netting_agreements` |
| `base_currency` | CHAR(3) | Default `USD` |
| `book_date` | DATE | Date of creation |
| `status` | VARCHAR(20) | `ACTIVE`, `MATURED`, `CLOSED` |

**Indexes:** `portfolio_type`, `counterparty_id`

---

### `trading.trades`
Individual trade/exposure records — handles both derivatives and banking book.

| Column | Type | Description |
|---|---|---|
| `trade_id` | VARCHAR(30) PK | e.g. `TRD-DRV-20240101-0001` |
| `portfolio_id` | VARCHAR(20) FK | References `trading.portfolios` |
| `asset_class` | VARCHAR(20) FK | References `ref.asset_classes` |
| `instrument_type` | VARCHAR(50) | `IRS`, `CDS`, `FXFwd`, `Equity_Swap`, etc. |
| `trade_date` | DATE | Trade inception date |
| `maturity_date` | DATE | Trade maturity date |
| `notional` | NUMERIC(25,2) | Notional amount |
| `notional_ccy` | CHAR(3) | Notional currency (default `USD`) |
| `direction` | SMALLINT | `1` = Long/Pay, `-1` = Short/Receive |
| `fixed_rate` | NUMERIC(10,6) | Fixed rate (e.g. for IRS) |
| `current_mtm` | NUMERIC(20,2) | Current mark-to-market value |
| `saccr_method` | VARCHAR(10) | `SA_CCR`, `IMM`, or `FALLBACK` |
| `fallback_trace_code` | VARCHAR(100) | Trace code explaining fallback trigger |
| `adjusted_notional` | NUMERIC(25,2) | d = notional × SD (CRE52.43) |
| `supervisory_delta` | NUMERIC(8,4) | Default 1.0 |
| `loan_type` | VARCHAR(30) | `TERM_LOAN`, `REVOLVING`, `BOND` (banking book) |
| `pd_override` | NUMERIC(12,8) | Borrower PD override |
| `lgd_override` | NUMERIC(8,4) | LGD override |
| `collateral_value` | NUMERIC(20,2) | Collateral value (default 0) |
| `collateral_type` | VARCHAR(30) | `CASH`, `BOND`, `EQUITY` |
| `status` | VARCHAR(20) | `ACTIVE`, `MATURED`, `CLOSED` |

**Indexes:** `portfolio_id`, `asset_class`, `status`, `maturity_date`

---

### `trading.credit_mitigants`
CDS protection and guarantees applied to Banking Book trades (CRE22).

| Column | Type | Description |
|---|---|---|
| `mitigant_id` | SERIAL PK | Auto-generated ID |
| `trade_id` | VARCHAR(30) FK | References `trading.trades` |
| `mitigant_type` | VARCHAR(30) | `CDS`, `GUARANTEE`, `CLN`, `SBLC` |
| `protection_seller` | VARCHAR(200) | Reference entity for CDS |
| `cds_notional` | NUMERIC(20,2) | CDS notional |
| `cds_premium_bps` | NUMERIC(8,2) | CDS premium in bps |
| `cds_maturity` | DATE | CDS maturity date |
| `recovery_rate` | NUMERIC(6,4) | Default 0.40 |
| `substitution_approach` | BOOLEAN | CRE22 double-default approach flag |
| `lgd_adjusted` | NUMERIC(8,4) | Post-mitigation LGD |

---

## `risk` — Risk Results

### `risk.saccr_results`
SA-CCR daily results per trade (CRE52).

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `portfolio_id` | VARCHAR(20) FK | References `trading.portfolios` |
| `trade_id` | VARCHAR(30) FK | References `trading.trades` |
| `replacement_cost` | NUMERIC(20,2) | RC = max(V − C, 0) |
| `pfe_multiplier` | NUMERIC(10,6) | PFE multiplier (floor 0.05) |
| `ead_sa_ccr` | NUMERIC(20,2) | EAD = α × (RC + mult × AddOn) |
| `add_on_aggregate` | NUMERIC(20,2) | Total aggregate add-on |
| `add_on_ir` | NUMERIC(20,2) | IR add-on |
| `add_on_fx` | NUMERIC(20,2) | FX add-on |
| `add_on_credit` | NUMERIC(20,2) | Credit add-on |
| `add_on_equity` | NUMERIC(20,2) | Equity add-on |
| `add_on_commodity` | NUMERIC(20,2) | Commodity add-on |
| `alpha` | NUMERIC(6,4) | α = 1.4 (CRE52.7) |
| `rwa_credit` | NUMERIC(20,2) | Credit RWA from SA-CCR |

**Index:** `(run_date, portfolio_id)`

---

### `risk.imm_results`
IMM Monte Carlo EPE/EEPE results per portfolio.

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `portfolio_id` | VARCHAR(20) FK | References `trading.portfolios` |
| `scenario_count` | INT | Number of Monte Carlo paths |
| `time_steps` | INT | Number of simulation time steps |
| `epe` | NUMERIC(20,2) | Expected Positive Exposure |
| `eepe` | NUMERIC(20,2) | Effective EPE |
| `eee` | NUMERIC(20,2) | Effective Expected Exposure |
| `ead_imm` | NUMERIC(20,2) | EAD = α × EEPE |
| `rwa_imm` | NUMERIC(20,2) | Credit RWA from IMM |
| `stressed_eepe` | NUMERIC(20,2) | Stressed EEPE |
| `stressed_ead` | NUMERIC(20,2) | Stressed EAD |
| `simulation_seed` | INT | RNG seed for reproducibility |
| `runtime_seconds` | NUMERIC(10,3) | Simulation runtime |

---

### `risk.airb_results`
A-IRB capital results — Banking Book only (CRE30-36).

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `portfolio_id` | VARCHAR(20) FK | References `trading.portfolios` |
| `trade_id` | VARCHAR(30) FK | References `trading.trades` |
| `pd_applied` | NUMERIC(12,8) | PD used in calculation |
| `lgd_applied` | NUMERIC(8,4) | LGD used in calculation |
| `ead_applied` | NUMERIC(20,2) | EAD used in calculation |
| `maturity_years` | NUMERIC(6,2) | Effective maturity M |
| `correlation_r` | NUMERIC(10,8) | Asset correlation R (CRE31 formula) |
| `capital_req_k` | NUMERIC(10,8) | Capital requirement K |
| `maturity_adj_b` | NUMERIC(10,8) | Maturity adjustment b |
| `rwa_airb` | NUMERIC(20,2) | A-IRB RWA |
| `el_best_estimate` | NUMERIC(20,2) | Expected Loss (best estimate) |

**Index:** `(run_date, portfolio_id)`

---

### `risk.frtb_results`
FRTB SBM and IMA results per portfolio (MAR21-23, MAR31-33).

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `portfolio_id` | VARCHAR(20) FK | References `trading.portfolios` |
| `method` | VARCHAR(10) | `SBM` or `IMA` |
| `sbm_delta_charge` | NUMERIC(20,2) | SBM delta capital charge |
| `sbm_vega_charge` | NUMERIC(20,2) | SBM vega capital charge |
| `sbm_curvature_charge` | NUMERIC(20,2) | SBM curvature capital charge |
| `sbm_total` | NUMERIC(20,2) | Total SBM charge |
| `es_99_10d` | NUMERIC(20,2) | Expected Shortfall — 99%, 10-day |
| `es_stressed` | NUMERIC(20,2) | Stressed ES |
| `nmrf_charge` | NUMERIC(20,2) | Non-Modellable Risk Factor charge |
| `ima_total` | NUMERIC(20,2) | Total IMA charge |
| `capital_mkt_risk` | NUMERIC(20,2) | Total market risk capital |
| `rwa_market` | NUMERIC(20,2) | Market RWA |

---

### `risk.cva_results`
CVA capital results — SA-CVA / BA-CVA / CCR-Proxy (MAR50).

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `counterparty_id` | INT FK | References `ref.counterparties` |
| `netting_id` | INT FK | References `trading.netting_agreements` |
| `method` | VARCHAR(15) | `SA_CVA`, `BA_CVA`, or `CCR_PROXY` |
| `fallback_trace` | TEXT | Trace code for fallback trigger |
| `ead_input` | NUMERIC(20,2) | EAD fed into CVA engine |
| `cva_estimate` | NUMERIC(20,2) | CVA dollar estimate |
| `ba_sc_charge` | NUMERIC(20,2) | BA-CVA standalone charge |
| `sa_delta_charge` | NUMERIC(20,2) | SA-CVA delta charge |
| `sa_vega_charge` | NUMERIC(20,2) | SA-CVA vega charge |
| `rwa_cva` | NUMERIC(20,2) | CVA RWA |
| `has_hedge` | BOOLEAN | Whether a CVA hedge is in place |
| `hedge_notional` | NUMERIC(20,2) | Hedge notional (default 0) |

**Index:** `(run_date, counterparty_id)`

---

### `risk.ccp_results`
CCP exposure and default fund contribution results (CRE54).

| Column | Type | Description |
|---|---|---|
| `result_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Calculation date |
| `ccp_name` | VARCHAR(100) | CCP name (e.g. `LCH`, `CME`) |
| `is_qualifying` | BOOLEAN | Whether CCP is a QCCP (default TRUE) |
| `trade_ead` | NUMERIC(20,2) | Trade EAD to CCP |
| `df_contribution` | NUMERIC(20,2) | Default fund contribution |
| `rwa_trade` | NUMERIC(20,2) | RWA on trade exposures |
| `rwa_dfc` | NUMERIC(20,2) | RWA on default fund contribution |
| `rwa_total` | NUMERIC(20,2) | Total CCP RWA |

---

### `risk.capital_summary`
Aggregated daily capital ratios and RWA across all risk types (RBC20-25).

| Column | Type | Description |
|---|---|---|
| `summary_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE UNIQUE | Calculation date (one row per day) |
| `rwa_credit_total` | NUMERIC(25,2) | Total credit RWA |
| `rwa_market_total` | NUMERIC(25,2) | Total market RWA |
| `rwa_operational` | NUMERIC(25,2) | Operational risk RWA (placeholder) |
| `rwa_cva` | NUMERIC(25,2) | CVA RWA |
| `rwa_ccp` | NUMERIC(25,2) | CCP RWA |
| `rwa_total` | NUMERIC(25,2) | Total RWA |
| `cet1_capital` | NUMERIC(25,2) | CET1 capital amount |
| `tier1_capital` | NUMERIC(25,2) | Tier 1 capital amount |
| `total_capital` | NUMERIC(25,2) | Total capital amount |
| `cet1_ratio` | NUMERIC(8,4) | CET1 / RWA |
| `tier1_ratio` | NUMERIC(8,4) | Tier 1 / RWA |
| `total_cap_ratio` | NUMERIC(8,4) | Total capital / RWA |
| `conservation_buffer` | NUMERIC(8,4) | Capital conservation buffer (default 2.5%) |
| `countercyclic_buf` | NUMERIC(8,4) | Counter-cyclical buffer |
| `output_floor_rwa` | NUMERIC(25,2) | Output floor RWA (RBC20.5) |
| `floor_triggered` | BOOLEAN | Whether output floor is binding |
| `cva_method` | VARCHAR(20) | CVA method used in this run |
| `cva_fallbacks` | INT | Number of CVA fallbacks this run |

---

### `risk.risk_limits`
Defined risk limits (firm-wide and portfolio-level).

| Column | Type | Description |
|---|---|---|
| `limit_id` | SERIAL PK | Auto-generated ID |
| `limit_code` | VARCHAR(30) | Unique code, e.g. `LIM-001` |
| `limit_name` | VARCHAR(200) | Descriptive name |
| `limit_type` | VARCHAR(30) | `EAD`, `RWA`, `VaR`, `ES`, `CAPITAL_RATIO` |
| `portfolio_id` | VARCHAR(20) | Scoped portfolio (NULL = firm-wide) |
| `counterparty_id` | INT | Scoped counterparty (nullable) |
| `limit_value` | NUMERIC(25,2) | Hard limit value |
| `warning_pct` | NUMERIC(6,4) | Warning threshold as % of limit (default 80%) |
| `is_active` | BOOLEAN | Whether limit is active |

**Seeded limits:**

| Code | Name | Type | Value |
|---|---|---|---|
| `LIM-001` | Firm-wide Credit EAD Limit | EAD | 5,000,000,000 |
| `LIM-002` | Firm-wide Market Risk Capital | CAPITAL_RATIO | 0.08 |
| `LIM-003` | CET1 Minimum Ratio | CAPITAL_RATIO | 0.045 |
| `LIM-004` | Total Capital Ratio Minimum | CAPITAL_RATIO | 0.08 |
| `LIM-005` | Single Counterparty EAD Limit | EAD | 500,000,000 |
| `LIM-006` | Derivatives Portfolio RWA Limit | RWA | 2,000,000,000 |
| `LIM-007` | Banking Book RWA Limit | RWA | 3,000,000,000 |
| `LIM-008` | FRTB Expected Shortfall (10d 99%) | ES | 100,000,000 |

---

### `risk.limit_breaches`
Limit breach events and acknowledgement tracking.

| Column | Type | Description |
|---|---|---|
| `breach_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Date of breach |
| `limit_id` | INT FK | References `risk.risk_limits` |
| `current_value` | NUMERIC(25,2) | Actual measured value |
| `limit_value` | NUMERIC(25,2) | Limit at time of breach |
| `utilisation_pct` | NUMERIC(8,4) | current_value / limit_value |
| `breach_type` | VARCHAR(20) | `WARNING` or `HARD_BREACH` |
| `acknowledged` | BOOLEAN | Whether breach has been acknowledged |
| `ack_user` | VARCHAR(100) | User who acknowledged |
| `ack_timestamp` | TIMESTAMPTZ | Acknowledgement timestamp |
| `notes` | TEXT | Free-text notes |

---

### `risk.backtesting`
Model backtesting records against realised P&L (MAR99 traffic light zones).

| Column | Type | Description |
|---|---|---|
| `bt_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Backtesting date |
| `portfolio_id` | VARCHAR(20) | Portfolio reference |
| `model_type` | VARCHAR(20) | `IMM_EPE`, `FRTB_ES`, `AIRB_EL` |
| `predicted_value` | NUMERIC(20,2) | Model-predicted value |
| `actual_value` | NUMERIC(20,2) | Realised value |
| `pnl` | NUMERIC(20,2) | Realised P&L |
| `exception_flag` | BOOLEAN | True if VaR/ES breached |
| `confidence_level` | NUMERIC(6,4) | Confidence level used |
| `lookback_days` | INT | Lookback window (default 250) |
| `exception_count_ytd` | INT | Exceptions year-to-date |
| `traffic_light` | VARCHAR(10) | `GREEN`, `AMBER`, `RED` (MAR99) |

---

## `audit` — Audit Trail

### `audit.run_log`
Engine execution history — one row per engine run.

| Column | Type | Description |
|---|---|---|
| `log_id` | BIGSERIAL PK | Auto-generated ID |
| `run_date` | DATE | Date of the run |
| `run_type` | VARCHAR(30) | `DAILY_RISK`, `BACKTEST`, `ADHOC` |
| `engine` | VARCHAR(50) | `SA_CCR`, `IMM`, `A_IRB`, `FRTB` |
| `status` | VARCHAR(20) | `SUCCESS`, `FAILED`, `PARTIAL` |
| `records_processed` | INT | Number of records processed |
| `runtime_seconds` | NUMERIC(10,3) | Execution time in seconds |
| `error_message` | TEXT | Error details (if any) |
| `triggered_by` | VARCHAR(100) | User or `SYSTEM` |

---

## Pre-built Views

### `risk.v_portfolio_exposure`
Active portfolio exposures joined with counterparty details.

```sql
SELECT portfolio_id, portfolio_type, portfolio_name, counterparty_name,
       external_rating, trade_count, gross_notional, net_mtm, status, book_date
FROM risk.v_portfolio_exposure;
```

### `risk.v_latest_capital`
Most recent row from `risk.capital_summary`.

```sql
SELECT * FROM risk.v_latest_capital;
```

### `risk.v_active_breaches`
All unacknowledged limit breaches, ordered by utilisation descending.

```sql
SELECT breach_id, run_date, limit_name, limit_type,
       current_value, limit_value, utilisation_pct, breach_type
FROM risk.v_active_breaches;
```

---

## Key Relationships

```
ref.counterparties
    ├── trading.portfolios          (counterparty_id)
    ├── trading.netting_agreements  (counterparty_id)
    └── risk.cva_results            (counterparty_id)

trading.netting_agreements
    ├── trading.portfolios          (netting_id)
    └── risk.cva_results            (netting_id)

trading.portfolios
    ├── trading.trades              (portfolio_id)
    ├── risk.saccr_results          (portfolio_id)
    ├── risk.imm_results            (portfolio_id)
    ├── risk.airb_results           (portfolio_id)
    └── risk.frtb_results           (portfolio_id)

trading.trades
    ├── trading.credit_mitigants    (trade_id)
    ├── risk.saccr_results          (trade_id)
    └── risk.airb_results           (trade_id)

risk.risk_limits
    └── risk.limit_breaches         (limit_id)
```
