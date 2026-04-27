# CCP Capital — Technical Guide
## Central Counterparty Exposure (CRE54)
### PROMETHEUS Risk Platform

---

## Table of Contents

1. Overview & Regulatory Basis
2. What Is a CCP and Why Does It Matter?
3. Calculation Pipeline
4. Trade Exposure to a QCCP (CRE54.4)
5. Initial Margin Treatment (CRE54.15)
6. Default Fund Contribution Capital (CRE54.32–38)
7. Unfunded Default Fund (CRE54.42)
8. Equity in a CCP (CRE54.17)
9. Client Clearing — Intermediary Role (CRE54.5–6)
10. Non-QCCP Treatment (CRE54.40–42)
11. Key Bug Fixes Applied (GAP-CCP-01 through 08)
12. Data Structures Reference
13. Glossary

**Appendix A** — Full Worked Example: Bank Clearing Through LCH (QCCP)
**Appendix B** — Full Worked Example: Non-QCCP Bilateral Clearing
**Appendix C** — Client Clearing Scenarios
**Appendix D** — Sensitivity Analysis: Effect of DF Proportional Share

---

## 1. Overview & Regulatory Basis

The CCP Capital engine computes the regulatory capital that a bank must hold for its exposures arising from **centrally cleared derivative transactions**. All cleared trades are novated to a Central Counterparty (CCP), which interposes itself as buyer to every seller and seller to every buyer, eliminating bilateral counterparty credit risk between clearing members.

However, a bank (clearing member) still bears residual credit risk to the CCP itself through:
- Mark-to-market fluctuations on cleared trades (trade exposure)
- Default fund contributions pledged to the CCP's mutualized loss waterfall

**Regulatory standard:** Basel III CRE54 (effective January 2023).

| Basel Section | Topic |
|---|---|
| CRE54.4 | Trade exposure to QCCP — 2% capital charge |
| CRE54.15 | Initial margin — segregated vs. non-segregated |
| CRE54.32–36 | Default Fund Contribution (DFC) — risk-sensitive method |
| CRE54.38 | DFC floor — 1.6% of funded DF |
| CRE54.40–42 | Non-QCCP treatment |
| CRE54.17 | Equity investment in CCP — 250% RW |
| CRE54.5–6 | Client clearing — intermediary role |

---

## 2. What Is a CCP and Why Does It Matter?

A **Central Counterparty (CCP)** is a financial market infrastructure (FMI) that sits between buyers and sellers in a derivatives market. Examples: LCH SwapClear (interest rate swaps), CME Clearing (futures), Eurex Clearing (European derivatives), ICE Clear Credit (CDS).

**The Basel incentive structure:**

| Exposure Type | QCCP Capital | Non-QCCP Capital |
|---|---|---|
| Trade EAD | 2% of net EAD × 12.5 = 25% RWA | 100%+ RWA |
| Initial Margin (segregated) | 0% | 100%+ RWA |
| Default Fund (funded) | K_i from risk-sensitive formula | Standard credit RW |

Basel deliberately makes QCCP clearing **very cheap** (effectively 1.6% RWA) to incentivise banks to clear through regulated CCPs.

### The CCP Loss Waterfall

When a clearing member defaults, losses are absorbed in order:

```
1. Defaulted member's IM (Initial Margin)
2. Defaulted member's DF contribution
3. CCP's own capital ("skin-in-the-game")
4. Surviving members' DF contributions (mutualized losses)
5. Assessment powers (further calls on surviving members)
```

Steps 4–5 are the bank's **systemic risk exposure** — why Basel requires capital for DF contributions.

---

## 3. Calculation Pipeline

```
INPUT: CCPExposure (per CCP relationship)
          │
          ▼
    _validate_ccp_exposure()
    ├── All monetary fields ≥ 0
    ├── df_contribution ≤ df_total (warning if breached)
    └── vm_posted ≤ trade_ead (warn, floor at 0)
          │
          ▼
    QCCP or Non-QCCP?
    ├── QCCP ──────────────────────────────────────────────────────┐
    │    ├── Trade EAD:    net_ead = max(trade_ead − vm, 0)        │
    │    │                 rwa_trade = net_ead × 2% × 12.5         │
    │    ├── IM:           seg → 0%  |  non-seg → 2% × 12.5       │
    │    ├── DFC:          _compute_dfc_capital_qccp()             │
    │    │    ├── risk-sensitive: max((DF_i/ΣDF)×K_CCP, DF_i×1.6%)│
    │    │    └── floor-only:    DF_i × 1.6%                       │
    │    │                 rwa_dfc = K_i × 12.5                    │
    │    ├── Unfunded DF:  df_unfunded × 12.5  (1250% RW)          │
    │    └── Equity:       equity_in_ccp × 2.5 × 12.5             │
    └── Non-QCCP ──────────────────────────────────────────────────┤
         All exposures × non_qccp_rw (default 100%) × 12.5        │
         Unfunded DF → 1250% RW regardless                         │
                                                                   │
    Client Clearing (if is_clearing_member):  ◄────────────────────┘
    ├── No guarantee (CRE54.5): 2% QCCP pass-through
    └── With guarantee (CRE54.6): 100% look-through

OUTPUT: CCPResult
    ├── rwa_trade, rwa_im, rwa_dfc, rwa_unfunded, rwa_equity, rwa_client
    └── rwa_total, capital_total (= rwa_total × 8%)
```

---

## 4. Trade Exposure to a QCCP (CRE54.4)

### Formula

```
net_trade_ead = max(trade_ead − vm_posted, 0)         [CRE54.4, GAP-CCP-03]
rwa_trade     = net_trade_ead × 2% × 12.5
capital_trade = rwa_trade × 8%  =  net_trade_ead × 2%
```

The **2% capital charge** (not 2% RW) reflects the extremely low credit risk of a QCCP compared to a bilateral counterparty. The factor 12.5 converts capital to RWA (since RWA = capital / 8%).

### Why VM is Netted

**Variation Margin (VM)** represents realised P&L that has been settled in cash — the bank has already received/paid the economic value. The EAD after VM netting represents only the **residual exposure** since the last margin call.

**GAP-CCP-03:** The original code did not net VM against trade EAD. This overstated trade exposure by the full amount of posted VM.

---

## 5. Initial Margin Treatment (CRE54.15)

Initial Margin is pre-funded collateral posted to cover potential future exposure during the close-out period.

| Segregation Status | Capital Treatment | Rationale |
|---|---|---|
| **Segregated** (legally bankruptcy-remote) | **0% RW** → no capital required | Bank can retrieve IM in CCP default |
| **Non-segregated** (commingled with CCP assets) | **2% capital charge** | IM may be lost in CCP default (no bankruptcy protection) |

```
rwa_im = 0                                  if im_segregated = True
rwa_im = im_posted × 2% × 12.5             if im_segregated = False
```

**Practical note:** Major CCPs (LCH, CME, Eurex) offer full segregation for clearing member IM. Ensure `im_segregated = True` is correctly populated to avoid overcapitalizing.

---

## 6. Default Fund Contribution Capital (CRE54.32–38)

The Default Fund (DF) is the most complex component. When a clearing member defaults and their IM is exhausted, the CCP draws on the **mutualized default fund** — contributions from all surviving clearing members. This is a systemic risk the bank must capitalize.

### Risk-Sensitive Method (CRE54.33–36)

Requires the CCP to disclose its **hypothetical capital K_CCP** — the capital the CCP would need if it were itself a bank clearing member.

```
Proportional share:  K_prop = (DF_i / ΣDF_CM) × K_CCP        [CRE54.33]
Floor:               K_floor = DF_i × 1.6%                    [CRE54.38]
Bank's DFC capital:  K_i = max(K_prop, K_floor)               [GAP-CCP-02]
RWA:                 rwa_dfc = K_i × 12.5
```

**GAP-CCP-01:** The original code used `K_i = 0.08 × K_CCP` (wrong — this applies the bank's 8% capital ratio to K_CCP without the proportional share). The correct formula allocates K_CCP proportionally by DF share.

**GAP-CCP-02:** The original code used `min(K_prop, K_floor)` — this inverted the floor into a cap! A bank with a small DF share but large K_CCP would get K_i = floor, while a bank with a large DF share and small K_CCP would have no floor protection. The correct operator is `max()`.

### Floor-Only Method (CRE54.38 Fallback)

When K_CCP is not disclosed (or df_total = 0):

```
K_i = DF_i × 1.6%
rwa_dfc = K_i × 12.5
```

This is a **floor** — it represents the minimum capital regardless of the CCP's risk profile.

---

## 7. Unfunded Default Fund (CRE54.42)

Some CCPs can **call** additional contributions from clearing members after a default (assessment powers). These contingent obligations attract:

```
rwa_unfunded = df_unfunded × 12.5      (= 1250% RW = 100% capital)
```

The 1250% RW applies equally to both QCCP and non-QCCP unfunded DF. It reflects the full capital charge on a contingent liability that could crystallise under stress.

---

## 8. Equity in a CCP (CRE54.17)

A bank may hold equity (exchange seats, membership stakes) in a CCP. These are treated as equity investments:

```
rwa_equity = equity_in_ccp × 250% × 12.5
capital    = equity_in_ccp × 250%
```

**GAP-CCP-04:** The original code had no treatment for CCP equity. The 250% RW reflects the subordinated loss-absorbing nature of CCP equity in the default waterfall.

---

## 9. Client Clearing — Intermediary Role (CRE54.5–6)

When a bank acts as **Clearing Member (CM)** and clears trades on behalf of clients, it incurs a contingent credit exposure to those clients.

### No Guarantee (CRE54.5)

The bank passes trades to the CCP without guaranteeing client performance:

```
rwa_client = client_ead × 2% × 12.5        (QCCP pass-through RW)
```

The 2% QCCP RW applies because the CCP bears the primary risk — the bank's contingent exposure is minimal.

### With Guarantee (CRE54.6)

The bank backstops client performance (full financial guarantee):

```
rwa_client = client_ead × 100% × 12.5      (look-through to client credit risk)
```

**GAP-CCP-05:** The original code had no distinction between guaranteed and non-guaranteed client clearing. Guarantees dramatically change the capital treatment — a guarantee turns a 2% charge into a 100% charge.

---

## 10. Non-QCCP Treatment (CRE54.40–42)

For **non-qualifying CCPs** (those that don't meet IOSCO PFMIs standards):

```
rwa_trade    = net_trade_ead  × non_qccp_rw × 12.5    (default 100%)
rwa_im       = im_posted      × non_qccp_rw × 12.5    (no segregation benefit)
rwa_dfc      = df_contribution × non_qccp_rw × 12.5   (standard credit RW)
rwa_unfunded = df_unfunded    × 12.5                   (1250% RW — same as QCCP)
rwa_equity   = equity_in_ccp  × non_qccp_rw × 12.5    (no 250% treatment)
```

The `non_qccp_rw` defaults to 100% but can be overridden to reflect the specific credit quality of the non-qualifying CCP.

---

## 11. Key Bug Fixes Applied

| Fix | Regulation | Description | Impact |
|---|---|---|---|
| **GAP-CCP-01** | CRE54.32–33 | DFC uses proportional share `(DF_i/ΣDF)×K_CCP` not flat `0.08×K_CCP` | Correct risk allocation |
| **GAP-CCP-02** | CRE54.38 | Floor enforced with `max()` not `min()` | Inverted floor was massively understating DFC capital |
| **GAP-CCP-03** | CRE54.4 | VM netted against trade EAD before applying RW | Correct exposure measurement |
| **GAP-CCP-04** | CRE54.17 | Equity in CCP at 250% RW added | New component — no prior treatment |
| **GAP-CCP-05** | CRE54.5–6 | Client guarantee flag added with look-through RW | Correct client clearing capital |
| **GAP-CCP-06** | CRE54.42 | Unfunded DFC uses 1250% RW for both QCCP and non-QCCP | Explicit path for both CCP types |
| **GAP-CCP-07** | — | Input validation via `_validate_ccp_exposure()` | Data quality guard-rails |
| **GAP-CCP-08** | — | CCPResult extended with per-component capital breakdown | Audit trail and attribution |

---

## 12. Data Structures Reference

### CCPExposure (Input)

| Field | Type | Description |
|---|---|---|
| `ccp_name` | str | CCP identifier (e.g. "LCH", "CME_CDS") |
| `is_qualifying` | bool | True = QCCP (LCH, CME, Eurex, ICE, JSCC) |
| `trade_ead` | float | Aggregate EAD of cleared trades (from SA-CCR/IMM) |
| `vm_posted` | float | Variation margin posted to CCP |
| `im_posted` | float | Initial margin posted to CCP |
| `im_segregated` | bool | True = bankruptcy-remote segregation |
| `df_contribution` | float | Bank's funded DF contribution (DF_i) |
| `df_total` | float | Total funded DF of all clearing members (ΣDF_CM) |
| `kccp` | float | Hypothetical capital of CCP (K_CCP) — disclosed by CCP |
| `df_unfunded` | float | Unfunded/contingent DF commitment |
| `equity_in_ccp` | float | Equity stake in CCP |
| `is_clearing_member` | bool | True if bank clears for clients |
| `client_ead` | float | EAD of client positions |
| `client_guarantee` | bool | True = bank guarantees client performance |
| `non_qccp_rw` | float | Override RW for non-QCCP (default 100%) |

### CCPResult (Output)

| Field | Description |
|---|---|
| `net_trade_ead` | Trade EAD after VM netting |
| `rwa_trade` | RWA from trade exposure |
| `rwa_im` | RWA from non-segregated IM |
| `k_dfc` | Required DFC capital amount |
| `rwa_dfc` | RWA from DFC (= k_dfc × 12.5) |
| `rwa_unfunded` | RWA from unfunded DF |
| `rwa_equity_in_ccp` | RWA from CCP equity holding |
| `rwa_client` | RWA from client clearing |
| `rwa_total` | Sum of all RWA components |
| `capital_total` | rwa_total × 8% |
| `dfc_method` | "risk_sensitive" / "floor_only" / "non_qccp" / "no_df" |

---

## 13. Glossary

| Term | Definition |
|---|---|
| **CCP** | Central Counterparty — interposes as buyer/seller to all trades |
| **QCCP** | Qualifying CCP — meets IOSCO PFMI standards; receives preferential capital treatment |
| **DF** | Default Fund — mutualized collateral pool funding CCP loss waterfall |
| **DFC** | Default Fund Contribution — the bank's share of the DF |
| **K_CCP** | Hypothetical capital requirement of the CCP itself (disclosed) |
| **IM** | Initial Margin — pre-funded collateral against potential future exposure |
| **VM** | Variation Margin — daily settlement of P&L changes |
| **MPOR** | Margin Period of Risk — time to close out a defaulted member's portfolio |
| **RW** | Risk Weight — percentage applied to EAD to determine RWA |
| **RWA** | Risk-Weighted Assets — the capital base metric (capital = RWA × 8%) |
| **CM** | Clearing Member — bank that has direct membership at a CCP |
| **Segregation** | Legal separation of client assets from CCP/CM assets |
| **PFMI** | Principles for Financial Market Infrastructures (IOSCO 2012) |

---

## Appendix A — Full Worked Example: Bank Clearing Through LCH (QCCP)

### Trade Setup

A bank (clearing member) at LCH SwapClear has the following positions:

| Parameter | Value |
|---|---|
| CCP | LCH SwapClear |
| Is Qualifying | Yes (QCCP) |
| Trade EAD (SA-CCR output) | $50,000,000 |
| Variation Margin posted | $8,000,000 |
| Initial Margin posted | $12,000,000 |
| IM segregated | Yes |
| Bank's DF contribution (DF_i) | $5,000,000 |
| Total DF of all CMs (ΣDF) | $200,000,000 |
| K_CCP (disclosed by LCH) | $3,000,000 |
| Unfunded DF commitment | $2,000,000 |
| Equity in LCH | $500,000 |
| Client EAD (no guarantee) | $10,000,000 |

---

### Step 1: Input Validation

All fields ≥ 0. ✓
- `df_contribution` ($5M) ≤ `df_total` ($200M) ✓
- `vm_posted` ($8M) ≤ `trade_ead` ($50M) ✓
- `kccp` ($3M) > 0 and `df_total` ($200M) > 0 → risk-sensitive method available ✓

---

### Step 2: Net Trade EAD (CRE54.4, GAP-CCP-03)

```
net_trade_ead = max(50,000,000 − 8,000,000, 0)
              = max(42,000,000, 0)
              = $42,000,000
```

VM netting saves capital on $8M of EAD.

---

### Step 3: Trade Exposure RWA

```
rwa_trade    = net_trade_ead × 2% × 12.5
             = 42,000,000 × 0.02 × 12.5
             = $10,500,000

capital_trade = 42,000,000 × 2%
              = $840,000
```

---

### Step 4: Initial Margin (CRE54.15)

IM is segregated → 0% RW:

```
rwa_im    = 0
capital_im = 0
```

If IM were NOT segregated:
```
rwa_im (non-seg) = 12,000,000 × 2% × 12.5 = $3,000,000
```

Segregation saves $240,000 in capital.

---

### Step 5: Default Fund Capital (CRE54.32–38)

**Proportional share (GAP-CCP-01):**
```
DF share     = DF_i / ΣDF = 5,000,000 / 200,000,000 = 2.50%

K_prop       = DF_share × K_CCP
             = 2.50% × 3,000,000
             = $75,000
```

**Floor (CRE54.38):**
```
K_floor      = DF_i × 1.6%
             = 5,000,000 × 1.6%
             = $80,000
```

**DFC Capital (GAP-CCP-02 — max, not min):**
```
K_i          = max(K_prop, K_floor)
             = max(75,000, 80,000)
             = $80,000

rwa_dfc      = K_i × 12.5
             = 80,000 × 12.5
             = $1,000,000
```

**Note:** The floor binds here. The proportional K_CCP allocation ($75k) is slightly below the 1.6% floor ($80k). The floor ensures a minimum capital even when the CCP's disclosed K_CCP suggests lower risk.

---

### Step 6: Unfunded Default Fund (CRE54.42)

```
rwa_unfunded = df_unfunded × 12.5
             = 2,000,000 × 12.5
             = $25,000,000

capital_unfunded = 2,000,000 × 100%
                 = $2,000,000
```

Unfunded commitments are expensive — 100% capital (1250% RW).

---

### Step 7: Equity in LCH (CRE54.17, GAP-CCP-04)

```
rwa_equity   = equity_in_ccp × 250% × 12.5
             = 500,000 × 2.50 × 12.5
             = $15,625,000

capital_equity = 500,000 × 250%
               = $1,250,000
```

---

### Step 8: Client Clearing (CRE54.5 — no guarantee)

```
rwa_client   = client_ead × 2% × 12.5
             = 10,000,000 × 0.02 × 12.5
             = $2,500,000

capital_client = 10,000,000 × 2%
               = $200,000
```

---

### Step 9: Total Capital Summary

| Component | EAD | RWA | Capital |
|---|---|---|---|
| Trade exposure (net of VM) | $42,000,000 | $10,500,000 | $840,000 |
| Initial margin (segregated) | $0 | $0 | $0 |
| Default fund (risk-sensitive) | — | $1,000,000 | $80,000 |
| Unfunded DF | $2,000,000 | $25,000,000 | $2,000,000 |
| Equity in LCH | $500,000 | $15,625,000 | $1,250,000 |
| Client clearing (no guarantee) | $10,000,000 | $2,500,000 | $200,000 |
| **TOTAL** | — | **$54,625,000** | **$4,370,000** |

**Effective capital ratio on gross trade EAD:** $4,370,000 / $50,000,000 = **8.74%**

---

### CRO Insight

The dominant capital driver is the **unfunded DF commitment** ($2M capital) and **CCP equity holding** ($1.25M capital). Both are relatively insensitive to market movements — they represent structural commitments. Management should review whether:
1. The unfunded commitment ceiling can be reduced in the CCP rulebook.
2. The equity stake is operationally necessary.

---

## Appendix B — Full Worked Example: Non-QCCP Bilateral Clearing

### Setup

| Parameter | Value |
|---|---|
| CCP | Regional CCP (non-QCCP) |
| Non-QCCP RW | 100% |
| Trade EAD | $20,000,000 |
| VM posted | $2,000,000 |
| IM posted | $3,000,000 |
| DF contribution | $1,000,000 |
| Unfunded DF | $500,000 |

### Calculation

```
net_ead      = max(20M − 2M, 0) = $18,000,000
rwa_trade    = 18,000,000 × 100% × 12.5 = $225,000,000
rwa_im       = 3,000,000  × 100% × 12.5 = $37,500,000
rwa_dfc      = 1,000,000  × 100% × 12.5 = $12,500,000
rwa_unfunded = 500,000    × 12.5         = $6,250,000
TOTAL RWA    = $281,250,000
Capital      = $22,500,000
```

**Comparison:** The same $20M trade EAD at a QCCP generates **$10.5M RWA** vs. **$225M RWA** at a non-QCCP — a **21× difference**. This is the Basel incentive for central clearing.

---

## Appendix C — Client Clearing Scenarios

### Scenario 1: Clearing Member, No Guarantee (CRE54.5)

| Parameter | Value |
|---|---|
| Client EAD | $30,000,000 |
| Bank guarantees client? | No |
| RW Applied | 2% (QCCP pass-through) |

```
rwa_client = 30,000,000 × 2% × 12.5 = $7,500,000
capital    = $600,000
```

### Scenario 2: Clearing Member, With Guarantee (CRE54.6)

| Parameter | Value |
|---|---|
| Client EAD | $30,000,000 |
| Bank guarantees client? | Yes |
| RW Applied | 100% (look-through) |

```
rwa_client = 30,000,000 × 100% × 12.5 = $375,000,000
capital    = $30,000,000
```

**Capital impact of guarantee:** $30M vs $0.6M = **50× increase**. Banks must carefully evaluate whether to offer financial guarantees to clients for their cleared positions.

---

## Appendix D — Sensitivity Analysis

### Effect of DF Proportional Share on DFC Capital

Assume: K_CCP = $10,000,000, DF_i = $5,000,000

| ΣDF_CM | DF Share | K_prop | K_floor | K_i (max) | RWA |
|---|---|---|---|---|---|
| $25,000,000 | 20.0% | $2,000,000 | $80,000 | $2,000,000 | $25,000,000 |
| $50,000,000 | 10.0% | $1,000,000 | $80,000 | $1,000,000 | $12,500,000 |
| $100,000,000 | 5.0% | $500,000 | $80,000 | $500,000 | $6,250,000 |
| $200,000,000 | 2.5% | $250,000 | $80,000 | $250,000 | $3,125,000 |
| $500,000,000 | 1.0% | $100,000 | $80,000 | $100,000 | $1,250,000 |
| $625,000,000 | 0.8% | $80,000 | $80,000 | **$80,000** | **$1,000,000** |
| $1,000,000,000 | 0.5% | $50,000 | $80,000 | $80,000 | $1,000,000 |

**Key insight:** Below a ΣDF of $625M, the proportional K_CCP method dominates. Above $625M total DF, the 1.6% floor becomes binding. Larger CCPs with more clearing members distribute K_CCP more widely — benefiting large members.

### Effect of VM Netting on Trade Capital

Assume: trade_ead = $100M, QCCP RW = 2%

| VM Posted | Net EAD | RWA | Capital | VM Netting Saving |
|---|---|---|---|---|
| $0 | $100M | $25,000,000 | $2,000,000 | — |
| $10M | $90M | $22,500,000 | $1,800,000 | $200,000 |
| $25M | $75M | $18,750,000 | $1,500,000 | $500,000 |
| $50M | $50M | $12,500,000 | $1,000,000 | $1,000,000 |
| $80M | $20M | $5,000,000 | $400,000 | $1,600,000 |

**Implication:** Active VM management directly reduces CCP capital. Banks with large IM/VM posting capabilities at major CCPs carry significantly lower capital on their cleared books.

