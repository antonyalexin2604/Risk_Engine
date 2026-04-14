"""
PROMETHEUS Risk Platform
Engine: CCP Exposure — Central Counterparty Capital
Regulatory basis: CRE54 (effective Jan 2023), CRE51.9, CRE55

Implements:
  - Trade exposure to Qualifying CCPs (QCCPs) — cleared derivatives (CRE54.4)
  - Variation Margin netting against trade EAD (CRE54.4)
  - Initial Margin: segregated (0% RW) vs. non-segregated (2% RW) (CRE54.15)
  - Default Fund Contribution (DFC) capital:
      Risk-sensitive method  (CRE54.32–36): proportional share K_i = (DF_i/ΣDF) × K_CCP
      Floor                  (CRE54.38):    K_i ≥ DF_i × 1.6%  → enforced via max()
  - Unfunded DFC at 1250% RW for QCCP and non-QCCP (CRE54.42)
  - Non-QCCP: standard credit RW framework (CRE54.40–42)
  - Client clearing — intermediary role (CRE54.5)
  - Client clearing — guarantee look-through (CRE54.6)
  - Equity / investment in CCP at 250% RW (CRE54.17)

Gap Remediation vs. prior implementation:
  GAP-CCP-01  CRE54.32–36: DFC capital uses proportional share (DF_i / ΣDF × K_CCP).
              `df_total` field added to CCPExposure. Old code used 0.08 × K_CCP (wrong).
  GAP-CCP-02  CRE54.38:    Floor enforced with max(), not min().
              Old code used min() — inverted the floor into a cap, massively under-stating DFC capital.
  GAP-CCP-03  CRE54.4:     `vm_posted` field added; VM netted against trade EAD before RW.
  GAP-CCP-04  CRE54.17:    `equity_in_ccp` field added → 250% RW treatment.
  GAP-CCP-05  CRE54.5–6:   `client_guarantee` flag added → look-through RW when bank backstops.
  GAP-CCP-06  CRE54.42:    Unfunded DFC uses explicit 1250% RW path for both QCCP and non-QCCP.
  GAP-CCP-07              Input validation via _validate_ccp_exposure().
  GAP-CCP-08              CCPResult extended with per-component capital breakdown.
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Risk Weights ─────────────────────────────────────────────────────────────
# NOTE: The codebase convention is to treat 'rw' as a direct capital percentage,
# so RWA = EAD × rw × 12.5  (where capital = EAD × rw and RWA = capital / 8%).
# This is consistent throughout the Prometheus engine suite (SA-CCR, CVA, etc.).

QCCP_TRADE_RW       = 0.02    # CRE54.4  : 2%   capital charge on cleared trade exposures to QCCP
NON_QCCP_TRADE_RW   = 1.00    # CRE54.40 : 100% capital (standard unsecured corporate RW fallback)
EQUITY_IN_CCP_RW    = 2.50    # CRE54.17 : 250% capital on equity / investment in a CCP
DFC_FLOOR_RATE      = 0.016   # CRE54.38 : 1.6% of funded DF as minimum capital floor
CLIENT_GUARANTEE_RW = 1.00    # CRE54.6  : 100% capital when bank guarantees client performance
                               #            (conservative proxy for look-through to client creditworthiness)


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class CCPExposure:
    """
    Inputs for one bank-to-CCP relationship.
    One CCPExposure instance per CCP (not per trade).
    Trade-level EADs are aggregated into trade_ead via SA-CCR / IMM upstream.
    """
    ccp_name:             str
    is_qualifying:        bool  = True    # QCCP (LCH, CME, Eurex, ICE, JSCC etc.)

    # ── Trade Exposure (CRE54.4) ──────────────────────────────────────────────
    trade_ead:            float = 0.0    # Aggregate EAD of cleared trades (from SA-CCR / IMM)
    vm_posted:            float = 0.0    # Variation Margin posted to CCP
                                          # GAP-CCP-03: Net trade EAD = max(trade_ead − vm_posted, 0)

    # ── Initial Margin (CRE54.15) ─────────────────────────────────────────────
    im_posted:            float = 0.0    # IM posted by bank to CCP
    im_segregated:        bool  = True   # True  → legally segregated & bankruptcy-remote → 0% RW
                                          # False → commingled / non-segregated              → 2% RW

    # ── Funded Default Fund (CRE54.32–38) ─────────────────────────────────────
    df_contribution:      float = 0.0    # Bank's funded DF contribution (DF_i)
    df_total:             float = 0.0    # Total funded DF of ALL clearing members (ΣDF_CM)
                                          # GAP-CCP-01: required for risk-sensitive method (CRE54.32)
                                          # If 0 → falls back to 1.6% floor only (CRE54.38)
    kccp:                 float = 0.0    # Hypothetical capital of the CCP (K_CCP) disclosed by CCP
                                          # CRE54.32: computed by CCP as if it were a clearing member

    # ── Unfunded Default Fund (CRE54.42) ─────────────────────────────────────
    df_unfunded:          float = 0.0    # Unfunded / contingent DF commitment → 1250% RW

    # ── Equity / Investment in CCP (CRE54.17) ─────────────────────────────────
    equity_in_ccp:        float = 0.0    # Equity stake or exchange seat treated as equity
                                          # GAP-CCP-04: 250% RW for QCCP equity holdings

    # ── Client Clearing — Intermediary Role (CRE54.5–9) ──────────────────────
    is_clearing_member:   bool  = True
    client_ead:           float = 0.0    # EAD of positions where bank is CM for its clients
    client_guarantee:     bool  = False  # GAP-CCP-05: True = bank guarantees client performance
                                          # CRE54.6: look-through to client credit RW (not 2%)

    # ── Non-QCCP Credit Quality (CRE54.40–42) ────────────────────────────────
    non_qccp_rw:          float = NON_QCCP_TRADE_RW  # Override for specific non-QCCP credit quality


@dataclass
class CCPResult:
    """
    Per-CCP capital result with full component breakdown.
    GAP-CCP-08: Extended from prior implementation to expose each sub-charge.
    """
    ccp_name:              str
    is_qualifying:         bool

    # ── Trade Exposure ─────────────────────────────────────────────────────────
    net_trade_ead:         float    # trade_ead net of VM (CRE54.4)
    rwa_trade:             float    # net_trade_ead × RW × 12.5
    rwa_im:                float    # IM (non-seg only) × RW × 12.5
    capital_trade:         float    # (rwa_trade + rwa_im) × 8%

    # ── Default Fund ──────────────────────────────────────────────────────────
    k_dfc:                 float    # DFC required capital (from risk-sensitive or floor method)
    rwa_dfc:               float    # k_dfc × 12.5
    rwa_unfunded:          float    # df_unfunded × 12.5  (1250% RW → 100% capital)
    dfc_method:            str      # "risk_sensitive" | "floor_only" | "non_qccp" | "no_df"

    # ── Equity in CCP ─────────────────────────────────────────────────────────
    rwa_equity_in_ccp:     float

    # ── Client Clearing ────────────────────────────────────────────────────────
    rwa_client:            float
    client_rw_note:        str      # describes which RW was applied to client EAD

    # ── Totals ─────────────────────────────────────────────────────────────────
    rwa_total:             float
    capital_total:         float    # rwa_total × 8%
    trade_rw:              float    # risk weight applied to trade EAD
    method_note:           str


# ─── Input Validation ─────────────────────────────────────────────────────────

def _validate_ccp_exposure(exp: CCPExposure) -> None:
    """
    Guard-rail validation on CCPExposure inputs.
    Raises ValueError on fatal issues; logs warnings on suspicious (but non-fatal) data.
    GAP-CCP-07.
    """
    for attr, label in [
        ("trade_ead",       "trade_ead"),
        ("vm_posted",       "vm_posted"),
        ("im_posted",       "im_posted"),
        ("df_contribution", "df_contribution"),
        ("df_total",        "df_total"),
        ("df_unfunded",     "df_unfunded"),
        ("equity_in_ccp",   "equity_in_ccp"),
        ("client_ead",      "client_ead"),
        ("kccp",            "kccp"),
    ]:
        val = getattr(exp, attr)
        if val < 0:
            raise ValueError(
                f"[{exp.ccp_name}] {label} must be ≥ 0, got {val:.2f}"
            )

    if exp.df_total > 0 and exp.df_contribution > exp.df_total:
        logger.warning(
            "[%s] df_contribution (%.0f) > df_total (%.0f) — capping proportional "
            "share at 100%% in DFC calculation.", exp.ccp_name,
            exp.df_contribution, exp.df_total
        )

    if exp.kccp > 0 and exp.df_total == 0:
        logger.warning(
            "[%s] K_CCP (%.0f) provided but df_total=0 — cannot apply risk-sensitive "
            "method (CRE54.32). Falling back to 1.6%% floor.", exp.ccp_name, exp.kccp
        )

    if exp.vm_posted > exp.trade_ead:
        logger.warning(
            "[%s] vm_posted (%.0f) > trade_ead (%.0f) — net trade EAD floored at 0.",
            exp.ccp_name, exp.vm_posted, exp.trade_ead
        )

    if exp.client_guarantee and not exp.is_clearing_member:
        logger.warning(
            "[%s] client_guarantee=True but is_clearing_member=False — "
            "guarantee flag has no effect.", exp.ccp_name
        )


# ─── DFC Capital Calculation ──────────────────────────────────────────────────

def _compute_dfc_capital_qccp(exp: CCPExposure) -> Tuple[float, str]:
    """
    Funded Default Fund capital charge for a QCCP per CRE54.32–38.

    Risk-sensitive method (CRE54.33–36) — requires both kccp AND df_total:
        proportional_k  = (DF_i / ΣDF_CM) × K_CCP        [CRE54.33]
        floor_k         = DF_i × 1.6%                      [CRE54.38]
        K_i             = max(proportional_k, floor_k)      [GAP-CCP-02: max not min]

    Fallback — floor only (CRE54.38) — when kccp or df_total unavailable:
        K_i             = DF_i × 1.6%

    Returns (k_dfc [capital amount], method_label).
    RWA is computed by the caller: rwa_dfc = k_dfc × 12.5.
    """
    if exp.df_contribution <= 0:
        return 0.0, "no_df"

    if exp.kccp > 0 and exp.df_total > 0:
        # GAP-CCP-01: Proportional share of K_CCP (CRE54.33)
        df_share       = min(exp.df_contribution / exp.df_total, 1.0)
        proportional_k = df_share * exp.kccp
        floor_k        = exp.df_contribution * DFC_FLOOR_RATE
        # GAP-CCP-02: max() enforces floor (floor = minimum, not cap)
        k_dfc          = max(proportional_k, floor_k)
        method         = "risk_sensitive"
        logger.debug(
            "[%s] DFC risk-sensitive: share=%.2f%% prop_K=%.0f floor_K=%.0f K_i=%.0f",
            exp.ccp_name, df_share * 100, proportional_k, floor_k, k_dfc
        )
    else:
        # CRE54.38 fallback: 1.6% floor only
        k_dfc  = exp.df_contribution * DFC_FLOOR_RATE
        method = "floor_only"
        logger.debug("[%s] DFC floor-only: K_i=%.0f (1.6%% × %.0f)",
                     exp.ccp_name, k_dfc, exp.df_contribution)

    return k_dfc, method


# ─── Master RWA Calculator ────────────────────────────────────────────────────

def compute_ccp_rwa(exposures: List[CCPExposure]) -> dict:
    """
    Compute CCP capital charges per CRE54.

    ── QCCP (CRE54.4–42) ──────────────────────────────────────────────────────

    Trade EAD (net of VM):     EAD_net = max(trade_ead − vm_posted, 0)       [CRE54.4 / GAP-CCP-03]
                               RWA     = EAD_net × 2% × 12.5

    IM posted (CRE54.15):      Segregated → 0% RW
                               Non-segregated → 2% RW × 12.5

    Funded DFC (CRE54.32–38):  K_i = max((DF_i / ΣDF) × K_CCP, DF_i × 1.6%)  [GAP-CCP-01/02]
                               RWA = K_i × 12.5

    Unfunded DFC (CRE54.42):   1250% RW → capital = 100% × df_unfunded
                               RWA = df_unfunded × 12.5                        [GAP-CCP-06]

    Equity in QCCP (CRE54.17): 250% capital charge                            [GAP-CCP-04]
                               RWA = equity_in_ccp × 2.50 × 12.5

    ── Non-QCCP (CRE54.40–42) ─────────────────────────────────────────────────

    All exposures use standard credit RW (default 100%; override via non_qccp_rw).
    Unfunded DF → 1250% RW regardless (CRE54.42 applies to both QCCP and non-QCCP).

    ── Client Clearing (CRE54.5–6) ────────────────────────────────────────────

    CM without guarantee (CRE54.5): 2% RW pass-through (QCCP) or standard RW (non-QCCP).
    CM with guarantee    (CRE54.6): Look-through to client credit → CLIENT_GUARANTEE_RW. [GAP-CCP-05]
    """
    results   = []
    total_rwa = 0.0

    for exp in exposures:
        _validate_ccp_exposure(exp)

        # ── Net trade EAD (CRE54.4, GAP-CCP-03) ──────────────────────────────
        net_trade_ead = max(exp.trade_ead - exp.vm_posted, 0.0)

        if exp.is_qualifying:
            rw = QCCP_TRADE_RW  # 2% capital charge per CRE54.4

            # Trade exposure RWA
            rwa_trade = net_trade_ead * rw * 12.5

            # Initial Margin (CRE54.15)
            rwa_im = (0.0 if exp.im_segregated
                      else exp.im_posted * rw * 12.5)

            # Funded DFC (CRE54.32–38) — GAP-CCP-01/02
            k_dfc, dfc_method = _compute_dfc_capital_qccp(exp)
            rwa_dfc = k_dfc * 12.5   # capital → RWA (capital = 8% × RWA)

            # Unfunded DFC (CRE54.42): 1250% RW → capital = 100% × df_unfunded
            # RWA = capital / 8% = df_unfunded × 12.5
            rwa_unfunded = exp.df_unfunded * 12.5   # GAP-CCP-06

            # Equity in QCCP (CRE54.17) — GAP-CCP-04
            rwa_equity = exp.equity_in_ccp * EQUITY_IN_CCP_RW * 12.5

        else:
            # Non-QCCP: standard credit framework (CRE54.40–42)
            rw         = exp.non_qccp_rw   # default 100%
            dfc_method = "non_qccp"

            rwa_trade    = net_trade_ead * rw * 12.5
            rwa_im       = exp.im_posted * rw * 12.5

            # Funded DF to non-QCCP → standard credit RW (CRE54.40)
            rwa_dfc      = exp.df_contribution * rw * 12.5
            k_dfc        = rwa_dfc * 0.08   # implied capital

            # Unfunded DF to non-QCCP → 1250% RW (CRE54.42 applies equally)
            rwa_unfunded = exp.df_unfunded * 12.5

            # Equity in non-QCCP → standard credit RW (no 250% treatment)
            rwa_equity   = exp.equity_in_ccp * rw * 12.5

        # ── Client Clearing (CRE54.5–6) — GAP-CCP-05 ────────────────────────
        if exp.is_clearing_member and exp.client_ead > 0:
            if exp.is_qualifying and not exp.client_guarantee:
                # CRE54.5: CM benefits from 2% QCCP RW (no back-stop guarantee)
                rwa_client      = exp.client_ead * QCCP_TRADE_RW * 12.5
                client_rw_note  = "2% QCCP pass-through (CRE54.5)"
            elif exp.is_qualifying and exp.client_guarantee:
                # CRE54.6: bank guarantees client → look-through to client credit risk
                rwa_client      = exp.client_ead * CLIENT_GUARANTEE_RW * 12.5
                client_rw_note  = "100% look-through (CRE54.6: bank guarantees client)"
            else:
                # Non-QCCP client clearing → standard credit RW
                rwa_client      = exp.client_ead * exp.non_qccp_rw * 12.5
                client_rw_note  = f"Non-QCCP standard RW ({exp.non_qccp_rw*100:.0f}%)"
        else:
            rwa_client     = 0.0
            client_rw_note = "N/A"

        # ── Totals ────────────────────────────────────────────────────────────
        rwa_total   = rwa_trade + rwa_im + rwa_dfc + rwa_unfunded + rwa_equity + rwa_client
        total_rwa  += rwa_total
        capital_tot = rwa_total * 0.08

        # ── Compose result ────────────────────────────────────────────────────
        seg_note  = "(seg-IM→0%)" if exp.im_segregated else "(non-seg-IM→2%)"
        vm_note   = f"[VM_net={net_trade_ead:.0f}]" if exp.vm_posted > 0 else ""
        qual_str  = "QCCP" if exp.is_qualifying else "Non-QCCP"

        results.append(CCPResult(
            ccp_name           = exp.ccp_name,
            is_qualifying      = exp.is_qualifying,
            net_trade_ead      = net_trade_ead,
            rwa_trade          = rwa_trade,
            rwa_im             = rwa_im,
            capital_trade      = (rwa_trade + rwa_im) * 0.08,
            k_dfc              = k_dfc,
            rwa_dfc            = rwa_dfc,
            rwa_unfunded       = rwa_unfunded,
            dfc_method         = dfc_method,
            rwa_equity_in_ccp  = rwa_equity,
            rwa_client         = rwa_client,
            client_rw_note     = client_rw_note,
            rwa_total          = rwa_total,
            capital_total      = capital_tot,
            trade_rw           = rw,
            method_note        = (
                f"{qual_str} CRE54 {seg_note} {vm_note} DFC:{dfc_method}"
            ),
        ))

        logger.info(
            "CCP [%s | %s] "
            "TradeRWA=%.0f  IM_RWA=%.0f  "
            "DFC_K=%.0f  DFC_RWA=%.0f (%s)  "
            "Unfunded_RWA=%.0f  Equity_RWA=%.0f  Client_RWA=%.0f  "
            "TOTAL_RWA=%.0f  Capital=%.0f",
            exp.ccp_name, qual_str,
            rwa_trade, rwa_im,
            k_dfc, rwa_dfc, dfc_method,
            rwa_unfunded, rwa_equity, rwa_client,
            rwa_total, capital_tot,
        )

    return {
        "ccp_results":   results,
        "total_rwa_ccp": total_rwa,
        "total_capital": total_rwa * 0.08,
    }
