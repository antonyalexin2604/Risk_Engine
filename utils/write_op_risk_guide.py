#!/usr/bin/env python3
"""Write Operational Risk Technical Guide"""

content = """# Operational Risk Technical Guide
## Standardised Measurement Approach — SMA (OPE25)
### PROMETHEUS Risk Platform

---

## Table of Contents

1. Overview and Regulatory Basis
2. SMA Architecture
3. Business Indicator Component (BIC)
4. Internal Loss Multiplier (ILM)
5. Operational Risk RWA
6. Loss Event Classification
7. Data Structures Reference
8. Glossary

**Appendix A** — BIC Calculation: Mid-Tier Bank Example
**Appendix B** — ILM Calculation with Elevated Loss History
**Appendix C** — Full SMA Capital Computation
**Appendix D** — Loss Event Classification Examples

---

## 1. Overview and Regulatory Basis

The Standardised Measurement Approach (SMA) is the Basel III/IV methodology for computing
operational risk capital. It replaced the Basic Indicator Approach (BIA) and Standardised
Approach (TSA) from Basel II.

| Regulation | Topic |
|---|---|
| OPE25 | SMA methodology — BIC + ILM |
| RBC20.10 | Operational risk capital in total RWA |
| OPE25.3 | Business Indicator subcomponents |
| OPE25.9 | BIC marginal coefficients by bucket |
| OPE25.12 | ILM formula |
| OPE25.15 | Loss data requirements |

Key formula:

    Operational Risk Capital = BIC x ILM
    RWA_OpRisk = Capital x 12.5

---

## 2. SMA Architecture

    Income Statement Data (3-year average)
            |
            v
    Business Indicator (BI) = ILDC + SC + FC
            |
            v
    Business Indicator Component (BIC)
      Bucket 1 (BI <= EUR 1bn):    BIC = BI x 12%
      Bucket 2 (EUR 1bn-30bn):     BIC = EUR 120M + (BI - 1bn) x 15%
      Bucket 3 (BI > EUR 30bn):    BIC = EUR 4,470M + (BI - 30bn) x 18%
            |
            v
    Internal Loss Multiplier (ILM)
      ILM = ln(e - 1 + (Loss_Component / BIC)^0.8)
      where Loss_Component = 15 x avg_annual_loss_10yr
            |
            v
    Capital = BIC x ILM
    RWA = Capital x 12.5

---

## 3. Business Indicator Component (BIC)

### Business Indicator (BI) Subcomponents

The BI captures three income streams that correlate with operational risk exposure:

**ILDC — Interest, Leases, Dividends Component:**

    ILDC = |Net_Interest_Income| + |Net_Lease_Income| + |Dividend_Income|

**SC — Services Component:**

    SC = max(Fee_Income, Fee_Expense) + max(Other_Op_Income, Other_Op_Expense)

**FC — Financial Component:**

    FC = |Net_P&L_Trading_Book| + |Net_P&L_Banking_Book|

**Business Indicator:**

    BI = ILDC + SC + FC

### BIC Marginal Coefficients (OPE25.9)

| Bucket | BI Range | Marginal Rate | Computation |
|---|---|---|---|
| 1 | <= EUR 1bn | 12% | BI x 0.12 |
| 2 | EUR 1-30bn | 15% | 120M + (BI - 1bn) x 0.15 |
| 3 | > EUR 30bn | 18% | 4,470M + (BI - 30bn) x 0.18 |

The marginal rates are progressive — large banks pay a higher rate on incremental BI. This
reflects the supervisory view that large banks have disproportionately higher operational risk
due to complexity, global footprint, and regulatory exposure.

---

## 4. Internal Loss Multiplier (ILM)

The ILM adjusts BIC upward or downward based on the bank's actual historical loss experience
versus the industry average implied by BIC.

    Loss_Component = 15 x avg_annual_loss_10yr

    ILM = ln(e - 1 + (Loss_Component / BIC)^0.8)

### ILM Behaviour Table

| Loss_Component / BIC | ILM | Interpretation |
|---|---|---|
| 0.10 | 0.53 | Very clean loss history — 47% capital reduction |
| 0.50 | 0.82 | Below-average losses |
| 1.00 | 1.00 | Average (ILM = 1 by construction) |
| 2.00 | 1.20 | Above-average losses — 20% surcharge |
| 5.00 | 1.51 | High losses — 51% surcharge |
| 10.00 | 1.72 | Very high losses — 72% surcharge |

### ILM Properties

1. **Calibrated to industry average:** When Loss_Component equals BIC, ILM = 1.0 exactly.
   Banks below average benefit; banks above average are penalised.

2. **Concave penalty function:** The 0.8 exponent means each additional dollar of losses has
   diminishing marginal impact — prevents runaway capital from extreme one-off events.

3. **Supervisory override:** National supervisors may set ILM = 1.0 (BIC-only) for Bucket 1
   banks. For Buckets 2 and 3, ILM must be applied as computed.

4. **10-year horizon:** Requires 10 years of high-quality internal loss data. Shorter
   histories may require supervisory estimates for missing years.

---

## 5. Operational Risk RWA

    Capital    = BIC x ILM
    RWA_OpRisk = Capital x 12.5    [from RBC20.10: RWA = Capital / 8%]

Operational Risk RWA feeds into Total RWA alongside Credit Risk, Market Risk, and CVA.

---

## 6. Loss Event Classification

### Basel Event Types (Level 1)

| Code | Category | Common Examples |
|---|---|---|
| INTERNAL_FRAUD | Internal Fraud | Rogue trading (Barings, SocGen), employee theft |
| EXTERNAL_FRAUD | External Fraud | Cyber attacks, card skimming, check fraud |
| EPWS | Employment Practices and Workplace Safety | Wrongful dismissal, discrimination claims |
| CPBP | Clients, Products and Business Practices | Mis-selling, LIBOR manipulation |
| DPA | Damage to Physical Assets | Natural disasters, terrorism |
| BDSF | Business Disruption and System Failures | IT outages, power failures |
| EDPM | Execution, Delivery and Process Management | Settlement fails, documentation errors |

### Loss Capture Thresholds (OPE25.15)

| Threshold | Requirement |
|---|---|
| >= EUR 20,000 | Must be captured in loss database |
| >= EUR 100,000 | Must include detailed root cause analysis |
| Near-misses | Should be captured qualitatively |

### Net Loss Definition

    Net_Loss = Gross_Loss - Recoveries - Insurance_Recovery

Only net losses enter the ILM calculation. Direct recoveries and insurance payments reduce
the loss amount. Multi-year settlements may require timing adjustments.

---

## 7. Data Structures Reference

### LossEvent

| Field | Type | Description |
|---|---|---|
| event_id | str | Unique loss event identifier |
| event_date | date | Date loss occurred |
| discovery_date | date | Date loss was discovered |
| booking_date | date | Date booked to P&L |
| event_type | str | Basel Level 1 category (CPBP, EDPM, etc.) |
| business_line | str | Basel business line |
| gross_loss_amount | float | Total loss (EUR millions) |
| recoveries | float | Direct recoveries (EUR millions) |
| insurance_recovery | float | Insurance recoveries (EUR millions) |
| description | str | Narrative description |
| root_cause | str | Root cause analysis |

### BusinessIndicatorData

| Field | Description |
|---|---|
| net_interest_income | NII from banking book activities |
| net_lease_income | Net lease income |
| dividend_income | Dividends received |
| fee_income | Fee and commission income |
| fee_expense | Fee and commission expense |
| other_operating_income | Other operating income |
| other_operating_expense | Other operating expense |
| net_trading_pnl | Net P&L from trading book |
| net_banking_book_pnl | Net P&L from banking book instruments |

---

## 8. Glossary

| Term | Definition |
|---|---|
| SMA | Standardised Measurement Approach |
| BI | Business Indicator |
| BIC | Business Indicator Component |
| ILM | Internal Loss Multiplier |
| ILDC | Interest, Leases, Dividends Component |
| SC | Services Component |
| FC | Financial Component |
| CPBP | Clients, Products and Business Practices |
| EDPM | Execution, Delivery and Process Management |
| BIA | Basic Indicator Approach (replaced by SMA) |
| TSA | Traditional Standardised Approach (replaced by SMA) |

---

## Appendix A — BIC Calculation: Mid-Tier Bank

### Income Statement Data (EUR millions, 3-year average)

| Component | Value (EUR M) |
|---|---|
| Net Interest Income | 2,800 |
| Net Lease Income | 150 |
| Dividend Income | 80 |
| Fee Income | 1,200 |
| Fee Expense | 400 |
| Other Operating Income | 300 |
| Other Operating Expense | 350 |
| Net Trading P&L | 500 |
| Net Banking Book P&L | -100 (loss) |

### Step 1: BI Subcomponents

    ILDC = 2,800 + 150 + 80 = EUR 3,030M

    SC   = max(1,200, 400) + max(300, 350)
         = 1,200 + 350
         = EUR 1,550M

    FC   = |500| + |-100|
         = 500 + 100
         = EUR 600M

### Step 2: Business Indicator

    BI = ILDC + SC + FC
       = 3,030 + 1,550 + 600
       = EUR 5,180M

### Step 3: BIC (Bucket 2 — EUR 1-30bn)

    BIC = 120 + (5,180 - 1,000) x 15%
        = 120 + 4,180 x 0.15
        = 120 + 627
        = EUR 747M

---

## Appendix B — ILM Calculation

### 10-Year Loss History (EUR M per year)

| Year | Net Loss |
|---|---|
| Y-10 | 85 |
| Y-9 | 120 |
| Y-8 | 45 |
| Y-7 | 310 (large CPBP settlement) |
| Y-6 | 90 |
| Y-5 | 65 |
| Y-4 | 180 |
| Y-3 | 55 |
| Y-2 | 100 |
| Y-1 | 75 |

    Average Annual Loss = (85+120+45+310+90+65+180+55+100+75) / 10
                        = 1,125 / 10
                        = EUR 112.5M

    Loss_Component = 15 x 112.5 = EUR 1,687.5M

### ILM Computation (BIC = EUR 747M from Appendix A)

    Ratio = 1,687.5 / 747 = 2.259

    ILM = ln(e - 1 + 2.259^0.8)
        = ln(2.71828 - 1 + 2.0146)
        = ln(3.7329)
        = 1.317

ILM = 1.317 means a 31.7% capital surcharge vs. industry average.

The Year Y-7 CPBP event (EUR 310M) is the dominant driver. As this event ages out of the
10-year window, the average will fall and ILM will reduce toward 1.0.

---

## Appendix C — Full SMA Capital Computation

Continuing from Appendices A and B:

    BIC     = EUR 747M
    ILM     = 1.317

    Capital = BIC x ILM = 747 x 1.317 = EUR 983.8M

    RWA     = Capital x 12.5 = 983.8 x 12.5 = EUR 12,297M (approx EUR 12.3bn)

As a percentage of BI: 983.8 / 5,180 = 19.0%
(Above the 15% Bucket 2 base rate due to the ILM surcharge.)

**Management takeaway:** Reducing CPBP risk exposure through improved controls and product
governance is the highest-value operational risk lever for this bank. As Y-7 rolls off the
10-year window in 3 years, ILM will mechanically decline — but only if no comparable event
occurs in the interim.

---

## Appendix D — Loss Event Classification Examples

| Scenario | Event Type | Business Line | Notes |
|---|---|---|---|
| Employee submits false expense claims EUR 200k | INTERNAL_FRAUD | CORPORATE_FINANCE | Must be captured; below EUR 1M but above threshold |
| Customer account hacked; EUR 50k stolen | EXTERNAL_FRAUD | RETAIL_BANKING | Insurance recovery reduces net loss |
| Mis-sold structured products; EUR 500M settlement | CPBP | RETAIL_BANKING | Largest event type by loss; often discovered years later |
| IT failure causes 4-hour trading outage; EUR 15M | BDSF | TRADING_SALES | System resilience failure |
| Derivatives settlement error; EUR 2M late fee | EDPM | PAYMENT_SETTLEMENT | Process control failure |
| Office destroyed in flood; EUR 5M reconstruction | DPA | All lines | Property loss + business interruption |

### Historical Context: Why CPBP Dominates

Industry data consistently shows CPBP (Clients, Products & Business Practices) generates the
largest losses by severity, even though EDPM generates more frequent (but smaller) events:

| Event Type | Frequency | Severity per Event | % of Total Industry Losses |
|---|---|---|---|
| CPBP | Low | Very High | ~40-50% |
| EDPM | High | Low-Medium | ~20-25% |
| EXTERNAL_FRAUD | Medium | Medium | ~15-20% |
| INTERNAL_FRAUD | Low | High (tail) | ~10-15% |
| Other | Low | Variable | ~5-10% |

Banks with large retail or wealth management businesses should prioritise CPBP controls and
conduct risk monitoring as the primary operational risk management lever.
"""

with open('/Users/aaron/Documents/Project/Prometheus/docs/OPERATIONAL_RISK_TECHNICAL_GUIDE.md', 'w') as f:
    f.write(content)
print("Operational Risk guide written successfully.")

