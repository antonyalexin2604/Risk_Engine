#!/usr/bin/env python3
"""Write CVA Sensitivities Technical Guide"""

content = """# CVA Sensitivities Technical Guide
## SA-CVA Full Sensitivities Implementation (MAR50.43-77)
### PROMETHEUS Risk Platform

---

## Table of Contents

1. Overview and Regulatory Basis
2. SA-CVA Sensitivity Structure
3. Six Delta Risk Classes
4. Five Vega Risk Classes
5. Cross-Risk-Class Aggregation (MAR50.44 Table 4)
6. Integration with IMM and AAD
7. Data Structures Reference
8. Glossary

**Appendix A** — CCSR Delta: Interest Rate Swap Counterparty
**Appendix B** — GIRR Delta: CVA Sensitivity to SOFR Curve
**Appendix C** — Equity Delta: TRS Counterparty
**Appendix D** — Cross-Risk-Class Aggregation Example
**Appendix E** — AAD vs Bump-and-Reprice

---

## 1. Overview and Regulatory Basis

This module implements the **complete SA-CVA sensitivity calculation** across all six delta
risk classes and five vega risk classes required by MAR50.43-77.

The base CVA engine (`cva.py`) implements the dominant risk class — Counterparty Credit
Spread Risk (CCSR) delta. This module extends that with the remaining five delta risk classes
and all five vega risk classes, enabling full SA-CVA compliance for complex derivative books.

| MAR50 Section | Topic |
|---|---|
| MAR50.43 | Six delta risk classes for SA-CVA |
| MAR50.44 | Cross-risk-class correlation matrix (Table 4) |
| MAR50.45 | Five vega risk classes (no CCSR vega) |
| MAR50.47 | Sensitivity computation methods |
| MAR50.48 | Vega is ALWAYS material — must be computed |
| MAR50.49 | RW_vega = 100% for all vega risk classes |
| MAR50.52 | Hedging disallowance parameter R = 0.01 |
| MAR50.53 | Bucket-level aggregation with R |
| MAR50.63 | Sector bucket Table 5 |
| MAR50.65 | Risk weights Table 7 by sector and IG/HY/NR |

---

## 2. SA-CVA Sensitivity Structure

SA-CVA capital is computed as:

    Capital_SA_CVA = Capital_Delta + Capital_Vega

where each component aggregates across risk classes using cross-risk-class correlations.

### 2.1 Sensitivity Definition (MAR50.47)

A sensitivity is the first-order change in CVA value per unit change in a risk factor:

    s_k = dCVA / dr_k

Sensitivity computation methods:
1. **AAD (Adjoint Algorithmic Differentiation):** Computes exact gradients in O(n) time
   rather than O(n) bump-and-reprice calls. Preferred for production.
2. **Bump-and-reprice:** Shift each risk factor by 1bp (or 1%) and revalue CVA.
   Computationally expensive but simple to implement.
3. **Closed-form approximation:** For the CCSR class, the formula dCVA/ds_i = EAD x M_eff x LGD
   provides a tractable approximation.

### 2.2 Weighted Sensitivity

    WS_ik = RW_k x s_ik

where RW_k is the supervisory risk weight for risk factor k (from MAR50.65 Table 7).

### 2.3 Capital per Bucket

    K_b = sqrt(max(Sum WS_k^2 + Sum_{k!=l} rho_kl x WS_k x WS_l, 0))

### 2.4 Capital per Risk Class

    K_rc = sqrt(Sum K_b^2 + Sum_{b!=c} gamma_bc x K_b x K_c)

---

## 3. Six Delta Risk Classes (MAR50.43)

### 3.1 Interest Rate (GIRR) — dCVA/dr

CVA is sensitive to interest rates through:
- The discount factor DF(t) = exp(-r x t) in the CVA integral
- Expected Exposure EE(t) depends on IR for IRS and floating-rate products

    delta_ir_k = dCVA / d(r_k)   [per SOFR/OIS tenor bucket]

    CVA_approx = Sum_t PD(t) x LGD x EE(t) x DF(t)
    dCVA/dr_k = -Sum_t PD(t) x LGD x EE(t) x t_k x DF(t)   [for tenor k]

Risk weights: Same GIRR table as FRTB (MAR50 references MAR21.44 Table 2).

### 3.2 FX — dCVA/dFX_spot

For cross-currency portfolios, CVA is sensitive to FX rates through:
- EAD in reporting currency changes when FX moves
- Discount factors in foreign currency

    delta_fx = dCVA / d(FX_spot)
             ~ CVA x notional_foreign / FX_spot   [first-order approximation]

Risk weights: Same FX RW table as FRTB (MAR50 references MAR21 FX table).

### 3.3 Counterparty Credit Spread (CCSR) — dCVA/ds_counterparty

This is the dominant risk class — implemented in the base cva.py engine.

    delta_ccsr = dCVA / d(s_counterparty)
               ~ EAD x M_eff x LGD   [Basel closed-form approximation]

Risk weights: MAR50.65 Table 7 (sector bucket x IG/HY/NR).

See CVA_TECHNICAL_GUIDE.md for full detail on CCSR implementation.

### 3.4 Reference Credit Spread (RCSR) — dCVA/ds_reference

For banks that sell CDS protection on third-party reference entities, the bank has reference
credit spread risk: if the reference entity's spread widens, the CDS protection the bank sold
gains value — and the bank's net CVA position changes.

    delta_rcsr = dCVA / d(s_reference_entity)

RCSR risk weights are the same as CCSR (Table 7 by sector/credit quality).

Correlation between CCSR and RCSR: 0.60 (Table 4) — they are related but not identical risks.

### 3.5 Equity — dCVA/dS_equity

For equity swap and equity option counterparties, CVA depends on equity prices through EE:

    delta_eq = dCVA / d(S_equity)
             ~ (dEE/dS) x LGD x PD x DF   [per counterparty equity exposure]

Risk weights: Same equity bucket RW as FRTB (MAR21.74 Table 6).

### 3.6 Commodity — dCVA/dC_commodity

For commodity swap counterparties:

    delta_cmdty = dCVA / d(C_commodity_k)   [per commodity/tenor bucket]

Risk weights: Same commodity RW as FRTB (MAR21.88 Table 10).

---

## 4. Five Vega Risk Classes (MAR50.45, MAR50.48)

**Critical requirement (MAR50.48):** Vega is ALWAYS material in SA-CVA, even without explicit
option hedges. This is because vega arises from the volatility parameters in the exposure
simulation model itself — Hull-White sigma_r for IRS, Black-Scholes sigma_eq for equity
derivatives. Banks cannot set vega to zero.

No CCSR vega per MAR50.45 — counterparty spread itself has no vega class in SA-CVA.

### 4.1 GIRR Vega — dCVA/d(sigma_IR)

From the Hull-White (or LMM) model used in exposure simulation:

    vega_girr_k = dCVA / d(sigma_IR_k)   [per vol tenor/expiry bucket]

Arises when the exposure model uses stochastic interest rates. Even for simple IRS portfolios
with no explicit option hedges, the CVA path value depends on IR vol for convexity.

RW_vega = 100% (MAR50.49)

### 4.2 FX Vega — dCVA/d(sigma_FX)

For cross-currency portfolios with FX optionality:

    vega_fx = dCVA / d(sigma_FX)

RW_vega = 100%

### 4.3 Reference Credit Spread Vega — dCVA/d(sigma_spread)

For counterparties with CDS option hedges or where the exposure model simulates stochastic
credit spreads:

    vega_rcsr = dCVA / d(sigma_CDS_spread)

RW_vega = 100%

### 4.4 Equity Vega — dCVA/d(sigma_equity)

For equity derivative counterparties:

    vega_eq = dCVA / d(sigma_equity)

Arises from the Black-Scholes vol used in equity exposure simulation.

RW_vega = 100%

### 4.5 Commodity Vega — dCVA/d(sigma_commodity)

For commodity derivative counterparties:

    vega_cmdty = dCVA / d(sigma_commodity)

RW_vega = 100%

---

## 5. Cross-Risk-Class Aggregation (MAR50.44 Table 4)

SA-CVA capital aggregates across the six delta risk classes using a supervisory correlation
matrix that captures the co-movement between different risk types.

### Correlation Matrix (MAR50.44 Table 4)

Risk class order: [GIRR, FX, CCSR, RCSR, EQ, CMDTY]

    GIRR  FX    CCSR  RCSR  EQ    CMDTY
    1.00  0.30  0.40  0.35  0.20  0.15   GIRR
    0.30  1.00  0.25  0.20  0.35  0.30   FX
    0.40  0.25  1.00  0.60  0.45  0.20   CCSR
    0.35  0.20  0.60  1.00  0.40  0.25   RCSR
    0.20  0.35  0.45  0.40  1.00  0.35   EQ
    0.15  0.30  0.20  0.25  0.35  1.00   CMDTY

### Economic Interpretation

| Pair | Correlation | Rationale |
|---|---|---|
| CCSR-RCSR | 0.60 | Counterparty and reference credit spreads move together in credit stress |
| CCSR-EQ | 0.45 | Credit and equity are correlated in market-wide stress (risk-off) |
| CCSR-GIRR | 0.40 | Flight-to-quality during credit stress drives IR lower |
| FX-EQ | 0.35 | Equity and FX are correlated in EM stress |
| CMDTY-EQ | 0.35 | Commodity and equity linked through macro growth expectations |
| GIRR-FX | 0.30 | Interest rate differentials drive FX |
| GIRR-CMDTY | 0.15 | Weak connection between rates and commodity prices |

### Aggregation Formula

    Total_Delta = sqrt(Sum_i K_i^2 + Sum_{i!=j} rho_ij x K_i x K_j)

where K_i is the capital for risk class i.

---

## 6. Integration with IMM and AAD

### Production Implementation Path

SA-CVA with all six delta risk classes requires integration with the exposure simulation
model (IMM engine). The recommended production implementation:

**Step 1: Monte Carlo Path Generation (IMM engine)**

    Generate N paths of all risk factors: {r(t), s(t), FX(t), S_eq(t), C_cmdty(t)}

**Step 2: CVA Pathwise Computation**

    For each path w, counterparty c:
      CVA_c(w) = LGD_c x Sum_t [ PD_c(t) x EE_c(t,w) x DF(t,w) ]

**Step 3: AAD Sensitivity Extraction**

    For each risk factor k:
      s_k = (1/N) x Sum_w [ dCVA_c(w)/dk ]   [expected sensitivity across paths]

AAD computes all sensitivities simultaneously in O(N) time rather than O(N x n_factors)
for bump-and-reprice.

**Step 4: Risk Weight Application and Aggregation**

    WS_k = RW_k x s_k
    K_b, K_rc computed as above

### Collateral in Sensitivity Computation

For margined netting sets, sensitivity computation must account for the CSA:

    dCVA/dk = d/dk [integral PD(t) x LGD x max(EE(t) - IM(t)/DF(t), 0) dt]

The IM(t) collateral reduces EE but is also sensitive to risk factors — particularly GIRR
(IM is typically a function of current exposure which depends on rates).

---

## 7. Data Structures Reference

### CVASensitivities

| Field | Type | Description |
|---|---|---|
| counterparty_id | str | Unique counterparty identifier |
| girr_delta | Dict[str, float] | GIRR delta per tenor: {tenor: sensitivity} |
| fx_delta | Dict[str, float] | FX delta per currency pair |
| ccsr_delta | float | CCSR delta (scalar for single counterparty) |
| rcsr_delta | Dict[str, float] | RCSR delta per reference entity |
| eq_delta | Dict[str, float] | Equity delta per underlying |
| cmdty_delta | Dict[str, float] | Commodity delta per commodity type |
| girr_vega | Dict[tuple, float] | GIRR vega per (expiry, tenor) bucket |
| fx_vega | Dict[str, float] | FX vega per currency pair |
| rcsr_vega | Dict[str, float] | Reference spread vega per entity |
| eq_vega | Dict[str, float] | Equity vega per underlying |
| cmdty_vega | Dict[str, float] | Commodity vega per type |
| computation_method | str | 'AAD' / 'BUMP_REPRICE' / 'CLOSED_FORM' |
| as_of_date | date | Sensitivity calculation date |

### SACVACapitalResult

| Field | Description |
|---|---|
| total_capital | Total SA-CVA capital (delta + vega) |
| delta_by_risk_class | Capital attribution by risk class |
| vega_by_risk_class | Vega capital by risk class |
| dominant_risk_class | Risk class with highest capital contribution |
| hedging_disallowance | Amount of capital from R=0.01 disallowance |

---

## 8. Glossary

| Term | Definition |
|---|---|
| SA-CVA | Standardised Approach for CVA |
| CCSR | Counterparty Credit Spread Risk |
| RCSR | Reference Credit Spread Risk |
| GIRR | General Interest Rate Risk |
| AAD | Adjoint Algorithmic Differentiation |
| WS | Weighted Sensitivity = RW x s |
| R | Hedging disallowance parameter = 0.01 (MAR50.52) |
| RW_vega | Vega risk weight = 100% for all classes (MAR50.49) |
| EE(t) | Expected Exposure at time t (from IMM paths) |
| IMM | Internal Models Method (stochastic exposure simulation) |
| CSA | Credit Support Annex (collateral agreement) |

---

## Appendix A — CCSR Delta: IRS Counterparty

**Setup:** Bank A (Financials, IG), EAD = USD 50M, 3Y maturity, CDS spread = 85bps, LGD = 60%.

CCSR is the primary CVA risk for most OTC derivative portfolios.

    spread   = 85 / 10000 = 0.0085
    M_eff    = (1 - exp(-0.043 x 3)) / (0.043 x 3) = 0.9380
    LGD      = 0.60

    delta_ccsr = EAD x M_eff x LGD
               = 50,000,000 x 0.9380 x 0.60
               = USD 28,140,000   [USD per unit spread]

    RW_ccsr (Financials, IG, Bucket 2) = 1.0%

    WS_ccsr = 0.010 x 28,140,000 = USD 281,400

    rwa_ccsr = 281,400 x 12.5 = USD 3,517,500

---

## Appendix B — GIRR Delta: CVA Sensitivity to SOFR Curve

**Setup:** Same Bank A IRS portfolio. CVA depends on SOFR curve through discount factors.

First-order GIRR sensitivity (per 1bp bump of SOFR):

    delta_girr_3Y = dCVA / d(SOFR_3Y)

For a fixed-maturity, CCSR-dominated portfolio, the GIRR sensitivity approximation:

    delta_girr_t = -PD(t) x LGD x EE(t) x t x DF(t)

For t = 3Y, DF(3Y) = exp(-0.043 x 3) = 0.8788:

    Approximate dCVA/d(SOFR_3Y) = -0.02 x 0.60 x 50,000,000 x 3 x 0.8788
                                 = USD -1,582,800   [negative: higher rates -> lower CVA]

    WS_girr = RW_3Y x |delta_girr| = 0.012 x 1,582,800 = USD 18,994

    rwa_girr = 18,994 x 12.5 = USD 237,425

This is approximately 7% of the CCSR contribution — confirming CCSR dominates for most
plain vanilla IRS portfolios. GIRR becomes material for long-dated portfolios and when the
bank uses extensive IR risk management.

---

## Appendix C — Equity Delta: TRS Counterparty

**Setup:** Counterparty B is a hedge fund with whom the bank has a total return swap (TRS)
on a tech stock index. EAD = USD 20M, credit quality HY (BB rating), sector = Technology.

    delta_eq = dCVA / d(S_tech_index)
             ~ (dEE/dS) x LGD x PD x DF   [first-order]

If EE scales linearly with tech index (TRS), dEE/dS ~ EAD / S_tech:

    delta_eq ~ (20,000,000 / 5000) x 0.60 x 0.03 x 0.88
             ~ 4000 x 0.0158
             ~ USD 63.2 per index point

    For 100-point shock on index:
    delta_eq_100pt = USD 6,320

    RW_eq (Technology, HY, Bucket 5) = 5.5% (Table 7)
    WS_eq = 0.055 x 6,320 = USD 347.6

Equity contribution is typically small relative to CCSR for TRS counterparties unless the
portfolio is very large or dominated by equity-sensitive instruments.

---

## Appendix D — Cross-Risk-Class Aggregation

**Portfolio:** Three counterparties contributing to different risk classes.

    K_GIRR  = USD 237,425   (from Appendix B)
    K_CCSR  = USD 281,400   (from Appendix A)
    K_EQ    = USD 347.6     (from Appendix C, scaled)

For simplicity, assume K_RCSR = K_FX = K_CMDTY = 0.

### Aggregation

    Total_Delta = sqrt(K_GIRR^2 + K_CCSR^2 + K_EQ^2 +
                       2 x rho_GIRR_CCSR x K_GIRR x K_CCSR +
                       2 x rho_GIRR_EQ   x K_GIRR x K_EQ   +
                       2 x rho_CCSR_EQ   x K_CCSR x K_EQ)

    = sqrt(237425^2 + 281400^2 + 348^2 +
           2 x 0.40 x 237425 x 281400 +
           2 x 0.20 x 237425 x 348 +
           2 x 0.45 x 281400 x 348)

    = sqrt(56,410,830,625 + 79,185,960,000 + 121,104 +
           53,544,960,000 + 33,074,880 + 88,055,280)

    = sqrt(189,262,901,889)

    ~ USD 435,044

    RWA = 435,044 x 12.5 = USD 5,438,050

For comparison: CCSR-only RWA = USD 3,517,500. Including GIRR adds USD 1.9M (55% increase).
The rho_GIRR_CCSR = 0.40 correlation means GIRR and CCSR do not fully diversify away.

---

## Appendix E — AAD vs Bump-and-Reprice

### Computational Complexity Comparison

For N = 100,000 paths, n_factors = 500 risk factors per counterparty, 200 counterparties:

| Method | Total Valuations | Approximate Time |
|---|---|---|
| Bump-and-reprice | N x n_factors x 200 = 10 billion | Days |
| AAD | N x 200 (single forward + backward pass) | Minutes |

### AAD Algorithm for CVA

    Forward pass:  Compute CVA_c(path) and build computation graph
    Backward pass: Propagate dL/dCVA_c = 1 backward through graph
                   Extract dCVA_c/dr_k for all risk factors k simultaneously

### Production Recommendation

1. Implement AAD in the Monte Carlo exposure engine (IMM)
2. Extract sensitivities at the path level; aggregate to portfolio level
3. Apply RW and bucket aggregation per MAR50
4. Combine CCSR (closed-form from cva.py) with AAD-derived GIRR/FX/EQ/CMDTY sensitivities

The closed-form CCSR approximation in cva.py remains valid as a baseline; full AAD
replaces it for the complete SA-CVA implementation.
"""

with open('/docs/Requirements/CVA_SENSITIVITIES_TECHNICAL_GUIDE.md', 'w') as f:
    f.write(content)
print("CVA Sensitivities guide written successfully.")

