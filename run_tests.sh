#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PROMETHEUS — Run the full model validation test suite
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
echo "Running 48 model validation tests..."
echo ""
python3 -m pytest tests/test_engines.py -v --tb=short
