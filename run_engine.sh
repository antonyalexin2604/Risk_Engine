#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PROMETHEUS — Run the daily risk engine (CLI)
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

DATE_ARG="${1:-today}"
echo "  Running risk engine for: $DATE_ARG"
echo ""

python3 - << PYEOF
import sys, os
sys.path.insert(0, "$PROJECT_ROOT")
from backend.main import PrometheusRunner
from datetime import date

runner = PrometheusRunner(sa_cva_approved=True)
results = runner.run_daily(date.today())
cap = results["capital_summary"]
cva = results["cva"]
ccp = results["ccp"]

print()
print("=" * 60)
print("  PROMETHEUS — Daily Risk Run")
print("=" * 60)
print(f"  CET1 {cap['cet1_ratio']:.2%}  |  T1 {cap['tier1_ratio']:.2%}  |  Total {cap['total_cap_ratio']:.2%}")
print()
print(f"  {'Component':<22} {'RWA (USD)':>16}   Standard")
print(f"  {'─'*50}")
print(f"  (1) Credit  (A-IRB)  {cap['rwa_credit']:>16,.0f}   CRE30-36")
print(f"  (2) CCR     (SA-CCR) {cap['rwa_ccr']:>16,.0f}   CRE51-53")
print(f"  (3) Market  (FRTB)   {cap['rwa_market']:>16,.0f}   MAR20-33")
print(f"  (4) CVA     [{cap['cva_method']:6s}] {cap['rwa_cva']:>16,.0f}   MAR50")
print(f"  (5) CCP     (CRE54)  {cap['rwa_ccp']:>16,.0f}   CRE54")
print(f"  (6) OpRisk  (stub)   {cap['rwa_operational']:>16,.0f}   OPE25")
print(f"  {'─'*50}")
print(f"  TOTAL RWA            {cap['rwa_total']:>16,.0f}  {'(floor applied)' if cap['floor_triggered'] else ''}")
print()
print(f"  CVA: SA={cva['by_method'].get('SA_CVA',0):,.0f}  BA={cva['by_method'].get('BA_CVA',0):,.0f}  Fallbacks={cva['fallback_count']}")
for pos in ccp['positions']:
    q = 'QCCP' if pos['is_qualifying'] else 'Non-QCCP'
    print(f"  {pos['ccp_name']:<22} [{q}] RWA \${pos['rwa_total']:>12,.0f}")
print()
print(f"  Backtesting : {results['backtesting']['traffic_light']}")
print("=" * 60)
PYEOF
