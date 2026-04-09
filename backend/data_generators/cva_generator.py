"""
PROMETHEUS Risk Platform
Module: CVA Input Generator

Synthesises CVAInput objects from derivative portfolio results.
Each counterparty in a derivative portfolio generates one CVA input,
aggregating EAD across all netting sets with that counterparty.

Credit spread availability is realistic:
  - Banks / Sovereigns with external ratings: spread available (SA-CVA eligible)
  - Unrated / EM corporates: no spread (falls back to BA-CVA with trace)

Also generates CCP cleared trade positions (LCH, CME, one non-QCCP)
for the CCP engine.
"""

from __future__ import annotations
import random
from typing import List, Dict, Optional

from backend.engines.cva import CVAInput
from backend.engines.ccp import CCPExposure
from backend.data_sources.credit_calibration import pd_from_rating

# Counterparty-level spread availability — mirrors the universe in portfolio_generator.py
# True = CDS spread data available → SA-CVA eligible
_SPREAD_AVAILABLE: Dict[str, bool] = {
    "CPTY-0001": True,   # Goldman Sachs — liquid CDS market
    "CPTY-0002": True,   # Deutsche Bank — liquid CDS market
    "CPTY-0003": True,   # Apple — investment grade, CDS available
    "CPTY-0004": True,   # Shell — IG corporate, CDS available
    "CPTY-0005": False,  # Republic of Germany — sovereign, no standard CDS
    "CPTY-0006": True,   # BNP Paribas — liquid CDS market
    "CPTY-0007": False,  # Toyota — Japanese corporate, spread data thin
    "CPTY-0008": False,  # Brazil — EM sovereign, use BA-CVA
}

# Representative market CDS spreads in basis points (illustrative)
_MARKET_SPREADS_BPS: Dict[str, float] = {
    "CPTY-0001": 42.0,   # GS ~42bp
    "CPTY-0002": 88.0,   # Deutsche ~88bp
    "CPTY-0003": 28.0,   # Apple ~28bp
    "CPTY-0004": 55.0,   # Shell ~55bp
    "CPTY-0006": 65.0,   # BNP ~65bp
}

# PD is now derived from the rating transition matrix via pd_from_rating();
# only lgd_mkt, rating, and maturity are needed here.
_COUNTERPARTY_PARAMS: Dict[str, Dict] = {
    "CPTY-0001": {"lgd_mkt": 0.40, "rating": "A+",  "maturity": 3.0},
    "CPTY-0002": {"lgd_mkt": 0.40, "rating": "BBB", "maturity": 4.0},
    "CPTY-0003": {"lgd_mkt": 0.40, "rating": "AA+", "maturity": 2.5},
    "CPTY-0004": {"lgd_mkt": 0.40, "rating": "A",   "maturity": 3.5},
    "CPTY-0005": {"lgd_mkt": 0.45, "rating": "AAA", "maturity": 5.0},
    "CPTY-0006": {"lgd_mkt": 0.40, "rating": "A-",  "maturity": 3.0},
    "CPTY-0007": {"lgd_mkt": 0.40, "rating": "A+",  "maturity": 2.0},
    "CPTY-0008": {"lgd_mkt": 0.45, "rating": "BB",  "maturity": 2.5},
}


def build_cva_inputs(
    processed_derivative_results: List[Dict],
    seed: int = 42,
) -> tuple[List[CVAInput], Dict[str, str]]:
    """
    Convert processed derivative portfolio results into CVAInput objects.

    Accepts the `results["derivative"]` list from PrometheusRunner.run_daily(),
    which contains the computed saccr EAD and imm EAD for each portfolio.

    Each counterparty maps to one CVAInput, aggregating EAD across all
    netting sets with that counterparty (CRE51.11).

    Returns:
        cva_inputs  — list of CVAInput, one per counterparty
        rating_map  — {counterparty_id: external_rating} for BA-CVA risk weights
    """
    rng = random.Random(seed)

    # Aggregate EAD per counterparty across multiple portfolios (CRE51.11)
    ead_by_cpty: Dict[str, float] = {}
    cpty_meta:   Dict[str, Dict]  = {}

    for port in processed_derivative_results:
        cpty_id = port.get("counterparty_id", port.get("counterparty", "UNKNOWN"))

        # SA-CCR EAD as base; use IMM EAD if available and above floor
        ead = port["saccr"]["ead"]
        imm = port.get("imm") or {}
        if imm.get("ead_imm", 0) > ead * 0.5:
            ead = imm["ead_imm"]

        ead_by_cpty[cpty_id] = ead_by_cpty.get(cpty_id, 0.0) + ead
        if cpty_id not in cpty_meta:
            cpty_meta[cpty_id] = {"portfolio_id": port["portfolio_id"]}

    cva_inputs: List[CVAInput] = []
    rating_map: Dict[str, str] = {}

    for cpty_id, total_ead in ead_by_cpty.items():
        params = _COUNTERPARTY_PARAMS.get(cpty_id, {
            "lgd_mkt": 0.40, "rating": "NR", "maturity": 2.5
        })

        has_spread = _SPREAD_AVAILABLE.get(cpty_id, False)
        spread_bps = _MARKET_SPREADS_BPS.get(cpty_id) if has_spread else None
        if spread_bps is not None:
            spread_bps *= rng.uniform(0.90, 1.10)

        has_hedge      = rng.random() < 0.30
        hedge_notional = total_ead * rng.uniform(0.20, 0.50) if has_hedge else 0.0
        hedge_maturity = params["maturity"] * rng.uniform(0.70, 1.0)

        cva_inputs.append(CVAInput(
            counterparty_id  = cpty_id,
            netting_set_id   = f"NET-{cpty_id}-AGG",
            ead              = total_ead,
            pd_1yr           = pd_from_rating(params["rating"], params["maturity"]),
            lgd_mkt          = params["lgd_mkt"],
            maturity_years   = params["maturity"],
            credit_spread_bps= spread_bps,
            has_cva_hedge    = has_hedge,
            hedge_notional   = hedge_notional,
            hedge_maturity   = hedge_maturity,
        ))
        rating_map[cpty_id] = params["rating"]

    return cva_inputs, rating_map


def build_ccp_exposures(seed: int = 42) -> List[CCPExposure]:
    """
    Generate three representative CCP cleared positions:
      - LCH SwapClear (QCCP) — interest rate swaps
      - CME Clearing (QCCP) — FX and commodity futures
      - HypotheticalCCP (non-QCCP) — for comparison / stress testing
    """
    rng = random.Random(seed)

    return [
        CCPExposure(
            ccp_name          = "LCH SwapClear",
            is_qualifying     = True,
            trade_ead         = rng.uniform(400_000_000, 600_000_000),   # ~$500M
            im_posted         = rng.uniform(40_000_000, 70_000_000),     # ~$55M IM
            df_contribution   = rng.uniform(8_000_000, 15_000_000),      # ~$11M DFC
            is_clearing_member= True,
            client_ead        = rng.uniform(50_000_000, 120_000_000),    # client trades
        ),
        CCPExposure(
            ccp_name          = "CME Clearing",
            is_qualifying     = True,
            trade_ead         = rng.uniform(150_000_000, 280_000_000),   # ~$215M
            im_posted         = rng.uniform(15_000_000, 30_000_000),
            df_contribution   = rng.uniform(3_000_000, 8_000_000),
            is_clearing_member= True,
            client_ead        = rng.uniform(20_000_000, 50_000_000),
        ),
        CCPExposure(
            ccp_name          = "Non-QCCP (Stress Test)",
            is_qualifying     = False,                                    # non-qualifying → 100% RW
            trade_ead         = rng.uniform(5_000_000, 20_000_000),      # small position
            im_posted         = 0.0,
            df_contribution   = rng.uniform(500_000, 2_000_000),
            is_clearing_member= False,
            client_ead        = 0.0,
        ),
    ]
