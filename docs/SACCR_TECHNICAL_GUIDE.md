# SA-CCR Technical Guide
## Standardised Approach for Counterparty Credit Risk (CRE52)
### PROMETHEUS Risk Platform

---

## Table of Contents

1. Overview & Regulatory Basis
2. SA-CCR Structure
3. Replacement Cost (RC)
4. PFE Multiplier
5. Add-On by Asset Class
6. EAD Formula and Margined Cap
7. Supervisory Delta — Options and CDOs
8. Key Gap Fixes Applied (GAP-01 to GAP-13)
9. Data Structures Reference
10. Glossary

**Appendix A** — Interest Rate Swap (IRS): Full Numeric Example
**Appendix B** — FX Forward: Full Numeric Example
**Appendix C** — CDS Single-Name: Full Numeric Example
**Appendix D** — Equity Option (Margined Netting Set)
**Appendix E** — Multi-Asset Netting Set

---

## 1. Overview & Regulatory Basis

SA-CCR is the **Basel standardised method** for computing Exposure at Default (EAD) for OTC derivatives and exchange-traded derivatives. EAD feeds into:
- Credit Risk RWA (× counterparty risk weight)
- CVA capital (via EAD as exposure proxy)
- CCP capital (as trade_ead input)

| CRE52 Section | Topic |
|---|---|
| CRE52.10 | Replacement Cost — unmargined netting set |
| CRE52.18 | Replacement Cost — margined netting set |
| CRE52.22–23 | PFE multiplier |
| CRE52.34 | Maturity factor — unmargined |
| CRE52.52 | Maturity factor — margined (MPOR-based) |
| CRE52.56–71 | Add-On computation per asset class |
| CRE52.2 | Margined EAD cap at unmargined EAD |
| CRE52.40–41 | Supervisory delta for options and CDO tranches |

### Key Formula

```
EAD = α × (RC + Multiplier × AddOn_aggregate)

where:
  α      = 1.4 (supervisory scaling factor)
  RC     = Replacement Cost
  AddOn  = Potential Future Exposure add-on (sum across asset classes)
  Multiplier = PFE multiplier (function of V and C)
```

---

## 2. SA-CCR Structure

```
Netting Set Input (trades + collateral)
        │
        ├── Replacement Cost (RC)
        │    ├── Unmargined: max(V − C, 0)            [CRE52.10]
        │    └── Margined:   max(V − C, TH + MTA − NICA, 0) [CRE52.18]
        │
        ├── PFE Multiplier
        │    mult = min(1, 0.05 + 0.95 × exp((V−C)/(2 × 0.95 × AddOn_agg)))
        │
        └── Add-On per Asset Class
             ├── IR:    hedging sets per currency; SD formula [CRE52.56–61]
             ├── FX:    per currency pair; SF × notional     [CRE52.62–65]
             ├── EQ:    single-name (32%/50%) or index (20%/80%) [CRE52.66–68]
             ├── CR:    rating-granular SF; single/index rho   [CRE52.69–72]
             └── CMDTY: by commodity type; electricity 40%    [CRE52.73–77]

EAD = α × (RC + mult × Σ AddOn_k)    [CRE52.6]
```

---

## 3. Replacement Cost (RC)

### Unmargined Netting Set (CRE52.10)

```
RC_unmargined = max(V − C, 0)

where:
  V = net MtM of the netting set (positive = in the money to bank)
  C = net collateral held (excluding NICA)
```

### Margined Netting Set (CRE52.18)

```
RC_margined = max(V − C, TH + MTA − NICA, 0)

where:
  TH   = Threshold (amount of exposure before margin calls trigger)
  MTA  = Minimum Transfer Amount
  NICA = Net Independent Collateral Amount (initial margin held net)
```

The second term `TH + MTA − NICA` represents the maximum potential exposure that exists at the margin of the collateral agreement — the "gap risk" within the MPOR.

---

## 4. PFE Multiplier (CRE52.22–23)

```
y          = (V − C) / (2 × 0.95 × AddOn_agg)
Multiplier = min(1.0, 0.05 + 0.95 × exp(y))
```

**Interpretation:**
- When `V − C ≥ 0` (in the money): multiplier approaches 1.0 — full add-on used
- When `V − C < 0` (out of the money): multiplier < 1 — reduced add-on reflects lower risk
- Floor of 0.05 — even deep OTM positions carry a minimum 5% of add-on

The multiplier captures the economic insight that a netting set already well out-of-the-money is unlikely to generate large future exposures. The 0.05 floor prevents multiplier from reaching zero.

---

## 5. Add-On by Asset Class

### 5.1 Interest Rate Add-On (CRE52.56–61)

IR add-ons are computed per **currency** (hedging set). Within each currency:

```
D_i = Adjusted Notional × SD_i × MF_i

where:
  Adjusted Notional = trade notional
  SD_i = Supervisory delta (+1 or −1 for linear; Black-Scholes for options)
  MF_i = Maturity Factor = sqrt(min(M, 1) / 1)   for unmargined
       = (3/2) × sqrt(MPOR / 250)                 for margined [GAP-01]

Effective Notional per time bucket (T_start, T_end in years):
  EN_i = D_i × (exp(−0.05 × T_start) − exp(−0.05 × T_end))

Time buckets: [0,1), [1,5), [5,∞)

Add-on per hedging set:
  AddOn_IR = SF_IR × sqrt(EN_1² + EN_2² + EN_3² + 1.4×EN_1×EN_2 + 1.4×EN_2×EN_3 + 0.6×EN_1×EN_3)
  SF_IR = 0.005 (0.5%)
```

**Note:** The 1.4 and 0.6 cross-bucket correlations reflect partial offset between adjacent maturity buckets.

### 5.2 FX Add-On (CRE52.62–65)

```
For each currency pair (USD/EUR, USD/GBP, etc.):
  Add-On_pair = SF_FX × |Σ SD_i × D_i|
  SF_FX = 0.04 (4%)
```

### 5.3 Equity Add-On (CRE52.66–68, GAP-04)

```
Single-name:   SF = 32%, ρ = 50%
Index:         SF = 20%, ρ = 80%

For each underlying:
  AddOn_eq = SF × |Σ SD_i × D_i|

Aggregation across underlyings:
  Total = sqrt((ρ × Σ AddOn_k)² + (1−ρ²) × Σ AddOn_k²)
```

**GAP-04:** Original code used SF=20%/ρ=50% for both single-name and index. Basel Table 2 specifies single-name has 32% SF (higher because individual stocks are more volatile) and lower correlation (50% vs 80%).

### 5.4 Credit Add-On (CRE52.69–72, GAP-02/03)

```
SF_credit by rating (Table 2):
  AAA: 0.38%  AA: 0.38%  A: 0.42%  BBB: 0.54%  BB: 1.06%  B: 1.60%  CCC: 6.00%

Single-name: ρ = 50%
Index CDS:   ρ = 80%    [GAP-03: was uniformly 50%]

For each reference entity / index:
  AddOn_cr = SF(rating) × |Σ SD_i × D_i|

Aggregation:
  Total_cr = sqrt((ρ × Σ AddOn_k)² + (1−ρ²) × Σ AddOn_k²)
```

**GAP-02:** Original used flat IG/HY SF split. Basel requires 7-grade rating-granular SFs — critical for accurate CDS capital.

### 5.5 Commodity Add-On (CRE52.73–77, GAP-05)

```
SF by commodity type (Table 2):
  Crude oil:    18%
  Electricity:  40%    [GAP-05: separate hedging set; was 18%]
  Gold:         18%
  Other metals: 18%
  Agricultural: 15%
  Other:        15%
```

**GAP-05:** Electricity is a separate hedging set with 40% SF (vs 18% for oil) because electricity is non-storable and exhibits extreme price spikes (e.g. Texas winter storm 2021).

---

## 6. EAD Formula and Margined Cap (CRE52.2)

```
EAD_unmargined = α × (RC_unmargined + mult_unmargined × AddOn)
EAD_margined   = α × (RC_margined   + mult_margined   × AddOn)

Final EAD = min(EAD_margined, EAD_unmargined)    [CRE52.2, GAP-08]
```

**GAP-08:** The margined EAD cap prevents a counterintuitive result where adding a margin agreement *increases* EAD (which could happen if the MF adjustment produces a higher add-on than the unmargined calculation).

---

## 7. Supervisory Delta — Options and CDOs

### Option Delta (CRE52.40, GAP-06)

For options (not plain vanilla forwards/swaps):

```
Call option:  δ = +N(d₁)
Put option:   δ = −N(−d₁)

d₁ = (ln((P + λ) / (K + λ)) + 0.5 × σ² × T) / (σ × sqrt(T))

where:
  P  = current underlying price
  K  = strike price
  σ  = supervisory volatility (from SUPERVISORY_VOL table)
  T  = option maturity
  λ  = shift parameter (ensures positive domain for rates)
        λ = 0.005 (50bp) for IR options to handle negative rates
        λ = 0 for other asset classes
```

**Supervisory volatilities (SUPERVISORY_VOL):**

| Asset Class | Supervisory Vol |
|---|---|
| IR | 50% |
| FX | 15% |
| EQ Single-Name | 120% |
| EQ Index | 75% |
| CR Single-Name | 100% |
| CR Index | 80% |
| CMDTY | 70% |

### CDO Tranche Delta (CRE52.41, GAP-07)

```
For tranched CDO positions:
  δ = +15 × exp(−14 × A) × (1 − exp(−14 × D))   [protection buyer]
  δ = −15 × exp(−14 × A) × (1 − exp(−14 × D))   [protection seller]

where:
  A = attachment point (e.g. 3% = 0.03)
  D = detachment point (e.g. 6% = 0.06)
```

---

## 8. Key Gap Fixes Applied

| Fix | Regulation | Description | Impact |
|---|---|---|---|
| **GAP-01** | CRE52.52 | Margined MF = (3/2) × sqrt(MPOR/250) — was missing 3/2 factor | Was understating add-on by 33% for margined trades |
| **GAP-02** | Table 2 | Credit SF is 7-grade rating-granular (not flat IG/HY) | Material for BB/B/CCC credits |
| **GAP-03** | Table 2 | Credit index ρ = 80% (was 50%) | 30% higher portfolio offset for CDX positions |
| **GAP-04** | Table 2 | EQ index SF=20%/ρ=80%; single-name SF=32%/ρ=50% | Correct EQ bifurcation |
| **GAP-05** | Table 2 | Electricity SF = 40% (separate hedging set) | 2.2× higher SF for power derivatives |
| **GAP-06** | CRE52.40 | Option supervisory delta — Black-Scholes + λ-shift | New capability; was returning +1/-1 for all options |
| **GAP-07** | CRE52.41 | CDO tranche delta with A/D attachment formula | New capability for synthetic CDO tranches |
| **GAP-08** | CRE52.2 | Margined EAD capped at unmargined EAD | Prevents margin agreement increasing EAD |
| **GAP-09** | CRE52.46–47 | Basis swap SF = ½×standard; vol transaction SF = 5× | Correct basis/vol transaction treatment |
| **GAP-10** | CRE52.37 | Variable notional uses `average_notional` field | Correct amortising/leveraged swap treatment |
| **GAP-11** | CRE52.60 | Removed duplicate `_resolve_sub_hedging_set()` call | Code correctness fix |
| **GAP-12** | CRE52.34 | `start_date` field for forward-starting swaps | Correct S in SD formula for forward swaps |
| **GAP-13** | Table 2 | SUPERVISORY_VOL dict added for all asset classes | Required for GAP-06 option delta |

---

## 9. Data Structures Reference

### Trade (Input)

| Field | Description |
|---|---|
| `trade_id` | Unique trade identifier |
| `asset_class` | 'IR', 'FX', 'EQ', 'CR', 'CMDTY' |
| `instrument_type` | 'IRS', 'CDS_Protection', 'FXFwd', 'EquitySwap', etc. |
| `notional` | Face / notional amount |
| `direction` | +1 = long/payer/protection buyer; −1 = short/receiver/seller |
| `maturity_date` | Trade maturity date |
| `current_mtm` | Current mark-to-market (USD) |
| `credit_sub_type` | 'SINGLE_NAME', 'INDEX_CDS', 'TRANCHED' |
| `credit_rating` | For credit trades: 'AAA'–'CCC' |
| `is_option` | True if option (triggers supervisory delta calc) |
| `option_type` | 'call' or 'put' |
| `strike` | Option strike price |
| `underlying_price` | Current underlying price |
| `start_date` | For forward-starting swaps |
| `average_notional` | For amortising or leveraged notionals |

---

## 10. Glossary

| Term | Definition |
|---|---|
| **RC** | Replacement Cost — current exposure if counterparty defaults today |
| **AddOn** | Potential Future Exposure add-on — captures possible future changes |
| **α** | Supervisory scaling factor = 1.4 (CRE52.6) |
| **SF** | Supervisory Factor — scaling the add-on by asset class/risk level |
| **SD** | Supervisory Delta — direction and optionality adjustment to notional |
| **MF** | Maturity Factor — adjusts for residual trade maturity |
| **MPOR** | Margin Period of Risk — days to close out a margined position |
| **NICA** | Net Independent Collateral Amount |
| **TH** | Threshold — exposure level before margin calls are triggered |
| **MTA** | Minimum Transfer Amount |
| **Hedging Set** | Group of trades with offsetting positions for add-on aggregation |
| **EAD** | Exposure at Default = α × (RC + mult × AddOn) |

---

## Appendix A — Interest Rate Swap: Full Numeric Example

### Trade Setup

A bank **pays fixed 3%** on a 5-year USD IRS, $10M notional. Current MtM = +$150,000 (in the money). Unmargined netting set. Valuation date: today.

| Parameter | Value |
|---|---|
| Asset class | IR |
| Notional | $10,000,000 |
| Direction | +1 (payer) |
| Maturity | 5.0 years |
| Start date | Today (spot-starting) |
| Current MtM | +$150,000 |
| Collateral held | $0 |

---

### Step 1: Replacement Cost

```
RC = max(V − C, 0)
   = max(150,000 − 0, 0)
   = $150,000
```

---

### Step 2: Maturity Factor (Unmargined)

```
MF = sqrt(min(M, 1) / 1)
   = sqrt(min(5.0, 1) / 1)
   = sqrt(1.0)
   = 1.0
```

(MF is capped at 1.0 for maturities > 1 year for unmargined trades)

---

### Step 3: Adjusted Notional with SD

For a vanilla IRS (linear), SD = +1.0 (payer position):

```
D = Notional × SD × MF
  = 10,000,000 × 1.0 × 1.0
  = $10,000,000
```

### Step 4: Effective Notional per Time Bucket

The 5-year IRS falls in bucket [1, 5) with T_start=0 and T_end=5:

```
EN_bucket2 = D × (exp(−0.05 × 0) − exp(−0.05 × 5))
           = 10,000,000 × (1.0 − exp(−0.25))
           = 10,000,000 × (1.0 − 0.7788)
           = 10,000,000 × 0.2212
           = $2,212,000
```

No trades in buckets 1 or 3, so EN_1 = EN_3 = 0.

---

### Step 5: IR Add-On

```
AddOn_IR = SF_IR × sqrt(EN_1² + EN_2² + EN_3² + cross-terms)
         = 0.005 × sqrt(0 + 2,212,000² + 0)
         = 0.005 × 2,212,000
         = $11,060
```

---

### Step 6: PFE Multiplier

```
y = (V − C) / (2 × 0.95 × AddOn)
  = 150,000 / (2 × 0.95 × 11,060)
  = 150,000 / 21,014
  = 7.138

Multiplier = min(1.0, 0.05 + 0.95 × exp(7.138))
           = min(1.0, 0.05 + 0.95 × 1252.3)
           = min(1.0, 1189.7)
           = 1.0
```

The large positive MtM forces multiplier = 1.0 (floor applies).

---

### Step 7: EAD

```
EAD = α × (RC + Multiplier × AddOn)
    = 1.4 × (150,000 + 1.0 × 11,060)
    = 1.4 × 161,060
    = $225,484
```

---

### Step 8: Credit Risk RWA (assuming BBB-rated counterparty, 100% RW)

```
RWA = EAD × RW = 225,484 × 1.00 = $225,484
Capital = 225,484 × 8% = $18,039
```

---

## Appendix B — FX Forward: Full Numeric Example

### Trade Setup

Bank is **long EUR/USD** forward. Buys EUR 10M at 1.080 in 1 year. Current spot = 1.095.
MtM = (1.095 − 1.080) × 10,000,000 = +$150,000.

| Parameter | Value |
|---|---|
| Asset class | FX |
| Notional | EUR 10,000,000 → $10,950,000 (at spot) |
| Direction | +1 (long EUR) |
| Maturity | 1.0 year |
| Current MtM | +$150,000 |
| Collateral | $0 |

### Add-On Calculation

```
SF_FX = 4.0%
D     = 10,950,000 × 1.0 × 1.0 = $10,950,000

AddOn_FX = SF_FX × |D| = 0.04 × 10,950,000 = $438,000
```

### EAD

```
Multiplier = 1.0 (in the money)
EAD = 1.4 × (150,000 + 1.0 × 438,000) = 1.4 × 588,000 = $823,200
```

---

## Appendix C — CDS Single-Name: Full Numeric Example

### Trade Setup

Bank buys $5M **protection** on a BB-rated corporate. 5-year CDS. MtM = −$50,000 (out of the money for protection buyer as spreads narrowed).

| Parameter | Value |
|---|---|
| Asset class | CR |
| Credit sub type | SINGLE_NAME |
| Credit rating | BB |
| Notional | $5,000,000 |
| Direction | +1 (protection buyer) |
| Maturity | 5.0 years |
| Current MtM | −$50,000 |
| Collateral | $0 |

### Supervisory Factor (GAP-02)

```
SF_credit (BB rating) = 1.06% = 0.0106   [from rating-granular Table 2]
```

### Add-On

```
D       = 5,000,000 × 1.0 × 1.0 = $5,000,000
AddOn_CR = SF × |D| = 0.0106 × 5,000,000 = $53,000
```

### PFE Multiplier (out of the money)

```
y = (−50,000) / (2 × 0.95 × 53,000)
  = −50,000 / 100,700
  = −0.4965

Multiplier = min(1.0, 0.05 + 0.95 × exp(−0.4965))
           = min(1.0, 0.05 + 0.95 × 0.6086)
           = min(1.0, 0.05 + 0.5782)
           = min(1.0, 0.6282)
           = 0.6282
```

Out-of-the-money → multiplier < 1.0 (reduced PFE).

### EAD

```
RC  = max(−50,000 − 0, 0) = 0   (OTM → no replacement cost)
EAD = 1.4 × (0 + 0.6282 × 53,000)
    = 1.4 × 33,295
    = $46,613
```

---

## Appendix D — Equity Option (Margined Netting Set, GAP-01)

### Trade Setup

Bank holds a **long call option** on SPX Index. $2M notional. Strike = 5,200, spot = 5,350. Maturity = 0.5 years. Margined (CSA), MPOR = 10 days. σ_eq_index = 75%.

### Supervisory Delta (GAP-06)

```
P = 5,350, K = 5,200, T = 0.5, σ = 75%, λ = 0

d₁ = (ln(5350/5200) + 0.5 × 0.75² × 0.5) / (0.75 × sqrt(0.5))
   = (ln(1.0288) + 0.5 × 0.5625 × 0.5) / (0.75 × 0.7071)
   = (0.02841 + 0.14063) / 0.53033
   = 0.16904 / 0.53033
   = 0.3188

SD = N(0.3188) = 0.6251   (call option: long EQ exposure)
```

### Maturity Factor — Margined (GAP-01)

```
MF_margined = (3/2) × sqrt(MPOR / 250)
            = 1.5 × sqrt(10 / 250)
            = 1.5 × sqrt(0.04)
            = 1.5 × 0.2
            = 0.30
```

**Without GAP-01 fix:** MF = sqrt(10/250) = 0.20 → add-on understated by 33%.

### Add-On

```
D_eq    = Notional × SD × MF = 2,000,000 × 0.6251 × 0.30 = $375,060
SF_eq   = 20% (index)
AddOn   = 0.20 × 375,060 = $75,012

Multiplier = 1.0 (assume in the money)
EAD_margined = 1.4 × (0 + 1.0 × 75,012) = $105,017
```

---

## Appendix E — Multi-Asset Netting Set

### Setup

A netting set with three trades:

| Trade | Asset | Notional | Direction | Add-On (Approx.) |
|---|---|---|---|---|
| IRS 5Y USD | IR | $10M | +1 | $11,060 |
| IRS 3Y USD | IR | $8M | −1 | −$8,480 (offsets) |
| FX EUR/USD | FX | $10M | +1 | $438,000 |

Net MtM = +$200,000. Collateral = $50,000.

### IR Aggregation (Same Currency, Partial Netting)

The +$10M and −$8M USD IRS positions partially offset within the USD hedging set:

```
Net EN_bucket2 = 2,212,000 − 1,697,000 = $515,000
AddOn_IR = 0.005 × 515,000 = $2,575
```

### Total Add-On

```
AddOn_IR = $2,575       (partially netted)
AddOn_FX = $438,000

Total AddOn = $2,575 + $438,000 = $440,575
```

**No cross-asset-class netting** — IR and FX add-ons always sum arithmetically.

### RC and EAD

```
RC   = max(200,000 − 50,000, 0) = $150,000
mult = 1.0 (in the money)
EAD  = 1.4 × (150,000 + 440,575) = 1.4 × 590,575 = $826,805
```

**Insight:** The FX forward dominates the add-on ($438k vs $2.6k for IR) because 4% SF is 8× higher than 0.5% IR SF. IR netting generated $8,480 in savings — illustrating why CSA agreements with robust netting are capital-efficient.

