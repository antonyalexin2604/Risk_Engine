"""
PROMETHEUS Risk Platform — Time-Series Persistence Layer

Writes each daily risk run snapshot to PostgreSQL so the dashboard
can display Year / Month / Date granularity for EAD and RWA.

Tables created on first write (idempotent DDL):
  prometheus_risk.daily_capital       — one row per run_date
  prometheus_risk.portfolio_snapshots — one row per (run_date, portfolio_id)
  prometheus_risk.trade_mtm_history   — one row per (run_date, trade_id)

Query helpers return pandas DataFrames for direct use in Streamlit.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ─── DDL ─────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS daily_capital (
    run_date          DATE         PRIMARY KEY,
    rwa_credit        NUMERIC(22,2),
    rwa_ccr           NUMERIC(22,2),
    rwa_market        NUMERIC(22,2),
    rwa_cva           NUMERIC(22,2),
    rwa_ccp           NUMERIC(22,2),
    rwa_operational   NUMERIC(22,2),
    rwa_total         NUMERIC(22,2),
    rwa_floor         NUMERIC(22,2),
    floor_triggered   BOOLEAN,
    cet1_capital      NUMERIC(22,2),
    tier1_capital     NUMERIC(22,2),
    total_capital     NUMERIC(22,2),
    cet1_ratio        NUMERIC(10,6),
    tier1_ratio       NUMERIC(10,6),
    total_cap_ratio   NUMERIC(10,6),
    cva_method        VARCHAR(20),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    run_date          DATE,
    portfolio_id      VARCHAR(50),
    portfolio_type    VARCHAR(20),      -- DERIVATIVE | BANKING_BOOK
    counterparty      VARCHAR(100),
    trade_count       INTEGER,
    gross_notional    NUMERIC(22,2),
    ead               NUMERIC(22,2),
    rwa               NUMERIC(22,2),
    mtm_net           NUMERIC(22,2),
    rc                NUMERIC(22,2),    -- replacement cost (derivatives)
    pfe_mult          NUMERIC(8,5),     -- PFE multiplier  (derivatives)
    addon_agg         NUMERIC(22,2),    -- total add-on    (derivatives)
    total_el          NUMERIC(22,2),    -- expected loss   (banking book)
    el_shortfall      NUMERIC(22,2),    -- EL vs provisions
    avg_risk_weight   NUMERIC(8,4),
    PRIMARY KEY (run_date, portfolio_id)
);

CREATE TABLE IF NOT EXISTS trade_mtm_history (
    run_date          DATE,
    portfolio_id      VARCHAR(50),
    trade_id          VARCHAR(80),
    asset_class       VARCHAR(10),
    instrument_type   VARCHAR(40),
    notional          NUMERIC(22,2),
    direction         SMALLINT,
    mtm               NUMERIC(22,2),
    ead               NUMERIC(22,2),    -- banking book only
    pd_applied        NUMERIC(10,6),    -- banking book only
    lgd_applied       NUMERIC(8,4),     -- banking book only
    rwa               NUMERIC(22,2),
    PRIMARY KEY (run_date, trade_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_date  ON daily_capital (run_date);
CREATE INDEX IF NOT EXISTS idx_ps_date  ON portfolio_snapshots (run_date);
CREATE INDEX IF NOT EXISTS idx_ps_type  ON portfolio_snapshots (portfolio_type, run_date);
CREATE INDEX IF NOT EXISTS idx_tmh_pid  ON trade_mtm_history (portfolio_id, run_date);
"""

# ─── Connection helper ────────────────────────────────────────────────────────

def _get_conn():
    """Return a raw psycopg2 connection using config.DB_CONFIG."""
    try:
        import psycopg2
        from backend.config import DB_CONFIG
        return psycopg2.connect(**DB_CONFIG)
    except ImportError:
        raise RuntimeError("psycopg2 not installed. Run: pip install psycopg2-binary")
    except Exception as e:
        raise RuntimeError(f"DB connection failed: {e}")


def ensure_schema() -> bool:
    """
    Create all tables and indexes if they don't exist. Safe to call every run.
    Returns True if successful, False if DB unavailable.
    """
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                for stmt in _DDL.strip().split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        cur.execute(stmt)
        conn.close()
        logger.info("DB schema verified / created")
        return True
    except Exception as e:
        logger.warning("DB unavailable — snapshots will not be persisted: %s", e)
        return False


# ─── Writers ─────────────────────────────────────────────────────────────────

def write_daily_capital(run_date: date, cap: Dict[str, Any]) -> bool:
    """Upsert one row into daily_capital."""
    sql = """
    INSERT INTO daily_capital
        (run_date, rwa_credit, rwa_ccr, rwa_market, rwa_cva, rwa_ccp,
         rwa_operational, rwa_total, rwa_floor, floor_triggered,
         cet1_capital, tier1_capital, total_capital,
         cet1_ratio, tier1_ratio, total_cap_ratio, cva_method)
    VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (run_date) DO UPDATE SET
        rwa_credit=EXCLUDED.rwa_credit, rwa_ccr=EXCLUDED.rwa_ccr,
        rwa_market=EXCLUDED.rwa_market, rwa_cva=EXCLUDED.rwa_cva,
        rwa_ccp=EXCLUDED.rwa_ccp, rwa_operational=EXCLUDED.rwa_operational,
        rwa_total=EXCLUDED.rwa_total, rwa_floor=EXCLUDED.rwa_floor,
        floor_triggered=EXCLUDED.floor_triggered,
        cet1_capital=EXCLUDED.cet1_capital, tier1_capital=EXCLUDED.tier1_capital,
        total_capital=EXCLUDED.total_capital,
        cet1_ratio=EXCLUDED.cet1_ratio, tier1_ratio=EXCLUDED.tier1_ratio,
        total_cap_ratio=EXCLUDED.total_cap_ratio, cva_method=EXCLUDED.cva_method
    """
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    run_date,
                    cap.get("rwa_credit", 0), cap.get("rwa_ccr", 0),
                    cap.get("rwa_market", 0), cap.get("rwa_cva", 0),
                    cap.get("rwa_ccp", 0), cap.get("rwa_operational", 0),
                    cap.get("rwa_total", 0), cap.get("rwa_floor", 0),
                    cap.get("floor_triggered", False),
                    cap.get("cet1_capital", 0), cap.get("tier1_capital", 0),
                    cap.get("total_capital", 0),
                    cap.get("cet1_ratio", 0), cap.get("tier1_ratio", 0),
                    cap.get("total_cap_ratio", 0), cap.get("cva_method", ""),
                ))
        conn.close()
        logger.debug("Wrote daily_capital for %s", run_date)
        return True
    except Exception as e:
        logger.warning("Failed to write daily_capital: %s", e)
        return False


def write_portfolio_snapshots(run_date: date, results: Dict) -> bool:
    """Upsert portfolio-level snapshots for derivative and banking book."""
    rows = []

    for p in results.get("derivative", []):
        s = p.get("saccr", {})
        imm = p.get("imm") or {}
        rows.append((
            run_date, p["portfolio_id"], "DERIVATIVE",
            p.get("counterparty", ""), p.get("trade_count", 0),
            p.get("gross_notional", 0),
            s.get("ead", 0),
            p.get("rwa_ccr", 0) + p.get("rwa_market", 0),
            imm.get("net_mtm", 0) if imm else sum(
                t.get("current_mtm", 0) for t in p.get("trades", [])),
            s.get("rc", 0), s.get("pfe_mult", 0), s.get("addon_agg", 0),
            None, None, None,
        ))

    for p in results.get("banking_book", []):
        total_ead = p.get("total_ead", 0)
        avg_rw    = p.get("avg_risk_weight", 0)
        rows.append((
            run_date, p["portfolio_id"], "BANKING_BOOK",
            p.get("counterparty", ""), p.get("exposure_count", 0),
            total_ead,
            total_ead,           # EAD = notional for banking book
            p.get("total_rwa", 0),
            None,                # no net MTM for banking book
            None, None, None,
            p.get("total_el", 0), p.get("el_shortfall", 0), avg_rw,
        ))

    if not rows:
        return True

    sql = """
    INSERT INTO portfolio_snapshots
        (run_date, portfolio_id, portfolio_type, counterparty, trade_count,
         gross_notional, ead, rwa, mtm_net, rc, pfe_mult, addon_agg,
         total_el, el_shortfall, avg_risk_weight)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (run_date, portfolio_id) DO UPDATE SET
        ead=EXCLUDED.ead, rwa=EXCLUDED.rwa, mtm_net=EXCLUDED.mtm_net,
        rc=EXCLUDED.rc, pfe_mult=EXCLUDED.pfe_mult, addon_agg=EXCLUDED.addon_agg,
        total_el=EXCLUDED.total_el, el_shortfall=EXCLUDED.el_shortfall,
        avg_risk_weight=EXCLUDED.avg_risk_weight
    """
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        conn.close()
        logger.debug("Wrote %d portfolio_snapshots for %s", len(rows), run_date)
        return True
    except Exception as e:
        logger.warning("Failed to write portfolio_snapshots: %s", e)
        return False


def write_trade_mtm_history(run_date: date, results: Dict) -> bool:
    """Upsert trade-level MTM and risk metrics into trade_mtm_history."""
    rows = []

    for p in results.get("derivative", []):
        pid = p["portfolio_id"]
        for t in p.get("trades", []):
            rows.append((
                run_date, pid,
                getattr(t, "trade_id", ""),
                getattr(t, "asset_class", ""),
                getattr(t, "instrument_type", ""),
                getattr(t, "notional", 0),
                getattr(t, "direction", 1),
                getattr(t, "current_mtm", 0),
                None, None, None,    # EAD/PD/LGD not applicable for derivatives
                None,
            ))

    for p in results.get("banking_book", []):
        pid = p["portfolio_id"]
        for t in p.get("airb_trades", []):
            rows.append((
                run_date, pid,
                t.get("trade_id", ""),
                "BANKING",
                "LOAN",
                t.get("ead", 0),
                1,
                None,
                t.get("ead", 0),
                t.get("pd", 0),
                t.get("lgd", 0),
                t.get("rwa", 0),
            ))

    if not rows:
        return True

    sql = """
    INSERT INTO trade_mtm_history
        (run_date, portfolio_id, trade_id, asset_class, instrument_type,
         notional, direction, mtm, ead, pd_applied, lgd_applied, rwa)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (run_date, trade_id) DO UPDATE SET
        mtm=EXCLUDED.mtm, ead=EXCLUDED.ead, rwa=EXCLUDED.rwa,
        pd_applied=EXCLUDED.pd_applied, lgd_applied=EXCLUDED.lgd_applied
    """
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        conn.close()
        logger.debug("Wrote %d trade_mtm_history rows for %s", len(rows), run_date)
        return True
    except Exception as e:
        logger.warning("Failed to write trade_mtm_history: %s", e)
        return False


def persist_run(run_date: date, results: Dict) -> bool:
    """
    Convenience: write all three tables in one call.
    Call this at the end of PrometheusRunner.run_daily().
    Returns True if all writes succeeded, False if any failed (run still continues).
    """
    ok  = write_daily_capital(run_date, results.get("capital_summary", {}))
    ok &= write_portfolio_snapshots(run_date, results)
    ok &= write_trade_mtm_history(run_date, results)
    if ok:
        logger.info("All snapshots persisted for %s", run_date)
    return ok


# ─── Readers (return pandas DataFrames for Streamlit) ─────────────────────────

def _read_df(sql: str, params=None):
    """Execute a SELECT and return a pandas DataFrame. Returns empty DF on error."""
    try:
        import pandas as pd
        conn = _get_conn()
        df = pd.read_sql(sql, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        logger.warning("DB read failed: %s", e)
        import pandas as pd
        return pd.DataFrame()


def read_capital_history(days: int = 90):
    """Last `days` rows of daily_capital, newest first."""
    return _read_df(
        "SELECT * FROM daily_capital ORDER BY run_date DESC LIMIT %s",
        (days,),
    )


def read_rwa_by_month(years: int = 2):
    """Month-end RWA aggregated by year and month."""
    return _read_df("""
        SELECT
            EXTRACT(YEAR  FROM run_date)::int AS year,
            EXTRACT(MONTH FROM run_date)::int AS month,
            MAX(run_date)                      AS month_end,
            AVG(rwa_total)                     AS avg_rwa_total,
            MAX(rwa_total)                     AS max_rwa_total,
            AVG(cet1_ratio)                    AS avg_cet1_ratio
        FROM daily_capital
        WHERE run_date >= CURRENT_DATE - INTERVAL '%s years'
        GROUP BY 1, 2
        ORDER BY 1 DESC, 2 DESC
    """, (years,))


def read_portfolio_trend(portfolio_id: str, days: int = 90):
    """EAD and RWA trend for a single portfolio."""
    return _read_df("""
        SELECT run_date, ead, rwa, mtm_net, rc, pfe_mult, addon_agg
        FROM portfolio_snapshots
        WHERE portfolio_id = %s
        ORDER BY run_date DESC
        LIMIT %s
    """, (portfolio_id, days))


def read_rwa_by_year():
    """Annual RWA summary for all available years."""
    return _read_df("""
        SELECT
            EXTRACT(YEAR FROM run_date)::int AS year,
            COUNT(*)                          AS trading_days,
            AVG(rwa_total)  AS avg_rwa_total,
            MIN(rwa_total)  AS min_rwa_total,
            MAX(rwa_total)  AS max_rwa_total,
            AVG(cet1_ratio) AS avg_cet1_ratio,
            MIN(cet1_ratio) AS min_cet1_ratio
        FROM daily_capital
        GROUP BY 1
        ORDER BY 1 DESC
    """)


def read_mtm_history_for_portfolio(portfolio_id: str, days: int = 30):
    """Trade-level MTM history for a portfolio over the past `days` days."""
    return _read_df("""
        SELECT h.run_date, h.trade_id, h.asset_class, h.instrument_type,
               h.notional, h.direction, h.mtm, h.rwa
        FROM trade_mtm_history h
        WHERE h.portfolio_id = %s
          AND h.run_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY h.run_date DESC, h.asset_class
    """, (portfolio_id, days))
