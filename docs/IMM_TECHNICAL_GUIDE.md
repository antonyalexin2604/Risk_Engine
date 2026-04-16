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

## Appendix: End-to-End Numeric Example

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

