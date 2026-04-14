# 🔱 PROMETHEUS — Basel III/IV Risk Management Platform

> A production-grade Credit & Market Risk engine implementing **SA-CCR, IMM, A-IRB, FRTB,
> CVA, and CCP** simultaneously — with a zero-jargon dashboard for Risk Control teams.
> Built to run on a **MacBook Air M1 (8 GB RAM)**.

---

## Regulatory Basis

| Engine | Standard | Scope |
|--------|----------|-------|
| SA-CCR | CRE52 | Derivative EAD — all trades |
| IMM / Monte Carlo | CRE53 | EPE/EEPE for eligible trades |
| A-IRB | CRE30–36 | Banking Book RWA |
| FRTB SBM + IMA | MAR20–33 | Market Risk capital |
| CVA (BA-CVA / SA-CVA) | MAR50 | CVA Risk RWA |
| CCP | CRE54 | Cleared derivative exposure |
| Capital | RBC20–25 | Five-part RWA + output floor |
| Margins | MGN | CSA / IM / VM / MTA |

---

## Five-Part RWA Formula (RBC20.9)

```
Total RWA = RWA_Credit(A-IRB)
          + RWA_CCR(SA-CCR / IMM)
          + RWA_Market(FRTB)
          + RWA_CVA(BA-CVA / SA-CVA)      ← MAR50
          + RWA_CCP(CRE54)                ← CRE54
          + RWA_OpRisk(OPE25 stub)

Output floor (RBC20.11) = max(Total, 72.5% × SA-based RWA)
Note: CVA RWA excluded from floor base (CAP10 FAQ1)
```

---

## Quick Start — MacBook Air M1

### Your project location
```
/Users/aaron/Documents/Project/Prometheus/
```

### Prerequisites (one-time, if not already installed)

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Docker Desktop for Apple Silicon
brew install --cask docker
# → Open Docker Desktop from Applications and wait for it to start

# Python 3.11 (if not installed)
brew install python@3.11
```

### Step 1 — Unzip to your project folder

```bash
# If you downloaded the zip:
cd /Users/aaron/Documents/Project
unzip PROMETHEUS_v1.zip
# Files land in:  /Users/aaron/Documents/Project/Prometheus/
```

### Step 2 — One-shot setup

```bash
cd /Users/aaron/Documents/Project/Prometheus
bash setup.sh
```

This single command:
- Checks Docker and Python
- Installs all Python dependencies
- Starts PostgreSQL + pgAdmin in Docker
- Runs the risk engine smoke test
- Runs all 48 validation tests
- Prints DBeaver and pgAdmin connection strings

### Step 3 — Launch the dashboard

```bash
bash /Users/aaron/Documents/Project/Prometheus/run_dashboard.sh
```

Opens at **http://localhost:8501**

### Step 4 — Run the risk engine (CLI)

```bash
bash /Users/aaron/Documents/Project/Prometheus/run_engine.sh
```

### Step 5 — Run tests

```bash
bash /Users/aaron/Documents/Project/Prometheus/run_tests.sh
```

Expected: **48/48 passed**

### Step 6 — Connect DBeaver

New Connection → PostgreSQL:
| Field | Value |
|-------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `prometheus_risk` |
| User | `risk_admin` |
| Password | `P@ssw0rd_Risk2024` |

pgAdmin is at **http://localhost:5050**
- Email: `admin@prometheus.risk` · Password: `Admin@2024`

---

## Project Structure

```
PROMETHEUS/
│
├── docker/
│   ├── docker-compose.yml      PostgreSQL 15 (arm64) + pgAdmin 4
│   └── init.sql                17 tables · 4 schemas · 8 risk limits
│
├── backend/
│   ├── config.py               All regulatory parameters
│   ├── main.py                 Daily risk orchestrator (5-part RWA)
│   │
│   ├── engines/
│   │   ├── sa_ccr.py           CRE52 — RC + PFE + 5 asset class add-ons
│   │   ├── imm.py              CRE53 — GBM + Hull-White MC (2,000 scenarios)
│   │   ├── a_irb.py            CRE31 — PD/LGD/M/R/K formula
│   │   ├── frtb.py             MAR21-33 — SBM + IMA + backtesting
│   │   ├── cva.py              MAR50 — BA-CVA / SA-CVA + fallback trace
│   │   └── ccp.py              CRE54 — QCCP 2% RW + DFC charge
│   │
│   └── data_generators/
│       ├── portfolio_generator.py   DRV-YYYY-NNN / BBK-YYYY-NNN portfolios
│       └── cva_generator.py         CVA inputs + CCP cleared positions
│
├── dashboard/
│   └── app.py                  Streamlit — 8 pages, xlsx/csv download
│
├── tests/
│   └── test_engines.py         48 model validation tests (all passing)
│
├── requirements.txt
└── README.md
```

---

## Regulatory Functional Requirements — Coverage

| Requirement | Status | Engine / File |
|-------------|--------|---------------|
| Credit Risk — SA-CCR | ✅ | `engines/sa_ccr.py` (CRE52) |
| Credit Risk — IMM | ✅ | `engines/imm.py` (CRE53) |
| SA-CCR / IMM fallback trace | ✅ | `sa_ccr.py` + `main.py` |
| Banking Book — A-IRB only | ✅ | `engines/a_irb.py` (CRE31) |
| Market Risk — FRTB | ✅ | `engines/frtb.py` (MAR21-33) |
| CVA — BA-CVA + SA-CVA + trace | ✅ | `engines/cva.py` (MAR50) |
| CCP exposure | ✅ | `engines/ccp.py` (CRE54) |
| Derivative portfolios ≥5 trades | ✅ | `portfolio_generator.py` |
| Banking Book portfolios ≥5 exp. | ✅ | `portfolio_generator.py` |
| CSA — IM, VM, Threshold, MTA | ✅ | `sa_ccr.py` NettingSet |
| CDS mitigants + double-default | ✅ | `a_irb.py` (CRE22) |
| Portfolio ID day-on-day | ✅ | `DRV-YYYY-NNN / BBK-YYYY-NNN` |
| Five-part RWA + output floor | ✅ | `main.py` (RBC20) |
| Risk limits + breach monitor | ✅ | Dashboard + `init.sql` |
| Backtesting MAR99 traffic-light | ✅ | `engines/frtb.py` |
| Downloadable reports xlsx/csv | ✅ | Dashboard Reports page |
| Operational Risk (extensible) | 🔲 | `config.py` flag, Sprint E |
| IMA PLA gate (MAR32) | 🔲 | Sprint B (next session) |

---

## System Requirements (M1 MacBook Air 8 GB)

| Component | Spec | Notes |
|-----------|------|-------|
| Python | 3.11+ | arm64 native |
| PostgreSQL | 15 (Docker) | ~200 MB RAM |
| Monte Carlo | 2,000 × 52 steps | ~40 MB RAM |
| Dashboard | Streamlit | ~150 MB RAM |
| Total footprint | ~500 MB RAM | Well within 8 GB |

---

## Next Sprints

| Sprint | What | Standard |
|--------|------|----------|
| **B** | IMA Eligibility Gate — PLA Test (Spearman + KS) | MAR32 |
| **C** | Extended test suite — CVA, CCP, Capital (75+ tests) | — |
| **D** | Dashboard: CVA page, CCP page, IMA PLA page | — |
| **E** | Operational Risk stub — OPE25 | OPE25 |
| **F** | Full documentation + LinkedIn package | — |

---

*PROMETHEUS · Basel III/IV · MacBook Air M1 · Python 3.11 · PostgreSQL 15*
