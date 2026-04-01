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
    ccp_name:           str
    is_qualifying:      bool = True    # QCCP (LCH, CME, Eurex, etc.)
    trade_ead:          float = 0.0   # bilateral EAD from cleared trades (SA-CCR)
    im_posted:          float = 0.0   # Initial margin posted to CCP
    df_contribution:    float = 0.0   # Default fund contribution
    ccp_total_assets:   float = 0.0   # CCP's total assets (for DFC calc, simplified)
    is_clearing_member: bool = True
    client_ead:         float = 0.0   # For client-clearing intermediary role

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
    Trade exposure: EAD × RW (2% for QCCP, 100% for non-QCCP).
    Default fund: simplified DFC = max(df_contribution × 1.6 × 12.5, 0)
    """
    results = []
    total_rwa = 0.0

    for exp in exposures:
        rw = QCCP_TRADE_RW if exp.is_qualifying else NON_QCCP_TRADE_RW

        # Trade exposure RWA
        rwa_trade = exp.trade_ead * rw * 12.5

        # Default fund contribution (CRE54 simplified):
        # K_CCP = DFC × 1.6% (QCCP) or standard (non-QCCP)
        if exp.is_qualifying and exp.df_contribution > 0:
            k_dfc    = exp.df_contribution * 0.016   # CRE54.33 simplified
            rwa_dfc  = k_dfc * 12.5
        else:
            rwa_dfc  = exp.df_contribution * NON_QCCP_TRADE_RW * 12.5

        # Client clearing intermediary (clearing member → client)
        rwa_client = exp.client_ead * 0.02 * 12.5 if exp.is_clearing_member else 0.0

        rwa_total = rwa_trade + rwa_dfc + rwa_client
        total_rwa += rwa_total

        results.append(CCPResult(
            ccp_name   = exp.ccp_name,
            rwa_trade  = rwa_trade,
            rwa_dfc    = rwa_dfc,
            rwa_total  = rwa_total,
            trade_rw   = rw,
            method_note= f"{'QCCP' if exp.is_qualifying else 'Non-QCCP'} CRE54",
        ))

        logger.info("CCP [%s] TrdRWA=%.0f  DFC_RWA=%.0f  Total=%.0f",
                    exp.ccp_name, rwa_trade, rwa_dfc, rwa_total)

    return {
        "ccp_results": results,
        "total_rwa_ccp": total_rwa,
    }
