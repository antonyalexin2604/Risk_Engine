#!/usr/bin/env python3
"""
PROMETHEUS — Historical Backfill
Run this once to populate the last 90 days of snapshots into PostgreSQL,
so the dashboard's trend charts and Year/Month/Date aggregation tables
render immediately on first launch.

Usage:
    cd /Users/aaron/Documents/Project/Prometheus
    .venv/bin/python backfill_history.py

Options (edit DAYS_BACK to change window):
    DAYS_BACK = 90   →  ~90 seconds on M1 (one run per calendar day)
    DAYS_BACK = 30   →  ~30 seconds (safe for a quick demo)

Runs in calendar-day order (oldest first) so the DB is coherent if
interrupted — just re-run and ON CONFLICT DO UPDATE handles duplicates.
Skips weekends by default (financial risk runs are business-day only).
"""

import sys
import os
import logging
import time
from datetime import date, timedelta

# Ensure the project root is on the path
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
# Keep Prometheus engine quiet during backfill
for name in ["prometheus", "backend", "engines", "imm", "frtb", "cva"]:
    logging.getLogger(name).setLevel(logging.ERROR)

from backend.main import PrometheusRunner
from backend.data_sources.persistence import ensure_schema, persist_run

# ─── Configuration ────────────────────────────────────────────────────────────
DAYS_BACK       = 90          # how many calendar days to backfill
SKIP_WEEKENDS   = True        # skip Saturday / Sunday
BATCH_PAUSE_SEC = 0.0         # optional pause between runs (0 = fastest)
# ─────────────────────────────────────────────────────────────────────────────

def is_business_day(d: date) -> bool:
    return d.weekday() < 5  # Mon=0 … Fri=4


def main():
    print(f"{'='*62}")
    print(f"  PROMETHEUS Historical Backfill — last {DAYS_BACK} days")
    print(f"  Skip weekends: {SKIP_WEEKENDS}")
    print(f"{'='*62}")

    if not ensure_schema():
        print("  ERROR: Cannot connect to PostgreSQL.")
        print("  Make sure Docker is running:  docker ps | grep prometheus")
        sys.exit(1)

    runner  = PrometheusRunner(sa_cva_approved=True)
    today   = date.today()

    dates_to_run = [
        today - timedelta(days=i)
        for i in range(DAYS_BACK, -1, -1)   # oldest first
    ]
    if SKIP_WEEKENDS:
        dates_to_run = [d for d in dates_to_run if is_business_day(d)]

    n      = len(dates_to_run)
    done   = 0
    errors = 0
    t_start = time.time()

    for run_date in dates_to_run:
        try:
            result = runner.run_daily(run_date)

            # Attach trade objects so persistence can read MTM
            dataset = result.get("_dataset_ref")
            if not dataset:
                # Re-generate to attach trades (already computed, fast re-run)
                from backend.data_generators.portfolio_generator import build_full_dataset
                dataset = build_full_dataset(book_date=run_date)
            for p_data, p_src in zip(result["derivative"], dataset["derivative_portfolios"]):
                p_data["trades"] = p_src["trades"]

            ok = persist_run(run_date, result)
            done += 1
            elapsed = time.time() - t_start
            eta = (elapsed / done) * (n - done) if done > 0 else 0
            status = "✓" if ok else "⚠ DB write partial"
            print(
                f"  {run_date.isoformat()}  {status}  "
                f"RWA={result['capital_summary']['rwa_total']/1e9:.3f}B  "
                f"CET1={result['capital_summary']['cet1_ratio']*100:.2f}%  "
                f"[{done}/{n}  ETA {int(eta)}s]"
            )
        except Exception as e:
            errors += 1
            print(f"  {run_date.isoformat()}  ERROR: {e}")

        if BATCH_PAUSE_SEC:
            time.sleep(BATCH_PAUSE_SEC)

    total_time = time.time() - t_start
    print(f"\n{'='*62}")
    print(f"  Backfill complete: {done} days written, {errors} errors")
    print(f"  Total time: {total_time:.1f}s  ({total_time/n:.2f}s per day)")
    print(f"{'='*62}")
    print(f"\n  Launch the dashboard and navigate to Capital Dashboard")
    print(f"  to see the 90-day trend charts and Year/Month tables.")


if __name__ == "__main__":
    main()
