-- =============================================================================
-- PROMETHEUS Risk Platform — Database Schema
-- Regulatory basis: Basel III/IV (CRE30-55, MAR10-99, MGN, RBC20-25, CAP10)
-- Database: PostgreSQL 15
-- =============================================================================

-- ─── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Schemas ─────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS ref;      -- Reference / static data
CREATE SCHEMA IF NOT EXISTS trading;  -- Portfolios & trades
CREATE SCHEMA IF NOT EXISTS risk;     -- Risk results
CREATE SCHEMA IF NOT EXISTS audit;    -- Audit trail

SET search_path = ref, trading, risk, audit, public;

-- =============================================================================
-- REFERENCE DATA
-- =============================================================================

-- Counterparty master (CRE30: obligor classification)
CREATE TABLE ref.counterparties (
    counterparty_id     SERIAL PRIMARY KEY,
    counterparty_code   VARCHAR(20) UNIQUE NOT NULL,   -- e.g. 'CPTY-0001'
    legal_name          VARCHAR(200) NOT NULL,
    country_iso2        CHAR(2) NOT NULL,
    sector              VARCHAR(50) NOT NULL,           -- 'Bank','Corp','Sovereign','SSE'
    rating_agency       VARCHAR(20),                   -- 'Moody','S&P','Fitch'
    external_rating     VARCHAR(10),                   -- 'AAA','BB+', etc.
    pd_1yr              NUMERIC(12,8),                 -- 1-yr PD (A-IRB)
    lgd_unsecured       NUMERIC(6,4) DEFAULT 0.45,     -- LGD floor per CRE32
    maturity_years      NUMERIC(6,2) DEFAULT 2.5,      -- Eff. maturity (M)
    is_financial        BOOLEAN DEFAULT FALSE,
    is_nfc_plus         BOOLEAN DEFAULT FALSE,         -- Non-Financial Corporates > threshold
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    -- extensible metadata
    extra               JSONB DEFAULT '{}'
);

-- Asset class lookup (used across SA-CCR, FRTB)
CREATE TABLE ref.asset_classes (
    asset_class_code    VARCHAR(20) PRIMARY KEY,       -- 'IR','FX','EQ','CR','CMDTY'
    asset_class_name    VARCHAR(100) NOT NULL,
    supervisory_factor  NUMERIC(8,4),                  -- CRE52: SF for SA-CCR
    supervisory_delta   NUMERIC(8,4) DEFAULT 1.0,
    correlation_rho     NUMERIC(8,4),                  -- intra-bucket correlation
    description         TEXT,
    extra               JSONB DEFAULT '{}'
);

INSERT INTO ref.asset_classes VALUES
  ('IR',    'Interest Rate',      0.0050, 1.0, 0.50, 'CRE52 Table 2',  '{}'),
  ('FX',    'Foreign Exchange',   0.0400, 1.0, 1.00, 'CRE52 Table 2',  '{}'),
  ('EQ',    'Equity',             0.3200, 1.0, 0.50, 'CRE52 Table 2',  '{}'),
  ('CR',    'Credit (SN)',        0.0500, 1.0, 0.50, 'CRE52 Table 2',  '{}'),
  ('CMDTY', 'Commodity',          0.1800, 1.0, 0.40, 'CRE52 Table 2',  '{}');

-- FRTB risk-factor bucket lookup (MAR21)
CREATE TABLE ref.frtb_buckets (
    bucket_id           SERIAL PRIMARY KEY,
    risk_class          VARCHAR(20) NOT NULL,    -- 'GIRR','CSR_NS','EQ','FX','CMDTY'
    bucket_number       SMALLINT,
    bucket_label        VARCHAR(100),
    risk_weight         NUMERIC(8,4),
    intra_corr_rho      NUMERIC(8,4),
    extra               JSONB DEFAULT '{}'
);

-- SA-CCR supervisory parameters (CRE52 Table 2)
CREATE TABLE ref.saccr_params (
    param_id            SERIAL PRIMARY KEY,
    asset_class         VARCHAR(20) REFERENCES ref.asset_classes(asset_class_code),
    subtype             VARCHAR(50),             -- e.g. 'IRS_TENOR_5Y', 'FX_SPOT'
    supervisory_factor  NUMERIC(8,4) NOT NULL,
    supervisory_duration NUMERIC(8,4),          -- for IR trades
    extra               JSONB DEFAULT '{}'
);

-- =============================================================================
-- PORTFOLIO & TRADE MANAGEMENT
-- =============================================================================

-- Netting Set / Master Agreement (ISDA) — satisfies req #6
CREATE TABLE trading.netting_agreements (
    netting_id          SERIAL PRIMARY KEY,
    netting_code        VARCHAR(30) UNIQUE NOT NULL,   -- 'NET-CPTY0001-001'
    counterparty_id     INT REFERENCES ref.counterparties(counterparty_id),
    agreement_type      VARCHAR(30) DEFAULT 'ISDA_2002',
    has_csa             BOOLEAN DEFAULT TRUE,
    -- CSA / Margin terms
    initial_margin      NUMERIC(20,2) DEFAULT 0,       -- IM posted (USD)
    variation_margin    NUMERIC(20,2) DEFAULT 0,       -- VM received (USD)
    threshold_amount    NUMERIC(20,2) DEFAULT 0,       -- MTA/Threshold (USD)
    mta                 NUMERIC(20,2) DEFAULT 500000,  -- Minimum Transfer Amount
    independent_amount  NUMERIC(20,2) DEFAULT 0,
    margining_freq_days SMALLINT DEFAULT 1,            -- daily=1
    mpor_days           SMALLINT DEFAULT 10,           -- Margin Period of Risk
    ccy                 CHAR(3) DEFAULT 'USD',
    start_date          DATE NOT NULL,
    end_date            DATE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- Portfolio header — separate for Derivatives and Banking Book (req #3)
CREATE TABLE trading.portfolios (
    portfolio_id        VARCHAR(20) PRIMARY KEY,       -- 'DRV-2024-001', 'BBK-2024-001'
    portfolio_type      VARCHAR(15) NOT NULL CHECK (portfolio_type IN ('DERIVATIVE','BANKING_BOOK')),
    portfolio_name      VARCHAR(200) NOT NULL,
    counterparty_id     INT REFERENCES ref.counterparties(counterparty_id),
    netting_id          INT REFERENCES trading.netting_agreements(netting_id),
    base_currency       CHAR(3) DEFAULT 'USD',
    book_date           DATE NOT NULL,                 -- day of creation
    status              VARCHAR(20) DEFAULT 'ACTIVE',  -- ACTIVE/MATURED/CLOSED
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    -- Extensible columns for future risk types
    extra               JSONB DEFAULT '{}'
);
CREATE INDEX idx_portfolios_type  ON trading.portfolios(portfolio_type);
CREATE INDEX idx_portfolios_cpty  ON trading.portfolios(counterparty_id);

-- Trade / Exposure table — handles both Derivatives and Banking Book (req #4,5)
CREATE TABLE trading.trades (
    trade_id            VARCHAR(30) PRIMARY KEY,       -- 'TRD-DRV-20240101-0001'
    portfolio_id        VARCHAR(20) REFERENCES trading.portfolios(portfolio_id),
    asset_class         VARCHAR(20) REFERENCES ref.asset_classes(asset_class_code),
    instrument_type     VARCHAR(50) NOT NULL,          -- 'IRS','CDS','FXFwd','Equity_Swap',etc.
    trade_date          DATE NOT NULL,
    maturity_date       DATE NOT NULL,
    notional            NUMERIC(25,2) NOT NULL,
    notional_ccy        CHAR(3) DEFAULT 'USD',
    direction           SMALLINT CHECK (direction IN (-1,1)),   -- 1=Long/Pay, -1=Short/Receive
    fixed_rate          NUMERIC(10,6),                -- for IRS etc.
    current_mtm         NUMERIC(20,2) DEFAULT 0,      -- Mark-to-Market value
    -- SA-CCR specific fields (CRE52)
    saccr_method        VARCHAR(10) DEFAULT 'SA_CCR' CHECK (saccr_method IN ('SA_CCR','IMM','FALLBACK')),
    fallback_trace_code VARCHAR(100),                 -- req #9: trace why fallback triggered
    adjusted_notional   NUMERIC(25,2),                -- d = notional * SD (CRE52.43)
    supervisory_delta   NUMERIC(8,4) DEFAULT 1.0,
    -- Banking Book specific
    loan_type           VARCHAR(30),                  -- 'TERM_LOAN','REVOLVING','BOND'
    pd_override         NUMERIC(12,8),                -- borrower PD override
    lgd_override        NUMERIC(8,4),
    collateral_value    NUMERIC(20,2) DEFAULT 0,
    collateral_type     VARCHAR(30),                  -- 'CASH','BOND','EQUITY'
    -- Lifecycle
    status              VARCHAR(20) DEFAULT 'ACTIVE',
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);
CREATE INDEX idx_trades_portfolio ON trading.trades(portfolio_id);
CREATE INDEX idx_trades_asset     ON trading.trades(asset_class);
CREATE INDEX idx_trades_status    ON trading.trades(status);
CREATE INDEX idx_trades_maturity  ON trading.trades(maturity_date);

-- Credit mitigants — CDS protection on Banking Book (req #7)
CREATE TABLE trading.credit_mitigants (
    mitigant_id         SERIAL PRIMARY KEY,
    trade_id            VARCHAR(30) REFERENCES trading.trades(trade_id),
    mitigant_type       VARCHAR(30) NOT NULL,          -- 'CDS','GUARANTEE','CLN','SBLC'
    protection_seller   VARCHAR(200),                  -- reference entity for CDS
    cds_notional        NUMERIC(20,2),
    cds_premium_bps     NUMERIC(8,2),
    cds_maturity        DATE,
    recovery_rate       NUMERIC(6,4) DEFAULT 0.40,
    substitution_approach BOOLEAN DEFAULT TRUE,        -- CRE22: double default?
    lgd_adjusted        NUMERIC(8,4),                 -- post-mitigation LGD
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- =============================================================================
-- RISK RESULTS  (daily snapshots — req #11)
-- =============================================================================

-- SA-CCR Results (CRE52)
CREATE TABLE risk.saccr_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    portfolio_id        VARCHAR(20) REFERENCES trading.portfolios(portfolio_id),
    trade_id            VARCHAR(30) REFERENCES trading.trades(trade_id),
    -- SA-CCR decomposition
    replacement_cost    NUMERIC(20,2),                 -- RC = max(V-C, 0)
    pfe_multiplier      NUMERIC(10,6),                 -- multiplier (floor 0.05)
    ead_sa_ccr          NUMERIC(20,2),                 -- EAD = alpha*(RC + mult*AddOn)
    add_on_aggregate    NUMERIC(20,2),
    add_on_ir           NUMERIC(20,2),
    add_on_fx           NUMERIC(20,2),
    add_on_credit       NUMERIC(20,2),
    add_on_equity       NUMERIC(20,2),
    add_on_commodity    NUMERIC(20,2),
    alpha               NUMERIC(6,4) DEFAULT 1.4,      -- CRE52.7
    rwa_credit          NUMERIC(20,2),
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);
CREATE INDEX idx_saccr_date_port ON risk.saccr_results(run_date, portfolio_id);

-- IMM Results (Monte Carlo EPE)
CREATE TABLE risk.imm_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    portfolio_id        VARCHAR(20) REFERENCES trading.portfolios(portfolio_id),
    scenario_count      INT,
    time_steps          INT,
    epe                 NUMERIC(20,2),                 -- Expected Positive Exposure
    eepe                NUMERIC(20,2),                 -- Effective EPE
    eee                 NUMERIC(20,2),                 -- Effective EE
    ead_imm             NUMERIC(20,2),                 -- alpha * EEPE
    rwa_imm             NUMERIC(20,2),
    -- IMM stress metrics
    stressed_eepe       NUMERIC(20,2),
    stressed_ead        NUMERIC(20,2),
    simulation_seed     INT,
    runtime_seconds     NUMERIC(10,3),
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- A-IRB Results (CRE30-36) — Banking Book only (req #10)
CREATE TABLE risk.airb_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    portfolio_id        VARCHAR(20) REFERENCES trading.portfolios(portfolio_id),
    trade_id            VARCHAR(30) REFERENCES trading.trades(trade_id),
    pd_applied          NUMERIC(12,8),
    lgd_applied         NUMERIC(8,4),
    ead_applied         NUMERIC(20,2),
    maturity_years      NUMERIC(6,2),
    -- A-IRB formula outputs (CRE31)
    correlation_r       NUMERIC(10,8),
    capital_req_k       NUMERIC(10,8),
    maturity_adj_b      NUMERIC(10,8),
    rwa_airb            NUMERIC(20,2),
    el_best_estimate    NUMERIC(20,2),
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);
CREATE INDEX idx_airb_date_port ON risk.airb_results(run_date, portfolio_id);

-- FRTB Results (MAR21-23 SBM + MAR31-33 IMA)
CREATE TABLE risk.frtb_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    portfolio_id        VARCHAR(20) REFERENCES trading.portfolios(portfolio_id),
    method              VARCHAR(10) DEFAULT 'SBM',     -- 'SBM' or 'IMA'
    -- SBM components (MAR21)
    sbm_delta_charge    NUMERIC(20,2),
    sbm_vega_charge     NUMERIC(20,2),
    sbm_curvature_charge NUMERIC(20,2),
    sbm_total           NUMERIC(20,2),
    -- IMA / ES (MAR33)
    es_99_10d           NUMERIC(20,2),                 -- ES at 99% 10-day
    es_stressed         NUMERIC(20,2),
    nmrf_charge         NUMERIC(20,2),                 -- Non-Modellable Risk Factors
    ima_total           NUMERIC(20,2),
    -- Capital
    capital_mkt_risk    NUMERIC(20,2),
    rwa_market          NUMERIC(20,2),
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- Aggregated capital summary (RBC20-25)
CREATE TABLE risk.capital_summary (
    summary_id          BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL UNIQUE,
    -- Pillar 1 RWA
    rwa_credit_total    NUMERIC(25,2) DEFAULT 0,
    rwa_market_total    NUMERIC(25,2) DEFAULT 0,
    rwa_operational     NUMERIC(25,2) DEFAULT 0,       -- placeholder req #2
    rwa_total           NUMERIC(25,2) DEFAULT 0,
    -- Capital ratios (RBC20)
    cet1_capital        NUMERIC(25,2) DEFAULT 0,
    tier1_capital       NUMERIC(25,2) DEFAULT 0,
    total_capital       NUMERIC(25,2) DEFAULT 0,
    cet1_ratio          NUMERIC(8,4),                  -- CET1 / RWA
    tier1_ratio         NUMERIC(8,4),
    total_cap_ratio     NUMERIC(8,4),
    -- Buffers (RBC30)
    conservation_buffer NUMERIC(8,4) DEFAULT 0.025,
    countercyclic_buf   NUMERIC(8,4) DEFAULT 0,
    -- Output floor (RBC20.5)
    output_floor_rwa    NUMERIC(25,2),
    floor_triggered     BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- Risk limits and breaches (req Technical #1)
CREATE TABLE risk.risk_limits (
    limit_id            SERIAL PRIMARY KEY,
    limit_code          VARCHAR(30) UNIQUE NOT NULL,
    limit_name          VARCHAR(200) NOT NULL,
    limit_type          VARCHAR(30),                   -- 'EAD','RWA','VaR','ES','CAPITAL_RATIO'
    portfolio_id        VARCHAR(20),                   -- NULL = firm-wide
    counterparty_id     INT,
    limit_value         NUMERIC(25,2),
    warning_pct         NUMERIC(6,4) DEFAULT 0.80,    -- warn at 80% of limit
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

CREATE TABLE risk.limit_breaches (
    breach_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    limit_id            INT REFERENCES risk.risk_limits(limit_id),
    current_value       NUMERIC(25,2),
    limit_value         NUMERIC(25,2),
    utilisation_pct     NUMERIC(8,4),
    breach_type         VARCHAR(20),                   -- 'WARNING','HARD_BREACH'
    acknowledged        BOOLEAN DEFAULT FALSE,
    ack_user            VARCHAR(100),
    ack_timestamp       TIMESTAMPTZ,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- Backtesting records (req Technical #7)
CREATE TABLE risk.backtesting (
    bt_id               BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    portfolio_id        VARCHAR(20),
    model_type          VARCHAR(20),                   -- 'IMM_EPE','FRTB_ES','AIRB_EL'
    predicted_value     NUMERIC(20,2),
    actual_value        NUMERIC(20,2),
    pnl                 NUMERIC(20,2),
    exception_flag      BOOLEAN DEFAULT FALSE,         -- breach of VaR/ES
    confidence_level    NUMERIC(6,4),
    lookback_days       INT DEFAULT 250,
    exception_count_ytd INT DEFAULT 0,
    traffic_light       VARCHAR(10),                   -- 'GREEN','AMBER','RED' (MAR99 zones)
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- =============================================================================
-- AUDIT SCHEMA
-- =============================================================================

CREATE TABLE audit.run_log (
    log_id              BIGSERIAL PRIMARY KEY,
    run_date            DATE,
    run_type            VARCHAR(30),                   -- 'DAILY_RISK','BACKTEST','ADHOC'
    engine              VARCHAR(50),                   -- 'SA_CCR','IMM','A_IRB','FRTB'
    status              VARCHAR(20),                   -- 'SUCCESS','FAILED','PARTIAL'
    records_processed   INT,
    runtime_seconds     NUMERIC(10,3),
    error_message       TEXT,
    triggered_by        VARCHAR(100) DEFAULT 'SYSTEM',
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- =============================================================================
-- VIEWS  — for dashboard queries
-- =============================================================================

CREATE OR REPLACE VIEW risk.v_portfolio_exposure AS
SELECT
    p.portfolio_id,
    p.portfolio_type,
    p.portfolio_name,
    c.legal_name            AS counterparty_name,
    c.external_rating,
    COUNT(t.trade_id)       AS trade_count,
    SUM(ABS(t.notional))    AS gross_notional,
    SUM(t.current_mtm)      AS net_mtm,
    p.status,
    p.book_date
FROM trading.portfolios p
LEFT JOIN ref.counterparties c USING (counterparty_id)
LEFT JOIN trading.trades t USING (portfolio_id)
WHERE t.status = 'ACTIVE'
GROUP BY p.portfolio_id, p.portfolio_type, p.portfolio_name,
         c.legal_name, c.external_rating, p.status, p.book_date;

CREATE OR REPLACE VIEW risk.v_latest_capital AS
SELECT *
FROM risk.capital_summary
ORDER BY run_date DESC
LIMIT 1;

CREATE OR REPLACE VIEW risk.v_active_breaches AS
SELECT
    lb.breach_id,
    lb.run_date,
    rl.limit_name,
    rl.limit_type,
    lb.current_value,
    lb.limit_value,
    ROUND(lb.utilisation_pct * 100, 2) AS utilisation_pct,
    lb.breach_type,
    lb.acknowledged
FROM risk.limit_breaches lb
JOIN risk.risk_limits rl USING (limit_id)
WHERE lb.acknowledged = FALSE
ORDER BY lb.utilisation_pct DESC;

-- =============================================================================
-- SEED: default limits
-- =============================================================================

INSERT INTO risk.risk_limits (limit_code, limit_name, limit_type, limit_value, warning_pct)
VALUES
  ('LIM-001', 'Firm-wide Credit EAD Limit',        'EAD',          5000000000, 0.80),
  ('LIM-002', 'Firm-wide Market Risk Capital',      'CAPITAL_RATIO', 0.08,      0.90),
  ('LIM-003', 'CET1 Minimum Ratio',                 'CAPITAL_RATIO', 0.045,     0.95),
  ('LIM-004', 'Total Capital Ratio Minimum',        'CAPITAL_RATIO', 0.08,      0.92),
  ('LIM-005', 'Single Counterparty EAD Limit',      'EAD',          500000000,  0.85),
  ('LIM-006', 'Derivatives Portfolio RWA Limit',    'RWA',          2000000000, 0.80),
  ('LIM-007', 'Banking Book RWA Limit',             'RWA',          3000000000, 0.80),
  ('LIM-008', 'FRTB Expected Shortfall (10d 99%)',  'ES',           100000000,  0.80);

-- Completion message
DO $$ BEGIN RAISE NOTICE 'PROMETHEUS schema initialised successfully.'; END $$;

-- CVA Results table (MAR50) — added per revised architecture
CREATE TABLE IF NOT EXISTS risk.cva_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    counterparty_id     INT REFERENCES ref.counterparties(counterparty_id),
    netting_id          INT REFERENCES trading.netting_agreements(netting_id),
    method              VARCHAR(15) NOT NULL,       -- 'SA_CVA' | 'BA_CVA' | 'CCR_PROXY'
    fallback_trace      TEXT,                       -- req #13 trace code
    ead_input           NUMERIC(20,2),
    cva_estimate        NUMERIC(20,2),
    ba_sc_charge        NUMERIC(20,2),
    sa_delta_charge     NUMERIC(20,2),
    sa_vega_charge      NUMERIC(20,2),
    rwa_cva             NUMERIC(20,2),
    has_hedge           BOOLEAN DEFAULT FALSE,
    hedge_notional      NUMERIC(20,2) DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);
CREATE INDEX idx_cva_date_cpty ON risk.cva_results(run_date, counterparty_id);

-- CCP Exposure Results (CRE54)
CREATE TABLE IF NOT EXISTS risk.ccp_results (
    result_id           BIGSERIAL PRIMARY KEY,
    run_date            DATE NOT NULL,
    ccp_name            VARCHAR(100) NOT NULL,
    is_qualifying       BOOLEAN DEFAULT TRUE,
    trade_ead           NUMERIC(20,2),
    df_contribution     NUMERIC(20,2),
    rwa_trade           NUMERIC(20,2),
    rwa_dfc             NUMERIC(20,2),
    rwa_total           NUMERIC(20,2),
    created_at          TIMESTAMPTZ DEFAULT now(),
    extra               JSONB DEFAULT '{}'
);

-- Extend capital_summary with CVA and CCP columns
ALTER TABLE IF EXISTS risk.capital_summary
    ADD COLUMN IF NOT EXISTS rwa_cva       NUMERIC(25,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS rwa_ccp       NUMERIC(25,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS cva_method    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS cva_fallbacks INT DEFAULT 0;

DO $$ BEGIN RAISE NOTICE 'CVA and CCP tables added.'; END $$;
