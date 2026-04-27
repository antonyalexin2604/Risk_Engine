# PROMETHEUS — Advanced Internal Ratings-Based Approach (A-IRB)
## Technical Reference: Capital Formula, RWA Drivers & All Functional Terms

**Regulatory Basis:** Basel III CRE30–CRE36 (effective January 2023)  
**Engine File:** `backend/engines/a_irb.py`  
**Prepared:** April 2026

---

## Table of Contents

1. [What Is A-IRB?](#1-what-is-a-irb)
2. [The A-IRB Calculation Pipeline](#2-the-a-irb-calculation-pipeline)
3. [The Basel Capital Formula — CRE31.4](#3-the-basel-capital-formula--cre314)
4. [Asset Correlation R — CRE31.5](#4-asset-correlation-r--cre315)
5. [Maturity Adjustment — CRE31.7](#5-maturity-adjustment--cre317)
6. [Credit Risk Mitigation (CRM) — CRE32](#6-credit-risk-mitigation-crm--cre32)
7. [Expected Loss and Provisions — CRE35](#7-expected-loss-and-provisions--cre35)
8. [Double-Default Framework — CRE22](#8-double-default-framework--cre22)
9. [Macroeconomic Overlay (Pillar 2 / ICAAP)](#9-macroeconomic-overlay-pillar-2--icaap)
10. [Dynamic Correlation Model (Pillar 2)](#10-dynamic-correlation-model-pillar-2)
11. [Stressed vs. Baseline Regime](#11-stressed-vs-baseline-regime)
12. [ESG / Climate Transition Risk — CRR3 Art. 87a](#12-esg--climate-transition-risk--crr3-art-87a)
13. [SA Output Floor — CRE20.4 / Basel IV](#13-sa-output-floor--cre204--basel-iv)
14. [Sensitivity Analysis — RWA Greeks](#14-sensitivity-analysis--rwa-greeks)
15. [Live Macro Data Feed — USMacroDataFeed](#15-live-macro-data-feed--usmacrodatafeed)
16. [Configuration Parameters](#16-configuration-parameters)
17. [Complete Glossary](#17-complete-glossary)
18. [Appendix A: Step-by-Step Numeric Example — Corporate Loan (No CRM)](#appendix-a-step-by-step-numeric-example--corporate-loan-no-crm)
19. [Appendix B: Numeric Example — Collateralised Real Estate Loan](#appendix-b-numeric-example--collateralised-real-estate-loan)
20. [Appendix C: Numeric Example — Guaranteed Exposure (Split-K Method)](#appendix-c-numeric-example--guaranteed-exposure-split-k-method)
21. [Appendix D: Numeric Example — Retail Mortgage Portfolio](#appendix-d-numeric-example--retail-mortgage-portfolio)
22. [Appendix E: Numeric Example — SME Corporate with CDS Double-Default](#appendix-e-numeric-example--sme-corporate-with-cds-double-default)
23. [Appendix F: Cross-Asset Comparison — All Asset Classes](#appendix-f-cross-asset-comparison--all-asset-classes)

---

## 1. What Is A-IRB?

The **Advanced Internal Ratings-Based (A-IRB) Approach** is the most sophisticated of the three Basel III credit-risk capital frameworks. It permits banks to use their own internally estimated risk parameters — subject to supervisory approval — to calculate minimum Pillar 1 capital requirements for Banking Book credit exposures.

### Why G-SIBs Use A-IRB

| Approach | PD | LGD | EAD | Capital Sensitivity |
|---|---|---|---|---|
| **Standardised (SA)** | Supervisor-assigned risk weights | Fixed | Fixed | Blunt; no obligor differentiation |
| **Foundation IRB (F-IRB)** | Bank estimates | Supervisor-prescribed | Supervisor-prescribed | Moderate |
| **Advanced IRB (A-IRB)** | **Bank estimates** | **Bank estimates** | **Bank estimates** | **Highest precision; maximum capital efficiency** |

A-IRB is **only applicable to the Banking Book** (loans, revolvers, guarantees, mortgages). Trading book exposures use CCR/IMM frameworks.

**Regulatory scope** (CRE30–CRE36):

| Standard | Content |
|---|---|
| CRE30 | IRB overview and asset-class definitions |
| CRE31 | Corporate/Bank/Sovereign risk-weight formula |
| CRE32 | Credit Risk Mitigation (collateral, guarantees, CDS) |
| CRE33 | Retail IRB (mortgage, revolving, other) |
| CRE35 | Expected Loss and Provisions treatment |
| CRE36 | LGD and EAD estimation standards |

---

## 2. The A-IRB Calculation Pipeline

Every exposure flows through these steps in the PROMETHEUS engine:

```
Banking Book Exposure (BankingBookExposure)
         │
         ▼
┌─────────────────────────────────────────────┐
│  Step 1: Input Validation & PD Resolution   │
│  • Validate PD ∈ [0,1], LGD ∈ [0,1], EAD≥0 │
│  • Apply PD floor (0.03% for corp/bank)     │
│  • Resolve PD from term structure if set    │
│  • CRE31.8: Cap M at 1Y for margined trades │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 2: ESG / Climate PD Uplift (CRR3)     │
│  • PD += brown_factor × uplift_rate         │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 3: Market Regime Stress (if enabled)  │
│  • PD × pd_stress_factor[asset_class]       │
│  • LGD × lgd_stress_factor[asset_class]     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 4: Credit Risk Mitigation Chain       │
│  (A) Retail deposit netting → EAD reduction │
│  (B) Funded collateral → LGD* (CRE32.10)   │
│  (C) Guarantee → Split-K (CRE32.24 FIX-04) │
│  (D) CDS → Double-default PD (CRE22.10)    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 5: Asset Correlation R (CRE31.5)      │
│  • R_regulatory = Basel formula (Pillar 1)  │
│  • R_internal   = sector/conc overlay (P2)  │
│  • Capital always uses R_regulatory         │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 6: Maturity Adjustment b (CRE31.7)    │
│  • b(PD) = (0.11852 − 0.05478×ln(PD))²     │
│  • Retail: b = 0, M = 1Y (no adj)          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 7: Capital Requirement K (CRE31.4)    │
│  • K = [LGD×N(z) − PD×LGD] × MA           │
│  • z = (N⁻¹(PD) + √R×N⁻¹(0.999))/√(1-R)  │
│  • MA = (1+(M-2.5)×b)/(1-1.5×b)           │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 8: RWA = K × 12.5 × EAD              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 9: EL and Provisions (CRE35)          │
│  • EL = PD × LGD × EAD                     │
│  • Shortfall = max(EL − Provisions, 0)      │
│  • Shortfall deducted from CET1             │
│  • Excess (up to 0.6% RWA) added to Tier 2 │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Step 10: SA Output Floor (CRE20.4)         │
│  • Floor = 72.5% × SA RWA                  │
│  • If IRB RWA < floor → binding uplift      │
└──────────────────┘
```

---

## 3. The Basel Capital Formula — CRE31.4

This is the **single most important equation** in the entire A-IRB framework. It converts PD, LGD, maturity, and asset correlation into a capital requirement K (expressed as a fraction of EAD).

### 3.1 The Full Formula

```
Step 1 — Vasicek conditional default probability:
  z = [N⁻¹(PD) + √R × N⁻¹(0.999)] / √(1 − R)

Step 2 — Capital before maturity adjustment:
  K_base = LGD × N(z) − PD × LGD

Step 3 — Maturity adjustment:
  MA = (1 + (M − 2.5) × b) / (1 − 1.5 × b)
  b  = (0.11852 − 0.05478 × ln(PD))²

Step 4 — Final capital requirement:
  K = K_base × MA

Step 5 — Risk-Weighted Assets:
  RWA = K × 12.5 × EAD
```

### 3.2 What Each Term Means

| Symbol | Meaning | Typical Values |
|---|---|---|
| **PD** | Probability of Default in 1 year | 0.03% (AAA) to 100% (defaulted) |
| **LGD** | Loss Given Default | 25%–75% (unsecured); 5%–45% (secured) |
| **EAD** | Exposure at Default | Face value of loan / drawn balance |
| **M** | Effective maturity in years | 1–5 years (Basel floor/cap) |
| **R** | Asset correlation | 12%–24% corp; 4% retail revolving |
| **N(·)** | Standard normal CDF | — |
| **N⁻¹(·)** | Inverse normal CDF | N⁻¹(0.999) = 3.0902 |
| **N⁻¹(0.999)** | 99.9th percentile normal | **3.0902** — the Basel confidence level |
| **z** | Conditional default threshold | Drives the tail of the loss distribution |
| **K** | Capital requirement per unit EAD | Typically 1%–20% |
| **12.5** | RWA multiplier = 1/8% | Converts capital to RWA |

### 3.3 Intuition — The Vasicek Model

The formula is derived from the **Vasicek single-factor model**. Every obligor's asset return is driven by:

```
Asset Return = √R × Systematic Factor + √(1−R) × Idiosyncratic Factor

Default when Asset Return < N⁻¹(PD)
```

- **R (correlation):** How much of the obligor's asset value is driven by the common market factor. High R = obligor moves with the economic cycle.
- **N⁻¹(0.999):** Basel fixes the systematic factor at its **99.9th percentile** — a "1-in-1000 year" bad scenario for the economy.
- **z:** The combined threshold. In a worst-case economy, z measures how far into the loss tail we are.
- **N(z):** The conditional default probability — the fraction of the portfolio that defaults in the 99.9% bad economic scenario.
- **LGD × N(z) − PD × LGD:** The unexpected loss (UL) — conditional loss minus expected loss. Capital covers UL.

### 3.4 The Confidence Level — Why 99.9%?

The Basel Committee calibrated the 99.9% confidence level so that well-diversified banking books hold enough capital to survive a **1-in-1,000 year** economic shock. This is equivalent to an approximate A-/BBB+ rating for the banking system itself.

---

## 4. Asset Correlation R — CRE31.5

The asset correlation R determines how much a single obligor's default probability is tied to the systematic economic factor.

### 4.1 Corporate / Bank / Sovereign Formula (CRE31.5)

```
R = 0.12 × (1 − exp(−50×PD)) / (1 − exp(−50))
  + 0.24 × [1 − (1 − exp(−50×PD)) / (1 − exp(−50))]
```

This is a **weighted interpolation** between:
- **0.12** (low-R bound): applies at high PD — distressed obligors are idiosyncratic (their defaults are not strongly correlated with each other)
- **0.24** (high-R bound): applies at low PD — investment-grade obligors are highly correlated with the economic cycle

**Intuition:** A high-quality investment-grade borrower that defaults is almost certainly doing so because of a systemic economic shock (everyone suffers together). A sub-investment-grade borrower that defaults may be doing so for idiosyncratic reasons (bad management, sector-specific issue). Hence low-PD obligors have **higher** R.

### 4.2 Retail Asset Classes

| Asset Class | R | Formula |
|---|---|---|
| **RETAIL_MORT** (Residential Mortgage) | **0.15** (fixed) | CRE31.13 — fixed, no PD dependence |
| **RETAIL_REV** (Revolving Credit — Cards/Overdrafts) | **0.04** (fixed) | CRE31.14 — lowest R; consumer defaults are highly idiosyncratic |
| **RETAIL_OTHER** (Other Retail) | **0.03–0.16** | CRE31.15 — formula with exp(−35×PD) |
| **HVCRE** (High-Volatility CRE) | **0.12–0.30** | CRE31.10 — wider range than standard corp |

### 4.3 SME Adjustment (CRE31.9)

For corporates with annual sales S ∈ (5, 50) million EUR:

```
R_SME = R_corp − 0.04 × (1 − (S − 5) / 45)
```

At S = 5 mEUR: reduction = 0.04 (maximum benefit). At S = 50 mEUR: no reduction.

**Why:** Small firms default more independently of the business cycle than large multinationals — they are less correlated with the systematic factor.

### 4.4 Large Financial Institution Multiplier (CRE31.7)

For regulated FIs with total assets ≥ USD 100bn or any unregulated FI:

```
R_FI = R × 1.25
```

**Why:** Financial institutions are highly interconnected (contagion risk). Their correlation with the systematic factor is higher than a standard corporate of the same PD.

---

## 5. Maturity Adjustment — CRE31.7

Longer-dated exposures carry more risk because there is more time for credit migration (downgrade or default). The maturity adjustment captures this:

```
b(PD) = (0.11852 − 0.05478 × ln(PD))²

MA = (1 + (M − 2.5) × b) / (1 − 1.5 × b)
```

Where:
- **b** = sensitivity of K to maturity — higher for low-PD (IG) obligors (they have more "room to fall")
- **M** = effective maturity in years, floored at 1 year, capped at 5 years (CRE31.7)
- **MA > 1** for M > 2.5 (long-dated loans penalised)
- **MA < 1** for M < 2.5 (short-dated loans benefit)
- **Retail:** b = 0, MA = 1 always (no maturity adjustment for retail)

**CRE31.8 — Daily-margined derivatives:** M is capped at 1 year when `is_margined = True`, dramatically reducing the maturity penalty for OTC derivatives that are daily-variation-margined.

---

## 6. Credit Risk Mitigation (CRM) — CRE32

CRM reduces capital requirements by recognising collateral, guarantees, and CDS. The PROMETHEUS engine applies a four-step CRM chain.

### 6.1 Step A — Retail Deposit Netting (CRE32.63)

Only for retail exposures where a bank holds a deposit from the same borrower:

```
EAD_net = max(EAD − Deposit, 0)
```

### 6.2 Step B — Funded Collateral: LGD* Formula (CRE32.10–13)

When the bank holds financial collateral, receivables, or real estate:

```
SC    = Collateral_Value × (1 − hc)   [credit-risk-adjusted collateral]
E_S   = min(SC, EAD)                  [secured portion]
E_U   = max(EAD − SC, 0)             [unsecured portion]

LGD*  = (E_U / EAD) × LGD_unsecured + (E_S / EAD) × LGD_secured
```

**Collateral parameters by type:**

| Type | LGD_secured | Haircut (hc) | LGD Floor |
|---|---|---|---|
| FINANCIAL (cash, securities) | 0% | 15% | 0% |
| RECEIVABLES | 20% | 40% | 10% |
| RESIDENTIAL_RE | 20% | 40% | **5%** (CRE32.17) |
| COMMERCIAL_RE | 20% | 40% | 10% |
| OTHER_PHYSICAL | 25% | 40% | 15% |

**Key fix (FIX-04 CRE32.13):** The haircut applies to the **collateral value**, not to the exposure. Previous implementations incorrectly inflated EAD by the haircut.

### 6.3 Step C — Guarantee: Split-K Method (CRE32.24–27)

When a third-party guarantee covers a fraction of the exposure:

```
K_covered   = K(PD_guarantor, LGD_guarantor, M, R_guarantor, b_guarantor)
K_uncovered = K(PD_obligor,   LGD_obligor,   M, R_obligor,   b_obligor)

K_blended = Coverage × K_covered + (1 − Coverage) × K_uncovered
```

**Why split-K, not blended PD?** The capital formula K is **non-linear** in PD. Blending PDs before feeding to K produces a different (typically overstated) result compared to computing K separately and then blending.

### 6.4 Step D — CDS Double-Default (CRE22.10)

When a CDS provides protection and both the obligor and the protection seller would need to default simultaneously for the bank to suffer a loss:

```
PD_dd = PD_obligor × (0.15 + 160 × PD_guarantor)
```

This formula recognises that **joint default probability** is far lower than either individual PD. The maximum benefit is floored at `PD_floor` and capped at `PD_obligor` (double-default cannot increase capital).

---

## 7. Expected Loss and Provisions — CRE35

### 7.1 Expected Loss

```
EL = PD × LGD × EAD
```

EL is the **average loss** the bank expects over a 1-year horizon. It is not capital — it should be covered by **loan loss provisions** (accounting reserves).

### 7.2 CET1 Shortfall vs. Tier 2 Excess

Under CRE35, the bank compares EL to its eligible provisions:

```
EL_diff = EL − Eligible Provisions

If EL_diff > 0:    CET1 Deduction = EL_diff           (insufficient provisioning)
If EL_diff < 0:    Tier 2 Add-back = min(|EL_diff|, 0.6% × RWA)
```

Only **Stage 3 (credit-impaired) specific provisions** under IFRS 9 are eligible for this offset. Stage 1 (12-month ECL) and Stage 2 (lifetime ECL, non-impaired) general provisions do not qualify.

**Capital impact:** A bank that is under-provisioned (EL > provisions) must deduct the shortfall from its highest-quality capital (CET1). This directly reduces the CET1 ratio.

---

## 8. Double-Default Framework — CRE22

The double-default formula (CRE22.10) is reproduced here in full:

```
PD_dd = PD_obligor × (0.15 + 160 × PD_guarantor)
```

**Worked example:**

```
PD_obligor   = 2.00%   (BBB-rated corporate)
PD_guarantor = 0.10%   (AA-rated bank guarantee)

PD_dd = 0.02 × (0.15 + 160 × 0.001)
       = 0.02 × (0.15 + 0.16)
       = 0.02 × 0.31
       = 0.62%

Capital reduction: from 2.00% PD to 0.62% PD → significant RWA savings
```

The 0.15 term represents the minimum contribution of the obligor's standalone risk even with a guarantor. The 160 × PD_g term amplifies the guarantor's quality — a higher-rated guarantor provides more benefit.

---

## 9. Macroeconomic Overlay (Pillar 2 / ICAAP)

The `MacroeconomicOverlay` class adjusts PD and LGD based on current market conditions. This is a **Pillar 2 / ICAAP** tool — it never feeds into Pillar 1 regulatory capital.

### 9.1 PD Macro Adjustment

```
PD_adjusted = PD_base × (1 + vix_impact + gdp_impact + default_impact)

vix_impact     = 0.15 × (VIX − 15) / 10
gdp_impact     = −0.20 × (GDP_growth − 2.0%)
default_impact = 0.50 × (credit_default_rate − 2%)

Adjustment factor clamped to [0.5×, 3.0×]
```

**Interpretation:**
- VIX rising from 15 to 25 (a stress event) → PD_adjusted = PD_base × 1.15
- GDP falling from 2% to −1% (a recession) → PD_adjusted = PD_base × 1.60
- Charge-off rate rising from 0.5% to 2% → PD_adjusted = PD_base × 1.75

### 9.2 LGD Macro Adjustment (Frye Effect)

```
LGD_adjusted = LGD_base × (1 + spread_impact + default_impact)

spread_impact  = 0.10 × (HY_spread_bp − 400bp) / 100
default_impact = 0.30 × (credit_default_rate − 2%)

Adjustment factor clamped to [0.7×, 1.5×]
```

**Why LGD rises in crises (Frye effect):** When many borrowers default simultaneously, the market for distressed assets becomes flooded. Recovery values fall because there are too many assets being liquidated at once and too few buyers. This is the **procyclicality** of LGD — PD and LGD are positively correlated in crisis.

### 9.3 Stress Index

The macro conditions are summarised into a composite stress index ∈ [0, 1]:

```
Stress Index = 0.25 × VIX/80 + 0.35 × (HY_spread − 300bp)/1000bp
             + 0.20 × (Unemployment − 3%)/5% + 0.20 × ChargeOff/10%

Regime Classification:
  Stress < 0.30  → NORMAL
  Stress ∈ [0.30, 0.60) → STRESSED
  Stress ≥ 0.60  → CRISIS
```

---

## 10. Dynamic Correlation Model (Pillar 2)

The `DynamicCorrelationModel` provides a regime-dependent view of asset correlation for Pillar 2 / ICAAP stress testing:

| Asset Class | Normal R | Stressed R | Crisis R | CRE31.5 Cap |
|---|---|---|---|---|
| CORP | 0.20 | 0.22 | **0.24** | 0.24 |
| BANK | 0.22 | 0.23 | **0.24** | 0.24 (×1.25 = 0.30 for large FI) |
| SOVEREIGN | 0.14 | 0.17 | 0.20 | 0.24 |
| RETAIL_MORT | 0.15 | 0.15 | 0.15 | Fixed (CRE31.13) |
| RETAIL_REV | 0.04 | 0.04 | 0.04 | Fixed (CRE31.14) |
| RETAIL_OTHER | 0.10 | 0.12 | 0.15 | 0.16 |

**Important:** Even in Pillar 2, all values are capped at the CRE31.5 regulatory ceiling. Previous implementations had crisis values of 0.40–0.85, which were empirically implausible and produced ICAAP capital 3–4× above Pillar 1.

---

## 11. Stressed vs. Baseline Regime

When `use_stressed_params = True`, PD and LGD are multiplied by regime-specific stress factors before the capital formula:

| Asset Class | PD Stress Factor | LGD Stress Factor | Use Case |
|---|---|---|---|
| CORP | 1.5× | 1.2× | Recession / credit cycle downturn |
| BANK | 1.4× | 1.15× | Financial sector stress |
| SOVEREIGN | 1.2× | 1.1× | Sovereign rating deterioration |
| HVCRE | 1.6× | 1.25× | Real estate market correction |
| RETAIL_MORT | 1.3× | 1.25× | House price decline |
| RETAIL_REV | 1.6× | 1.3× | Consumer income shock |
| RETAIL_OTHER | 1.4× | 1.25× | General retail stress |

**HVCRE has the highest stress factor** — reflecting the historical evidence that commercial real estate values can fall 40–60% in severe downturns, dramatically increasing LGD, while default rates spike more than standard corporates.

---

## 12. ESG / Climate Transition Risk — CRR3 Art. 87a

A climate transition risk PD uplift is applied based on the exposure's `climate_brown_factor` (0 = green/neutral, 1 = fully brown/fossil fuel):

```
PD_final = PD_base + brown_factor × uplift_rate[asset_class]
```

| Asset Class | Max PD Uplift (fully brown) |
|---|---|
| CORP | +50bp |
| BANK | +20bp |
| SOVEREIGN | +10bp |
| HVCRE | +80bp (highest — physical risk from stranded assets) |
| RETAIL_MORT | +30bp (flood-zone mortgages) |

This is a regulatory add-on under EU CRR3 Article 87a, reflecting transition risk (carbon taxes, stranded asset risk) and physical risk (climate damage to collateral).

---

## 13. SA Output Floor — CRE20.4 / Basel IV

Under Basel IV (fully phased in from January 2025), IRB RWA cannot be less than 72.5% of the Standardised Approach RWA for the same exposure:

```
Floor RWA  = 72.5% × SA RWA
Floor Binding  = (IRB RWA < Floor RWA)
SA Floor Uplift = max(Floor RWA − IRB RWA, 0)
```

This is the most significant structural change from Basel III to Basel IV for G-SIBs. Banks with historically low IRB RWA ratios (e.g., large mortgage books with internally estimated LGDs of 5–10%) face the largest capital increases from this floor.

---

## 14. Sensitivity Analysis — RWA Greeks

The engine computes sensitivities of RWA to parameter changes using finite differences:

| Sensitivity | Measure | Description |
|---|---|---|
| `rwa_sensitivity_pd` | ΔRWA per +10bp PD | How much capital changes with a 1-notch deterioration |
| `rwa_sensitivity_lgd` | ΔRWA per +5% LGD | Impact of LGD model conservatism or collateral haircut increase |
| `rwa_sensitivity_ead` | ΔRWA per +10% EAD | Impact of CCF changes or undrawn commitment utilisation |

**RWA Attribution (rwa_drivers):**

```
base_rwa              = total RWA from formula
pd_contribution       = fraction of RWA attributable to PD level
lgd_contribution      = fraction attributable to LGD
correlation_internal  = Pillar 2 view (with sector/concentration overlays)
correlation_regulatory = Pillar 1 view (pure Basel formula)
maturity_adjustment   = extra capital due to long maturity
mitigant_benefit      = RWA reduction from CRM (collateral, guarantee, CDS)
```

---

## 15. Live Macro Data Feed — USMacroDataFeed

The `USMacroDataFeed` class provides real-time US macroeconomic data for Pillar 2 / ICAAP overlay calculations. It uses a **three-tier fallback** architecture:

| Tier | Source | Series | Frequency |
|---|---|---|---|
| 1 | Bloomberg BSAPI | VIX, T10Y2Y, HY OAS, Unemployment, GDP | Intraday real-time |
| 2 | FRED (St. Louis Fed) | VIXCLS, T10Y2Y, BAMLH0A0HYM2, UNRATE, A191RL1Q225SBEA, CORBLACBS | Daily close |
| 3 | yfinance | ^VIX, ^TNX−^IRX | 15-min delayed |
| Floor | Hard-coded averages | VIX=20, HY=450bp, Unemployment=4.5%, GDP=2.0% | Static fallback |

**Thread safety:** A single RLock protects the in-memory cache. Concurrent daily batch runs always see a consistent snapshot.

**Caching:** TTL = 3,600 seconds (1 hour) by default. An optional JSON disk cache allows overnight batch runs to share their macro snapshot with intraday processes.

---

## 16. Configuration Parameters

Defined in `backend/config.py` and `AIRBConfiguration`:

| Parameter | Value | Description |
|---|---|---|
| `pd_floor` | **0.0003** (0.03%) | Minimum PD for any non-defaulted exposure (CRE31.5) |
| `lgd_floor_unsecured` | **0.25** (25%) | CRE32.16 senior unsecured LGD floor |
| `maturity_floor` | **1.0 year** | CRE31.7 minimum effective maturity |
| `maturity_cap` | **5.0 years** | CRE31.7 maximum effective maturity |
| `alpha_multiplier` | **1.4** | SA-CCR EAD multiplier (used in CCR, not A-IRB directly) |
| `sa_output_floor_ratio` | **0.725** | 72.5% Basel IV output floor (CRE20.4) |
| `N⁻¹(0.999)` | **3.0902** | Confidence level for Basel capital formula |

---

## 17. Complete Glossary

| Term | Formula / Definition | Regulatory Ref |
|---|---|---|
| **A-IRB** | Advanced Internal Ratings-Based Approach | CRE30 |
| **b(PD)** | Maturity sensitivity: `(0.11852 − 0.05478×ln(PD))²` | CRE31.7 |
| **CET1** | Common Equity Tier 1 — highest quality capital | CRE20 |
| **CRM** | Credit Risk Mitigation — collateral, guarantees, CDS | CRE32 |
| **Double-Default** | `PD_dd = PD_o × (0.15 + 160×PD_g)` | CRE22.10 |
| **EAD** | Exposure at Default — drawn balance / loan amount | CRE30 |
| **EL** | Expected Loss = `PD × LGD × EAD` | CRE35 |
| **EL Shortfall** | `max(EL − Provisions, 0)` → deducted from CET1 | CRE35.2 |
| **EL Excess** | `max(Provisions − EL, 0)` → added to Tier 2 (cap: 0.6% RWA) | CRE35.3 |
| **Frye Effect** | Positive correlation between PD and LGD in downturns | CRE36 |
| **HVCRE** | High Volatility Commercial Real Estate — R ∈ [0.12, 0.30] | CRE31.10 |
| **K** | Capital Requirement per unit EAD (decimal fraction) | CRE31.4 |
| **LGD** | Loss Given Default — fraction of EAD lost if default occurs | CRE36 |
| **LGD*** | LGD adjusted for funded collateral (CRM-adjusted) | CRE32.10 |
| **LGD Floor (unsecured)** | Minimum LGD = **25%** for senior unsecured | CRE32.16 |
| **MA** | Maturity Adjustment = `(1+(M−2.5)×b)/(1−1.5×b)` | CRE31.7 |
| **M** | Effective Maturity ∈ [1, 5] years | CRE31.7 |
| **N(·)** | Cumulative Normal distribution function | — |
| **N⁻¹(0.999)** | Inverse normal at 99.9th percentile = **3.0902** | CRE31.4 |
| **PD** | Probability of Default (1-year horizon) | CRE36 |
| **PD Floor** | Minimum PD = **0.03%** for CORP/BANK/SOV | CRE31.5 |
| **R** | Asset Correlation ∈ [0.12, 0.24] for CORP | CRE31.5 |
| **R_regulatory** | Basel-formula R (Pillar 1 capital — never adjusted) | CRE31.5 |
| **R_internal** | Sector/concentration-adjusted R (Pillar 2 only) | Internal |
| **RWA** | Risk-Weighted Assets = `K × 12.5 × EAD` | CRE20 |
| **SA Output Floor** | IRB RWA ≥ 72.5% × SA RWA (Basel IV) | CRE20.4 |
| **SME Adjustment** | R reduction for sales ∈ (5, 50) mEUR | CRE31.9 |
| **Split-K** | Guarantee capital: `cov×K_g + (1−cov)×K_o` | CRE32.24 |
| **Stress Index** | Composite macro indicator [0,1] for regime classification | Internal |
| **Tier 2** | Second-tier capital (subordinated debt, provisions) | CRE20 |
| **UL** | Unexpected Loss = `K × EAD` — what capital covers | CRE31 |
| **Vasicek Model** | Single-factor model underlying CRE31.4 | Academic |
| **z** | `(N⁻¹(PD) + √R × N⁻¹(0.999)) / √(1−R)` — conditional default threshold | CRE31.4 |

---

## Appendix A: Step-by-Step Numeric Example — Corporate Loan (No CRM)

### The Exposure

> **Obligor:** Investment-grade UK corporate (BBB-rated)  
> **Asset Class:** CORP  
> **EAD:** USD 10,000,000 (a USD 10M term loan, fully drawn)  
> **PD:** 0.50% (0.0050) — consistent with BBB-/Ba1  
> **LGD:** 45% (0.45) — senior unsecured, no collateral  
> **Maturity:** 3 years  
> **Sector:** INDUSTRIALS  
> **SME Sales:** 0 (large corporate — no SME adjustment)  
> **Market Regime:** NORMAL

---

### Step 1: PD Floor Check

```
PD_floor = 0.0003 (0.03%)
PD_eff   = max(0.0050, 0.0003) = 0.0050  (above floor — no change)
LGD_eff  = max(0.45, 0.25)    = 0.45    (above unsecured floor — no change)
M_eff    = 3.0 years                      (within [1, 5])
```

---

### Step 2: Asset Correlation R (CRE31.5)

```
exp(−50 × PD) = exp(−50 × 0.0050) = exp(−0.25) = 0.7788
1 − exp(−50)  ≈ 1.0000   (exp(−50) ≈ 0)

R_base = 0.12 × (1 − 0.7788) / 1.0 + 0.24 × (1 − (1 − 0.7788) / 1.0)
       = 0.12 × 0.2212        + 0.24 × (1 − 0.2212)
       = 0.12 × 0.2212        + 0.24 × 0.7788
       = 0.02654               + 0.18691
       = 0.21345

No SME adjustment (large corporate).
No FI multiplier (not a financial institution).

R_regulatory = 0.2135
```

**Key insight:** At PD = 0.50% (IG), R = 21.4% — relatively high, close to the 24% cap. This IG corporate is strongly correlated with the economic cycle.

---

### Step 3: Maturity Adjustment b and MA

```
b = (0.11852 − 0.05478 × ln(0.0050))²
  = (0.11852 − 0.05478 × (−5.2983))²
  = (0.11852 + 0.29024)²
  = (0.40876)²
  = 0.16708

MA = (1 + (3.0 − 2.5) × 0.16708) / (1 − 1.5 × 0.16708)
   = (1 + 0.5 × 0.16708) / (1 − 0.25062)
   = (1 + 0.08354) / 0.74938
   = 1.08354 / 0.74938
   = 1.4459
```

**Interpretation:** A 3-year maturity increases the capital charge by 44.6% compared to a 2.5-year reference maturity. This reflects the greater credit migration risk over 3 years.

---

### Step 4: Capital Requirement K (CRE31.4)

```
N⁻¹(PD)   = N⁻¹(0.0050) = −2.5758  (5th percentile of normal)
N⁻¹(0.999) = 3.0902

z = (N⁻¹(PD) + √R × N⁻¹(0.999)) / √(1 − R)
  = (−2.5758 + √0.2135 × 3.0902) / √(1 − 0.2135)
  = (−2.5758 + 0.4621 × 3.0902) / √0.7865
  = (−2.5758 + 1.4279) / 0.8869
  = (−1.1479) / 0.8869
  = −1.2948

N(z) = N(−1.2948) = 0.0977   (about 9.77% conditional default probability)

K_base = LGD × N(z) − PD × LGD
       = 0.45 × 0.0977 − 0.0050 × 0.45
       = 0.04397 − 0.00225
       = 0.04172

K = K_base × MA
  = 0.04172 × 1.4459
  = 0.06031   (6.031% of EAD)
```

**Interpretation:**
- In the 99.9% bad economic scenario, 9.77% of the portfolio defaults (N(z))
- Average loss given default = 45%
- Conditional loss = 9.77% × 45% = 4.40% of EAD
- Minus expected loss (0.50% × 45% = 0.225%) = **unexpected loss = 4.17%**
- Multiplied by maturity adjustment (×1.446) = **final K = 6.03%**

---

### Step 5: RWA

```
RWA = K × 12.5 × EAD
    = 0.06031 × 12.5 × $10,000,000
    = $7,538,750

Risk Weight (%) = RWA / EAD = 75.4%
Capital Charge  = K × EAD = 0.06031 × $10,000,000 = $603,100
```

---

### Step 6: Expected Loss and Provisions

```
EL     = PD × LGD × EAD
       = 0.0050 × 0.45 × $10,000,000
       = $22,500

Assume Provisions held = $15,000 (Stage 3 eligible)

EL_diff = $22,500 − $15,000 = +$7,500  (shortfall)

CET1 Deduction = $7,500
```

---

### Summary

```
Input Parameters:
  EAD = $10,000,000    PD = 0.50%    LGD = 45%    M = 3yr

Intermediate Results:
  R       = 0.2135     (21.4% asset correlation)
  b       = 0.16708    (maturity sensitivity)
  MA      = 1.4459     (44.6% maturity uplift)
  z       = −1.2948    (conditional threshold)
  N(z)    = 9.77%      (conditional default probability at 99.9%)

Output:
  K       = 6.03%      (capital per unit EAD)
  RWA     = $7,538,750 (75.4% risk weight)
  EL      = $22,500    (expected loss — for provisioning)
  EL Shortfall = $7,500 → CET1 deduction
```

---

## Appendix B: Numeric Example — Collateralised Real Estate Loan

### The Exposure

> **Product:** Commercial Real Estate loan  
> **Asset Class:** CORP (CRE loan treated as corporate)  
> **EAD:** USD 5,000,000  
> **PD:** 1.00% (0.010) — BB+ rated developer  
> **LGD (unsecured):** 45% (pre-CRM)  
> **Maturity:** 5 years  
> **Collateral:** Commercial Real Estate, value = USD 4,000,000  
> **Collateral Haircut (hc):** 40% (CRE32 COMMERCIAL_RE)  
> **LGD_secured:** 20% (CRE32.12 for commercial real estate)

---

### Step 1: LGD* Calculation (CRE32.10–13)

```
SC    = Collateral × (1 − hc) = $4,000,000 × (1 − 0.40) = $2,400,000
E_S   = min(SC, EAD)          = min($2,400,000, $5,000,000) = $2,400,000
E_U   = max(EAD − SC, 0)      = max($5,000,000 − $2,400,000, 0) = $2,600,000

LGD*  = (E_U / EAD) × LGD_u + (E_S / EAD) × LGD_s
       = ($2,600,000 / $5,000,000) × 0.45 + ($2,400,000 / $5,000,000) × 0.20
       = 0.52 × 0.45 + 0.48 × 0.20
       = 0.2340 + 0.0960
       = 0.3300   (33%)

Floor check: LGD* ≥ 10% (CRE32 COMMERCIAL_RE floor) ✓

LGD_eff = 33%
```

**Capital saved by collateral:** LGD reduced from 45% to 33% — a 12 percentage point reduction.

---

### Step 2–5: K and RWA Calculation

```
PD  = 1.00%,  LGD_eff = 33%,  M = 5.0yr

R = 0.12 × (1 − exp(−0.50)) / 1.0 + 0.24 × (1 − …)
  = 0.12 × 0.3935 + 0.24 × 0.6065
  = 0.04722 + 0.14556
  = 0.1928   (19.3%)

b = (0.11852 − 0.05478 × ln(0.010))²
  = (0.11852 − 0.05478 × (−4.6052))²
  = (0.11852 + 0.25224)²
  = (0.37076)²
  = 0.13746

MA = (1 + (5.0 − 2.5) × 0.13746) / (1 − 1.5 × 0.13746)
   = (1 + 0.34365) / (1 − 0.20619)
   = 1.34365 / 0.79381
   = 1.6929

z = (N⁻¹(0.010) + √0.1928 × 3.0902) / √(1 − 0.1928)
  = (−2.3263 + 0.4391 × 3.0902) / √0.8072
  = (−2.3263 + 1.3565) / 0.8985
  = −0.9698 / 0.8985
  = −1.0793

N(z) = N(−1.0793) = 0.1402   (14.02% conditional default probability)

K_base = 0.33 × 0.1402 − 0.010 × 0.33
       = 0.04627 − 0.00330
       = 0.04297

K = 0.04297 × 1.6929 = 0.07278   (7.28%)
```

---

### Summary

```
                      No CRM         With RE Collateral
PD                    1.00%          1.00%
LGD                   45%            33%           (−12pp from LGD*)
K                     8.59%          7.28%         (−15.2% capital reduction)
RWA                   $5,369,500     $4,549,750    (−$819,750 saved)
Risk Weight           107.4%         91.0%
EL                    $45,000        $33,000       (lower provisioning need)
```

**Collateral efficiency:** USD 4M of commercial real estate (after 40% haircut → $2.4M effective) reduces RWA by $819,750. The "return on collateral" (RWA saved / collateral value) = 20.5%.

---

## Appendix C: Numeric Example — Guaranteed Exposure (Split-K Method)

### The Exposure

> **Obligor:** Mid-cap corporate, PD = 3.00% (BB-rated)  
> **Guarantor:** Investment-grade bank, PD = 0.20% (A-rated)  
> **EAD:** USD 8,000,000  
> **LGD_obligor:** 45% (unsecured senior)  
> **LGD_guarantor:** 45%  
> **Guarantee Coverage:** 60% of EAD  
> **Maturity:** 4 years

---

### Step 1: Compute K_obligor (uncovered portion — 40%)

```
PD_obligor = 3.00%
R_obligor  = 0.12 × (1 − exp(−1.50)) + 0.24 × (1 − …) = 0.1659  (16.6%)
b_obligor  = (0.11852 − 0.05478 × ln(0.030))² = (0.11852 + 0.19118)² = 0.09580
MA_obl     = (1 + (4 − 2.5) × 0.09580) / (1 − 1.5 × 0.09580) = 1.2044

z_obl      = (N⁻¹(0.030) + √0.1659 × 3.0902) / √0.8341
           = (−1.8808 + 1.2586) / 0.9133
           = −0.6815

N(z_obl)   = N(−0.6815) = 0.2478

K_base_obl = 0.45 × 0.2478 − 0.030 × 0.45 = 0.11151 − 0.01350 = 0.09801
K_obligor  = 0.09801 × 1.2044 = 0.11804   (11.80%)
```

---

### Step 2: Compute K_guarantor (covered portion — 60%)

```
PD_guarantor = 0.20%
R_guarantor  = 0.12 × (1 − exp(−0.10)) + 0.24 × (1 − …) = 0.2274  (22.7%)
b_guarantor  = (0.11852 − 0.05478 × ln(0.002))² = (0.11852 + 0.33929)² = 0.20975
MA_gua       = (1 + (4 − 2.5) × 0.20975) / (1 − 1.5 × 0.20975) = 1.5316

z_gua        = (N⁻¹(0.002) + √0.2274 × 3.0902) / √0.7726
            = (−2.8782 + 1.4730) / 0.8790
            = −1.5974

N(z_gua)     = N(−1.5974) = 0.0551

K_base_gua   = 0.45 × 0.0551 − 0.002 × 0.45 = 0.02480 − 0.00090 = 0.02390
K_guarantor  = 0.02390 × 1.5316 = 0.03661   (3.66%)
```

---

### Step 3: Split-K Blending (CRE32.24 — FIX-04)

```
K_blended = Coverage × K_guarantor + (1 − Coverage) × K_obligor
           = 0.60 × 0.03661 + 0.40 × 0.11804
           = 0.02197 + 0.04722
           = 0.06919   (6.92%)
```

---

### Summary — Guarantee Benefit

```
                    No Guarantee    With 60% Guarantee
PD applied          3.00%           60%×0.20% + 40%×3.00% (split)
K                   11.80%          6.92%          (−41.4% capital reduction!)
RWA                 $11,803,200     $6,918,720     (−$4,884,480)
Risk Weight         147.5%          86.5%
```

**Why split-K matters:** If we had incorrectly blended PDs (60%×0.20% + 40%×3.00% = 1.32%) and fed that single PD to K, we would get K ≈ 8.1% — 17% higher than the correct 6.92%. The **non-linearity** of the Vasicek formula means PD blending overstates capital.

---

## Appendix D: Numeric Example — Retail Mortgage Portfolio

### The Exposure

> **Product:** Residential mortgage portfolio (aggregated)  
> **Asset Class:** RETAIL_MORT  
> **EAD:** USD 50,000,000 (portfolio of 500 mortgages, average $100k each)  
> **PD:** 0.80% (weighted average — well-seasoned UK owner-occupier portfolio)  
> **LGD:** 15% (low — first-charge residential mortgage, LTV 65%)  
> **Maturity:** Fixed at 1 year (CRE31.13 — no maturity adjustment for retail)

---

### Key Differences for Retail

- **R = 0.15 (fixed)** — not the PD-dependent corporate formula
- **b = 0, MA = 1** — no maturity adjustment
- **No maturity adjustment** — K formula is simpler

---

### Capital Calculation

```
R  = 0.15 (fixed — CRE31.13)
b  = 0    (retail — no maturity adjustment)
MA = 1.0

N⁻¹(0.0080) = −2.4089
z = (−2.4089 + √0.15 × 3.0902) / √(1 − 0.15)
  = (−2.4089 + 0.3873 × 3.0902) / √0.85
  = (−2.4089 + 1.1962) / 0.9220
  = −1.2127 / 0.9220
  = −1.3152

N(z) = N(−1.3152) = 0.0942   (9.42% conditional default probability)

K_base = LGD × N(z) − PD × LGD
       = 0.15 × 0.0942 − 0.0080 × 0.15
       = 0.01413 − 0.00120
       = 0.01293

K = K_base × MA = 0.01293 × 1.0 = 0.01293   (1.29%)
```

---

### Summary

```
EAD = $50,000,000   PD = 0.80%   LGD = 15%   R = 0.15 (fixed)

K       = 1.29%
RWA     = 0.01293 × 12.5 × $50,000,000 = $8,081,250
Risk Weight = 16.2%
EL      = 0.80% × 15% × $50M = $60,000

Compare to Standardised Approach:
  SA Risk Weight (LTV 65%) = 35%   (CRE20)
  SA RWA = 35% × $50M = $17,500,000

SA Output Floor: 72.5% × $17,500,000 = $12,687,500
IRB RWA = $8,081,250 < Floor = $12,687,500

→ SA Floor IS binding — IRB uplift = $4,606,250
→ Effective RWA = $12,687,500   (floor-constrained)
→ This illustrates why Basel IV significantly impacts retail mortgage books!
```

**Critical insight for the CRO:** The SA output floor (Basel IV) is most impactful for **retail mortgages and other low-risk assets where IRB models generate far lower capital than the SA**. Banks cannot simply argue their internal models justify 16% risk weights when the SA says 35% — the floor sets a binding minimum at 72.5% of SA.

---

## Appendix E: Numeric Example — SME Corporate with CDS Double-Default

### The Exposure

> **Obligor:** UK SME manufacturer, annual sales = €20 million  
> **Asset Class:** CORP  
> **EAD:** USD 3,000,000  
> **PD_obligor:** 2.00% (BB-rated SME)  
> **LGD_obligor:** 45%  
> **Maturity:** 2 years  
> **CDS Protection:** 100% coverage from A-rated bank (PD_guarantor = 0.15%)  
> **CDS LGD:** 45%

---

### Step 1: SME Correlation Adjustment

```
Sales = €20M → S_mEUR = 20 (in range 5–50)

R_base = 0.12 × (1 − exp(−1.0)) + 0.24 × (1 − …)
       = 0.12 × 0.6321 + 0.24 × 0.3679
       = 0.07585 + 0.08830
       = 0.16415

SME adjustment = −0.04 × (1 − (S − 5) / 45)
               = −0.04 × (1 − (20 − 5) / 45)
               = −0.04 × (1 − 0.3333)
               = −0.04 × 0.6667
               = −0.02667

R_SME = 0.16415 − 0.02667 = 0.1375   (13.75%)
```

**SME benefit:** R reduced from 16.4% to 13.8% — less correlated with the economic cycle.

---

### Step 2: Double-Default PD (CRE22.10)

```
PD_dd = PD_obligor × (0.15 + 160 × PD_guarantor)
       = 0.0200 × (0.15 + 160 × 0.0015)
       = 0.0200 × (0.15 + 0.240)
       = 0.0200 × 0.390
       = 0.0078   (0.78%)
```

**Double-default benefit:** PD reduced from 2.00% to 0.78% — capital falls significantly.

---

### Step 3: K with Double-Default

```
PD_eff = 0.78%,  LGD_eff = 45%,  R = 0.1375,  M = 2yr

b = (0.11852 − 0.05478 × ln(0.0078))²
  = (0.11852 + 0.27077)²
  = (0.38929)²
  = 0.15155

MA = (1 + (2.0 − 2.5) × 0.15155) / (1 − 1.5 × 0.15155)
   = (1 − 0.07578) / (1 − 0.22733)
   = 0.92422 / 0.77267
   = 1.1961

z = (N⁻¹(0.0078) + √0.1375 × 3.0902) / √0.8625
  = (−2.4189 + 0.3708 × 3.0902) / 0.9288
  = (−2.4189 + 1.1457) / 0.9288
  = −1.2732 / 0.9288
  = −1.3708

N(z) = N(−1.3708) = 0.0852

K_base = 0.45 × 0.0852 − 0.0078 × 0.45 = 0.03834 − 0.00351 = 0.03483
K      = 0.03483 × 1.1961 = 0.04166   (4.17%)
```

---

### Summary — Layered Capital Benefits

```
                      Baseline    +SME Adj    +SME+CDS DD
PD applied            2.00%       2.00%       0.78%
R                     16.4%       13.75%      13.75%
K                     8.59%       7.78%       4.17%
RWA                   $3,221,250  $2,917,500  $1,563,750
Risk Weight           107.4%      97.2%       52.1%
Capital Saving        —           −$303,750   −$1,657,500
```

**Three capital levers on one trade:**
1. SME sales volume reduction in R: −$303,750 RWA
2. CDS double-default PD: −$1,353,750 additional RWA
3. **Total saving vs. no-CRM baseline: −$1,657,500** (51.5% reduction)

---

## Appendix F: Cross-Asset Comparison — All Asset Classes

### F.1 Reference Portfolio — Seven Exposures, Same PD and LGD

To isolate the effect of **asset class and correlation** on capital, here is a clean comparison of USD 10M exposures, all with PD = 1.00%, LGD = 45%, M = 3 years:

| Asset Class | R | b | MA | K | RWA | Risk Weight |
|---|---|---|---|---|---|---|
| SOVEREIGN | 19.3% | 0.13746 | 1.693 | 7.28% | $9,099,000 | 91.0% |
| **CORP** | **19.3%** | 0.13746 | 1.693 | **7.28%** | **$9,099,000** | **91.0%** |
| BANK (standard) | 19.3% | 0.13746 | 1.693 | 7.28% | $9,099,000 | 91.0% |
| BANK (large FI ×1.25) | 24.1% | 0.13746 | 1.693 | 8.47% | $10,587,500 | 105.9% |
| HVCRE | 22.0% | 0.13746 | 1.693 | 8.02% | $10,025,000 | 100.3% |
| RETAIL_MORT | 15.0% | 0 | 1.0 | 4.08% | $5,100,000 | 51.0% |
| RETAIL_REV | 4.0% | 0 | 1.0 | 1.82% | $2,275,000 | 22.8% |
| RETAIL_OTHER | 12.0% | 0 | 1.0 | 3.41% | $4,262,500 | 42.6% |

**Key observations:**

1. **RETAIL_REV (revolving credit)** has the lowest risk weight (22.8%) despite the same PD — the 4% fixed correlation reflects that consumer card defaults are largely idiosyncratic
2. **BANK (large FI)** has the highest risk weight (105.9%) — the 1.25× multiplier for financial interconnectedness adds a meaningful premium
3. **RETAIL_MORT** benefits from both fixed R=15% and the absence of a maturity adjustment
4. For CORP/BANK/SOV, R and K are identical at this PD level — the asset class distinction matters most at the margins (FI multiplier, HVCRE cap)

### F.2 The Effect of Maturity

Same exposure (CORP, PD=1%, LGD=45%), varying maturity:

| Maturity | MA | K | RWA | Capital vs. 1yr |
|---|---|---|---|---|
| 1 year | 0.9140 | 4.60% | $5,750,000 | — |
| 2 years | 1.0570 | 5.32% | $6,650,000 | +$900,000 (+15.7%) |
| **3 years (reference)** | **1.6929** | **7.28%** | **$9,099,000** | +$3,349,000 (+58.2%) |
| 4 years | 1.3766 | 6.93% | $8,662,500 | +$2,912,500 (+50.7%) |
| 5 years | 1.6929 | 8.52% | $10,650,000 | +$4,900,000 (+85.2%) |

**CRO observation:** A 5-year term loan requires 85% more capital than a 1-year revolving facility to the same borrower at the same PD and LGD. Structuring long-dated credit as revolvers (M capped at 1 year if annually reviewed) can be a significant capital management tool — subject to legal substance.

### F.3 The Effect of PD — Capital Non-Linearity

Same exposure (CORP, LGD=45%, M=3yr), varying PD:

| Rating | PD | R | K | Risk Weight | EL |
|---|---|---|---|---|---|
| AAA | 0.03% (floor) | 23.9% | 2.89% | 36.2% | $1,350 |
| AA | 0.05% | 23.7% | 3.66% | 45.8% | $2,250 |
| A | 0.10% | 23.3% | 4.56% | 57.0% | $4,500 |
| BBB+ | 0.25% | 22.2% | 5.58% | 69.8% | $11,250 |
| **BBB (reference)** | **0.50%** | **21.3%** | **6.03%** | **75.4%** | **$22,500** |
| BB+ | 1.00% | 19.3% | 7.28% | 91.0% | $45,000 |
| BB | 2.00% | 16.4% | 8.59% | 107.4% | $90,000 |
| BB− | 5.00% | 12.5% | 9.19% | 114.9% | $225,000 |
| B | 10.00% | 12.2% | 8.94% | 111.8% | $450,000 |
| CCC | 20.00% | 12.0% | 8.02% | 100.3% | $900,000 |

**Critical non-linearity insight:** Capital (K) **peaks around BB−/B rating (5–10% PD) and then decreases** for higher PDs. This is because:
- At very high PDs (20%), the expected loss (EL = 20%×45% = 9%) is already very large — most of the loss is "expected" and should be provisioned, not capitalised
- The Vasicek formula subtracts EL from the conditional loss, so as PD rises, EL grows faster than the conditional loss differential

This creates a counter-intuitive result: a CCC-rated borrower at 20% PD requires less capital (K=8.02%) than a BB− borrower at 5% PD (K=9.19%). The CRO should ensure provisions are adequate for the high-PD tail — otherwise the EL shortfall creates a CET1 deduction that restores the true economic cost.

---

*This document was prepared from the PROMETHEUS `a_irb.py` source code and reflects the implementation as of April 2026. Regulatory references are to the Basel Framework (bis.org/basel_framework) CRE30–CRE36 standards effective 1 January 2023.*

