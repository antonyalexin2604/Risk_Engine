# PROMETHEUS — Internal Models Method (IMM)
## Technical Reference: EPE, EEPE & All Functional Terms

**Regulatory Basis:** Basel III CRE53 (effective January 2023)  
**Engine File:** `backend/engines/imm.py`  
**Prepared:** April 2026

---

## Table of Contents

1. [What Is IMM?](#1-what-is-imm)
2. [The IMM Calculation Pipeline](#2-the-imm-calculation-pipeline)
3. [Monte Carlo Simulation Framework](#3-monte-carlo-simulation-framework)
4. [All Exposure Metrics — Definitions & Formulas](#4-all-exposure-metrics--definitions--formulas)
5. [Stochastic Process Models](#5-stochastic-process-models)
6. [Correlation & Factor Model](#6-correlation--factor-model)
7. [Stressed EEPE — 2007–2009 Calibration](#7-stressed-eepe--20072009-calibration)
8. [CSA / Collateral Adjustment](#8-csa--collateral-adjustment)
9. [Credit Valuation Adjustment (CVA)](#9-credit-valuation-adjustment-cva)
10. [Dynamic Initial Margin (DIM)](#10-dynamic-initial-margin-dim)
11. [FRTB Counterparty Risk Add-On](#11-frtb-counterparty-risk-add-on)
12. [Sensitivity Analysis — Greeks](#12-sensitivity-analysis--greeks)
13. [Incremental & Marginal Risk](#13-incremental--marginal-risk)
14. [Stress Test Scenarios](#14-stress-test-scenarios)
15. [RWA Derivation](#15-rwa-derivation)
16. [Configuration Parameters](#16-configuration-parameters)
17. [Complete Glossary of All Terms](#17-complete-glossary-of-all-terms)
18. [Appendix A: Monte Carlo Walk-Through — Equity Trade](#appendix-a-monte-carlo-simulation-walk-through--single-equity-trade)
19. [Appendix B: End-to-End Numeric Example (3-Trade Portfolio)](#appendix-b-end-to-end-numeric-example)
20. [Appendix C: Monte Carlo Walk-Through — Interest Rate Trade](#appendix-c-monte-carlo-simulation-walk-through--interest-rate-trade)
21. [Appendix D: Monte Carlo Walk-Through — FX Trade](#appendix-d-monte-carlo-simulation-walk-through--fx-trade)
22. [Appendix E: Monte Carlo Walk-Through — Commodity Trade](#appendix-e-monte-carlo-simulation-walk-through--commodity-trade)
23. [Appendix F: Monte Carlo Walk-Through — Credit Derivative Trade](#appendix-f-monte-carlo-simulation-walk-through--credit-derivative-trade)

---

## 1. What Is IMM?

The **Internal Models Method (IMM)** is the most advanced of the three Basel III approaches for computing **Exposure at Default (EAD)** for OTC derivatives and securities financing transactions (SFTs). It replaces the simple SA-CCR look-up tables with a full Monte Carlo simulation of future market states.

### Why Banks Use IMM

| Approach | EAD Method | Capital Relief vs. SA-CCR |
|---|---|---|
| Current Exposure Method (CEM) | Notional × add-on factor | None (legacy) |
| SA-CCR | RC + PFE (supervisory deltas) | Moderate |
| **IMM** | **α × EEPE (simulated)** | **Highest — up to 40–60% lower capital** |

IMM approval requires explicit supervisory sign-off (CRE53.1–53.5). G-SIBs typically run IMM alongside SA-CCR for validation.

---

## 2. The IMM Calculation Pipeline

Every IMM run flows through these exact steps in the PROMETHEUS engine:

```
Trades (N instruments)
        │
        ▼
┌─────────────────────────────────────────────┐
│   Step 1: Monte Carlo Path Generation        │
│   • GBM for EQ, FX, CMDTY                   │
│   • Hull-White 1F for IR                    │
│   • Antithetic variance reduction (2× paths)│
│   • Correlated draws via Cholesky factoring │
└──────────────────┬──────────────────────────┘
                   │  (N_eff × T) paths per risk factor
                   ▼
┌─────────────────────────────────────────────┐
│   Step 2: MtM Valuation at Each Time Step   │
│   • MtM(t) = notional × direction × Δprice │
│   • Bond pricing w/ convexity for IR trades │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│   Step 3: Netting Set Aggregation           │
│   • Net MtM = Σ MtM(trade i) per scenario   │
│   • Exposure = max(Net MtM, 0)              │
└──────────────────┬──────────────────────────┘
                   │  Exposure matrix: (N_eff × T)
                   ▼
┌─────────────────────────────────────────────┐
│   Step 4: Exposure Profile Construction     │
│   • EE(t)  = mean across scenarios          │
│   • EEE(t) = max(EE(t), EEE(t-1))          │  ← non-decreasing
│   • PFE(t) = 95th percentile                │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│   Step 5: Regulatory Metrics                │
│   • EPE  = avg(EE)  over [0, 1yr]           │
│   • EEPE = avg(EEE) over [0, 1yr]           │
│   • EAD  = α × EEPE    (α = 1.4)           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│   Step 6: Stressed EEPE (parallel run)      │
│   • Re-simulate with 2007–09 stressed vols  │
│   • Stressed EAD = α × Stressed EEPE       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│   Step 7: CSA / Collateral Adjustment       │
│   • RC_csa = max(V - C, TH + MTA - NICA, 0)│
│   • EEPE_mpor = EEPE × √(MPOR / 250)        │
│   • EAD_csa = α × (RC_csa + EEPE_mpor)     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         CVA / DIM / FRTB add-ons
                   │
                   ▼
         RWA = EAD × RW × 12.5 × 8%
```

---

## 3. Monte Carlo Simulation Framework

### 3.1 Scenario Parameters

| Parameter | Value | Description |
|---|---|---|
| `num_scenarios` | 2,000 base | Base simulation paths |
| Effective scenarios | **4,000** | Doubled by antithetic sampling |
| `time_steps` | 52 | Weekly steps over 1 year |
| `time_horizon_years` | 1.0 | 1-year horizon |
| `dt` | 1/52 ≈ 0.0192 yr | Time step size |
| Memory footprint | ~40 MB | Safe for 8 GB RAM |

### 3.2 Antithetic Variance Reduction

For each base set of random draws **Z**, a second set **−Z** is generated. The two sets are stacked:

```
Base paths:       S(t) = S₀ × exp((μ - σ²/2)dt + σ√dt × Z)
Antithetic paths: S(t) = S₀ × exp((μ - σ²/2)dt − σ√dt × Z)

Final path matrix: [Base paths; Antithetic paths]  → shape (4000, 52)
```

**Why it matters:** Antithetic sampling halves the variance of the EE estimator with no extra computational cost — the positive bias in one set is cancelled by the negative bias in the other. This is a regulatory best-practice technique (CRE53.21).

### 3.3 Path Caching

Within a single netting-set run, paths for the same risk factor are generated once and reused across all trades sharing that asset class. This avoids redundant simulation and ensures internal consistency in the netting aggregation.

> **Stressed runs do NOT use the base cache** — a separate fresh set of paths is generated with stressed volatility parameters. This ensures stress EAD genuinely reflects a different market environment.

---

## 4. All Exposure Metrics — Definitions & Formulas

### 4.1 Mark-to-Market (MtM)

The current fair value of a trade from the bank's perspective.

```
MtM(t, scenario i) = Notional × Direction × (Price(t,i) / Price(0) − 1)
```

- `Direction` = +1 for long/receive-fixed, −1 for short/pay-fixed
- For interest rate trades: uses **bond pricing with convexity** (see §5.2)
- For CDS (credit): `MtM = Notional × Duration × (spread(t) − spread(0))`

### 4.2 Exposure (E)

The **loss** the bank would suffer if the counterparty defaulted. Since the bank only loses when the position is in-the-money:

```
Exposure(t, scenario i) = max(MtM(t, scenario i), 0)
```

Floored at zero — the bank does not pay the counterparty if MtM is negative.

### 4.3 Netting Set Exposure

Within a legally enforceable netting agreement, MtMs across all trades are summed before taking the floor:

```
Net MtM(t, i)    = Σⱼ MtM(trade j, t, scenario i)
Exposure(t, i)   = max(Net MtM(t, i), 0)
```

This is the key capital benefit of bilateral netting: in-the-money and out-of-the-money trades offset each other.

### 4.4 Expected Exposure (EE)

The **average exposure across all scenarios** at time *t*:

```
EE(t) = (1 / N_eff) × Σᵢ Exposure(t, scenario i)
       = mean over scenarios of max(MtM, 0) at each time step
```

- Shape: vector of length T (one value per time step)
- Analogous to the expected loss given counterparty default at time *t*
- Regulatory reference: **CRE53.13**

**Key property:** EE(t) can decrease over time as trades mature. This is why the regulatory framework uses EEE instead for capital purposes.

### 4.5 Effective Expected Exposure (EEE)

A **non-decreasing version** of the EE profile — it cannot fall below the previous time-step's value:

```
EEE(t₀) = EE(t₀)
EEE(tₙ) = max(EE(tₙ), EEE(tₙ₋₁))    for n = 1, 2, ..., T
```

**Why non-decreasing?** It captures the regulatory concern that banks may opportunistically close profitable trades before the computation date, leaving only unfavourable positions. The non-decreasing constraint is a conservatism that prevents this "cherry-picking" benefit.

**Implementation in code:**
```python
def _effective_ee(self, ee: np.ndarray) -> np.ndarray:
    eee = np.zeros_like(ee)
    eee[0] = ee[0]
    for t in range(1, len(ee)):
        eee[t] = max(ee[t], eee[t-1])
    return eee
```

### 4.6 Expected Positive Exposure (EPE)

The **time-average of the EE profile** over the first year:

```
EPE = (1/T) × Σₜ EE(t)   for t ∈ [0, 1yr]
    = mean(EE vector)
```

- A single scalar value
- Commonly used for pricing (CVA) but **NOT** used for regulatory capital under IMM
- The capital metric is EEPE (see below)
- Regulatory reference: **CRE53.14**

### 4.7 Effective Expected Positive Exposure (EEPE)

The **time-average of the EEE profile** over the first year — this is the **primary regulatory capital driver** under IMM:

```
EEPE = (1/T) × Σₜ EEE(t)   for t ∈ [0, 1yr]
      = mean(EEE vector)
```

- Single scalar
- EEPE ≥ EPE always (because EEE ≥ EE at every time step)
- The time-averaging is only over the **first year** even for longer-dated trades
- Regulatory reference: **CRE53.15**

**The difference between EPE and EEPE:**

| Metric | Based On | Can Decrease? | Used For |
|---|---|---|---|
| EPE | EE (raw average) | Yes | CVA pricing, internal benchmarking |
| **EEPE** | EEE (non-decreasing) | No | **Regulatory capital (EAD_IMM)** |

### 4.8 Exposure at Default (EAD) — IMM Method

The regulatory capital exposure under IMM:

```
EAD_IMM = α × EEPE
```

Where:
- **α = 1.4** — the regulatory supervisory alpha factor (CRE53.16)
- This 40% loading reflects model uncertainty, wrong-way risk not captured in EEPE, and the possibility that actual loss-given-default exceeds the average exposure

The alpha of 1.4 was set by the Basel Committee based on empirical studies of the ratio of actual CCR losses to model-predicted EEPE. Banks may apply to use a lower firm-specific alpha if approved by their supervisor (minimum floor: 1.2).

### 4.9 Potential Future Exposure (PFE)

The **95th percentile exposure** across scenarios at each time step:

```
PFE(t) = Percentile₉₅{ Exposure(t, scenario i) : i = 1..N_eff }
```

- Represents a worst-case exposure at a given confidence level
- Used for credit limit monitoring, not regulatory capital
- Analogous to VaR but for counterparty exposure rather than P&L

### 4.10 Relationship Summary

```
Scenario paths (N_eff × T)
         │
         ├──► mean(axis=0) ──► EE(t)  ──► mean ──► EPE   (pricing)
         │                          │
         │                    enforce non-decreasing
         │                          │
         │                     EEE(t) ──► mean ──► EEPE  ──► ×α ──► EAD_IMM
         │
         └──► percentile(95, axis=0) ──► PFE(t)           (limit management)
```

---

## 5. Stochastic Process Models

### 5.1 Geometric Brownian Motion (GBM) — EQ, FX, CMDTY

Used for equities, foreign exchange, and commodity risk factors.

**Continuous-time SDE:**
```
dS/S = μ dt + σ dW
```

**Discretised (exact log-normal scheme):**
```
S(t + dt) = S(t) × exp[(μ − σ²/2) dt + σ√dt × Z]
```

Where:
- `μ` = drift (annual) = 0.05 (5% risk-neutral drift)
- `σ` = volatility (annual) = 0.20 base; 0.40 stressed
- `Z ~ N(0,1)` = standard normal random draw
- `S₀ = 1.0` (normalised; MtM is relative return × notional)

**The `σ²/2` Itô correction** prevents upward bias in the expected value that would arise from a naïve Euler scheme. It ensures `E[S(T)] = S₀ × exp(μT)`.

**Antithetic version:**
```
S_anti(t + dt) = S(t) × exp[(μ − σ²/2) dt − σ√dt × Z]
```

Uses `−Z` instead of `+Z` — the negative of the same random draw.

### 5.2 Hull-White 1-Factor Model (IR)

Used for interest rate risk factors. The short rate *r* follows an Ornstein-Uhlenbeck process with mean reversion.

**Continuous-time SDE:**
```
dr = κ(θ − r) dt + σᵣ dW
```

**Discretised (explicit Euler scheme):**
```
r(t + dt) = r(t) + κ(θ − r(t)) dt + σᵣ√dt × Z
```

Where:
- `κ` = mean reversion speed = 0.10 (pulls rate back to θ at rate 10% per year)
- `θ` = long-run mean rate = 0.045 (4.5%, calibrated from OIS forward curve)
- `σᵣ` = IR volatility = 0.015 base; 0.030 stressed
- `r₀` = initial short rate = 0.05 (5%)

**Bond Pricing with Convexity Correction:**

IR trade MtM is computed as the change in bond price rather than the change in rate directly:

```
P(r) ≈ 1 − duration × Δr + 0.5 × convexity × (Δr)²
```

Where:
- `Δr = r(t) − r₀` = rate change from initial level
- `duration` = trade's remaining maturity in years (computed at runtime)
- `convexity` = 0.05 × duration² / 100 (approximation)

The convexity term accounts for the **positive convexity** of bond prices: duration understates the price gain when rates fall and overstates the price loss when rates rise.

**Bond MtM:**
```
MtM_IR(t, i) = Notional × direction × [P(r(t,i)) − 1]
```

### 5.3 Credit Default Swap (CDS) Exposure

```
MtM_CR(t, i) = Notional × direction × duration × (spread(t,i) − spread₀)
```

Where spread paths are simulated as GBM with:
- `S₀ = 0.01` (100bp initial spread)
- `vol = 0.50` (50% spread volatility — high to reflect jump risk)

### 5.4 Model Summary by Asset Class

| Asset Class | Code | Model | Key Parameters |
|---|---|---|---|
| Equity | `EQ` | GBM | μ=5%, σ=20% (base), 40% (stressed) |
| Foreign Exchange | `FX` | GBM | μ=5%, σ=20% (base), 40% (stressed) |
| Interest Rate | `IR` | Hull-White 1F | κ=10%, θ=4.5%, σᵣ=1.5% (base), 3.0% (stressed) |
| Credit (CDS) | `CR` | GBM (spread) | S₀=100bp, vol=50% |
| Commodity | `CMDTY` | GBM | μ=5%, σ=30% (base) |

---

## 6. Correlation & Factor Model

### 6.1 Factor Structure

Six risk factors are modelled with a full correlation matrix:

| Index | Factor | Description |
|---|---|---|
| 0 | EQ | Equity risk |
| 1 | FX | Foreign exchange risk |
| 2 | IR | Interest rate risk |
| 3 | CR | Credit spread risk |
| 4 | CMDTY | Commodity risk |
| 5 | Market | Systemic / common market factor |

### 6.2 Correlation Matrix

```
         EQ    FX    IR    CR    CMDTY  MKT
EQ    [1.00, 0.60, 0.20, 0.50, 0.40, 0.70]
FX    [0.60, 1.00, 0.15, 0.30, 0.35, 0.65]
IR    [0.20, 0.15, 1.00, 0.10, 0.05, 0.25]
CR    [0.50, 0.30, 0.10, 1.00, 0.20, 0.60]
CMDTY [0.40, 0.35, 0.05, 0.20, 1.00, 0.55]
MKT   [0.70, 0.65, 0.25, 0.60, 0.55, 1.00]
```

Key observations:
- EQ–FX correlation of 0.60: equity and FX tend to co-move (risk-off sells equities and weakens domestic currency)
- IR has low correlation with everything (rates driven by central bank policy, not systemic risk)
- Credit correlates highly with equity (0.50) and the market factor (0.60) — consistent with the Merton model
- The market factor loads heavily on all assets — represents the systemic component

### 6.3 Cholesky Decomposition for Correlated Draws

To generate correlated random variables from the independent standard normals, the Cholesky factorisation of the correlation matrix is applied:

```
Σ = L × L^T    (Cholesky decomposition, lower-triangular L)

Correlated draws: Z_corr = Z_uncorr @ L^T
```

Where `Z_uncorr` is a matrix of independent N(0,1) draws.

This is implemented via:
```python
self.corr_chol = cholesky(self.p.correlation_matrix, lower=True)
correlated = np.einsum('...i,ji->...j', uncorrelated, self.corr_chol)
```

The matrix is validated to be **symmetric positive-definite** (all eigenvalues > 0) before decomposition. If the matrix fails this check, calibration would produce unreliable risk estimates.

---

## 7. Stressed EEPE — 2007–2009 Calibration

### 7.1 Regulatory Requirement

CRE53.17 requires banks to run a **parallel simulation using parameters calibrated to the most stressful one-year period** in the observation window — typically the 2007–2009 global financial crisis.

### 7.2 Stressed Parameters

| Parameter | Base | Stressed | Ratio |
|---|---|---|---|
| Equity vol (σ) | 20% | **40%** | 2× |
| IR vol (σᵣ) | 1.5% | **3.0%** | 2× |
| FX vol | 20% | **40%** | 2× |
| Correlation matrix | Base | Base (unchanged) | — |

The stressed calibration window is: **1 January 2007 — 31 December 2009**

### 7.3 Stressed EAD Calculation

```
Stressed EEPE = average(Stressed EEE) over [0, 1yr]
Stressed EAD  = α × Stressed EEPE
```

### 7.4 Capital Floor

The regulatory capital charge uses the **higher** of the base and stressed metrics in practice:
```
Capital EAD = max(Base EAD, Stressed EAD)
```

This prevents banks from gaming the system by calibrating to a benign recent period.

---

## 8. CSA / Collateral Adjustment

### 8.1 Credit Support Annex (CSA) Terms

| Parameter | Code Name | Default | Description |
|---|---|---|---|
| Threshold (TH) | `threshold` | $500,000 | Minimum exposure before counterparty posts collateral |
| Haircut (h) | `haircut` | 2% | Discount applied to collateral value |
| Margin Period of Risk (MPOR) | `margin_period_of_risk` | 10 days | Time lag to replace/close out after counterparty default |
| Initial Margin (IM) | `initial_margin` | 0 | Upfront margin (one-way) |
| Independent Amount (IA) | `independent_amount` | 0 | One-way collateral independent of MtM |
| Daily Settlement | `daily_settlement` | True | Whether VM settles T+0 |

### 8.2 Regulatory CSA EAD (CRE53.22–53.23)

The PROMETHEUS engine implements the **two-component CRE53 regulatory formula**:

**Component 1: RC Benefit (Current Exposure after VM)**

This mirrors the SA-CCR Replacement Cost formula (CRE52.18):

```
C     = VM + IM           (total collateral received)
RC_csa = max(V − C, TH + MTA − NICA, 0)
```

Where:
- `V` = current net MtM of the netting set
- `VM` = variation margin received
- `IM` = initial margin received
- `TH` = threshold
- `MTA` = minimum transfer amount
- `NICA` = net independent collateral amount (= IM received)

**Component 2: MPOR Benefit (Future Exposure Scaling)**

The future exposure window is reduced from the full trade maturity to just the MPOR:

```
EEPE_mpor = EEPE_gross × √(MPOR / 250)
```

For a standard 10-day MPOR:
```
√(10 / 250) = √0.04 = 0.2
EEPE_mpor = EEPE_gross × 0.2   → 80% reduction in future exposure
```

**Combined Regulatory EAD:**

```
EAD_csa = α × (RC_csa + EEPE_mpor)
```

### 8.3 CSA EAD Reduction Example

```
Given:
  EEPE_gross = 50,000
  V = 45,000,  VM = 40,000,  IM = 0
  TH = 500,  MTA = 0,  MPOR = 10 days

Step 1: RC_csa = max(45000−40000, 500+0−0, 0) = max(5000, 500, 0) = 5,000

Step 2: EEPE_mpor = 50,000 × √(10/250) = 50,000 × 0.2 = 10,000

Step 3: EAD_csa = 1.4 × (5,000 + 10,000) = 1.4 × 15,000 = 21,000

Base EAD (no CSA) = 1.4 × 50,000 = 70,000

CSA Reduction = (70,000 − 21,000) / 70,000 = 70%  ← significant capital saving
```

### 8.4 Path-Level CSA Adjustment (Internal Use)

In addition to the regulatory formula, the engine provides a **path-level collateral adjustment** for internal analytics:

```
Net Exposure(t, i) = max(0, (Exposure(t,i) − TH) × h)
EE_net(t)          = mean over scenarios of Net Exposure(t, i)
EEE_net(t)         = non-decreasing envelope of EE_net
EEPE_csa           = mean(EEE_net) over [0, 1yr]
EAD_csa_internal   = α × EEPE_csa
```

This path-level method is more accurate but is supplementary; the regulatory EAD uses the CRE53.22 formula above.

---

## 9. Credit Valuation Adjustment (CVA)

CVA is the **market value of counterparty credit risk** — the expected loss due to the counterparty defaulting before maturity.

### 9.1 Formula

```
CVA = ∫₀ᵀ (1 − RR) × EE(t) × dQ(t) × D(t)
```

**Discretised (trapezoidal integration):**
```
CVA = Σₜ (1 − RR) × EE_mid(t) × PD(t) × D(t)
```

Where:
- `RR` = recovery rate = **40%** (Basel standard)
- `EE_mid(t)` = (EE(t) + EE(t+1)) / 2 (midpoint approximation)
- `PD(t)` = probability of default over [t, t+dt] = 1 − exp(−λ × dt)
- `λ` = hazard rate = CDS spread / (1 − RR)
- `D(t)` = discount factor = exp(−r × t) with r = 3%
- `CDS spread` = credit default swap spread for the counterparty (default: 50bp)

### 9.2 Interpretation

| CVA Value | Meaning |
|---|---|
| Higher CVA | Counterparty is riskier (wider CDS) or exposure is larger |
| CVA = 0 | Perfectly safe counterparty (zero default probability) |

CVA represents the upfront cost that should be charged to a counterparty for bearing their credit risk. A CRO would see this as the "fair-value haircut" on the trade portfolio.

---

## 10. Dynamic Initial Margin (DIM)

DIM captures the **tail risk beyond EEPE** that might be required as initial margin under bilateral margin rules (BCBS-IOSCO UMR framework).

### 10.1 Formula

```
DIM = max(0, (ES₉₇.₅ − EEPE) / α)
```

Where:
- `ES₉₇.₅` = Expected Shortfall at 97.5% confidence (approximated by PFE_95)
- `α` = 1.4 (regulatory alpha)
- Floored at zero (DIM cannot be negative)

### 10.2 Intuition

- If ES ≈ EEPE, DIM ≈ 0 — the tail is not much worse than the average (well-behaved distribution)
- If ES >> EEPE, DIM > 0 — the tail is "fat", requiring extra margin protection

---

## 11. FRTB Counterparty Risk Add-On

A simplified add-on for **Fundamental Review of the Trading Book (FRTB)** counterparty risk:

```
FRTB_addon = 0.15 × Notional_total × √(EEPE / Notional_total)
           = 0.15 × √(EEPE × Notional_total)
```

This captures that the FRTB CCR risk scales with both the notional size (portfolio risk) and the relative exposure intensity (EEPE / notional).

---

## 12. Sensitivity Analysis — Greeks

The engine computes first-order sensitivities of EAD to market parameters using **central finite differences**:

```
∂EAD/∂x ≈ [EAD(x + ε) − EAD(x − ε)] / (2ε)
```

A new Monte Carlo engine is spun up for each bump, recalculating the full EEPE with the perturbed parameter.

### 12.1 Vega — Equity (∂EAD/∂σ_EQ)

```
Bump size: ε = 1% (0.01)
Interpretation: change in EAD for a 1% increase in equity volatility
```

A large positive vega_equity means the portfolio EAD is highly sensitive to equity vol spikes — a warning sign under stress scenarios.

### 12.2 Vega — Interest Rate (∂EAD/∂σ_IR)

```
Bump size: ε = 0.1% (0.001)
Interpretation: change in EAD for a 10bp increase in IR volatility
```

### 12.3 Vega — Credit (∂EAD/∂ρ_CR)

Measured via bumping the credit factor row/column in the correlation matrix:
```
Bump size: 5% correlation point change on CR index (row/col 3)
```

### 12.4 Rho — Rate Level Sensitivity (∂EAD/∂r)

```
Bump size: ±25bp (0.0025)
Interpretation: change in EAD for a 25bp parallel shift in rates (via drift μ)
```

A negative rho means EAD falls when rates rise — common for pay-fixed IR portfolios.

### 12.5 Lambda — Market Factor Correlation (∂EAD/∂ρ_MKT)

```
Bump size: 5% correlation point change on market factor (row/col 5)
Interpretation: sensitivity to systemic correlation increases (crisis scenario)
```

Large positive lambda indicates concentration risk — the portfolio would underperform significantly in a systemic stress event.

### 12.6 All Greeks Summary

| Greek | Formula | Bump | Regulatory Use |
|---|---|---|---|
| `vega_equity` | ∂EAD/∂σ_EQ | 1% vol | FRTB SA sensitivity |
| `vega_ir` | ∂EAD/∂σ_IR | 10bp vol | FRTB SA sensitivity |
| `vega_credit` | ∂EAD/∂ρ_CR | 5% corr | CVA sensitivity |
| `rho` | ∂EAD/∂r | 25bp | IR risk |
| `lambda_corr` | ∂EAD/∂ρ_MKT | 5% corr | Wrong-way risk indicator |
| `vega_stress` | ∂EAD/∂σ (large) | 5% vol | Stress calibration sensitivity |
| `volga` | ∂²EAD/∂σ² | — | (Reserved — second-order) |
| `vanna` | ∂²EAD/∂σ∂r | — | (Reserved — second-order) |

---

## 13. Incremental & Marginal Risk

### 13.1 Marginal EAD per Trade

The change in total portfolio EAD when a single trade is removed:

```
Marginal EAD(trade i) = EAD(full portfolio) − EAD(portfolio without trade i)
```

This measures the **diversification benefit or concentration risk** of each trade.

- A large positive marginal EAD → trade adds significant risk (consider netting, collateral, or termination)
- A negative marginal EAD → trade **reduces** portfolio EAD (natural hedge — keep it!)

### 13.2 Component Contribution by Asset Class

Trades are grouped by `asset_class` and an isolated EAD is computed for each group:

```
EAD_contribution(EQ) = EAD(only EQ trades) / EAD(full portfolio) × 100%
```

This identifies which asset class drives counterparty risk concentration.

### 13.3 Trade Ranking

Trades are ranked in descending order by marginal EAD. The top-ranked trade has the most systemic counterparty risk impact and should be prioritised for collateral negotiation or novation.

---

## 14. Stress Test Scenarios

Six regulatory-aligned scenarios are pre-defined:

| Scenario | Shock | Description |
|---|---|---|
| `normal` | None | Base calibration (current market) |
| `rates_up_100bp` | IR +100bp parallel | Rapid monetary tightening |
| `rates_down_100bp` | IR −100bp parallel | Emergency rate cut (ZIRP shock) |
| `curve_steepening` | Long rates +50bp, short unchanged | Bear steepening |
| `equity_spike` | EQ vol × 2 | VIX doubling (like March 2020) |
| `credit_widening` | Credit spreads +200bp | Credit market seizure |

Each scenario applies the shock to `MarketParams`, creates a new `MonteCarloEngine` with the stressed parameters, and runs the full EPE/EEPE pipeline. Results are returned as a `Dict[str, ExposureProfile]` for comparison.

---

## 15. RWA Derivation

Capital is converted to Risk-Weighted Assets using the Basel capital ratio framework:

```
Capital Charge = EAD × Risk Weight (RW)
RWA = Capital Charge / 8%
    = EAD × RW × 12.5
```

The factor 12.5 = 1 / 8% converts from capital to RWA (since minimum capital = 8% of RWA under Basel III Pillar 1).

For CCR:
```
RWA_IMM = EAD_IMM × RW × 12.5 × 0.08
         = EAD_IMM × RW
```

The `risk_weight` parameter defaults to 1.0 (100% risk weight for unrated / standardised).

---

## 16. Configuration Parameters

Defined in `backend/config.py`:

| Parameter | Class | Value | Description |
|---|---|---|---|
| `num_scenarios` | `IMM` | 2,000 | Base Monte Carlo paths |
| `time_steps` | `IMM` | 52 | Weekly steps in 1-year horizon |
| `time_horizon_years` | `IMM` | 1.0 | Simulation horizon |
| `random_seed` | `IMM` | Fixed | Reproducibility seed |
| `alpha` | `SACCR` | **1.4** | Regulatory EAD multiplier |

---

## 17. Complete Glossary of All Terms

| Term | Formula / Definition | Source |
|---|---|---|
| **α (Alpha)** | Regulatory multiplier = **1.4** applied to EEPE to get EAD | CRE53.16 |
| **Antithetic Sampling** | Variance reduction using −Z alongside +Z in Monte Carlo | CRE53.21 |
| **Bond Convexity** | Second-order price sensitivity to rate changes: `0.5 × convexity × Δr²` | Market standard |
| **C (Total Collateral)** | `C = VM + IM` — total collateral received from counterparty | CRE52.18 |
| **Cholesky Decomposition** | Factorises correlation matrix for correlated random draws: `Σ = L × Lᵀ` | Numerical methods |
| **CDS Spread** | Market credit default swap spread used to calibrate hazard rate | CVA pricing |
| **CVA** | Credit Valuation Adjustment: `(1−RR) × Σ EE(t) × PD(t) × D(t)` | CRE53 / BCBS |
| **DIM** | Dynamic Initial Margin: `max(0, (ES − EEPE) / α)` | UMR / SIMM |
| **Direction** | +1 (long/receive) or −1 (short/pay) trade orientation | Trade metadata |
| **dt** | Time step size = `time_horizon / time_steps` = 1/52 years | Simulation |
| **Duration** | Trade remaining maturity in years; drives IR/CDS bond price sensitivity | Market standard |
| **EAD_IMM** | Exposure at Default = `α × EEPE` | **CRE53.15–16** |
| **EAD_csa** | CSA-adjusted EAD = `α × (RC_csa + EEPE_mpor)` | **CRE53.22** |
| **EE(t)** | Expected Exposure = `mean{ max(MtM(t,i), 0) }` over all scenarios | **CRE53.13** |
| **EEE(t)** | Effective EE = `max(EE(t), EEE(t−1))` — non-decreasing | **CRE53.13** |
| **EEPE** | Effective EPE = `mean(EEE)` over `[0, 1yr]` | **CRE53.15** |
| **EPE** | Expected Positive Exposure = `mean(EE)` over `[0, 1yr]` | **CRE53.14** |
| **ES** | Expected Shortfall at 97.5% (approximated by PFE_95 in engine) | FRTB / IMM |
| **Exposure** | `max(MtM, 0)` — positive MtM only (bank only loses when in-the-money) | CCR definition |
| **FRTB add-on** | `0.15 × √(EEPE × Notional)` | FRTB SA-CVA |
| **GBM** | Geometric Brownian Motion: `dS/S = μdt + σdW` | Market standard |
| **Greeks** | Sensitivities of EAD to market parameters (vega, rho, lambda) | Internal risk |
| **Haircut (h)** | Discount on collateral value (2% default) | CSA terms |
| **Hazard Rate (λ)** | Default intensity: `λ = CDS spread / (1 − RR)` | CVA pricing |
| **Hull-White** | 1-factor IR model: `dr = κ(θ−r)dt + σᵣdW` | Market standard |
| **IA** | Independent Amount — one-way collateral independent of MtM | CSA terms |
| **ILM** | Internal Loss Multiplier (Operational Risk, not IMM) | OPE25 |
| **IM** | Initial Margin received from counterparty | BCBS-IOSCO UMR |
| **κ (kappa)** | Mean reversion speed in Hull-White model = 0.10 | Hull-White |
| **Marginal EAD** | `EAD(full) − EAD(without trade i)` — trade-level risk contribution | Internal |
| **MtM** | Mark-to-Market = current fair value of a derivative position | Accounting |
| **MPOR** | Margin Period of Risk — days to replace collateral post-default (10 days standard) | CRE53.22 |
| **MTA** | Minimum Transfer Amount — smallest collateral call | CSA terms |
| **NICA** | Net Independent Collateral Amount = IM received | CRE52.18 |
| **Netting Set** | Group of trades under a single enforceable netting agreement | CCR definition |
| **PFE(t)** | Potential Future Exposure = 95th percentile exposure at time t | Limit management |
| **RC_csa** | Replacement Cost under CSA = `max(V−C, TH+MTA−NICA, 0)` | CRE52.18 |
| **Recovery Rate (RR)** | Expected recovery on default = **40%** | Basel standard |
| **RWA** | Risk-Weighted Assets = `EAD × RW × 12.5` | CRE20 |
| **Stressed EEPE** | EEPE computed with 2007–09 stressed volatilities | CRE53.17 |
| **θ (theta)** | Long-run mean rate in Hull-White model = 0.045 | Hull-White |
| **TH** | Threshold — minimum exposure triggering a collateral call | CSA terms |
| **Time Grid** | Vector of 52 weekly time points from dt to 1.0 year | Simulation |
| **V** | Current net MtM of the netting set | CRE52.18 |
| **VM** | Variation Margin received from counterparty | CSA / CRE52 |
| **Vega** | Sensitivity of EAD to volatility: `∂EAD/∂σ` | Sensitivity |
| **Wrong-Way Risk** | Correlation between counterparty default and exposure magnitude | CRE53 |

---

## Appendix A: Monte Carlo Simulation Walk-Through — Single Equity Trade

> **Purpose:** This appendix is designed for non-quantitative stakeholders (CRO, Board Risk Committee, Regulators). It walks through every step of the Monte Carlo simulation for a single equity trade in plain language, with concrete numbers, to illustrate exactly how the exposure metrics — **EPE, EEPE, EEE, and PFE** — are derived.

---

### A.1 The Trade

> **Product:** Equity Total Return Swap (TRS)  
> **Underlying:** Hypothetical large-cap equity (e.g., bank holds a long TRS on a single stock)  
> **Notional:** USD 10,000,000  
> **Direction:** Long (+1) — bank receives equity returns, pays LIBOR  
> **Maturity:** 1 year  
> **Initial Stock Price (S₀):** 100  
> **Annual Volatility (σ):** 20%  
> **Annual Drift (μ):** 5%

**What does "exposure" mean for this trade?**

If the stock goes UP from 100 to 110, the trade is worth +10% × $10M = **+$1,000,000** to the bank. If the counterparty defaults at that moment, the bank **loses** $1,000,000.

If the stock goes DOWN from 100 to 90, the trade is worth −10% × $10M = **−$1,000,000** to the bank. If the counterparty defaults, the bank owes them money — so the bank's **loss is zero** (it walks away).

This asymmetry — "I only lose when the trade is in my favour" — is the fundamental logic of `Exposure = max(MtM, 0)`.

---

### A.2 Setting Up the Simulation

The engine runs **4,000 scenarios** (2,000 base + 2,000 antithetic) over **52 weekly time steps** (1 year).

Each scenario is one possible "future history" of the stock price. Here is a simplified illustration with **just 6 scenarios** to make the arithmetic transparent:

```
Parameters:
  S₀    = 100        (initial stock price, normalised)
  σ     = 20%        (annual volatility)
  μ     = 5%         (annual drift)
  dt    = 1/52 year  (one week)
  σ²/2  = 0.02       (Itô correction — prevents upward bias)

GBM formula:
  S(t+dt) = S(t) × exp[(μ − σ²/2)×dt + σ×√dt × Z]
           = S(t) × exp[0.0288×dt + 0.20×0.1386 × Z]
           where Z ~ N(0,1)
```

---

### A.3 Six Illustrative Scenarios — Stock Price Paths

For clarity we show the stock price at **4 selected time points**: 3 months (t=13), 6 months (t=26), 9 months (t=39), 12 months (t=52).

```
Scenario | 3m (t=13)  | 6m (t=26)  | 9m (t=39)  | 12m (t=52) | Outcome
─────────────────────────────────────────────────────────────────────────
  #1      |   108       |   115       |   123       |   130      | Strong bull
  #2      |   104       |   107       |   110       |   105      | Modest up / fade
  #3      |    98       |   102       |    96       |   100      | Flat / sideways
  #4      |    93       |    88       |    82       |    78      | Steady bear
  #5      |   112       |    95       |    88       |    92      | Spike then fall
  #6      |    86       |    72       |    65       |    58      | Severe bear
─────────────────────────────────────────────────────────────────────────
(antithetic paths mirror each scenario with −Z — they ensure symmetry)
```

**Visualisation of the 6 paths:**

```
Stock Price
  130 |                              ●  (Sc.1)
  125 |
  120 |                   ●  (Sc.1)
  115 |          ●  (Sc.1)
  112 |          ●  (Sc.5)
  110 |                   ●  (Sc.2)
  108 |  ●  (Sc.1)                ●  (Sc.2)
  107 |          ●  (Sc.2)
  105 |  ●  (Sc.2)
  104 |
  102 |          ●  (Sc.3)
  100 |  S₀ ─────────────────────────────── ●  (Sc.3)
   98 |  ●  (Sc.3)
   96 |                   ●  (Sc.3)
   95 |                   ●  (Sc.5)
   93 |  ●  (Sc.4)
   92 |                              ●  (Sc.5)
   88 |          ●  (Sc.4)        ●  (Sc.5)
   86 |  ●  (Sc.6)
   82 |                   ●  (Sc.4)
   78 |                              ●  (Sc.4)
   72 |          ●  (Sc.6)
   65 |                   ●  (Sc.6)
   58 |                              ●  (Sc.6)
      └────────────────────────────────────► Time
         0    3m    6m    9m    12m
```

---

### A.4 Converting Stock Price to Mark-to-Market (MtM)

The MtM of the equity TRS at each scenario and time point is:

```
MtM(t, scenario i) = Notional × Direction × (S(t,i) / S₀ − 1)
                   = $10,000,000 × (+1) × (S(t,i) / 100 − 1)
```

**MtM Table (USD):**

```
Scenario | 3m          | 6m           | 9m           | 12m
──────────────────────────────────────────────────────────────────
  #1      | +$800,000   | +$1,500,000  | +$2,300,000  | +$3,000,000
  #2      | +$400,000   |   +$700,000  | +$1,000,000  |   +$500,000
  #3      | −$200,000   |   +$200,000  |   −$400,000  |         $0
  #4      | −$700,000   | −$1,200,000  | −$1,800,000  | −$2,200,000
  #5      | +$1,200,000 |   −$500,000  |   −$1,200,000| −$800,000
  #6      | −$1,400,000 | −$2,800,000  | −$3,500,000  | −$4,200,000
──────────────────────────────────────────────────────────────────
```

**Key insight:** Negative MtM means the stock fell below the initial price. The bank owes money to the counterparty — but this is NOT a credit risk to the bank.

---

### A.5 Calculating Exposure — "Floor at Zero"

```
Exposure(t, scenario i) = max(MtM(t, scenario i), 0)
```

**Exposure Table (USD):**

```
Scenario | 3m          | 6m           | 9m           | 12m
──────────────────────────────────────────────────────────────────
  #1      | +$800,000   | +$1,500,000  | +$2,300,000  | +$3,000,000
  #2      | +$400,000   |   +$700,000  | +$1,000,000  |   +$500,000
  #3      |       $0    |   +$200,000  |         $0   |         $0
  #4      |       $0    |         $0   |         $0   |         $0
  #5      | +$1,200,000 |         $0   |         $0   |         $0
  #6      |       $0    |         $0   |         $0   |         $0
──────────────────────────────────────────────────────────────────
```

Scenarios 4 and 6 contribute **zero exposure** at all time points — the bank is out-of-the-money and has no credit risk in those scenarios.

---

### A.6 Expected Exposure EE(t) — The Average

EE(t) is the simple average of Exposure across all 6 scenarios:

```
EE(3m)  = ($800k + $400k + $0 + $0 + $1,200k + $0) / 6  = $400,000
EE(6m)  = ($1,500k + $700k + $200k + $0 + $0 + $0) / 6  = $400,000
EE(9m)  = ($2,300k + $1,000k + $0 + $0 + $0 + $0) / 6  = $550,000
EE(12m) = ($3,000k + $500k + $0 + $0 + $0 + $0) / 6    = $583,333
```

> In the full production engine, this average is taken across **4,000 scenarios**, making the estimate statistically robust.

---

### A.7 Effective Expected Exposure EEE(t) — Non-Decreasing Envelope

The EEE applies the "ratchet" constraint: it can only stay flat or increase, never decrease:

```
EEE(t₀) = EE(t₀)                       (at inception)
EEE(tₙ) = max(EE(tₙ), EEE(tₙ₋₁))      (forward ratchet)
```

Applied to our example:

```
Step                    | Value         | Explanation
────────────────────────────────────────────────────────────────────────
EEE(3m) = EE(3m)        | $400,000      | First step — initialised to EE
EEE(6m) = max(EE(6m), EEE(3m))
        = max($400k, $400k)             | $400,000      | Unchanged — EE flat
EEE(9m) = max(EE(9m), EEE(6m))
        = max($550k, $400k)             | $550,000      | Rises with EE
EEE(12m)= max(EE(12m), EEE(9m))
        = max($583k, $550k)             | $583,333      | Rises with EE
────────────────────────────────────────────────────────────────────────
```

**Visualisation — EE vs EEE:**

```
Exposure
 $600k |                              ●  EEE(12m) = $583k
 $580k |                         ↗   ◆  EE(12m) = $583k
 $560k |                    ●  EEE(9m) = $550k
 $550k |                    ◆  EE(9m) = $550k
 $450k |
 $400k |  ●──────────●  EEE(3m)=$400k, EEE(6m)=$400k (flat — ratchet holds)
 $400k |  ◆          ◆  EE(3m)=$400k,  EE(6m)=$400k
       └─────────────────────────────────────────► Time
          3m    6m    9m   12m
          
  ● = EEE (Effective EE — non-decreasing)
  ◆ = EE  (raw expected exposure — can decrease)
```

**Why does this matter to the CRO?**

Without the ratchet, EE could fall at 6 months (perhaps because many trades are maturing). This would give the misleading impression that credit risk is disappearing. The EEE forces the bank to hold capital against the **peak exposure reached so far** — preventing an artificial reduction due to selective trade maturities.

---

### A.8 EPE and EEPE — Scalar Capital Metrics

Both EPE and EEPE are simple averages over all 52 weekly time steps (illustrated here with 4 points):

**EPE — time average of EE:**
```
EPE = (1/4) × (EE(3m) + EE(6m) + EE(9m) + EE(12m))
    = (1/4) × ($400k + $400k + $550k + $583k)
    = (1/4) × $1,933k
    ≈ $483,333
```

**EEPE — time average of EEE:**
```
EEPE = (1/4) × (EEE(3m) + EEE(6m) + EEE(9m) + EEE(12m))
     = (1/4) × ($400k + $400k + $550k + $583k)
     ≈ $483,333
```

> In this example EPE ≈ EEPE because EE was non-decreasing. In portfolios where EE dips mid-life (e.g., amortising trades), EEPE will be **visibly higher** than EPE.

---

### A.9 Potential Future Exposure PFE(t) — The "Worst Case" Line

PFE is the **95th percentile exposure** at each time point. With only 6 scenarios, the 95th percentile would be the highest observation. With 4,000 scenarios, it is the 3,800th largest value.

For our example (using the 6-scenario subset):

```
PFE(3m)  = max visible positive exposure = $1,200,000   (Scenario 5)
PFE(6m)  = $1,500,000                                   (Scenario 1)
PFE(9m)  = $2,300,000                                   (Scenario 1)
PFE(12m) = $3,000,000                                   (Scenario 1)
```

**PFE is used for credit limit monitoring** — it answers the question: "In a bad but plausible outcome (95% confidence), what is my maximum exposure at month 6?" If this exceeds the credit limit for the counterparty, the trade should be declined or collateralised.

---

### A.10 Complete Picture — All Four Metrics Together

```
  Exposure
  $3.0M |                                   ◇ PFE(12m) = $3.0M
  $2.5M |
  $2.3M |                    ◇ PFE(9m)
  $2.0M |
  $1.5M |          ◇ PFE(6m)
  $1.2M |  ◇ PFE(3m)
        |
  $583k |                              ● EEE(12m) = EEPE input
  $550k |                    ● EEE(9m)
  $500k |
  $483k |  ════════════════════════════  EPE / EEPE ≈ $483k (time avg)
  $400k |  ●────────● EEE(3m)=EEE(6m)
        |
        |  ◆        ◆ EE(3m)=EE(6m)     ◆ EE(9m)     ◆ EE(12m)
        └──────────────────────────────────────────────────────► Time
           3m       6m                  9m            12m

  ◇ = PFE (95th pctile — credit limit line)
  ● = EEE (non-decreasing exposure — feeds EEPE → EAD)
  ◆ = EE  (average exposure — feeds EPE → CVA)
  ══ = EEPE scalar (average of EEE — the regulatory capital driver)
```

**Summary table:**

| Metric | Value | Used For |
|---|---|---|
| **EE(t)** | $400k → $583k over time | CVA pricing, internal analytics |
| **EEE(t)** | $400k → $583k (ratcheted) | Feeds EEPE — regulatory capital |
| **EPE** | ≈ $483,333 | CVA pricing, internal benchmarking |
| **EEPE** | ≈ $483,333 | **Regulatory capital driver** |
| **PFE(95%)** | $1.2M → $3.0M | Credit limit monitoring |
| **EAD_IMM** | α × EEPE = 1.4 × $483k = **$676,667** | Capital & RWA |
| **RWA** | EAD × 12.5 × 8% = EAD × 1.0 = **$676,667** | Basel III Pillar 1 |

---

### A.11 Why Monte Carlo? — The Significance for a G-SIB

The Chief Risk Officer should understand three key reasons why Monte Carlo simulation is indispensable — and why PROMETHEUS implements it at scale (4,000 paths × 52 time steps):

**1. Captures Non-Linear Exposure Profiles**

For a simple equity TRS, the relationship between stock price and exposure is linear. But for **options, swaptions, or cross-currency swaps**, the exposure profile is deeply non-linear. Monte Carlo naturally captures these shapes; closed-form formulas cannot.

**2. Handles Portfolio Netting**

When the bank has 50 trades with the same counterparty — some equity, some IR, some FX — the netting benefit cannot be computed analytically. Monte Carlo runs all 50 trades in the **same scenario** and nets them at the portfolio level. This is mathematically correct; the alternative (summing individual EADs) is highly conservative and over-states capital.

**3. Generates the Full Distribution**

From 4,000 scenarios, the engine extracts:
- The **mean** → EE, EPE (for CVA pricing)
- The **non-decreasing envelope mean** → EEE, EEPE (for regulatory capital)
- The **95th percentile** → PFE (for credit limits)
- The **tail mean (ES)** → for FRTB add-on and DIM

This is only possible because Monte Carlo preserves the **entire distribution** of future exposure, not just a single number. The alpha factor of **1.4** applied to EEPE (mandated by Basel CRE53.16) partially compensates for residual model uncertainty — but it is the simulation itself that makes the capital number defensible to supervisors.

---

### A.12 Stressed Scenario — What Happens in a Crisis?

With **stressed volatility (σ = 40%, double the base)**:

```
Base scenario:
  EEPE       ≈ $483,333
  EAD_IMM    = 1.4 × $483,333 = $676,667

Stressed scenario (2007–09 calibration, σ = 40%):
  EEPE_stressed ≈ $820,000   (nearly double — driven by σ² term in GBM)
  EAD_stressed  = 1.4 × $820,000 = $1,148,000

Capital EAD (regulatory floor):
  Capital EAD = max($676,667, $1,148,000) = $1,148,000
```

**Doubling volatility roughly doubles EEPE** — because the range of possible stock prices widens in both directions, but since exposure is floored at zero (we only count upside scenarios), the expected upside grows with variance. This is the **convexity of exposure to volatility**, and it is precisely why the Basel Committee requires stress testing against historical crisis periods.

---

## Appendix B: End-to-End Numeric Example

### Portfolio: 3 trades, no CSA

```
Trade 1: EQ, Notional = 10,000,000, Direction = +1
Trade 2: IR, Notional = 25,000,000, Direction = −1
Trade 3: FX, Notional = 5,000,000,  Direction = +1

Parameters: σ_EQ = 20%, κ=10%, θ=4.5%, σ_IR=1.5%
Scenarios: 4,000 (2,000 base + 2,000 antithetic)
Time steps: 52 weekly steps
```

**Step-by-step output (illustrative):**

```
1. Simulate 4,000 × 52 paths per risk factor
2. Compute net MtM = MtM_EQ + MtM_IR + MtM_FX per scenario per time step
3. Exposure = max(Net MtM, 0)

4. EE(t) at t=0.25yr ≈ 450,000
   EE(t) at t=0.50yr ≈ 620,000
   EE(t) at t=1.00yr ≈ 580,000   ← can decrease (trade maturity effects)

5. EEE(t=0.25) = 450,000
   EEE(t=0.50) = 620,000
   EEE(t=1.00) = 620,000          ← locked at previous peak

6. EPE  = mean(EE)  over 52 steps ≈ 510,000
   EEPE = mean(EEE) over 52 steps ≈ 580,000    ← higher than EPE

7. EAD_IMM = 1.4 × 580,000 = 812,000

8. Stressed EAD (σ_EQ = 40%):
   Stressed EEPE ≈ 950,000
   Stressed EAD  = 1.4 × 950,000 = 1,330,000

9. CVA (CDS = 50bp, RR = 40%):
   λ = 0.005 / 0.60 = 0.00833
   CVA ≈ 12,400

10. RWA = 812,000 × 1.0 × 12.5 × 0.08 = 812,000
```

---

*This document was auto-generated from the PROMETHEUS `imm.py` source code and reflects the implementation as of April 2026. Regulatory references are to the Basel Framework (bis.org/basel_framework) CRE53 standard effective 1 January 2023.*

---

## Appendix C: Monte Carlo Simulation Walk-Through — Interest Rate Trade

> **Purpose:** Illustrate how the Hull-White 1-Factor model simulates future interest rate paths and how exposure is derived for a plain vanilla Interest Rate Swap (IRS) — the most common OTC derivative in any G-SIB trading book.

---

### C.1 The Trade

> **Product:** Interest Rate Swap (IRS) — Pay Fixed / Receive Floating  
> **Notional:** USD 25,000,000  
> **Direction:** −1 (bank pays fixed, receives LIBOR — a "payer swap")  
> **Maturity:** 5 years (exposure horizon: 1 year per IMM convention)  
> **Initial Rate (r₀):** 5.00%  
> **Fixed Coupon Rate:** 5.00% (at-the-money at inception → MtM = 0 at t=0)  
> **Duration at inception:** 4.5 years (approximate)

**What does "exposure" mean for this trade?**

The bank pays a fixed 5% coupon and receives floating LIBOR. If rates **rise** above 5%, the floating leg pays more than the fixed leg — the swap is in-the-money for the bank (positive MtM). If the counterparty defaults when rates are high, the bank loses that positive mark-to-market value.

If rates **fall**, the swap is out-of-the-money for the bank — it is paying above-market. Counterparty default in that scenario is no loss to the bank (it walks away from an unfavourable position).

---

### C.2 The Hull-White Model — How Rates Are Simulated

Unlike equities (which can grow unboundedly), interest rates are mean-reverting — they tend to drift back toward a long-run equilibrium. The **Hull-White 1-Factor model** captures this:

```
Continuous SDE:
  dr = κ(θ − r) dt + σᵣ dW

Discretised:
  r(t+dt) = r(t) + κ × (θ − r(t)) × dt + σᵣ × √dt × Z

Parameters:
  κ  = 0.10   (mean reversion speed — pulls rate back at 10% per year)
  θ  = 0.045  (long-run equilibrium rate = 4.5%)
  σᵣ = 0.015  (rate volatility = 1.5% per year)
  r₀ = 0.050  (initial short rate = 5.0%)
  dt = 1/52   (weekly steps)
```

**Key difference from GBM:** Mean reversion means extreme rate moves are dampened over time. A rate that spikes to 8% will be pulled back toward 4.5% — rates do not "random-walk" to infinity.

---

### C.3 Six Illustrative Rate Scenarios (%)

```
Scenario | 3m (t=13) | 6m (t=26) | 9m (t=39) | 12m (t=52) | Outcome
──────────────────────────────────────────────────────────────────────
  #1      |   5.80%   |   6.40%   |   6.90%   |   7.20%    | Strong rise — payer wins
  #2      |   5.30%   |   5.60%   |   5.50%   |   5.70%    | Modest rise
  #3      |   4.90%   |   4.70%   |   4.80%   |   4.60%    | Slight fall — near-flat
  #4      |   4.20%   |   3.80%   |   3.50%   |   3.30%    | Falling rate environment
  #5      |   6.10%   |   5.20%   |   4.50%   |   4.40%    | Spike then reversion
  #6      |   3.80%   |   3.20%   |   2.80%   |   2.50%    | Severe rate drop (ZIRP shock)
──────────────────────────────────────────────────────────────────────
```

**Visualisation of rate paths:**

```
Rate (%)
  7.20% |                              ● (Sc.1)
  6.90% |                   ● (Sc.1)
  6.40% |          ● (Sc.1)
  6.10% |          ● (Sc.5)
  5.80% |  ● (Sc.1)
  5.70% |                              ● (Sc.2)
  5.60% |          ● (Sc.2)
  5.50% |                   ● (Sc.2)
  5.30% |  ● (Sc.2)
  5.00% |  r₀ ─────────────────────────────── (at-the-money)
  4.90% |  ● (Sc.3)         ● (Sc.3)
  4.60% |                              ● (Sc.3)
  4.50% |                   ● (Sc.5)   ● (Sc.5)
  4.40% |
  4.20% |  ● (Sc.4)
  3.80% |  ● (Sc.6)         ● (Sc.4)
  3.50% |                   ● (Sc.4)
  3.30% |                              ● (Sc.4)
  3.20% |          ● (Sc.6)
  2.80% |                   ● (Sc.6)
  2.50% |                              ● (Sc.6)
        └──────────────────────────────────────► Time
           0      3m      6m      9m     12m

  ── mean reversion pulls all paths back toward θ = 4.5% over time
```

---

### C.4 Converting Rate Paths to Mark-to-Market

For an IRS the MtM is computed via **bond price change** using duration and convexity:

```
Δr(t, i)       = r(t, i) − r₀          (rate change from inception)
P(r)           = 1 − duration × Δr + 0.5 × convexity × (Δr)²
convexity      = 0.05 × duration² / 100
duration       = 4.5 years (at inception)

MtM(t, i) = Notional × direction × [P(r(t,i)) − 1]
           = $25,000,000 × (−1) × [−4.5 × Δr + 0.5 × 0.010125 × Δr²]
```

**For a pay-fixed swap, direction = −1:** When rates rise (Δr > 0), the bond price falls, but the bank's position (receiving the fallen fixed-rate bond value) gains → positive MtM.

**MtM Table (USD):**

```
Scenario | Δr@3m    | MtM@3m      | Δr@6m    | MtM@6m      | Δr@12m   | MtM@12m
────────────────────────────────────────────────────────────────────────────────────
  #1      | +0.80%  | +$900,000   | +1.40%  | +$1,575,000  | +2.20%  | +$2,457,500
  #2      | +0.30%  | +$337,500   | +0.60%  | +$675,000    | +0.70%  | +$787,500
  #3      | −0.10%  | −$112,500   | −0.30%  | −$337,500    | −0.40%  | −$450,000
  #4      | −0.80%  | −$900,000   | −1.20%  | −$1,350,000  | −1.70%  | −$1,912,500
  #5      | +1.10%  | +$1,237,500 | +0.20%  | +$225,000    | −0.60%  | −$675,000
  #6      | −1.20%  | −$1,350,000 | −1.80%  | −$2,025,000  | −2.50%  | −$2,812,500
────────────────────────────────────────────────────────────────────────────────────
```

> **Direction logic for pay-fixed:** When rates rise by 0.80% (Sc.1 at 3m), the bank is paying below-market. The swap's MtM = +$900k — a gain to the bank. Counterparty default here is costly.

---

### C.5 Exposure, EE, EEE, EPE, EEPE, PFE

**Exposure = max(MtM, 0):**

```
Scenario | Exposure@3m  | Exposure@6m   | Exposure@9m  | Exposure@12m
──────────────────────────────────────────────────────────────────────
  #1      | $900,000    | $1,575,000    | $2,160,000   | $2,457,500
  #2      | $337,500    |   $675,000    |   $787,500   |   $787,500
  #3      |       $0    |         $0    |         $0   |         $0
  #4      |       $0    |         $0    |         $0   |         $0
  #5      | $1,237,500  |   $225,000    |         $0   |         $0
  #6      |       $0    |         $0    |         $0   |         $0
──────────────────────────────────────────────────────────────────────
```

**EE (average across 6 scenarios):**

```
EE(3m)  = ($900k + $337.5k + $0 + $0 + $1,237.5k + $0) / 6  = $412,500
EE(6m)  = ($1,575k + $675k + $0 + $0 + $225k + $0) / 6      = $412,500
EE(9m)  = ($2,160k + $787.5k + $0 + $0 + $0 + $0) / 6       = $491,250
EE(12m) = ($2,457.5k + $787.5k + $0 + $0 + $0 + $0) / 6     = $540,833
```

**EEE (non-decreasing ratchet):**

```
EEE(3m)  = $412,500   (= EE — initialised)
EEE(6m)  = max($412,500, $412,500) = $412,500   (flat)
EEE(9m)  = max($491,250, $412,500) = $491,250   (rises)
EEE(12m) = max($540,833, $491,250) = $540,833   (rises further)
```

**Scalar Metrics:**

```
EPE     = ($412.5k + $412.5k + $491.25k + $540.83k) / 4  ≈ $464,271
EEPE    = ($412.5k + $412.5k + $491.25k + $540.83k) / 4  ≈ $464,271
EAD_IMM = 1.4 × $464,271 ≈ $649,979

PFE(3m)  = $1,237,500   (Scenario 5 — rate spike)
PFE(6m)  = $1,575,000   (Scenario 1 — sustained rise)
PFE(12m) = $2,457,500   (Scenario 1 — rising rate environment)
```

---

### C.6 Key Insight — IRS Exposure Profile Shape

```
Exposure
 $2.5M |                              ◇ PFE(12m)
 $1.6M |          ◇ PFE(6m)
 $1.2M |  ◇ PFE(3m)
       |
 $541k |                              ● EEE(12m)
 $491k |                   ● EEE(9m)
 $464k |  ══════════════════════════  EEPE ≈ $464k
 $412k |  ●──────────●  EEE(3m)=EEE(6m)
 $412k |  ◆          ◆  EE(3m)=EE(6m)   ◆ EE(9m)    ◆ EE(12m)
       └──────────────────────────────────────────────────────► Time
          3m          6m              9m            12m
```

**IRS-specific observation:** The exposure profile for a payer swap is **hump-shaped** — it rises as rates have time to move away from inception, then falls as the trade approaches maturity (fewer remaining coupons). This hump is less visible here (1-year window) but becomes critical for 10-year swaps. The EEE ratchet ensures the peak of the hump is always preserved in the capital calculation.

**Stressed scenario (σᵣ = 3.0%, double):**

```
Stressed EEPE ≈ $780,000
Stressed EAD  = 1.4 × $780,000 = $1,092,000
Capital EAD   = max($649,979, $1,092,000) = $1,092,000
```

---

## Appendix D: Monte Carlo Simulation Walk-Through — FX Trade

> **Purpose:** Illustrate how a Foreign Exchange Forward is simulated and how its exposure profile differs from equity and interest rate trades — notably its **linearly growing** exposure profile.

---

### D.1 The Trade

> **Product:** FX Forward — Bank buys EUR, sells USD at maturity  
> **Notional:** USD 5,000,000 (≡ EUR 4,545,455 at spot rate 1.10)  
> **Direction:** +1 (long EUR / short USD — bank benefits when EUR strengthens)  
> **Maturity:** 1 year  
> **Initial FX Spot Rate (S₀):** 1.10 USD per EUR  
> **Forward Rate (K):** 1.10 (at-the-money forward at inception)  
> **Volatility (σ_FX):** 20% per annum  
> **Drift (μ):** 5% (risk-neutral drift under covered interest parity)

**What does "exposure" mean for this trade?**

The bank has locked in buying EUR at 1.10. If EUR appreciates to 1.25, the bank buys cheap — the forward is worth +$681,818 (MtM gain). If the counterparty defaults, the bank cannot execute the favourable forward and loses that amount.

If EUR depreciates to 0.95, the bank must buy EUR expensively — but if the counterparty defaults, the bank simply cancels the forward and buys EUR at spot (a benefit). **Loss = zero**.

---

### D.2 GBM for FX — Same Formula, Different Interpretation

```
FX Rate paths follow GBM (covered interest parity drift):
  S(t+dt) = S(t) × exp[(μ − σ²/2)×dt + σ×√dt × Z]

Parameters:
  S₀  = 1.10  (USD/EUR spot)
  σ   = 0.20  (20% annual FX vol)
  μ   = 0.05  (5% drift — approximation)
  K   = 1.10  (forward strike = current spot, at-the-money)
  dt  = 1/52
```

The **FX forward MtM** at time t is the present value of the expected payoff at maturity:

```
MtM(t, i) = Notional_USD × (S(t,i) − K) / K
           = $5,000,000 × (S(t,i) − 1.10) / 1.10
```

This simplification treats the forward as equivalent to a long FX spot position for exposure purposes (consistent with CRE53 for 1-year horizon).

---

### D.3 Six FX Rate Scenarios (USD/EUR)

```
Scenario | 3m       | 6m       | 9m       | 12m      | Outcome
────────────────────────────────────────────────────────────────
  #1      |  1.17   |  1.22   |  1.29   |  1.35    | Strong EUR rally
  #2      |  1.13   |  1.15   |  1.18   |  1.16    | Moderate EUR gain
  #3      |  1.09   |  1.11   |  1.08   |  1.10    | Flat / sideways
  #4      |  1.05   |  1.00   |  0.96   |  0.93    | EUR weakens steadily
  #5      |  1.20   |  1.08   |  1.02   |  1.05    | Flash rally then reversal
  #6      |  0.98   |  0.88   |  0.82   |  0.76    | EUR crash (risk-off shock)
────────────────────────────────────────────────────────────────
```

**Visualisation:**

```
FX Rate (USD/EUR)
  1.35 |                              ● (Sc.1 — EUR strong)
  1.29 |                   ● (Sc.1)
  1.22 |          ● (Sc.1)
  1.20 |          ● (Sc.5)
  1.18 |                   ● (Sc.2)
  1.17 |  ● (Sc.1)
  1.16 |                              ● (Sc.2)
  1.13 |  ● (Sc.2)
  1.11 |          ● (Sc.3)
  1.10 |  S₀/K ──────────────────────────── ● (Sc.3)
  1.09 |  ● (Sc.3)
  1.08 |                   ● (Sc.3)         ● (Sc.5)
  1.05 |  ● (Sc.4)                          ● (Sc.5)
  1.02 |                   ● (Sc.5)
  1.00 |          ● (Sc.4)
  0.98 |  ● (Sc.6)
  0.96 |                   ● (Sc.4)
  0.93 |                              ● (Sc.4)
  0.88 |          ● (Sc.6)
  0.82 |                   ● (Sc.6)
  0.76 |                              ● (Sc.6 — EUR crash)
       └──────────────────────────────────────────────► Time
          0      3m      6m       9m      12m
```

---

### D.4 MtM, Exposure, EE, EEE and Key Metrics

**MtM Table (USD):**

```
Scenario | MtM@3m       | MtM@6m       | MtM@9m       | MtM@12m
─────────────────────────────────────────────────────────────────────
  #1      | +$318,182   | +$545,455   | +$863,636   | +$1,136,364
  #2      | +$136,364   | +$227,273   | +$363,636   |   +$272,727
  #3      | −$45,455    |   +$45,455  | −$90,909    |           $0
  #4      | −$227,273   | −$454,545   | −$636,364   |   −$772,727
  #5      | +$454,545   | −$90,909    | −$363,636   |   −$227,273
  #6      | −$545,455   | −$1,000,000 | −$1,272,727 | −$1,545,455
─────────────────────────────────────────────────────────────────────
```

**Exposure = max(MtM, 0):**

```
EE(3m)  = ($318k + $136k + $0 + $0 + $454.5k + $0) / 6  = $151,515
EE(6m)  = ($545k + $227k + $45.5k + $0 + $0 + $0) / 6   = $136,290
EE(9m)  = ($864k + $364k + $0 + $0 + $0 + $0) / 6       = $204,545
EE(12m) = ($1,136k + $273k + $0 + $0 + $0 + $0) / 6     = $234,848
```

**EEE (ratchet applied):**

```
EEE(3m)  = $151,515
EEE(6m)  = max($136,290, $151,515) = $151,515   ← EE fell — ratchet holds!
EEE(9m)  = max($204,545, $151,515) = $204,545
EEE(12m) = max($234,848, $204,545) = $234,848
```

> **Ratchet in action:** EE actually **fell** at 6m (Scenario 5's spike had already reversed). Without the EEE ratchet, the bank would appear to have lower exposure at 6m — which would reduce capital. The non-decreasing constraint prevents this.

**Scalar Metrics:**

```
EPE     ≈ ($151.5k + $136.3k + $204.5k + $234.8k) / 4 ≈ $181,788
EEPE    ≈ ($151.5k + $151.5k + $204.5k + $234.8k) / 4 ≈ $185,563
EAD_IMM = 1.4 × $185,563 ≈ $259,788

PFE(3m)  = $454,545    (Scenario 5 — flash rally)
PFE(6m)  = $545,455    (Scenario 1 — sustained EUR rally)
PFE(12m) = $1,136,364  (Scenario 1 — EUR at 1.35)
```

---

### D.5 Key Insight — FX Exposure Profile Shape

```
Exposure
 $1.14M |                              ◇ PFE(12m)
 $545k  |          ◇ PFE(6m)
 $454k  |  ◇ PFE(3m)
        |
 $235k  |                              ● EEE(12m)
 $205k  |                   ● EEE(9m)
 $186k  |  ══════════════════════════  EEPE ≈ $186k
 $152k  |  ●─────────●  EEE(3m)=EEE(6m) (ratchet held flat)
 $152k  |  ◆         ●  EE(3m) > EE(6m) ← dip captured by ratchet
        └──────────────────────────────────────────────────────► Time
           3m          6m            9m            12m
```

**FX-specific observation:** FX forwards have a naturally **increasing exposure profile** — the further into the future, the wider the range of possible exchange rates (GBM dispersion grows as √t). This is why large FX forward books are capital-intensive even when they appear hedged on a notional basis. The EEE ratchet is particularly important when short-dated FX spikes reverse, as seen in Scenario 5.

**Stressed scenario (σ_FX = 40%):**

```
Stressed EEPE ≈ $315,000
Stressed EAD  = 1.4 × $315,000 = $441,000
Capital EAD   = max($259,788, $441,000) = $441,000
```

---

## Appendix E: Monte Carlo Simulation Walk-Through — Commodity Trade

> **Purpose:** Illustrate how a commodity forward (e.g., oil) is simulated under GBM. Commodity trades are characterised by **higher base volatility** (30%) and pronounced **seasonal/supply-shock dynamics** that make the stressed capital charge significantly higher than other asset classes.

---

### E.1 The Trade

> **Product:** Commodity Forward — Long Oil (bank receives oil price return)  
> **Underlying:** Crude Oil (Brent) forward  
> **Notional:** USD 8,000,000  
> **Direction:** +1 (long — bank benefits if oil price rises)  
> **Initial Price (S₀):** 80 USD/barrel (reference price — normalised)  
> **Forward Price (K):** 80 (at-the-money at inception)  
> **Volatility (σ):** 30% per annum (higher than equity — reflects supply/geopolitical risk)  
> **Drift (μ):** 5%

**What does "exposure" mean for this trade?**

If oil rises to $100/barrel (+25%), the forward is worth +$2,000,000 to the bank. If the counterparty (e.g., oil producer hedge counterparty) defaults, the bank loses $2,000,000.

If oil crashes to $60 (−25%), the counterparty would owe the bank nothing — the bank can re-hedge at spot.

---

### E.2 GBM for Commodities — Higher Volatility

```
S(t+dt) = S(t) × exp[(μ − σ²/2)×dt + σ×√dt × Z]

Parameters:
  S₀  = 80    (USD/barrel, normalised)
  σ   = 0.30  (30% annual vol — higher than equity/FX)
  μ   = 0.05
  K   = 80    (at-the-money forward strike)
  dt  = 1/52

MtM(t, i) = Notional × (S(t,i) − K) / K
           = $8,000,000 × (S(t,i) − 80) / 80
```

---

### E.3 Six Oil Price Scenarios (USD/barrel)

```
Scenario | 3m     | 6m     | 9m     | 12m    | Outcome
───────────────────────────────────────────────────────────────
  #1      |  90   |  100   |  112   |  120   | Supply disruption — sustained rally
  #2      |  85   |   88   |   92   |   89   | Moderate gain
  #3      |  78   |   82   |   76   |   80   | Flat / range-bound
  #4      |  72   |   65   |   58   |   55   | Demand shock — bear market
  #5      | 105   |   78   |   70   |   72   | Geopolitical spike then reversal
  #6      |  65   |   52   |   45   |   40   | Severe crash (demand collapse)
───────────────────────────────────────────────────────────────
```

**Visualisation:**

```
Oil Price (USD/bbl)
  120 |                              ● (Sc.1)
  112 |                   ● (Sc.1)
  105 |  ● (Sc.5 — geopolitical spike)
  100 |          ● (Sc.1)
   92 |                   ● (Sc.2)
   90 |  ● (Sc.1)
   89 |                              ● (Sc.2)
   88 |          ● (Sc.2)
   85 |  ● (Sc.2)
   82 |          ● (Sc.3)
   80 |  K/S₀ ──────────────────────────── ● (Sc.3)
   78 |  ● (Sc.3)         ● (Sc.5)
   76 |                   ● (Sc.3)
   72 |  ● (Sc.4)                          ● (Sc.5)
   70 |                   ● (Sc.5)
   65 |  ● (Sc.6)                          ● (Sc.4)
   58 |                   ● (Sc.4)
   55 |                              ● (Sc.4)
   52 |          ● (Sc.6)
   45 |                   ● (Sc.6)
   40 |                              ● (Sc.6)
      └──────────────────────────────────────────► Time
         0      3m      6m      9m      12m
```

---

### E.4 MtM, Exposure, and Metrics

**MtM Table (USD):**

```
Scenario | MtM@3m       | MtM@6m       | MtM@9m       | MtM@12m
──────────────────────────────────────────────────────────────────────
  #1      | +$1,000,000 | +$2,000,000 | +$3,200,000 | +$4,000,000
  #2      |   +$500,000 |   +$800,000 | +$1,200,000 |   +$900,000
  #3      |   −$200,000 |   +$200,000 |   −$400,000 |           $0
  #4      |   −$800,000 | −$1,500,000 | −$2,200,000 | −$2,500,000
  #5      | +$2,500,000 |   −$200,000 |   −$1,000,000|   −$800,000
  #6      | −$1,500,000 | −$2,800,000 | −$3,500,000 | −$4,000,000
──────────────────────────────────────────────────────────────────────
```

**Exposure = max(MtM, 0):**

```
EE(3m)  = ($1,000k + $500k + $0 + $0 + $2,500k + $0) / 6  = $666,667
EE(6m)  = ($2,000k + $800k + $200k + $0 + $0 + $0) / 6    = $500,000
EE(9m)  = ($3,200k + $1,200k + $0 + $0 + $0 + $0) / 6     = $733,333
EE(12m) = ($4,000k + $900k + $0 + $0 + $0 + $0) / 6       = $816,667
```

**EEE (ratchet):**

```
EEE(3m)  = $666,667
EEE(6m)  = max($500,000, $666,667) = $666,667   ← ratchet holds (EE fell)
EEE(9m)  = max($733,333, $666,667) = $733,333
EEE(12m) = max($816,667, $733,333) = $816,667
```

**Scalar Metrics:**

```
EPE     ≈ ($666.7k + $500k + $733.3k + $816.7k) / 4 ≈ $679,167
EEPE    ≈ ($666.7k + $666.7k + $733.3k + $816.7k) / 4 ≈ $720,833
EAD_IMM = 1.4 × $720,833 ≈ $1,009,167

PFE(3m)  = $2,500,000   (Sc.5 — geopolitical spike)
PFE(6m)  = $2,000,000   (Sc.1)
PFE(12m) = $4,000,000   (Sc.1 — sustained rally)
```

---

### E.5 Key Insight — Commodity Exposure is Higher and More Volatile

```
Exposure
 $4.0M |                              ◇ PFE(12m)
 $2.5M |  ◇ PFE(3m — geopolitical spike)
 $2.0M |          ◇ PFE(6m)
       |
 $817k |                              ● EEE(12m)
 $733k |                   ● EEE(9m)
 $721k |  ══════════════════════════  EEPE ≈ $721k
 $667k |  ●─────────●  EEE(3m)=EEE(6m)  (ratchet held — EE dipped at 6m)
       |  ◆         ▼ EE(6m) fell to $500k ← Sc.5 spike reversed
       └──────────────────────────────────────────────────────► Time
          3m          6m            9m            12m
```

**Commodity-specific observations:**

- **Higher base exposure:** EEPE of $721k on $8M notional (9.0% exposure/notional ratio) vs. ~4.8% for FX — direct consequence of 30% vs 20% volatility
- **Spike-and-reversal risk:** Scenario 5 shows a geopolitical spike to $105 creating a massive short-term exposure ($2.5M PFE) that quickly reverses. Without the ratchet, EEE would incorrectly fall. The ratchet preserves this in the capital base.
- **Stressed scenario impact:** Doubling vol from 30% to 60% creates near-quadratic increase in EEPE (variance of GBM grows as σ²)

**Stressed scenario (σ = 60%):**

```
Stressed EEPE ≈ $1,380,000
Stressed EAD  = 1.4 × $1,380,000 = $1,932,000
Capital EAD   = max($1,009,167, $1,932,000) = $1,932,000
```

---

## Appendix F: Monte Carlo Simulation Walk-Through — Credit Derivative Trade

> **Purpose:** Illustrate how a Credit Default Swap (CDS) is simulated. CDS exposure is unique — it is driven by **credit spread movements**, not price levels, and the MtM formula uses duration rather than simple price ratios. This is the most complex and often most misunderstood asset class in CCR calculations.

---

### F.1 The Trade

> **Product:** CDS — Bank bought protection (long protection / short credit risk)  
> **Reference Entity:** Single-name corporate credit (e.g., Investment-Grade corporate)  
> **Notional:** USD 10,000,000  
> **Direction:** +1 (long protection — bank benefits if spreads widen, i.e., credit deteriorates)  
> **Initial Spread (s₀):** 100bp (1.00%)  
> **Duration (D):** 4.0 years (proxy for present value of protection leg)  
> **CDS Spread Volatility:** 50% per annum (high — reflects jump-to-default and rating migration)  
> **Drift (μ):** 5%

**What does "exposure" mean for this trade?**

The bank paid a 100bp premium to buy protection. If the reference entity's credit deteriorates and spreads widen to 250bp, the CDS can be sold for a profit — it is worth more than what was paid. The MtM gain is the bank's exposure if the CDS counterparty (protection seller) defaults.

If spreads tighten to 50bp (credit improved), the CDS is worth less. If the counterparty defaults in this scenario, the bank simply loses a slightly more expensive hedge — but no mark-to-market gain is at risk.

**The double-default risk:** What makes credit derivatives unique is the potential **wrong-way risk** — the CDS counterparty (protection seller) may be most likely to default precisely when the reference entity's credit is deteriorating. This is why credit trades have the highest correlation to the market factor in the PROMETHEUS model.

---

### F.2 CDS Spread Simulation — GBM on Spreads

```
Spread paths follow GBM (spreads are strictly positive, log-normal is appropriate):
  s(t+dt) = s(t) × exp[(μ − σ²/2)×dt + σ×√dt × Z]

Parameters:
  s₀  = 0.0100  (100bp initial spread)
  σ   = 0.50    (50% annual spread vol — high, reflecting jump risk)
  μ   = 0.05    (drift)
  D   = 4.0     (CDS duration in years)
  dt  = 1/52

MtM(t, i) = Notional × direction × D × (s(t,i) − s₀)
           = $10,000,000 × (+1) × 4.0 × (s(t,i) − 0.0100)

Note: MtM is positive (gain) when spreads WIDEN (credit deteriorates)
      MtM is negative (loss) when spreads TIGHTEN (credit improves)
```

---

### F.3 Six CDS Spread Scenarios (basis points)

```
Scenario | 3m (bp) | 6m (bp) | 9m (bp) | 12m (bp) | Outcome
────────────────────────────────────────────────────────────────────
  #1      |  145    |  185    |  240    |  300     | Credit deterioration (fallen angel)
  #2      |  115    |  125    |  135    |  128     | Moderate widening
  #3      |   95    |  105    |   90    |  100     | Flat / oscillating
  #4      |   80    |   65    |   55    |   50     | Strong credit improvement
  #5      |  200    |  110    |   85    |   95     | Idiosyncratic spike then recovery
  #6      |   60    |   42    |   35    |   28     | Dramatic tightening (re-rating event)
────────────────────────────────────────────────────────────────────
```

**Visualisation of spread paths:**

```
CDS Spread (bp)
  300 |                              ● (Sc.1 — fallen angel)
  240 |                   ● (Sc.1)
  200 |  ● (Sc.5 — idiosyncratic spike)
  185 |          ● (Sc.1)
  145 |  ● (Sc.1)
  135 |                   ● (Sc.2)
  128 |                              ● (Sc.2)
  125 |          ● (Sc.2)
  115 |  ● (Sc.2)
  110 |          ● (Sc.5)
  105 |          ● (Sc.3)
  100 |  s₀ ────────────────────────────── ● (Sc.3)
   95 |  ● (Sc.3)          ● (Sc.5)
   90 |                   ● (Sc.3)
   85 |                   ● (Sc.5)
   80 |  ● (Sc.4)                          ● (Sc.5)
   65 |          ● (Sc.4)
   60 |  ● (Sc.6)
   55 |                   ● (Sc.4)
   50 |                              ● (Sc.4)
   42 |          ● (Sc.6)
   35 |                   ● (Sc.6)
   28 |                              ● (Sc.6)
      └──────────────────────────────────────────── ► Time
         0      3m      6m       9m      12m

  Scenarios above 100bp = positive MtM (bank's long protection position gains)
  Scenarios below 100bp = negative MtM (protection cheapened — bank would not lose if c/p defaults)
```

---

### F.4 MtM, Exposure and Metrics

**MtM Formula:**
```
MtM(t,i) = $10,000,000 × 4.0 × (s(t,i) − 0.0100)
```

**MtM Table (USD):**

```
Scenario | Δs@3m    | MtM@3m      | Δs@6m    | MtM@6m      | Δs@12m   | MtM@12m
────────────────────────────────────────────────────────────────────────────────────
  #1      | +45bp   | +$1,800,000 | +85bp   | +$3,400,000  | +200bp  | +$8,000,000
  #2      | +15bp   |   +$600,000 | +25bp   | +$1,000,000  |  +28bp  | +$1,120,000
  #3      |  −5bp   |   −$200,000 |  +5bp   |   +$200,000  |    0bp  |           $0
  #4      | −20bp   |   −$800,000 | −35bp   | −$1,400,000  |  −50bp  | −$2,000,000
  #5      | +100bp  | +$4,000,000 | +10bp   |   +$400,000  |   −5bp  |   −$200,000
  #6      | −40bp   | −$1,600,000 | −58bp   | −$2,320,000  |  −72bp  | −$2,880,000
────────────────────────────────────────────────────────────────────────────────────
```

**Exposure = max(MtM, 0):**

```
EE(3m)  = ($1,800k + $600k + $0 + $0 + $4,000k + $0) / 6  = $1,066,667
EE(6m)  = ($3,400k + $1,000k + $200k + $0 + $400k + $0) / 6 = $833,333
EE(9m)  = ($5,600k + $1,400k + $0 + $0 + $0 + $0) / 6     = $1,166,667
EE(12m) = ($8,000k + $1,120k + $0 + $0 + $0 + $0) / 6     = $1,520,000
```

**EEE (ratchet):**

```
EEE(3m)  = $1,066,667
EEE(6m)  = max($833,333, $1,066,667) = $1,066,667   ← ratchet holds (EE fell!)
EEE(9m)  = max($1,166,667, $1,066,667) = $1,166,667
EEE(12m) = max($1,520,000, $1,166,667) = $1,520,000
```

> **Ratchet is critical here:** EE fell at 6m because Scenario 5's spike (200bp) had already partially reversed. The EEE non-decreasing constraint ensures the capital base does not decrease when an idiosyncratic spike starts unwinding — exactly the credit deterioration scenario regulators are most concerned about.

**Scalar Metrics:**

```
EPE     ≈ ($1,067k + $833k + $1,167k + $1,520k) / 4 ≈ $1,146,667
EEPE    ≈ ($1,067k + $1,067k + $1,167k + $1,520k) / 4 ≈ $1,205,000
EAD_IMM = 1.4 × $1,205,000 ≈ $1,687,000

PFE(3m)  = $4,000,000   (Sc.5 — idiosyncratic spike to 200bp)
PFE(6m)  = $3,400,000   (Sc.1 — sustained deterioration)
PFE(12m) = $8,000,000   (Sc.1 — fallen angel scenario → 300bp)
```

---

### F.5 Key Insight — CDS Exposure Profile and Wrong-Way Risk

```
Exposure
 $8.0M |                              ◇ PFE(12m) — fallen angel
 $4.0M |  ◇ PFE(3m) — idiosyncratic spike
 $3.4M |          ◇ PFE(6m)
       |
 $1.52M|                              ● EEE(12m)
 $1.21M|                   ● EEE(9m)
 $1.21M|  ══════════════════════════  EEPE ≈ $1.21M
 $1.07M|  ●─────────●  EEE(3m) = EEE(6m)  (ratchet held — EE dipped at 6m)
 $833k |            ◆  EE(6m) fell ← Sc.5 idiosyncratic spike reversed
       └──────────────────────────────────────────────────────► Time
          3m          6m            9m            12m
```

**CDS-specific observations:**

**1. Highest EEPE/Notional ratio of all asset classes:**

| Asset Class | Notional    | EEPE        | EEPE/Notional |
|---|---|---|---|
| Equity TRS  | $10,000,000 | $483,333    | 4.8% |
| IRS (Pay Fixed) | $25,000,000 | $464,271 | 1.9% |
| FX Forward  | $5,000,000  | $185,563    | 3.7% |
| Commodity Forward | $8,000,000 | $720,833 | 9.0% |
| **CDS (Long Protection)** | **$10,000,000** | **$1,205,000** | **12.1%** |

CDS has the highest EEPE/notional ratio — driven by 50% spread volatility and the **jump-to-default** dynamics where spreads can move from 100bp to 300bp+ in a single event.

**2. Wrong-Way Risk (WWR) — the unique CDS danger:**

```
Scenario: Reference entity starts deteriorating (spreads widen from 100bp to 300bp)
  → Bank's CDS position gains $8M in MtM
  → BUT: the CDS counterparty (protection seller) is likely also a financial institution
  → Financial institutions are correlated with each other (EQ-CR correlation = 0.50 in PROMETHEUS)
  → As credit spreads widen, the CDS counterparty's own CDS spread is widening too
  → The probability of CDS counterparty default is HIGHEST at exactly the moment exposure is HIGHEST

This is Wrong-Way Risk: correlation between counterparty PD and trade exposure.
CRE53.16 requires specific treatment. PROMETHEUS captures this via the
correlation matrix (credit factor loaded 0.60 on market factor).
```

**3. CVA for a CDS position:**

```
CVA = (1 − RR) × Σ EE(t) × PD_ctp(t) × D(t)
    = 0.60 × Σ EE(t) × PD_ctp(t) × exp(−0.03 × t)

If counterparty CDS spread = 80bp:
  λ_ctp = 0.0080 / 0.60 = 0.01333
  PD(1yr) = 1 − exp(−0.01333) ≈ 1.32%
  CVA ≈ 0.60 × $1,146,667 × 0.0132 ≈ $9,083

This is the premium the bank should theoretically charge the CDS counterparty
for bearing their credit risk on this protection-buying position.
```

**Stressed scenario (σ_spread = 100%, double the base):**

```
Stressed EEPE ≈ $2,100,000
Stressed EAD  = 1.4 × $2,100,000 = $2,940,000
Capital EAD   = max($1,687,000, $2,940,000) = $2,940,000
```

---

## Appendix G: Cross-Asset Comparison — All Five Trade Types

### G.1 Summary Table — All Metrics at a Glance

| Trade | Asset Class | Notional | Model | Base Vol | EEPE | EAD_IMM | Stressed EAD | PFE(12m) |
|---|---|---|---|---|---|---|---|---|
| Equity TRS (Long) | EQ | $10M | GBM | 20% | $483k | $677k | $1,148k | $3,000k |
| IRS (Pay Fixed) | IR | $25M | Hull-White | 1.5% | $464k | $650k | $1,092k | $2,458k |
| FX Forward (Long EUR) | FX | $5M | GBM | 20% | $186k | $260k | $441k | $1,136k |
| Commodity Forward (Long Oil) | CMDTY | $8M | GBM | 30% | $721k | $1,009k | $1,932k | $4,000k |
| CDS (Long Protection) | CR | $10M | GBM (spread) | 50% | $1,205k | $1,687k | $2,940k | $8,000k |

### G.2 EEPE as % of Notional — Capital Intensity by Asset Class

```
Asset Class     | EEPE / Notional | Driver
────────────────────────────────────────────────────────────────────
IRS             |     1.9%        | Low IR vol (1.5%), mean reversion dampens extremes
FX Forward      |     3.7%        | Medium vol (20%), but linear payoff grows with √t
Equity TRS      |     4.8%        | GBM with 20% vol, no mean reversion
Commodity Fwd   |     9.0%        | Higher vol (30%), supply shock spikes
CDS Prot.       |    12.1%        | Highest vol (50%), jump-to-default, wrong-way risk
────────────────────────────────────────────────────────────────────
```

### G.3 The Role of the EEE Ratchet — When It Mattered

| Trade | Did EE Fall Mid-Life? | EEE Ratchet Effect | Capital Impact |
|---|---|---|---|
| Equity TRS | No — EE grew monotonically | Minimal | EEPE ≈ EPE |
| IRS (Pay Fixed) | Minimal | Small uplift at 6m | EEPE ≈ EPE |
| FX Forward | **Yes — EE fell at 6m** (Sc.5 spike reversed) | Ratchet held EEE flat | EEPE > EPE by ~2% |
| Commodity Forward | **Yes — EE fell at 6m** (Sc.5 spike reversed) | Ratchet preserved $667k | EEPE > EPE by ~6% |
| CDS (Long Prot.) | **Yes — EE fell at 6m** (Sc.5 idiosyncratic) | Ratchet preserved $1,067k | EEPE > EPE by ~5% |

### G.4 Key Takeaway for the CRO

```
The three levers that drive EAD under IMM:

  1. Volatility (σ):    Higher vol → wider distribution → higher EE → higher EEPE
                        Commodity (30%) and Credit (50%) are the most capital-intensive

  2. EEE Ratchet:       Prevents capital from falling when short-lived spikes reverse
                        Most impactful for instruments with high short-term vol
                        (CDS, Commodity) that tend to spike-and-revert

  3. Alpha (×1.4):      A flat 40% supervisory loading on all asset classes
                        Compensates for model uncertainty, wrong-way risk,
                        and concentration risk not fully captured in EEPE

EAD_IMM = 1.4 × EEPE — this single formula links every Monte Carlo path,
every scenario, every time step back to one regulatory capital number.
```


---

*This document was auto-generated from the PROMETHEUS `imm.py` source code and reflects the implementation as of April 2026. Regulatory references are to the Basel Framework (bis.org/basel_framework) CRE53 standard effective 1 January 2023.*
