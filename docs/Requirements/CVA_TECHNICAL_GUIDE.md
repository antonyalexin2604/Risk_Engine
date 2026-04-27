# CVA Risk Capital — Technical Guide
## Credit Valuation Adjustment (MAR50)
### PROMETHEUS Risk Platform

---

## Table of Contents

1. Overview & Regulatory Basis
2. What Is CVA and Why Does It Generate Capital?
3. CVA Capital Approaches — Overview
4. Materiality Threshold (MAR50.9)
5. BA-CVA — Basic Approach (MAR50.14–38)
6. SA-CVA — Standardised Approach (MAR50.40–77)
7. CVA Engine — Method Routing and Fallback Logic
8. Proxy Spread Cascade (MAR50.32(3))
9. Wrong-Way Risk (MAR50.32)
10. Live Market Data Integration
11. Key Regulatory Fixes Applied (FIX-01 through FIX-09)
12. Data Structures Reference
13. Glossary

**Appendix A** — Numeric Walk-Through: BA-CVA (Reduced, No Hedges)
**Appendix B** — Numeric Walk-Through: BA-CVA (Full, With Hedges)
**Appendix C** — Numeric Walk-Through: SA-CVA with Sector Buckets
**Appendix D** — Wrong-Way Risk: CDS on Financials
**Appendix E** — Cross-Method Comparison Portfolio

---

## 1. Overview & Regulatory Basis

CVA (Credit Valuation Adjustment) is the market value of **counterparty credit risk** embedded in a derivative portfolio. It represents the expected loss from counterparty default, accounting for the future value of trades at the time of default.

**CVA Capital** (distinct from CVA Value) captures the risk that CVA itself will change due to movements in credit spreads, rates, FX, equity, and other market risk factors. It is a **market risk charge** sitting in the Market Risk RWA bucket, not the Credit Risk bucket.

| Basel Section | Topic |
|---|---|
| MAR50.9 | Materiality threshold (EUR 100bn notional) |
| MAR50.14 | BA-CVA reduced version |
| MAR50.20–21 | BA-CVA full version with hedges |
| MAR50.29 | Supervisory rho = 0.50 (fixed) |
| MAR50.32 | Wrong-way risk; proxy spread for illiquid counterparties |
| MAR50.40–77 | SA-CVA sensitivities-based approach |
| MAR50.43 | SA-CVA six delta risk classes |
| MAR50.45–49 | SA-CVA five vega risk classes |
| MAR50.63–65 | Sector buckets (Table 5) and risk weights (Table 7) |
| RBC20.9(2) | CVA RWA feeds total RWA as distinct Market Risk line item |
| CAP10 FAQ1 | CVA RWA excluded from SA output floor base |

---

## 2. What Is CVA and Why Does It Generate Capital?

### CVA Value

CVA is the risk-neutral expected loss from counterparty default:

```
CVA ≈ LGD × Integral[0→T] {PD(t) × EE(t) × DF(t) dt}

where:
  LGD  = Loss Given Default (market-implied from CDS recovery)
  PD(t) = Risk-neutral default probability at time t (from CDS spread)
  EE(t) = Expected Exposure at time t (from IMM or SA-CCR)
  DF(t) = Risk-free discount factor
```

### Why Capital is Required

CVA itself is an asset (a valuation adjustment) that fluctuates with:
- **Credit spread changes** — if counterparty spreads widen, CVA increases (more expected loss)
- **Exposure changes** — if rates/FX/equity move, EE changes, so CVA changes
- **Correlation between spread and exposure** (wrong-way risk)

The **2007–2009 crisis** showed that ~2/3 of credit losses from counterparty credit risk came from CVA mark-to-market movements, not actual defaults. Basel III responded by mandating CVA capital.

---

## 3. CVA Capital Approaches — Overview

```
Portfolio of non-cleared derivatives
           │
           ▼
    MAR50.9: Materiality check
    ├── Below EUR 100bn notional → 100% of CCR RWA as proxy
    └── Above EUR 100bn notional → compute CVA capital
                │
                ├── SA-CVA approved + live CDS spreads?
                │    └── SA-CVA (MAR50.40-77)
                │
                └── Otherwise → BA-CVA (MAR50.14–38)
                     ├── Reduced (no hedges) — MAR50.14
                     └── Full (with hedges) — MAR50.20–21
```

| Approach | When Available | Benefit |
|---|---|---|
| **SA Output Floor (CCR proxy)** | Below EUR 100bn notional | Simplest — no CVA model needed |
| **BA-CVA Reduced** | Always available | Simple EAD-based; no hedge recognition |
| **BA-CVA Full** | Always (if hedges present) | Reduces capital by recognising eligible CVA hedges |
| **SA-CVA** | Supervisory approval + live spreads | Lowest capital for well-hedged portfolios |

---

## 4. Materiality Threshold (MAR50.9)

**FIX-04:** The original code used USD 1M CCR RWA as the threshold — wrong by four orders of magnitude. The correct threshold is:

```
Threshold: Aggregate non-centrally-cleared derivative NOTIONAL ≤ EUR 100 billion

If notional ≤ EUR 100bn → CVA RWA = 100% of CCR RWA (proxy)
If notional >  EUR 100bn → must compute BA-CVA or SA-CVA
```

For most G-SIBs, the notional far exceeds EUR 100bn. The threshold mainly relieves small regional banks from running CVA models.

---

## 5. BA-CVA — Basic Approach (MAR50.14–38)

### Core Concept

BA-CVA estimates CVA capital from the **EAD** of each counterparty (not from sensitivity to market risk factors). It uses:
- **Supervisory credit spreads** (rating-based, from MAR50 Table 1)
- **Supervisory correlation** ρ = 0.50 (fixed, not market-implied)
- **Effective maturity discount** for time value

### Stand-Alone CVA Capital: SC_c (MAR50.15)

```
SC_c = RW_c × M_c_eff × EAD_c

where:
  RW_c     = Supervisory spread for counterparty's rating (see table below)
  EAD_c    = EAD from SA-CCR or IMM (with WWR add-on if applicable)
  M_c_eff  = (1 − exp(−r × M_c)) / (r × M_c)   [effective maturity discount]
  r        = OIS/SOFR rate
  M_c      = Effective maturity of the netting set (years)
```

**Supervisory spread by rating (MAR50 Table 1):**

| Rating | Supervisory Spread (bps) |
|---|---|
| AAA | 38 |
| AA | 38 |
| A | 42 |
| BBB | 54 |
| BB | 106 |
| B | 160 |
| CCC | 600 |
| NR (unrated) | 54 (BBB equivalent) |

### Reduced BA-CVA (MAR50.14) — No Hedge Recognition

```
K_reduced = sqrt(ρ² × (Σ SC_c)² + (1 − ρ²) × Σ SC_c²)
          where ρ = 0.50 (supervisory)

Capital   = DS × K_reduced × 12.5   [DS = 0.65 per MAR50.14]
```

**FIX-01:** The original code was missing the **DS = 0.65 discount scalar**. This overstated BA-CVA capital by ~54% (1/0.65 = 1.54×). DS was introduced in the 2019 FRTB reforms as a calibration offset.

### Full BA-CVA (MAR50.20–21) — With Hedges

```
SNH_c  = ρ_hc × RW_h × DF_h × Notional_h    [single-name hedge, MAR50.23]
IH     = 0.7 × Σ RW_index × DF_index × N_index  [index hedge, MAR50.24]

Systematic  = Σ SC_c − Σ SNH_c − IH
Idiosyncratic = Σ (SC_c − SNH_c)²

K_full  = sqrt(ρ² × Systematic² + (1−ρ²) × Idiosyncratic) + Σ sqrt(HMA_c)
HMA_c   = (1 − ρ_hc²) × (RW_h × DF_h × N_h)²   [hedge misalignment, MAR50.25]

Capital = DS × max(K_full, β × K_reduced) × 12.5   [β = 0.25 floor, MAR50.20]
```

**FIX-02:** The original hedge reduction formula `(0.50 × notional × spread)` had no MAR50 basis. The correct SNH/IH/HMA structure with supervisory hedge correlations (ρ_hc) is now implemented.

**Supervisory hedge correlations (MAR50 Table 2):**

| Hedge Type | ρ_hc |
|---|---|
| References counterparty directly | 100% |
| Legally related (parent/subsidiary) | 80% |
| Same sector and region | 50% |

---

## 6. SA-CVA — Standardised Approach (MAR50.40–77)

SA-CVA requires supervisory approval and live CDS spread data per counterparty.

### Six Delta Risk Classes (MAR50.43)

| Risk Class | Sensitivity | Example |
|---|---|---|
| Interest Rate (GIRR) | ∂CVA/∂r per tenor | IRS counterparties |
| FX | ∂CVA/∂FX_spot | Cross-currency swap counterparties |
| Counterparty Credit Spread | ∂CVA/∂s_counterparty | All OTC derivative counterparties |
| Reference Credit Spread | ∂CVA/∂s_reference | Protection seller on third-party CDS |
| Equity | ∂CVA/∂S_equity | Equity TRS/option counterparties |
| Commodity | ∂CVA/∂C_commodity | Commodity swap counterparties |

### SA-CVA Delta Charge (Counterparty Credit Spread — implemented)

```
delta_sens    = EAD_eff × M_eff × LGD

RW_spread     = Risk weight from MAR50.65 Table 7 (by sector bucket + IG/HY)

delta_charge  = RW_spread × delta_sens

Net weighted sensitivity (with hedge, MAR50.52–53):
  ws_hedge    = (1 − R) × ρ_hc × RW_spread × N_hedge × M_eff_hedge × LGD
  ws_net      = max(delta_charge − ws_hedge, 0)
  R = 0.01 (hedging disallowance parameter per MAR50.53)

rwa_delta     = ws_net × 12.5
```

**FIX-05:** Original code selected RW by `pd_1yr < 0.02` (IG/HY split by PD threshold) — no MAR50 basis. The correct approach uses the **8-bucket sector structure** (Table 5 → Table 7):

**SA-CVA Risk Weights (MAR50.65 Table 7):**

| Bucket | Sector | IG RW | HY/NR RW |
|---|---|---|---|
| 1 | Sovereign / Muni | 0.5% | 2.0% |
| 2 | Financials | 1.0% | 4.0% |
| 3 | Industrials / Energy | 3.0% | 7.0% |
| 4 | Consumer | 3.0% | 8.5% |
| 5 | Technology / Telecom | 2.0% | 5.5% |
| 6 | Healthcare / Utilities | 1.5% | 5.0% |
| 7 | Other | 5.0% | 12.0% |
| 8 | Qualified Index | 1.5% | 5.0% |

### Five Vega Risk Classes (MAR50.45, MAR50.48)

**FIX-06:** MAR50.48 states vega must **always** be computed — it is not optional even for non-option portfolios. Vega arises from the volatility parameters (σ) in the exposure simulation model (Hull-White σ_r for IRS, Black-Scholes σ_eq for equity derivatives).

| Vega Risk Class | Description |
|---|---|
| GIRR Vega | ∂CVA/∂σ_IR (swaption vol surface) |
| FX Vega | ∂CVA/∂σ_FX (FX option vol) |
| Reference Credit Spread Vega | ∂CVA/∂σ_spread (CDS options) |
| Equity Vega | ∂CVA/∂σ_equity (equity option vol) |
| Commodity Vega | ∂CVA/∂σ_commodity |

Note: **No counterparty credit spread vega** per MAR50.45 (CCSR is not a vega risk class).

---

## 7. CVA Engine — Method Routing and Fallback Logic

### Routing Decision Tree

```python
compute_portfolio_cva(inputs, total_ccr_rwa, total_notional_eur=...)

Step 1: Materiality check (MAR50.9)
        if total_notional_eur ≤ 100bn EUR:
            return CCR_PROXY (cva_rwa = total_ccr_rwa)

Step 2: Enrich missing spreads (_enrich_missing_spreads)
        for each counterparty without credit_spread_bps:
            Tier 1: sector/credit_quality/region peer lookup
            Tier 2: live IG/HY market index spread

Step 3: Eligibility check per counterparty
        SA-CVA eligible if:
            sa_cva_approved = True
            credit_spread_bps is not None
            spread_source = 'LIVE'  (proxy spreads → BA-CVA)

Step 4: Route to SA-CVA or BA-CVA

Step 5: Record fallback trace codes for all BA-CVA counterparties
```

### Fallback Trace Codes

| Code | Reason | Action |
|---|---|---|
| `NO_SA_APPROVAL` | SA-CVA not approved by supervisor | Apply for approval; document model |
| `MISSING_SPREADS` | No CDS spread data | Engage credit desk for proxy spreads |
| `BELOW_THRESHOLD` | Notional ≤ EUR 100bn | CCR proxy applied — simpler calculation |
| `HEDGES_INELIGIBLE` | CVA hedges don't meet MAR50 eligibility | Review hedge documentation |
| `MODEL_LIMITATION` | Trade type not validated in CVA model | Extend model or apply BA-CVA |

---

## 8. Proxy Spread Cascade (MAR50.32(3))

For illiquid counterparties without traded CDS, banks must estimate credit spreads:

```
Tier 1: Sector / credit_quality / region peer lookup
        → estimate_proxy_spread(sector, credit_quality, region)
        → Must be calibrated to liquid CDS peers monthly

Tier 2: Live market index spread
        → IG counterparty → CDX IG (FRED BAMLC0A0CM)
        → HY/NR counterparty → CDX HY (FRED BAMLH0A0HYM2)
```

**MAR50.40 compliance:** Proxy spreads (spread_source ≠ 'LIVE') are **not eligible** for SA-CVA. They route to BA-CVA. SA-CVA requires observable market credit spreads.

**Audit trail:** Every CVAResult carries `spread_source` field:
- `LIVE` — direct CDS market data
- `PROXY_SECTOR` — from peer lookup table
- `PROXY_INDEX_IG` — from CDX IG index
- `PROXY_INDEX_HY` — from CDX HY index

---

## 9. Wrong-Way Risk (MAR50.32)

Wrong-Way Risk (WWR) occurs when the counterparty is most likely to default **exactly when the exposure is largest** — a positive correlation between PD and EE.

**Classic example:** Bank buys CDS protection from a bank counterparty. If credit spreads widen (indicating stress), the CDS gains value (EE increases) AND the counterparty's PD increases. The bank is exposed to losing its hedge precisely when it needs it most.

### WWR in PROMETHEUS

```python
# CVAInput fields
is_wrong_way: bool  = False    # Flags WWR counterparty
wwr_add_on:   float = 0.0      # Conservative EAD uplift (% of EAD)

# Applied in both BA-CVA and SA-CVA
ead_eff = ead * (1.0 + wwr_add_on) if is_wrong_way else ead
```

Basel allows discretion in WWR modelling (MAR50.32). The Prometheus implementation uses a conservative flat add-on. Production should implement correlation-based modelling between exposure paths and default intensity.

---

## 10. Live Market Data Integration

### CVAMarketDataFeed

Fetches live market data from FRED (no API key required):

| Series | Parameter | FRED Code |
|---|---|---|
| SOFR (risk-free rate) | `risk_free_rate` | `SOFR` |
| IG OAS spread | `credit_spread_ig` | `BAMLC0A0CM` |
| HY OAS spread | `credit_spread_hy` | `BAMLH0A0HYM2` |
| VIX index | `vix_level` | `VIXCLS` (or yfinance) |

### Supervisory vs Stress ρ

**FIX-03:** The original code scaled ρ from 0.50 to 0.80 based on VIX. Basel MAR50.14(2) is explicit: **ρ = 0.50 is a fixed supervisory parameter**. It cannot be dynamically adjusted.

| ρ Function | Use Case | Value |
|---|---|---|
| `supervisory_rho()` | Regulatory capital (BA-CVA, SA-CVA) | Always 0.50 |
| `stress_rho()` | Pillar 2 ICAAP / internal stress testing | 0.50–0.80 (VIX-driven) |

---

## 11. Key Regulatory Fixes Applied

| Fix | Severity | Regulation | Description | Capital Impact |
|---|---|---|---|---|
| **FIX-01** | HIGH | MAR50.14 | DS=0.65 added to BA-CVA | Was overstating by ~54% |
| **FIX-02** | HIGH | MAR50.21 | BA-CVA hedge reduction rewritten (SNH/IH/HMA) | Correct hedge recognition |
| **FIX-03** | HIGH | MAR50.29 | supervisory_rho() = 0.50 (fixed, not VIX-scaled) | Correct regulatory rho |
| **FIX-04** | MEDIUM | MAR50.9 | Threshold: EUR 100bn notional (not USD 1M CCR RWA) | ~4 orders of magnitude correction |
| **FIX-05** | MEDIUM | MAR50.65 | SA-CVA RW by sector bucket (8-bucket, not PD threshold) | Correct RW selection |
| **FIX-06** | MEDIUM | MAR50.48 | Vega always computed (not optional) | Ensures completeness |
| **FIX-07** | MEDIUM | MAR50.15 | Multi-netting-set support per counterparty | Accuracy for complex counterparties |
| **FIX-08** | LOW | MAR50.32 | WWR flag and EAD add-on added | Explicit WWR treatment |
| **FIX-09** | LOW | MAR50.32 | Proxy spread function with sector/rating/region | MAR50.32(3) compliance |

---

## 12. Data Structures Reference

### CVAInput

| Field | Description |
|---|---|
| `counterparty_id` | Unique counterparty identifier |
| `ead` | Exposure At Default from SA-CCR or IMM |
| `pd_1yr` | 1-year probability of default |
| `lgd_mkt` | Market-implied LGD (overridden by sector recovery if market provided) |
| `maturity_years` | Effective maturity of netting set |
| `credit_spread_bps` | Live CDS spread (bps); None = proxy required |
| `sector` | Sector for SA-CVA bucket routing (Table 5) |
| `credit_quality` | 'IG' / 'HY' / 'NR' — for SA-CVA RW selection (Table 7) |
| `has_cva_hedge` | True if a CVA hedge is in place |
| `hedge_type` | 'DIRECT' / 'LEGALLY_RELATED' / 'SAME_SECTOR' |
| `is_wrong_way` | True if exposure correlates positively with PD |
| `wwr_add_on` | Conservative EAD uplift for WWR (fraction of EAD) |
| `netting_sets` | List of `NettingSetEAD` for multi-netting-set counterparties |
| `spread_source` | 'LIVE' / 'PROXY_SECTOR' / 'PROXY_INDEX_IG' / 'PROXY_INDEX_HY' |

### CVAResult

| Field | Description |
|---|---|
| `method` | 'SA_CVA' / 'BA_CVA' / 'CCR_PROXY' |
| `fallback_trace` | Trace code explaining why BA-CVA was applied |
| `rwa_cva` | Total CVA RWA for this counterparty |
| `ba_sc_charge` | BA-CVA stand-alone charge SC_c |
| `sa_delta_charge` | SA-CVA delta charge (counterparty credit spread) |
| `sa_vega_charge` | SA-CVA vega charge |
| `cva_estimate` | CVA value estimate (PD × LGD × EAD × M_eff) |
| `spread_source` | Provenance of credit spread used |

---

## 13. Glossary

| Term | Definition |
|---|---|
| **CVA** | Credit Valuation Adjustment — market value of counterparty default risk |
| **BA-CVA** | Basic Approach — EAD-based, always available |
| **SA-CVA** | Standardised Approach — sensitivity-based, requires approval |
| **DS** | Discount Scalar = 0.65 (MAR50.20) — calibration factor for BA-CVA |
| **β** | Beta = 0.25 (MAR50.20) — floor on hedged BA-CVA vs. unhedged |
| **ρ** | Supervisory correlation parameter = 0.50 (MAR50.29) |
| **SC_c** | Stand-alone CVA capital for counterparty c |
| **SNH_c** | Single-name hedge benefit for counterparty c |
| **IH** | Index hedge aggregate benefit |
| **HMA_c** | Hedge misalignment adjustment for indirect hedges |
| **EE(t)** | Expected Exposure at time t |
| **EAD** | Exposure at Default (point-in-time measure) |
| **LGD** | Loss Given Default (market-implied from CDS recovery) |
| **WWR** | Wrong-Way Risk — positive correlation between PD and exposure |
| **GIRR** | General Interest Rate Risk |
| **CCSR** | Counterparty Credit Spread Risk |
| **RCSR** | Reference Credit Spread Risk |

---

## Appendix A — Numeric Walk-Through: BA-CVA Reduced (No Hedges)

### Portfolio Setup

A bank has three OTC derivative counterparties (all above EUR 100bn threshold):

| Counterparty | Rating | EAD | Maturity | Sector |
|---|---|---|---|---|
| Bank A (Financial) | A | $50,000,000 | 3.0 years | Financials |
| Corp B (Industrial) | BBB | $30,000,000 | 5.0 years | Industrials |
| Corp C (Energy) | BB | $20,000,000 | 2.0 years | Energy |

**Market Conditions:** SOFR = 4.3%, ρ = 0.50 (supervisory), DS = 0.65

---

### Step 1: Supervisory Spreads from Rating

| Counterparty | Rating | RW_c |
|---|---|---|
| Bank A | A | 0.42% = 0.0042 |
| Corp B | BBB | 0.54% = 0.0054 |
| Corp C | BB | 1.06% = 0.0106 |

---

### Step 2: Effective Maturity Discount M_eff

Formula: `M_eff = (1 − exp(−r × M)) / (r × M)` where r = 4.3% = 0.043

**Bank A (M = 3.0 years):**
```
M_eff_A = (1 − exp(−0.043 × 3.0)) / (0.043 × 3.0)
        = (1 − exp(−0.129)) / 0.129
        = (1 − 0.8790) / 0.129
        = 0.1210 / 0.129
        = 0.9380
```

**Corp B (M = 5.0 years):**
```
M_eff_B = (1 − exp(−0.043 × 5.0)) / (0.043 × 5.0)
        = (1 − exp(−0.215)) / 0.215
        = (1 − 0.8066) / 0.215
        = 0.1934 / 0.215
        = 0.8995
```

**Corp C (M = 2.0 years):**
```
M_eff_C = (1 − exp(−0.043 × 2.0)) / (0.043 × 2.0)
        = (1 − exp(−0.086)) / 0.086
        = (1 − 0.9176) / 0.086
        = 0.0824 / 0.086
        = 0.9581
```

---

### Step 3: Stand-Alone CVA Capital SC_c

```
SC_A = RW_A × M_eff_A × EAD_A
     = 0.0042 × 0.9380 × 50,000,000
     = $197,000 (approx.)

SC_B = 0.0054 × 0.8995 × 30,000,000
     = $145,700 (approx.)

SC_C = 0.0106 × 0.9581 × 20,000,000
     = $203,100 (approx.)
```

---

### Step 4: K_reduced Aggregation

```
Σ SC_c   = 197,000 + 145,700 + 203,100 = $545,800
Σ SC_c²  = 197,000² + 145,700² + 203,100²
         = 38,809,000,000 + 21,228,490,000 + 41,249,610,000
         = 101,287,100,000

K_reduced = sqrt(ρ² × (Σ SC)² + (1−ρ²) × Σ SC²)
          = sqrt(0.50² × 545,800² + (1−0.25) × 101,287,100,000)
          = sqrt(0.25 × 297,898,240,000 + 0.75 × 101,287,100,000)
          = sqrt(74,474,560,000 + 75,965,325,000)
          = sqrt(150,439,885,000)
          = $387,860
```

---

### Step 5: Final Capital and RWA

```
Capital  = DS × K_reduced × 12.5
         = 0.65 × 387,860 × 12.5
         = $3,151,113

RWA_CVA  = DS × K_reduced × 12.5 = $3,151,113
  (note: CVA capital = CVA RWA since the 12.5 factor IS already the RWA conversion)
```

**Attribution:**

| Counterparty | SC_c | Share | RWA |
|---|---|---|---|
| Bank A | $197,000 | 36.1% | $1,137,555 |
| Corp B | $145,700 | 26.7% | $841,148 |
| Corp C | $203,100 | 37.2% | $1,172,410 |
| **Total** | **$545,800** | **100%** | **$3,151,113** |

---

### What the Numbers Mean

- Corp C (BB-rated Energy) drives 37% of CVA capital despite only 20% of EAD — because its spread (1.06%) is 2.5× higher than Bank A's (0.42%).
- Without DS=0.65, capital would be $4,847,866 — **54% higher**. This is why FIX-01 was critical.

---

## Appendix B — Numeric Walk-Through: BA-CVA Full (With CDS Hedge)

### Extending the Appendix A Portfolio

The bank buys a 3-year CDS on Corp C (BB-rated Energy) with:
- Notional: $20,000,000
- Hedge type: DIRECT (references Corp C exactly)
- CDS spread: 110 bps
- Maturity: 3.0 years (maturity mismatch vs 2.0-year exposure)

### SNH_C Calculation (MAR50.23)

```
ρ_hc      = 1.00 (DIRECT hedge)
RW_h      = 0.0106 (BB rating, same as Corp C)
M_h_eff   = (1 − exp(−0.043 × 3.0)) / (0.043 × 3.0) = 0.9380

SNH_C = ρ_hc × RW_h × M_h_eff × N_hedge
      = 1.00 × 0.0106 × 0.9380 × 20,000,000
      = $198,748
```

### HMA_C (Hedge Misalignment Adjustment, MAR50.25)

Since hedge is DIRECT (ρ_hc = 1.00):
```
HMA_C = (1 − ρ_hc²) × (RW_h × M_h_eff × N_h)²
      = (1 − 1.0²) × ...
      = 0   (perfect correlation → no misalignment)
```

### K_full (MAR50.21)

```
Systematic  = Σ SC_c − Σ SNH_c − IH
            = 545,800 − 198,748 − 0
            = $347,052

Idiosyncratic = Σ (SC_c − SNH_c)²
              = (197,000 − 0)² + (145,700 − 0)² + (203,100 − 198,748)²
              = 38,809,000,000 + 21,228,490,000 + 18,932,336
              = 60,056,422,336

K_full = sqrt(0.25 × 347,052² + 0.75 × 60,056,422,336) + 0
       = sqrt(0.25 × 120,445,078,704 + 45,042,316,752)
       = sqrt(30,111,269,676 + 45,042,316,752)
       = sqrt(75,153,586,428)
       = $274,142
```

### Beta Floor Check (MAR50.20)

```
β × K_reduced = 0.25 × 387,860 = $96,965
K_full        = $274,142

K_hedged = max(K_full, β × K_reduced) = max(274,142, 96,965) = $274,142
Capital  = DS × K_hedged × 12.5 = 0.65 × 274,142 × 12.5 = $2,227,528
```

**Capital saving from hedge:** $3,151,113 − $2,227,528 = **$923,585 (29% reduction)**

---

## Appendix C — Numeric Walk-Through: SA-CVA

### Setup

Bank A (Financials, IG, live CDS spread = 85 bps), no hedge, 3Y maturity, EAD = $50M, SOFR = 4.3%.

**SA-CVA eligible:** SA-CVA approved, spread_source = 'LIVE'.

### Bucket and Risk Weight

```
Sector = "Financials" → Bucket 2
Credit Quality = "IG"
RW_spread (MAR50.65 Table 7, Bucket 2 IG) = 1.0% = 0.010
```

### Delta Sensitivity

```
spread   = 85 bps / 10000 = 0.0085
M_eff    = (1 − exp(−0.043 × 3)) / (0.043 × 3) = 0.9380
LGD      = 1 − recovery_Financials = 1 − 0.40 = 0.60

delta_sens = EAD × M_eff × LGD
           = 50,000,000 × 0.9380 × 0.60
           = $28,140,000

delta_charge = RW_spread × delta_sens
             = 0.010 × 28,140,000
             = $281,400

rwa_delta = delta_charge × 12.5 = $3,517,500
```

### Comparison: BA-CVA vs SA-CVA for Bank A

| Approach | Capital | RWA |
|---|---|---|
| BA-CVA (share of $3.15M) | $1,137,555 | $1,137,555 |
| SA-CVA | $3,517,500 | $3,517,500 |

SA-CVA is **higher** here because the 1.0% RW_spread (Financials IG) × LGD effect is larger than the BA-CVA supervisory spread (0.42%). SA-CVA benefits most from hedge recognition and when actual spreads are narrow relative to supervisory proxies.

---

## Appendix D — Wrong-Way Risk: CDS on Financials

### Setup

Bank buys $30M CDS protection from a financial counterparty on an index.
- `is_wrong_way = True` (protection seller faces same stress as CDS market)
- `wwr_add_on = 0.25` (25% EAD uplift as conservative proxy)

### WWR Impact

```
EAD_base = $30,000,000
EAD_eff  = EAD_base × (1 + wwr_add_on) = 30M × 1.25 = $37,500,000

SC_c (with WWR) = RW × M_eff × EAD_eff
               = 0.0042 × 0.9380 × 37,500,000
               = $147,807   (vs $118,245 without WWR, +25%)
```

**CRO Note:** WWR is often underestimated in stress. A 25% add-on is conservative but reasonable for financial sector counterparties selling credit protection during market stress events. Production should model correlation between counterparty default intensity and trade mark-to-market.

---

## Appendix E — Cross-Method Portfolio Comparison

| Scenario | Method | Capital | Notes |
|---|---|---|---|
| Below EUR 100bn notional | CCR Proxy | = CCR RWA | Simplest; threshold bank |
| Above threshold, no SA approval | BA-CVA Reduced | $3,151,113 | Appendix A result |
| BA-CVA with direct hedge on Corp C | BA-CVA Full | $2,227,528 | Appendix B result |
| Bank A via SA-CVA only | SA-CVA | $3,517,500 | Appendix C |
| Financials CPY with WWR | BA-CVA + WWR | +25% add-on | Appendix D |

**Key insight for the CRO:** BA-CVA with well-structured direct hedges can be more capital-efficient than SA-CVA for portfolios where counterparty spreads are high relative to supervisory proxies. SA-CVA earns its advantage primarily when the bank has tight, well-hedged credit positions in IG sectors (where the Table 7 RW is low).

