#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PROMETHEUS — Launch the Streamlit dashboard
# Run from anywhere:  bash /Users/aaron/Documents/Project/Prometheus/run_dashboard.sh
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
echo "  Project : $PROJECT_ROOT"
echo "  Opening : http://localhost:8501"
echo "  Stop    : Ctrl+C"
echo ""
python3 -m streamlit run dashboard/app.py \
  --server.port 8501 \
  --server.headless false \
  --browser.gatherUsageStats false
