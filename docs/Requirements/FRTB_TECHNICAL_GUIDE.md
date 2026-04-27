# FRTB Technical Guide
## Fundamental Review of the Trading Book (MAR10 / MAR21–23 / MAR31–33)
### PROMETHEUS Risk Platform
**Last Updated:** Version 3.8 — Apr-27-2026  
**Key Changes (v3.8):** Fix 5a — corrected liquidity horizon table (MAR33.12); Fix 5b — IMACapitalRegister 60-day rolling IMCC (MAR33.5)

---
## Table of Contents
1. Overview & Regulatory Basis
2. FRTB Architecture
3. Sensitivities-Based Method (SBM)
4. Internal Models Approach (IMA)
5. Market Risk Capital
6. Key Bug Fixes Applied
7. Glossary
**Appendix A** — Delta Charge: IR Bond Position (GIRR)
**Appendix B** — Equity Option: Delta + Vega + Curvature
**Appendix C** — IMA Expected Shortfall Numeric Example
**Appendix D** — NMRF Charge
**Appendix E** — Backtesting Traffic Light
---
## 1. Overview & Regulatory Basis
FRTB replaces the 1996 Basel II VaR approach for market risk. It establishes a clearer trading/banking book boundary, a more risk-sensitive standardised method (SBM), and a rigorous internal model framework (IMA).
| Basel Section | Topic |
|---|---|
| MAR10 | Scope: trading book boundary |
| MAR21 | SBM — Delta charge |
| MAR22 | SBM — Vega charge |
| MAR23 | SBM — Curvature charge |
| MAR31 | IMA — Expected Shortfall, NMRF |
| MAR32 | IMA — Backtesting |
| MAR33 | IMA — P&L attribution, capital floor |
| MAR99 | Backtesting traffic-light examples |
---
## 2. FRTB Architecture
```
Trading Book Positions
    │
    ├── SBM (always computed)
    │    ├── Delta charge  (RW × WS → bucket → cross-bucket)
    │    ├── Vega charge   (same structure)
    │    └── Curvature charge (CVR± stress scenarios)
    │
    ├── IMA (if approved)
    │    ├── Expected Shortfall (ES 97.5%, stressed period)
    │    ├── NMRF stress scenarios (SSRM per factor)
    │    └── Backtesting (250-day window)
    │
    └── Capital = max(SBM, IMA) × 12.5 → Market Risk RWA
```
---
## 3. Sensitivities-Based Method (SBM)
### 3.1 Delta Charge
**Weighted Sensitivity:**
```
WS_ik = RW_k × s_ik
```
**Bucket aggregation (three-scenario framework, MAR21.6 — FIX-01):**
```
K_b = sqrt(max(Σ WS_k² + Σ_{k≠l} ρ_kl × WS_k × WS_l, 0))
```
Three correlation scenarios — highest K_b is used:
| Scenario | ρ_high | ρ_low |
|---|---|---|
| Base | ρ | ρ |
| High (stressed) | ρ + 0.25 × (1 − ρ) | max(2ρ − 1, 0) |
| Low | ρ × 0.75 | ρ × 0.75 |
**FIX-01:** Original used `abs()` on ρ_high and wrong ρ_low formula (0.5625×ρ). Corrected to Basel MAR21.6 formulas.
**Cross-bucket:**
```
Delta_charge = sqrt(Σ K_b² + Σ_{b≠c} γ_bc × K_b × K_c)
```
**GIRR Risk Weights (10 tenors, MAR21.44 — FIX-04):**
| Tenor | RW |
|---|---|
| 3M | 1.7% |
| 6M | 1.6% |
| 1Y | 1.6% |
| 2Y | 1.3% |
| 3Y | 1.2% |
| 5Y | 1.1% |
| 10Y | 1.1% |
| 15Y | 1.2% |
| 20Y | 1.3% |
| 30Y | 1.5% |
FIX-04: Table trimmed from 13 to correct 10 entries.
### 3.2 Vega Charge
Same structure as delta; sensitivities are option vega (∂V/∂σ) per vol tenor bucket.
### 3.3 Curvature Charge (FIX-02)
```
CVR⁺_k = −[V(x_k + RW_k × x_k) − V(x_k) − RW_k × x_k × delta_k]
CVR⁻_k = −[V(x_k − RW_k × x_k) − V(x_k) + RW_k × x_k × delta_k]
Ξ_b = max(Σ CVR_k² + Σ_{k≠l} ρ_kl² × CVR_k × CVR_l, 0)
K_curv_b = max(Ξ⁺_b, Ξ⁻_b)
```
**FIX-02:** Original applied `sqrt(Ξ_b)`. Ξ_b is already in capital dollar units — applying sqrt was dimensionally wrong and understated curvature capital.
**FIX-03:** Removed non-existent "MAR21.100 SBM floor." The three-scenario framework itself limits diversification; no additional floor exists in Basel.
---
## 4. Internal Models Approach (IMA)
### 4.1 Expected Shortfall (MAR33.8 — FIX-05)
```
ES(97.5%) = E[Loss | Loss > VaR(97.5%)]
tail_count = math.ceil(0.025 × n_scenarios)   ← FIX-05 (was int(), now ceil())
ES = mean of the tail_count worst P&L observations
```
For 250 scenarios: `ceil(0.025 × 250) = ceil(6.25) = 7` worst days averaged.
**Liquidity Horizons (Fix 5a — MAR33.12 Table 1, Version 3.8):**

| Risk Class | Key | LH | Bucket | Version 3.8 Change |
|---|---|---|---|---|
| GIRR, FX major, large-cap EQ | `GIRR`, `FX`, `EQ_LARGE_CAP` | 10 days | j=1 | Unchanged |
| Large-cap EQ (non-specified), liquid commodities | `EQ_LARGE`, `CMDTY_ENERGY` | 20 days | j=2 | Unchanged |
| Small-cap EQ, other FX, other commodities | `EQ`, `FX_OTHER`, `CMDTY` | 40 days | j=3 | Unchanged |
| **IG credit spread (non-sec, CTP)** | **`CSR_NS_IG`, `CSR_CTP_IG`** | **60 days** | j=4 | **New key added** |
| **Non-IG credit spread, all securitisation** | **`CSR_NS`, `CSR_SEC`** | **120 days** | j=5 | **Was 40d / 60d — corrected** |

`CSR_NS` corrected: **40 → 120 days** (non-IG credit is the j=5 bucket per MAR33.12).  
`CSR_SEC` corrected: **60 → 120 days** (non-IG securitisation is j=5, not j=4).  
`CSR_NS_IG` added at 60 days for investment-grade credit spread non-securitisation.  
Unknown risk classes default conservatively to **120 days**.
### 4.2 Non-Modellable Risk Factors (NMRF — MAR31.14, FIX-07)
Risk factors with < 24 price observations/year are NMRF. Capital = SSRM (Stressed Scenario Risk Measure) per factor, bank-estimated.
**FIX-07:** Default of 0.0015 (15bp flat proxy) removed. No MAR31 basis. Callers must supply `factor_ssrm` explicitly.
### 4.3 Backtesting Traffic Light (MAR32/MAR99)
250-day window; compare actual P&L to VaR(99%,1-day):
| Exceptions | Zone | Capital Multiplier k |
|---|---|---|
| 0–4 | Green | 1.50 |
| 5 | Yellow | 1.70 |
| 6 | Yellow | 1.76 |
| 7 | Yellow | 1.83 |
| 8 | Yellow | 1.88 |
| 9 | Yellow | 1.92 |
| 10+ | Red | 2.00 (revert to SBM) |
---
## 5. Market Risk Capital

### 5.1 IMA Capital Formula — 60-Day Rolling IMCC (Fix 5b, Version 3.8 / MAR33.5)

MAR33.5 requires IMA capital to be the **maximum of today's ES and the 60-business-day average
multiplied by the scaling factor mc**:

```
IMCC_t = max(ES_today, mc_t × ES_60d_avg)
```

where `mc_t = 1.5 + backtesting_addon` (floor 1.5; amber-zone add-on per MAR32.9 table).

**`IMACapitalRegister`** (new class in `backend/engines/frtb.py`, Version 3.8):
- Maintains a 60-business-day rolling deque of daily ES values
- `regulatory_imcc(es_today)` returns `max(ES_today, mc × avg_60d)` and the binding reason
- `to_dict()` / `from_dict()` for PostgreSQL persistence across daily runs
- `set_exceptions(n)` wires the amber-zone add-on from the backtesting module

| Backtesting exceptions (12m) | Zone | Add-on | mc |
|---|---|---|---|
| 0–4 | Green | 0.00 | **1.50** |
| 5 | Amber | 0.40 | 1.90 |
| 6 | Amber | 0.50 | 2.00 |
| 7 | Amber | 0.65 | 2.15 |
| 8 | Amber | 0.75 | 2.25 |
| 9 | Amber | 0.85 | 2.35 |
| 10+ | Red | — | IMA disallowed |

`FRTBEngine` now carries `self.ima_register = IMACapitalRegister()` initialised at startup.

### 5.2 Overall Market Risk Capital

```
IMA_capital = (IMCC + NMRF_charge) × 12.5        ← IMCC replaces k × ES (Fix 5b)
SBM_capital = SBM_total × 12.5
Market Risk RWA = max(IMA_capital, SBM_capital)
```
---
## 6. Key Bug Fixes Applied
| Fix | Severity | Impact |
|---|---|---|
| FIX-01 | HIGH | Three-scenario ρ_high/ρ_low corrected (MAR21.6) |
| FIX-02 | HIGH | Curvature Ξ_b: removed erroneous sqrt() (MAR23.6) |
| FIX-03 | MEDIUM | Removed non-existent MAR21.100 SBM floor |
| FIX-04 | MEDIUM | GIRR RW table: 13 → 10 correct tenors (MAR21.44) |
| FIX-05 | MEDIUM | ES tail count: ceil() not int() (MAR33.8) |
| FIX-06 | MEDIUM | CSR_SEC and CSR_CTP risk weights added (MAR21.73) |
| FIX-07 | LOW | NMRF default charge removed (MAR31.14) |
| FIX-08 | LOW | Duplicate docstring in FRTBEngine.compute() merged |
| FIX-09 | LOW | Shock application: additive not multiplicative |
| FIX-10 | LOW | Correlation config in try/finally |
| FIX-11 | LOW | GIRR inter-bucket scalar limitation documented |
| FIX-12 | LOW | Commodity bucket assignment documented |
| **FIX-5a** | **HIGH** | **CSR_NS LH corrected 40→120d; CSR_SEC 60→120d; CSR_NS_IG added @60d (MAR33.12 Table 1)** |
| **FIX-5b** | **MEDIUM** | **IMACapitalRegister: 60-day rolling IMCC = max(ES_today, mc×ES_avg); mc floor 1.5 (MAR33.5)** |

---
## 7. Glossary
| Term | Definition |
|---|---|
| SBM | Sensitivities-Based Method |
| IMA | Internal Models Approach |
| ES | Expected Shortfall (97.5% confidence) |
| NMRF | Non-Modellable Risk Factor |
| SSRM | Stressed Scenario Risk Measure |
| GIRR | General Interest Rate Risk |
| CSR | Credit Spread Risk |
| CVR | Curvature Risk (CVR+ and CVR−) |
| WS | Weighted Sensitivity = RW × sensitivity |
| k | Backtesting capital multiplier (1.50–2.00) |
---
## Appendix A — Delta Charge: IR Bond (GIRR)
**Setup:** Long $10M 5-year USD Treasury. Duration ≈ 4.5Y. Sensitivity to 5Y point: +$450,000.
```
WS_5Y = RW_5Y × s_5Y = 0.011 × 450,000 = $4,950
K_b (single bucket) = $4,950
Delta_GIRR = $4,950
RWA = 4,950 × 12.5 = $61,875
```
---
## Appendix B — Equity Option: Delta + Vega + Curvature
**Setup:** Long AAPL call options. Bucket 5 (Large Cap Developed), RW = 30%.
| Sensitivity | Value |
|---|---|
| Delta | +$500,000 |
| Vega | +$150,000 |
```
WS_delta = 0.30 × 500,000 = $150,000
WS_vega  = 0.30 × 150,000 = $45,000
Curvature: Long options → positive gamma → CVR typically ≤ 0 → K_curv = 0
Total SBM = 150,000 + 45,000 + 0 = $195,000
RWA = 195,000 × 12.5 = $2,437,500
```
---
## Appendix C — IMA Expected Shortfall
**Setup:** 250 scenarios. Seven worst losses (USD):
| Rank | Loss |
|---|---|
| 1 | $5,200,000 |
| 2 | $4,800,000 |
| 3 | $4,200,000 |
| 4 | $3,800,000 |
| 5 | $3,500,000 |
| 6 | $3,100,000 |
| 7 | $2,900,000 |
```
tail_count = ceil(0.025 × 250) = 7   (FIX-05; was int() → 6)
ES = (5,200,000 + 4,800,000 + 4,200,000 + 3,800,000 + 3,500,000 + 3,100,000 + 2,900,000) / 7
   = 27,500,000 / 7
   = $3,928,571
```
---
## Appendix D — NMRF Charge
**Setup:** Private credit position; issuer has no CDS; only 12 dealer quotes/year → NMRF.
```
SSRM = Bank-estimated stressed loss from March 2020 scenario = $850,000
NMRF_capital = $850,000
NMRF_RWA     = $10,625,000
```
Old flat proxy (FIX-07 removed): 0.0015 × $20M = $30,000 → **understated by 97%**.
---
## Appendix E — Backtesting Traffic Light
8 exceptions in 250 days → Yellow zone, k = 1.88.
```
IMA_capital = 1.88 × ES × 12.5
At 10 exceptions → Red zone → revert to SBM (regulatory floor)
```
P&L Attribution (MAR33): Hypothetical P&L must be sufficiently correlated with Risk-Theoretical P&L. Failure → IMA ineligible → SBM applies.
