"""
PROMETHEUS Risk Platform
Engine: CCP Exposure — Central Counterparty Capital
Regulatory basis: CRE54 (effective Jan 2023), CRE51.9

Implements:
  - Trade exposure to Qualifying CCPs (QCCPs) — cleared derivatives
  - Default fund contribution (DFC) capital charge
  - Client clearing: clearing member acting as intermediary
  - CRE55: same rules apply for trading book CCR
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─── Risk weights for QCCP exposures ─────────────────────────────────────────
# CRE54: trade exposures to a QCCP → 2% risk weight
QCCP_TRADE_RW    = 0.02
NON_QCCP_TRADE_RW= 1.00   # non-qualifying CCP: standard credit RW

@dataclass
class CCPExposure:
    ccp_name:            str
    is_qualifying:       bool  = True    # QCCP (LCH, CME, Eurex, etc.)
    trade_ead:           float = 0.0    # bilateral EAD from cleared trades (SA-CCR)
    im_posted:           float = 0.0    # Initial margin posted to CCP
    im_segregated:       bool  = True   # True = IM is held in segregated account
    df_contribution:     float = 0.0    # Funded default fund contribution
    df_unfunded:         float = 0.0    # Unfunded default fund commitment
    ccp_total_assets:    float = 0.0    # CCP total assets (for DFC calc, simplified)
    kccp:                float = 0.0    # Hypothetical CCP capital (CRE54.32)
    is_clearing_member:  bool  = True
    client_ead:          float = 0.0    # Client-clearing intermediary role

@dataclass
class CCPResult:
    ccp_name:          str
    rwa_trade:         float
    rwa_dfc:           float
    rwa_total:         float
    trade_rw:          float
    method_note:       str

def compute_ccp_rwa(exposures: List[CCPExposure]) -> dict:
    """
    Compute CCP capital charges per CRE54.

    QCCP trade exposure (CRE54.4):
      - Trade EAD × 2% risk weight
      - IM posted (non-segregated) treated as exposure → 2% RW
      - IM posted (segregated)     → 0% RW  (CRE54.15)

    Default fund (CRE54.31–39 simplified approach):
      - K_CCP = 8% × KCCP (hypothetical capital of the CCP)
      - Bank share = DFC / Total_DFC_all_members
      - If KCCP not provided → simplified K_CCP = DFC × 1.6%

    Unfunded DFC commitments also attract capital at 1250% RW (CRE54.42).
    Non-QCCP: standard credit RW applies (100%).
    Client clearing intermediary: RW = 2% (CRE54.5).
    """
    results = []
    total_rwa = 0.0

    for exp in exposures:
        if exp.is_qualifying:
            rw = QCCP_TRADE_RW  # 2%

            # Trade exposure RWA (CRE54.4)
            rwa_trade = exp.trade_ead * rw * 12.5

            # Initial margin posted (CRE54.15):
            # Segregated IM → 0% RW; non-segregated → 2% RW
            rwa_im = (0.0 if exp.im_segregated
                      else exp.im_posted * rw * 12.5)

            # Default fund (CRE54.31–39):
            # Simplified: if KCCP provided use risk-sensitive method, else flat 1.6%
            if exp.kccp > 0 and exp.df_contribution > 0:
                # Bank share of hypothetical CCP capital requirement
                # CRE54.32: K_CCP = 8% × KCCP; bank contribution proportional
                k_bank = 0.08 * exp.kccp  # simplified (assumes bank = full DFC)
                k_dfc  = min(k_bank, exp.df_contribution * 0.016)
            elif exp.df_contribution > 0:
                k_dfc = exp.df_contribution * 0.016   # CRE54.33 fallback
            else:
                k_dfc = 0.0
            rwa_dfc = k_dfc * 12.5

            # Unfunded default fund commitments → 1250% RW (CRE54.42)
            rwa_unfunded = exp.df_unfunded * 12.50 * 12.5  # 1250% × EAD / 12.5 → ×12.5 cancels but kept for clarity
            # Correction: RWA = unfunded × 1250% → capital = unfunded × 1250%/12.5 = unfunded × 100%
            # So rwa_unfunded = exp.df_unfunded * 12.50  (capital = exp.df_unfunded, rwa = cap * 12.5)
            rwa_unfunded = exp.df_unfunded * 12.5  # 100% capital req × 12.5

        else:
            rw = NON_QCCP_TRADE_RW  # 100%
            rwa_trade    = exp.trade_ead * rw * 12.5
            rwa_im       = exp.im_posted * rw * 12.5
            rwa_dfc      = exp.df_contribution * rw * 12.5   # CRE54.42: non-QCCP at 1250%
            rwa_unfunded = exp.df_unfunded * rw * 12.5

        # Client clearing intermediary (CRE54.5)
        rwa_client = (exp.client_ead * QCCP_TRADE_RW * 12.5
                      if exp.is_clearing_member and exp.is_qualifying else
                      exp.client_ead * NON_QCCP_TRADE_RW * 12.5
                      if exp.is_clearing_member else 0.0)

        rwa_total = rwa_trade + rwa_im + rwa_dfc + rwa_unfunded + rwa_client
        total_rwa += rwa_total

        results.append(CCPResult(
            ccp_name    = exp.ccp_name,
            rwa_trade   = rwa_trade + rwa_im,
            rwa_dfc     = rwa_dfc + rwa_unfunded,
            rwa_total   = rwa_total,
            trade_rw    = rw,
            method_note = f"{'QCCP' if exp.is_qualifying else 'Non-QCCP'} CRE54"
                          + (" (segregated IM)" if exp.im_segregated else " (non-seg IM)"),
        ))

        logger.info("CCP [%s] TradeRWA=%.0f  IM_RWA=%.0f  DFC_RWA=%.0f  Client=%.0f  Total=%.0f",
                    exp.ccp_name, rwa_trade, rwa_im, rwa_dfc, rwa_client, rwa_total)

    return {
        "ccp_results":   results,
        "total_rwa_ccp": total_rwa,
    }
