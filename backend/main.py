"""
PROMETHEUS Risk Platform — Main Risk Run Orchestrator
Sprint A: Full five-part RWA formula per RBC20.9

RWA Components:
  1. Credit RWA      — A-IRB (banking book)   CRE30-36
  2. CCR RWA         — SA-CCR / IMM           CRE51-53
  3. Market RWA      — FRTB SBM + IMA         MAR20-33
  4. CVA RWA         — BA-CVA / SA-CVA        MAR50
  5. CCP RWA         — CRE54                  CRE54
  6. Operational RWA — OPE25 stub (placeholder, req 2)

Total RWA = (1)+(2)+(3)+(4)+(5)+(6)
Output floor (RBC20.11): max(Total RWA, 72.5% x SA-based RWA)
CVA RWA excluded from output floor base (CAP10 FAQ1).
"""

from __future__ import annotations
import logging
import numpy as np
from datetime import date
from typing import Dict, List

from backend.engines.sa_ccr  import SACCREngine
from backend.engines.imm     import IMMEngine
from backend.engines.a_irb   import AIRBEngine
from backend.engines.frtb    import FRTBEngine, BacktestEngine, Sensitivity
from backend.engines.cva     import CVAEngine
from backend.engines.ccp     import compute_ccp_rwa

from backend.data_generators.portfolio_generator import build_full_dataset
from backend.data_generators.cva_generator      import build_cva_inputs, build_ccp_exposures

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("prometheus.runner")

OP_RISK_ENABLED  = False
OP_RISK_RWA_STUB = 0.0


class PrometheusRunner:
    def __init__(self, sa_cva_approved: bool = False):
        self.saccr    = SACCREngine()
        self.imm      = IMMEngine()
        self.airb     = AIRBEngine()
        self.frtb     = FRTBEngine()
        self.cva      = CVAEngine(sa_cva_approved=sa_cva_approved)
        self.backtest = BacktestEngine()

    def run_daily(self, run_date: date = None) -> Dict:
        run_date = run_date or date.today()
        logger.info("=" * 70)
        logger.info("PROMETHEUS Daily Risk Run — %s", run_date.isoformat())
        logger.info("=" * 70)

        dataset = build_full_dataset(book_date=run_date)
        results = {
            "run_date": run_date.isoformat(),
            "derivative": [], "banking_book": [],
            "cva": {}, "ccp": {},
            "capital_summary": {}, "backtesting": {},
        }

        rwa_credit = 0.0
        rwa_ccr    = 0.0
        rwa_market = 0.0
        rwa_cva    = 0.0
        rwa_ccp    = 0.0
        rwa_op     = OP_RISK_RWA_STUB

        # 1. Derivative portfolios
        for port in dataset["derivative_portfolios"]:
            pid     = port["portfolio_id"]
            netting = port["netting"]
            trades  = port["trades"]
            cpty_id = port["counterparty"]["id"]
            logger.info("Processing derivative portfolio: %s", pid)

            saccr_res  = self.saccr.compute_ead(netting, run_date)
            imm_trades = [t for t in trades if t.saccr_method == "IMM"]
            imm_res    = None
            if imm_trades:
                imm_res = self.imm.run_for_portfolio(imm_trades, run_date, netting_set=netting)

            ead_ccr = saccr_res.ead
            # Use CSA-adjusted EAD for floor check (CRE53.5)
            if imm_res and imm_res["ead_imm_csa"] < saccr_res.ead * 0.5:
                logger.warning("Portfolio %s: IMM below SA-CCR floor — floor applied", pid)
                for t in imm_trades:
                    if t.saccr_method == "IMM":
                        t.saccr_method   = "FALLBACK"
                        t.fallback_trace = f"FALLBACK|{t.trade_id}|REGULATORY_FLOOR|CRE53.5"

            port_rwa_ccr  = ead_ccr * 1.0 * 12.5 * 0.08
            rwa_ccr      += port_rwa_ccr

            sensitivities = self._generate_sensitivities(pid, trades)
            pnl_series    = np.random.default_rng(42).normal(0, 50_000, 250)
            frtb_res = self.frtb.compute(
                portfolio_id=pid, sensitivities=sensitivities,
                pnl_series=pnl_series, n_nmrf=2,
                avg_notional=sum(t.notional for t in trades) / len(trades),
                run_date=run_date,
            )
            rwa_market += frtb_res.rwa_market

            results["derivative"].append({
                "portfolio_id":   pid,
                "counterparty":   port["counterparty"]["name"],
                "counterparty_id":cpty_id,
                "trade_count":    len(trades),
                "gross_notional": sum(abs(t.notional) for t in trades),
                "saccr": {
                    "ead": saccr_res.ead, "rc": saccr_res.replacement_cost,
                    "pfe_mult": saccr_res.pfe_multiplier,
                    "addon_ir": saccr_res.add_on_ir, "addon_fx": saccr_res.add_on_fx,
                    "addon_credit": saccr_res.add_on_credit,
                    "addon_equity": saccr_res.add_on_equity,
                    "addon_commodity": saccr_res.add_on_commodity,
                    "addon_agg": saccr_res.add_on_aggregate,
                },
                "imm": imm_res,
                "ead_imm_csa": imm_res.get("ead_imm_csa", 0) if imm_res else 0,
                "csa_reduction_pct": imm_res.get("csa_reduction_pct", 0) if imm_res else 0,
                "frtb": {
                    "sbm_total": frtb_res.sbm_total, "sbm_delta": frtb_res.sbm_delta,
                    "sbm_vega": frtb_res.sbm_vega, "sbm_curvature": frtb_res.sbm_curvature,
                    "es_10d": frtb_res.es_99_10d, "es_stressed": frtb_res.es_stressed,
                    "ima_total": frtb_res.ima_total,
                    "capital": frtb_res.capital_market_risk,
                    "rwa_market": frtb_res.rwa_market,
                },
                "rwa_ccr":    port_rwa_ccr,
                "rwa_market": frtb_res.rwa_market,
            })

        # 2. Banking book
        for port in dataset["banking_portfolios"]:
            pid = port["portfolio_id"]
            logger.info("Processing banking book portfolio: %s", pid)
            airb_summary = self.airb.compute_portfolio(port["exposures"])
            rwa_credit  += airb_summary["total_rwa"]
            results["banking_book"].append({
                "portfolio_id":   pid,
                "counterparty":   port["counterparty"]["name"],
                "exposure_count": len(port["exposures"]),
                "total_ead":      airb_summary["total_ead"],
                "total_rwa":      airb_summary["total_rwa"],
                "total_el":       airb_summary["total_el"],
                "el_shortfall":   airb_summary["el_shortfall"],
                "avg_risk_weight":airb_summary["avg_risk_weight"],
                "airb_trades": [
                    {"trade_id": r.trade_id, "pd": r.pd_applied, "lgd": r.lgd_applied,
                     "ead": r.ead_applied, "rwa": r.rwa, "el": r.el,
                     "correlation": r.correlation_r, "capital_k": r.capital_req_k}
                    for r in airb_summary["trade_results"]
                ],
            })

        # 3. CVA (MAR50) — Sprint A
        logger.info("SPRINT A: CVA engine (MAR50)")
        cva_inputs, rating_map = build_cva_inputs(results["derivative"], seed=42)
        cva_result = self.cva.compute_portfolio_cva(
            inputs=cva_inputs, total_ccr_rwa=rwa_ccr,
            rating_map=rating_map, run_date=run_date,
        )
        rwa_cva = cva_result["total_rwa_cva"]

        hedge_rwa_reduction = sum(
            inp.hedge_notional * 0.0042 * 12.5
            for inp in cva_inputs if inp.has_cva_hedge
        )
        rwa_market_adj = max(rwa_market - hedge_rwa_reduction, rwa_market * 0.95)

        cva_by_method = {"SA_CVA": 0.0, "BA_CVA": 0.0, "CCR_PROXY": 0.0}
        cva_cpts = []
        for cid, res in cva_result["method_summary"].items():
            cva_by_method[res.method] = cva_by_method.get(res.method, 0.0) + res.rwa_cva
            cva_cpts.append({
                "counterparty_id": cid, "method": res.method,
                "rwa_cva": res.rwa_cva, "cva_estimate": res.cva_estimate,
                "fallback_trace": res.fallback_trace,
                "has_hedge": next((i.has_cva_hedge for i in cva_inputs if i.counterparty_id == cid), False),
            })
        results["cva"] = {
            "total_rwa_cva": rwa_cva, "method": cva_result["method"],
            "fallback_count": len(cva_result["fallback_traces"]),
            "fallback_traces": cva_result["fallback_traces"],
            "by_method": cva_by_method, "counterparties": cva_cpts,
            "hedge_rwa_reduction": hedge_rwa_reduction,
            "rwa_market_adjusted": rwa_market_adj,
        }
        logger.info("CVA: RWA=%.0f Method=%s SA=%.0f BA=%.0f Fallbacks=%d",
                    rwa_cva, cva_result["method"],
                    cva_by_method["SA_CVA"], cva_by_method["BA_CVA"],
                    len(cva_result["fallback_traces"]))

        # 4. CCP (CRE54) — Sprint A
        logger.info("SPRINT A: CCP engine (CRE54)")
        ccp_exposures = build_ccp_exposures(seed=42)
        ccp_result    = compute_ccp_rwa(ccp_exposures)
        rwa_ccp       = ccp_result["total_rwa_ccp"]
        results["ccp"] = {
            "total_rwa_ccp": rwa_ccp,
            "positions": [
                {"ccp_name": r.ccp_name, "is_qualifying": exp.is_qualifying,
                 "trade_ead": exp.trade_ead, "im_posted": exp.im_posted,
                 "df_contribution": exp.df_contribution, "trade_rw": r.trade_rw,
                 "rwa_trade": r.rwa_trade, "rwa_dfc": r.rwa_dfc,
                 "rwa_total": r.rwa_total, "method_note": r.method_note}
                for r, exp in zip(ccp_result["ccp_results"], ccp_exposures)
            ],
        }
        logger.info("CCP: RWA=%.0f (%d positions)", rwa_ccp, len(ccp_exposures))

        # 5. Capital summary — five-part RWA (RBC20)
        rwa_market_final    = rwa_market_adj
        rwa_total_pre_floor = rwa_credit + rwa_ccr + rwa_market_final + rwa_cva + rwa_ccp + rwa_op
        rwa_sa_based        = rwa_credit + rwa_ccr + rwa_market + rwa_ccp + rwa_op  # CVA excluded
        rwa_floor           = rwa_sa_based * 0.725
        rwa_total           = max(rwa_total_pre_floor, rwa_floor)
        floor_triggered     = rwa_total > rwa_total_pre_floor

        cet1 = rwa_total * 0.13; tier1 = cet1 * 1.10; total_cap = tier1 * 1.20
        cet1_ratio = cet1 / rwa_total if rwa_total > 0 else 0
        t1_ratio   = tier1 / rwa_total if rwa_total > 0 else 0
        tc_ratio   = total_cap / rwa_total if rwa_total > 0 else 0

        results["capital_summary"] = {
            "run_date": run_date.isoformat(),
            "rwa_credit": rwa_credit, "rwa_ccr": rwa_ccr,
            "rwa_market": rwa_market_final, "rwa_cva": rwa_cva,
            "rwa_ccp": rwa_ccp, "rwa_operational": rwa_op,
            "rwa_total_pre_floor": rwa_total_pre_floor,
            "rwa_sa_based": rwa_sa_based, "rwa_floor": rwa_floor,
            "rwa_total": rwa_total, "floor_triggered": floor_triggered,
            "cet1_capital": cet1, "tier1_capital": tier1, "total_capital": total_cap,
            "cet1_ratio": cet1_ratio, "tier1_ratio": t1_ratio, "total_cap_ratio": tc_ratio,
            "cet1_minimum": 0.045, "tier1_minimum": 0.060, "total_cap_minimum": 0.080,
            "conservation_buffer": 0.025,
            "cva_method": cva_result["method"],
            "cva_fallback_count": len(cva_result["fallback_traces"]),
        }

        # 6. Backtesting
        rng_bt = np.random.default_rng(99)
        predicted_var = np.abs(rng_bt.normal(50_000, 10_000, 250))
        actual_pnl    = rng_bt.normal(0, 55_000, 250)
        bt_result = self.backtest.evaluate(predicted_var, actual_pnl)
        results["backtesting"] = {**bt_result, "model": "FRTB_ES", "run_date": run_date.isoformat()}

        logger.info("=" * 70)
        logger.info("RISK RUN COMPLETE  [%s]", run_date.isoformat())
        logger.info("  (1) Credit RWA  : USD %.0f", rwa_credit)
        logger.info("  (2) CCR RWA     : USD %.0f", rwa_ccr)
        logger.info("  (3) Market RWA  : USD %.0f", rwa_market_final)
        logger.info("  (4) CVA RWA     : USD %.0f  [%s]", rwa_cva, cva_result["method"])
        logger.info("  (5) CCP RWA     : USD %.0f", rwa_ccp)
        logger.info("  (6) OpRisk RWA  : USD %.0f  [stub]", rwa_op)
        logger.info("  TOTAL RWA       : USD %.0f  %s", rwa_total,
                    "(floor applied)" if floor_triggered else "")
        logger.info("  CET1 Ratio      : %6.2f%%", cet1_ratio * 100)
        logger.info("=" * 70)
        return results

    def _generate_sensitivities(self, pid: str, trades) -> List[Sensitivity]:
        import random
        rng = random.Random(hash(pid) % 2**31)
        rc_map = {"IR": "GIRR", "FX": "FX", "EQ": "EQ", "CR": "CSR_NS", "CMDTY": "CMDTY"}
        return [
            Sensitivity(
                trade_id=t.trade_id, risk_class=rc_map.get(t.asset_class, "GIRR"),
                bucket=str(rng.randint(1, 5)),
                risk_factor=f"{t.asset_class}_FACTOR_{rng.randint(1,3)}",
                delta=rng.uniform(-t.notional*0.001, t.notional*0.001),
                vega=rng.uniform(0, t.notional*0.0005),
                curvature_up=rng.uniform(-t.notional*0.0002, 0),
                curvature_dn=rng.uniform(-t.notional*0.0002, 0),
            )
            for t in trades
        ]


if __name__ == "__main__":
    runner  = PrometheusRunner(sa_cva_approved=True)
    results = runner.run_daily()
    cap = results["capital_summary"]
    cva = results["cva"]
    ccp = results["ccp"]
    print(f"\n{'='*65}")
    print(f"  PROMETHEUS — Sprint A Complete")
    print(f"{'='*65}")
    print(f"  CET1 {cap['cet1_ratio']:.2%}  |  T1 {cap['tier1_ratio']:.2%}  |  Total {cap['total_cap_ratio']:.2%}")
    print(f"\n  Five-Part RWA (USD)")
    print(f"  (1) Credit        : {cap['rwa_credit']:>15,.0f}")
    print(f"  (2) CCR           : {cap['rwa_ccr']:>15,.0f}")
    print(f"  (3) Market (FRTB) : {cap['rwa_market']:>15,.0f}")
    print(f"  (4) CVA [{cap['cva_method']:8s}]: {cap['rwa_cva']:>15,.0f}")
    print(f"  (5) CCP           : {cap['rwa_ccp']:>15,.0f}")
    print(f"  (6) OpRisk [stub] : {cap['rwa_operational']:>15,.0f}")
    print(f"  {'─'*35}")
    print(f"  TOTAL RWA         : {cap['rwa_total']:>15,.0f}  {'(floor)' if cap['floor_triggered'] else ''}")
    print(f"\n  CVA breakdown — SA: ${cva['by_method'].get('SA_CVA',0):,.0f}  BA: ${cva['by_method'].get('BA_CVA',0):,.0f}")
    print(f"  CVA fallback traces: {cva['fallback_count']}")
    for pos in ccp["positions"]:
        q = "QCCP" if pos["is_qualifying"] else "Non-QCCP"
        print(f"  {pos['ccp_name']:<22} [{q}] RWA ${pos['rwa_total']:>12,.0f}")
    print(f"  Backtesting: {results['backtesting']['traffic_light']}")
    print(f"{'='*65}")
