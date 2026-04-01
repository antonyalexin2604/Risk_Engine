#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PROMETHEUS — Setup script for MacBook Air M1
# Expected location: /Users/aaron/Documents/Project/Prometheus/setup.sh
# Run with:  bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

# ── Resolve project root (wherever this script lives) ────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║        PROMETHEUS Risk Platform — M1 Setup               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Project root : $PROJECT_ROOT"
echo ""

# ── 0. Confirm we are in the right place ─────────────────────────────────────
if [[ ! -f "$PROJECT_ROOT/requirements.txt" ]]; then
  echo "✗  Cannot find requirements.txt in $PROJECT_ROOT"
  echo "   Make sure you unzipped into the correct folder and run from there."
  exit 1
fi

# ── 1. Architecture check ─────────────────────────────────────────────────────
ARCH=$(uname -m)
echo "▶ Architecture : $ARCH"
if [[ "$ARCH" == "arm64" ]]; then
  echo "  ✓ Apple Silicon (M1) detected — native arm64 mode"
else
  echo "  ⚠  Not arm64 — proceeding, but Docker image may need Rosetta"
fi

# ── 2. Docker check ───────────────────────────────────────────────────────────
echo ""
echo "▶ Checking Docker..."
if ! command -v docker &>/dev/null; then
  echo "  ✗ Docker not found."
  echo ""
  echo "  Install Docker Desktop for Apple Silicon:"
  echo "  https://www.docker.com/products/docker-desktop/"
  echo ""
  echo "  Then re-run:  bash $SCRIPT_DIR/setup.sh"
  exit 1
fi
if ! docker info &>/dev/null 2>&1; then
  echo "  ✗ Docker is installed but not running."
  echo "  Open Docker Desktop from your Applications folder,"
  echo "  wait for the whale icon to stop animating, then re-run."
  exit 1
fi
echo "  ✓ Docker is running"

# ── 3. Python check ───────────────────────────────────────────────────────────
echo ""
echo "▶ Checking Python..."
PYTHON=""
for cmd in python3.11 python3.12 python3.10 python3; do
  if command -v "$cmd" &>/dev/null; then
    VER=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
    MAJOR=$(echo "$VER" | cut -d. -f1)
    MINOR=$(echo "$VER" | cut -d. -f2)
    if [[ "$MAJOR" -ge 3 && "$MINOR" -ge 9 ]]; then
      PYTHON="$cmd"
      echo "  ✓ Using $cmd  (version $VER)"
      break
    fi
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "  ✗ Python 3.9+ not found."
  echo "  Install with:  brew install python@3.11"
  exit 1
fi

# ── 4. pip / dependencies ─────────────────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies..."
cd "$PROJECT_ROOT"
"$PYTHON" -m pip install -r requirements.txt --quiet --upgrade
echo "  ✓ All dependencies installed"

# ── 5. Start database ─────────────────────────────────────────────────────────
echo ""
echo "▶ Starting PostgreSQL + pgAdmin (Docker)..."
cd "$PROJECT_ROOT/docker"
docker-compose up -d
cd "$PROJECT_ROOT"

echo "  Waiting for PostgreSQL to accept connections..."
READY=0
for i in $(seq 1 45); do
  if docker exec prometheus_db pg_isready -U risk_admin -d prometheus_risk &>/dev/null 2>&1; then
    echo "  ✓ PostgreSQL ready  (took ${i}s)"
    READY=1
    break
  fi
  printf "."
  sleep 1
done
echo ""
if [[ $READY -eq 0 ]]; then
  echo "  ⚠  PostgreSQL not ready after 45s."
  echo "  Check logs with:  docker logs prometheus_db"
  echo "  You can continue — the risk engine doesn't require the DB for the smoke test."
fi

# ── 6. Smoke test — risk engine ───────────────────────────────────────────────
echo ""
echo "▶ Running smoke test (risk engine)..."
"$PYTHON" -c "
import sys, os
sys.path.insert(0, '$PROJECT_ROOT')
from backend.main import PrometheusRunner
from datetime import date
runner = PrometheusRunner(sa_cva_approved=True)
results = runner.run_daily(date.today())
cap = results['capital_summary']
assert cap['rwa_total'] > 0
assert cap['rwa_cva'] >= 0
assert cap['rwa_ccp'] > 0
print(f'  CET1 Ratio : {cap[\"cet1_ratio\"]:.2%}')
print(f'  Total RWA  : \${cap[\"rwa_total\"]:>14,.0f}')
print(f'  Credit RWA : \${cap[\"rwa_credit\"]:>14,.0f}')
print(f'  CCR RWA    : \${cap[\"rwa_ccr\"]:>14,.0f}')
print(f'  Market RWA : \${cap[\"rwa_market\"]:>14,.0f}')
print(f'  CVA RWA    : \${cap[\"rwa_cva\"]:>14,.0f}  [{cap[\"cva_method\"]}]')
print(f'  CCP RWA    : \${cap[\"rwa_ccp\"]:>14,.0f}')
print(f'  Floor      : {\"triggered\" if cap[\"floor_triggered\"] else \"not triggered\"}')
" && echo "  ✓ Smoke test passed" || { echo "  ✗ Smoke test failed — see output above"; exit 1; }

# ── 7. Model validation tests ────────────────────────────────────────────────
echo ""
echo "▶ Running 48 model validation tests..."
"$PYTHON" -m pytest "$PROJECT_ROOT/tests/test_engines.py" -v --tb=short 2>&1 | tail -8
echo ""

# ── 8. Write launch scripts ──────────────────────────────────────────────────
echo "▶ Writing launch scripts..."

cat > "$PROJECT_ROOT/run_dashboard.sh" << DASH_EOF
#!/usr/bin/env bash
# Launch the PROMETHEUS dashboard
PROJECT_ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$PROJECT_ROOT"
echo "Opening dashboard at http://localhost:8501"
python3 -m streamlit run dashboard/app.py
DASH_EOF
chmod +x "$PROJECT_ROOT/run_dashboard.sh"

cat > "$PROJECT_ROOT/run_engine.sh" << ENGINE_EOF
#!/usr/bin/env bash
# Run the daily risk engine from the command line
PROJECT_ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "\$PROJECT_ROOT"
python3 -c "
import sys; sys.path.insert(0, '.')
from backend.main import PrometheusRunner
from datetime import date
runner = PrometheusRunner(sa_cva_approved=True)
results = runner.run_daily(date.today())
cap = results['capital_summary']
print()
print('Five-Part RWA  (USD)')
print(f'  (1) Credit  : {\$cap[\"rwa_credit\"]:>14,.0f}')
print(f'  (2) CCR     : {\$cap[\"rwa_ccr\"]:>14,.0f}')
print(f'  (3) Market  : {\$cap[\"rwa_market\"]:>14,.0f}')
print(f'  (4) CVA     : {\$cap[\"rwa_cva\"]:>14,.0f}')
print(f'  (5) CCP     : {\$cap[\"rwa_ccp\"]:>14,.0f}')
print(f'  TOTAL       : {\$cap[\"rwa_total\"]:>14,.0f}')
print(f'  CET1 Ratio  : {cap[\"cet1_ratio\"]:.2%}')
"
ENGINE_EOF
chmod +x "$PROJECT_ROOT/run_engine.sh"

echo "  ✓ run_dashboard.sh created"
echo "  ✓ run_engine.sh created"

# ── 9. Done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅  Setup Complete!                                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Launch dashboard:"
echo "    bash $PROJECT_ROOT/run_dashboard.sh"
echo "  — or —"
echo "    cd $PROJECT_ROOT && streamlit run dashboard/app.py"
echo ""
echo "  Dashboard URL  :  http://localhost:8501"
echo ""
echo "  DBeaver connection:"
echo "    Host     : localhost"
echo "    Port     : 5432"
echo "    Database : prometheus_risk"
echo "    User     : risk_admin"
echo "    Password : P@ssw0rd_Risk2024"
echo ""
echo "  pgAdmin  :  http://localhost:5050"
echo "    Email   :  admin@prometheus.risk"
echo "    Password:  Admin@2024"
echo ""
