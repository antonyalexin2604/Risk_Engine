"""
PROMETHEUS — Fix 6  (G-SIB Capital Surcharge + Three-Tier Structure)
──────────────────────────────────────────────────────────────────────
Fix 6 (HIGH | RBC20 / BCBS G-SIB framework): G-SIB buffer and proper
three-tier capital breakdown (CET1 / AT1 / Tier 2).

Issues in current main.py:
  (a) No G-SIB surcharge applied (1%–3.5% additional CET1 required)
  (b) Capital is derived from RWA (backwards logic):
      cet1 = rwa * 0.13   ← wrong direction
      Should be: cet1_ratio = cet1_actual / rwa (ratio from actual capital)
  (c) No distinction between CET1 floor, conservation buffer, G-SIB buffer
  (d) AT1 and T2 computed as multiples of CET1 — not regulatory definitions

HOW TO APPLY
────────────
Import GSIBCapitalFramework in backend/main.py and replace the capital
summary block with calls to compute_capital_adequacy().
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ─── G-SIB Bucket Configuration ───────────────────────────────────────────────

@dataclass
class GSIBProfile:
    """
    G-SIB identification and applicable capital surcharge.

    BCBS G-SIB framework: banks are assigned to five buckets based on
    their systemic importance score. The surcharge ranges from 1.0% to
    3.5% of CET1 (additional to the base 7.0% CET1 requirement).

    US G-SIB surcharge (OCC/Fed rule, Method 2) may differ from BCBS
    buckets — US firms are subject to Method 1 AND Method 2 (whichever
    is higher). PROMETHEUS uses BCBS buckets for regulatory purposes.
    """
    bank_name:    str   = "PROMETHEUS Bank"
    gsib_bucket:  int   = 2        # BCBS bucket 1–5 (1=lowest, 5=empty bucket)
    ccyb_rate:    float = 0.0      # Countercyclical buffer (jurisdiction-specific)
    is_us_gsib:   bool  = True     # US G-SIBs face additional TLAC/SLR requirements

    # BCBS surcharge table (MAR / BCBS G-SIB framework)
    _SURCHARGE_TABLE: Dict[int, float] = field(default_factory=lambda: {
        1: 0.010,   # 1.0% — bucket 1
        2: 0.015,   # 1.5% — bucket 2
        3: 0.020,   # 2.0% — bucket 3
        4: 0.025,   # 2.5% — bucket 4
        5: 0.035,   # 3.5% — bucket 5 (currently empty)
    })

    @property
    def gsib_surcharge(self) -> float:
        """G-SIB CET1 surcharge as a decimal (e.g. 0.015 = 1.5%)."""
        return self._SURCHARGE_TABLE.get(self.gsib_bucket, 0.015)

    @property
    def total_cet1_minimum(self) -> float:
        """
        Total minimum CET1 ratio:
          4.5% minimum + 2.5% conservation buffer + CCyB + G-SIB surcharge
        """
        return 0.045 + 0.025 + self.ccyb_rate + self.gsib_surcharge

    @property
    def total_tier1_minimum(self) -> float:
        """Minimum T1 = CET1 min + 1.5% AT1 minimum."""
        return self.total_cet1_minimum + 0.015

    @property
    def total_capital_minimum(self) -> float:
        """Minimum Total Capital = T1 min + 2.0% T2 minimum."""
        return self.total_tier1_minimum + 0.020


@dataclass
class CapitalBase:
    """
    Actual capital by tier, as reported in the balance sheet.
    Populate from the bank's regulatory capital report (call report / FFIEC).

    For PROMETHEUS demo purposes, these are simulated based on assumptions
    consistent with a US G-SIB targeting a 12–13% CET1 ratio.
    """
    cet1_actual:   float    # Common Equity Tier 1 capital (USD)
    at1_actual:    float    # Additional Tier 1 capital (USD)
    tier2_actual:  float    # Tier 2 capital (USD)

    @property
    def tier1_total(self) -> float:
        return self.cet1_actual + self.at1_actual

    @property
    def total_capital(self) -> float:
        return self.tier1_total + self.tier2_actual


def simulate_capital_base(rwa_total: float, target_cet1_ratio: float = 0.130) -> CapitalBase:
    """
    Simulate a plausible capital base for a US G-SIB targeting a ~13% CET1 ratio.
    
    Replace this with actual regulatory capital data from the bank's FFIEC 101
    or equivalent regulatory capital report in production.

    Typical US G-SIB capital stack (approximate):
      CET1 ~ 13% of RWA  (well above 8%–10.5% minimums)
      AT1  ~  1.5% of RWA
      T2   ~  2.0% of RWA
    """
    cet1  = rwa_total * target_cet1_ratio
    at1   = rwa_total * 0.015   # AT1: minimum 1.5%, typically AT1 notes/pref shares
    tier2 = rwa_total * 0.020   # T2: subordinated debt, general loan loss reserves
    return CapitalBase(cet1_actual=cet1, at1_actual=at1, tier2_actual=tier2)


def compute_capital_adequacy(
    rwa_total:   float,
    gsib:        GSIBProfile,
    capital:     Optional[CapitalBase] = None,
) -> Dict:
    """
    Compute regulatory capital adequacy with proper G-SIB framework.

    Returns a dict suitable for the capital_summary key in main.py results,
    replacing the current simplified cet1 = rwa * 0.13 logic.

    Args:
        rwa_total: Final regulatory RWA (after output floor, Fix 4)
        gsib:      G-SIB profile with bucket and CCyB
        capital:   Actual capital by tier; if None, simulates a plausible base

    Returns:
        Dict with all capital adequacy metrics for the dashboard.
    """
    cap = capital or simulate_capital_base(rwa_total)

    # ── Capital ratios ────────────────────────────────────────────────────────
    cet1_ratio  = cap.cet1_actual  / rwa_total if rwa_total > 0 else 0.0
    t1_ratio    = cap.tier1_total  / rwa_total if rwa_total > 0 else 0.0
    tc_ratio    = cap.total_capital / rwa_total if rwa_total > 0 else 0.0

    # ── Minimum requirements (G-SIB adjusted) ────────────────────────────────
    cet1_min  = gsib.total_cet1_minimum
    t1_min    = gsib.total_tier1_minimum
    tc_min    = gsib.total_capital_minimum

    # ── Headroom (capital ratio minus minimum) ────────────────────────────────
    cet1_headroom = cet1_ratio - cet1_min
    t1_headroom   = t1_ratio   - t1_min
    tc_headroom   = tc_ratio   - tc_min

    # ── Breach flags ─────────────────────────────────────────────────────────
    cet1_breach = cet1_ratio < cet1_min
    t1_breach   = t1_ratio   < t1_min
    tc_breach   = tc_ratio   < tc_min

    # ── Maximum distributable amount (MDA) trigger ───────────────────────────
    # MDA restricts dividends/buybacks if CET1 is below the combined buffer
    combined_buffer = 0.025 + gsib.ccyb_rate + gsib.gsib_surcharge
    mda_trigger     = cet1_ratio < (0.045 + combined_buffer)

    logger.info("=" * 65)
    logger.info("CAPITAL ADEQUACY [Fix 6 — G-SIB Framework]")
    logger.info("  Bank: %s | Bucket: %d | Surcharge: %.1f%% | CCyB: %.1f%%",
                gsib.bank_name, gsib.gsib_bucket,
                gsib.gsib_surcharge * 100, gsib.ccyb_rate * 100)
    logger.info("  RWA Total      : USD %14.0f", rwa_total)
    logger.info("  ─── Capital ─────────────────────────────────────────────")
    logger.info("  CET1           : USD %14.0f  (%.2f%%)  min=%.2f%%  %s",
                cap.cet1_actual, cet1_ratio * 100, cet1_min * 100,
                "BREACH" if cet1_breach else "OK")
    logger.info("  AT1            : USD %14.0f", cap.at1_actual)
    logger.info("  Tier 1 Total   : USD %14.0f  (%.2f%%)  min=%.2f%%  %s",
                cap.tier1_total, t1_ratio * 100, t1_min * 100,
                "BREACH" if t1_breach else "OK")
    logger.info("  Tier 2         : USD %14.0f", cap.tier2_actual)
    logger.info("  Total Capital  : USD %14.0f  (%.2f%%)  min=%.2f%%  %s",
                cap.total_capital, tc_ratio * 100, tc_min * 100,
                "BREACH" if tc_breach else "OK")
    logger.info("  ─── G-SIB Buffers ───────────────────────────────────────")
    logger.info("  4.5%% CET1 min + 2.5%% conservation + %.1f%% G-SIB + %.1f%% CCyB = %.1f%% CET1 min",
                gsib.gsib_surcharge * 100, gsib.ccyb_rate * 100, cet1_min * 100)
    logger.info("  CET1 headroom  : %+.2f%%  %s",
                cet1_headroom * 100, "⚠ MDA TRIGGER" if mda_trigger else "")
    logger.info("=" * 65)

    return {
        # Capital amounts
        "cet1_capital":        cap.cet1_actual,
        "at1_capital":         cap.at1_actual,
        "tier2_capital":       cap.tier2_actual,
        "tier1_capital":       cap.tier1_total,
        "total_capital":       cap.total_capital,

        # Ratios
        "cet1_ratio":          round(cet1_ratio, 6),
        "tier1_ratio":         round(t1_ratio, 6),
        "total_cap_ratio":     round(tc_ratio, 6),

        # Minimums (G-SIB adjusted)
        "cet1_minimum":        round(cet1_min, 6),
        "tier1_minimum":       round(t1_min, 6),
        "total_cap_minimum":   round(tc_min, 6),

        # G-SIB framework
        "gsib_bucket":         gsib.gsib_bucket,
        "gsib_surcharge":      gsib.gsib_surcharge,
        "conservation_buffer": 0.025,
        "ccyb_rate":           gsib.ccyb_rate,

        # Buffer components
        "combined_buffer_rate": combined_buffer,

        # Headroom
        "cet1_headroom":       round(cet1_headroom, 6),
        "tier1_headroom":      round(t1_headroom, 6),
        "tc_headroom":         round(tc_headroom, 6),

        # Status
        "cet1_breach":         cet1_breach,
        "tier1_breach":        t1_breach,
        "total_cap_breach":    tc_breach,
        "mda_trigger":         mda_trigger,
        "any_breach":          cet1_breach or t1_breach or tc_breach,
    }


# ─── Default G-SIB profile for PROMETHEUS (US G-SIB, Bucket 2) ────────────────
DEFAULT_GSIB = GSIBProfile(
    bank_name    = "PROMETHEUS Bank N.A.",
    gsib_bucket  = 2,       # 1.5% surcharge — mid-range US G-SIB
    ccyb_rate    = 0.0,     # Update when Fed activates CCyB
    is_us_gsib   = True,
)


# ─── INTEGRATION INSTRUCTIONS ─────────────────────────────────────────────────
INTEGRATION_NOTE = """
Steps to apply Fix 6 to backend/main.py and dashboard/app.py:

IN backend/main.py:
  1. Import this module:
       from backend.engines.gsib_capital import (
           compute_capital_adequacy, DEFAULT_GSIB, simulate_capital_base
       )

  2. REPLACE the capital summary block:
       BEFORE:
         cet1 = rwa_total * 0.13; tier1 = cet1 * 1.10; total_cap = tier1 * 1.20
         ...
       AFTER:
         cap_result = compute_capital_adequacy(rwa_total, gsib=DEFAULT_GSIB)
         results["capital_summary"] = {
             **results["capital_summary"],   # keep existing RWA fields
             **cap_result,                   # add G-SIB capital fields
         }

  3. Add GSIB profile to config (backend/config.py):
       GSIB_BUCKET = 2        # Set to actual BCBS bucket
       CCYB_RATE   = 0.0     # Update when countercyclical buffer activated

IN dashboard/app.py (Capital page):
  4. Replace the ratio display to show three-tier breakdown:
       CET1 ratio vs CET1 minimum (4.5% + 2.5% conservation + CCyB + G-SIB)
       AT1 ratio  vs AT1 minimum  (1.5%)
       T2 ratio   vs T2 minimum   (2.0%)
       Total capital vs total minimum

  5. Add G-SIB buffer waterfall chart:
       4.5% base | 2.5% conservation | X.X% G-SIB | Y.Y% CCyB | actual CET1

  6. Add MDA trigger indicator (red alert when CET1 < combined buffer threshold)

FILE LOCATION: Save this file as backend/engines/gsib_capital.py

Basel references: RBC20.6, BCBS G-SIB framework (Nov 2022 update),
                  US Fed Regulation Q (12 CFR 217)
"""

if __name__ == "__main__":
    # Quick demo
    rwa = 500_000_000_000   # $500bn RWA — representative US G-SIB
    result = compute_capital_adequacy(rwa, gsib=DEFAULT_GSIB)
    print(f"\nCET1 ratio: {result['cet1_ratio']:.2%}  (min {result['cet1_minimum']:.2%})")
    print(f"T1 ratio:   {result['tier1_ratio']:.2%}  (min {result['tier1_minimum']:.2%})")
    print(f"TC ratio:   {result['total_cap_ratio']:.2%}  (min {result['total_cap_minimum']:.2%})")
    print(f"G-SIB bucket {result['gsib_bucket']} surcharge: {result['gsib_surcharge']:.1%}")
    print(INTEGRATION_NOTE)
