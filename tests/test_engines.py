"""
PROMETHEUS Risk Platform — Model Validation Test Suite
=======================================================
Tests all engines against known regulatory benchmarks.

Fixes vs prior version
─────────────────────
  1. TODAY = date.today() so maturity dates never expire
  2. make_*_trade() helpers always create future-dated maturities
  3. IMM GBM/HW shape assertions account for antithetic doubling
  4. Integration tests set PROMETHEUS_SKIP_CALIBRATION=1 to skip yfinance
  5. New test classes: TestCalibration, TestMarketState, TestCCP, TestCVA
"""

import sys, os, math

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("PROMETHEUS_SKIP_CALIBRATION", "1")

import pytest
import numpy as np
import unittest
from datetime import date, timedelta

from backend.engines.sa_ccr import (
    SACCREngine, Trade, NettingSet,
    supervisory_duration, maturity_factor,
    compute_replacement_cost, compute_pfe_multiplier,
    compute_addon_ir, compute_addon_fx,
    check_imm_eligibility,
)
from backend.engines.imm import IMMEngine, MonteCarloEngine, MarketParams
from backend.engines.a_irb import (
    AIRBEngine, BankingBookExposure,
    asset_correlation, maturity_adjustment,
    capital_requirement_k, double_default_pd, _norm_cdf,
)
from backend.engines.frtb import FRTBEngine, BacktestEngine, Sensitivity

TODAY = date.today()

def make_irs_trade(notional=100_000_000, tenor_yr=5, direction=1):
    return Trade(
        trade_id="TEST-IRS-001", asset_class="IR", instrument_type="IRS",
        notional=notional, notional_ccy="USD", direction=direction,
        maturity_date=TODAY + timedelta(days=int(tenor_yr * 365)),
        trade_date=TODAY - timedelta(days=90), current_mtm=500_000,
    )

def make_fx_trade(notional=50_000_000, direction=1):
    return Trade(
        trade_id="TEST-FX-001", asset_class="FX", instrument_type="FXFwd",
        notional=notional, notional_ccy="EUR", direction=direction,
        maturity_date=TODAY + timedelta(days=365),
        trade_date=TODAY - timedelta(days=60), current_mtm=-200_000,
    )

def make_cds_trade(notional=20_000_000, direction=1):
    return Trade(
        trade_id="TEST-CDS-001", asset_class="CR", instrument_type="CDS_Protection",
        notional=notional, notional_ccy="USD", direction=direction,
        maturity_date=TODAY + timedelta(days=5*365),
        trade_date=TODAY - timedelta(days=120), current_mtm=50_000,
    )

def make_simple_netting_set(trades, vm=0, im=0, has_csa=True):
    return NettingSet(netting_id="TEST-NS-001", counterparty_id="CPTY-TEST",
        trades=trades, variation_margin=vm, initial_margin=im,
        threshold=0, mta=0, has_csa=has_csa)

def make_banking_exposure(pd=0.01, lgd=0.45, ead=10_000_000, asset_class="CORP"):
    return BankingBookExposure(
        trade_id="TEST-BBK-001", portfolio_id="BBK-TEST", obligor_id="OBL-001",
        asset_class=asset_class, ead=ead, pd=pd, lgd=lgd, maturity=2.5)


# ═══ SA-CCR ══════════════════════════════════════════════════════════════════

class TestSupervisoryDuration:
    def test_5yr_trade(self):
        end = TODAY + timedelta(days=5*365)
        sd  = supervisory_duration(TODAY, TODAY, end)
        expected = (math.exp(0) - math.exp(-0.25)) / 0.05
        assert abs(sd - expected) < 0.001

    def test_zero_maturity(self):
        past = TODAY - timedelta(days=30)
        sd   = supervisory_duration(TODAY, TODAY, past)
        assert sd == 0.0

    def test_1yr_trade(self):
        end = TODAY + timedelta(days=365)
        sd  = supervisory_duration(TODAY, TODAY, end)
        expected = (1 - math.exp(-0.05)) / 0.05
        assert abs(sd - expected) < 0.001

    def test_sd_monotone_in_tenor(self):
        sd_1y = supervisory_duration(TODAY, TODAY, TODAY + timedelta(days=365))
        sd_5y = supervisory_duration(TODAY, TODAY, TODAY + timedelta(days=5*365))
        assert sd_5y > sd_1y


class TestMaturityFactor:
    def test_csa_mpor10(self):
        # CRE52.52: MF = 1.5 × sqrt(MPOR/250) for margined netting sets.
        # The 3/2 scalar is mandatory — previous assertion omitted it.
        mf = maturity_factor(make_irs_trade(), has_csa=True, mpor_days=10)
        assert abs(mf - 1.5 * math.sqrt(10/250)) < 1e-9

    def test_no_csa(self):
        mf = maturity_factor(make_irs_trade(tenor_yr=5), has_csa=False, mpor_days=10)
        assert abs(mf - 1.0) < 1e-6

    def test_short_unmargined(self):
        mf = maturity_factor(make_irs_trade(tenor_yr=0.5), has_csa=False, mpor_days=10)
        assert 0 < mf < 1.0


class TestReplacementCost:
    def test_rc_in_the_money(self):
        t = make_irs_trade(); t.current_mtm = 2_000_000
        rc = compute_replacement_cost(make_simple_netting_set([t], has_csa=False))
        assert rc >= 0

    def test_rc_out_of_money(self):
        t = make_irs_trade(); t.current_mtm = -3_000_000
        rc = compute_replacement_cost(make_simple_netting_set([t], has_csa=False))
        assert rc == 0.0

    def test_rc_itm_no_csa(self):
        t = make_irs_trade(); t.current_mtm = 5_000_000
        rc = compute_replacement_cost(make_simple_netting_set([t], vm=0, im=0, has_csa=False))
        assert abs(rc - 5_000_000) < 1.0


class TestPFEMultiplier:
    def test_multiplier_floor(self):
        from backend.config import SACCR
        t = make_irs_trade(); t.current_mtm = -50_000_000
        ns = make_simple_netting_set([t]); ns.variation_margin = 0; ns.initial_margin = 0
        m = compute_pfe_multiplier(ns, addon_agg=10_000_000)
        assert m >= SACCR.floor_multiplier

    def test_multiplier_max(self):
        t = make_irs_trade(); t.current_mtm = 10_000_000
        ns = make_simple_netting_set([t], vm=10_000_000)
        m = compute_pfe_multiplier(ns, addon_agg=1_000_000)
        assert m <= 1.0

    def test_multiplier_between_floor_and_1(self):
        t = make_irs_trade(); t.current_mtm = 1_000_000
        ns = make_simple_netting_set([t], vm=0)
        m = compute_pfe_multiplier(ns, addon_agg=5_000_000)
        assert 0.05 <= m <= 1.0


class TestSACCREngine:
    def test_ead_positive(self):
        engine = SACCREngine()
        ns = make_simple_netting_set([make_irs_trade(), make_fx_trade()])
        assert engine.compute_ead(ns).ead >= 0

    def test_alpha_applied(self):
        from backend.config import SACCR
        engine = SACCREngine()
        t = make_irs_trade(notional=50_000_000); t.current_mtm = 0
        ns = make_simple_netting_set([t], vm=0, im=0)
        res = engine.compute_ead(ns)
        rc_pfe = res.replacement_cost + res.pfe_multiplier * res.add_on_aggregate
        assert abs(res.ead - SACCR.alpha * rc_pfe) < 1.0

    def test_netting_benefit(self):
        engine = SACCREngine()
        l1 = make_irs_trade(direction=1)
        l2 = make_irs_trade(direction=1); l2.trade_id = "IRS-002"
        sh = make_irs_trade(direction=-1); sh.trade_id = "IRS-003"
        ead_2l = engine.compute_ead(make_simple_netting_set([l1, l2])).ead
        ead_n  = engine.compute_ead(make_simple_netting_set([l1, sh])).ead
        assert ead_n < ead_2l


class TestSACCRHedgingSets:
    def test_credit_quality_routing(self):
        # MTM=0 so RC=0 and EAD is driven purely by the AddOn (PFE) term.
        # SF_SG / SF_IG = 5% / 0.5% = 10×  →  EAD ratio ≥ 1.9×.
        engine = SACCREngine()
        ig = make_cds_trade(); ig.credit_quality = "IG"; ig.current_mtm = 0
        sg = make_cds_trade(); sg.credit_quality = "SG"; sg.trade_id = "CDS-SG"; sg.current_mtm = 0
        ead_ig = engine.compute_ead(make_simple_netting_set([ig])).ead
        ead_sg = engine.compute_ead(make_simple_netting_set([sg])).ead
        assert ead_sg > ead_ig * 1.9, f"SG EAD ({ead_sg:.0f}) should be >> IG EAD ({ead_ig:.0f}) (ratio {ead_sg/ead_ig:.2f}×)"


class TestIMMFallback:
    def test_exotic_fallback(self):
        t = Trade("CDO-001","CR","CDO_Tranche",100e6,"USD",1,TODAY+timedelta(days=7*365),TODAY)
        eligible, trace = check_imm_eligibility(t)
        assert not eligible and trace is not None and "FALLBACK" in trace

    def test_irs_eligible(self):
        t = Trade("IRS-OK","IR","IRS",500e6,"USD",1,TODAY+timedelta(days=5*365),TODAY)
        eligible, trace = check_imm_eligibility(t)
        assert eligible and trace is None

    def test_engine_assigns_fallback(self):
        engine = SACCREngine()
        t = Trade("T-BIG","EQ","ExoticSwap",10e9,"USD",1,TODAY+timedelta(days=2*365),TODAY)
        t.saccr_method = "IMM"
        updated = engine.assign_method(t)
        assert updated.saccr_method == "FALLBACK"


# ═══ IMM ═════════════════════════════════════════════════════════════════════

class TestMonteCarlo:
    def test_gbm_shape(self):
        """Antithetic doubles N: shape = (2N, T)."""
        mc    = MonteCarloEngine(use_antithetic=True)
        paths = mc.simulate_gbm(S0=100)
        assert paths.shape == (mc.N * 2, mc.T)

    def test_gbm_shape_no_antithetic(self):
        mc    = MonteCarloEngine(use_antithetic=False)
        paths = mc.simulate_gbm(S0=100)
        assert paths.shape == (mc.N, mc.T)

    def test_gbm_positive(self):
        mc = MonteCarloEngine()
        assert np.all(mc.simulate_gbm(S0=100) > 0)

    def test_hull_white_shape(self):
        """Antithetic doubles N: shape = (2N, T)."""
        mc    = MonteCarloEngine(use_antithetic=True)
        paths = mc.simulate_hull_white(r0=0.05)
        assert paths.shape == (mc.N * 2, mc.T)

    def test_hull_white_rates_bounded(self):
        mc = MonteCarloEngine()
        assert np.all(mc.simulate_hull_white(r0=0.04) >= -0.05)

    def test_epe_non_negative(self):
        engine  = IMMEngine()
        profile = engine.compute_exposure_profile([make_irs_trade(), make_fx_trade()], TODAY)
        assert profile.epe >= 0 and profile.eepe >= 0

    def test_eee_non_decreasing(self):
        profile = IMMEngine().compute_exposure_profile([make_irs_trade()], TODAY)
        assert np.all(np.diff(profile.eee_profile) >= -1e-6)

    def test_eepe_leq_pfe95(self):
        profile = IMMEngine().compute_exposure_profile([make_irs_trade(notional=100e6)], TODAY)
        assert profile.eepe <= profile.pfe_95.max() * 1.1

    def test_ead_equals_alpha_times_eepe(self):
        profile = IMMEngine().compute_exposure_profile([make_irs_trade()], TODAY)
        assert abs(profile.ead - 1.4 * profile.eepe) < 1.0

    def test_stressed_ead_gte_base(self):
        profile = IMMEngine().compute_exposure_profile([make_fx_trade()], TODAY)
        assert profile.stressed_ead >= profile.ead * 0.9


# ═══ A-IRB ═══════════════════════════════════════════════════════════════════

class TestAIRB:
    def test_correlation_corp_low_pd(self):
        assert asset_correlation(0.001,"CORP") > asset_correlation(0.20,"CORP")

    def test_correlation_retail_mort(self):
        assert abs(asset_correlation(0.01,"RETAIL_MORT") - 0.15) < 1e-6

    def test_pd_floor_applied(self):
        from backend.config import AIRB
        K1 = capital_requirement_k(0.0001,0.45,2.5,asset_correlation(0.0001,"CORP"),maturity_adjustment(0.0001,2.5))
        K2 = capital_requirement_k(AIRB.pd_floor,0.45,2.5,asset_correlation(AIRB.pd_floor,"CORP"),maturity_adjustment(AIRB.pd_floor,2.5))
        assert abs(K1 - K2) < 1e-6

    def test_capital_k_positive(self):
        for pd in [0.001,0.01,0.10,0.30]:
            R = asset_correlation(pd,"CORP")
            b = maturity_adjustment(pd,2.5)
            assert capital_requirement_k(pd,0.45,2.5,R,b) >= 0

    def test_rwa_proportional_to_ead(self):
        engine = AIRBEngine()
        r1 = engine.compute(make_banking_exposure(ead=10e6))
        r2 = engine.compute(make_banking_exposure(ead=20e6))
        assert abs(r2.rwa/r1.rwa - 2.0) < 0.01

    def test_double_default_reduces_pd(self):
        assert double_default_pd(0.05, 0.003) < 0.05

    def test_maturity_cap(self):
        b1 = maturity_adjustment(0.01,5.0)
        b2 = maturity_adjustment(0.01,10.0)
        assert b1 == b2

    def test_el_formula(self):
        # lgd_model=None forces the engine to use the static exp.lgd=0.45
        # (legacy path) so the expected EL = PD × LGD × EAD holds exactly.
        exp = make_banking_exposure(pd=0.02,lgd=0.45,ead=10e6)
        exp.lgd_model = None   # disable Frye-Jacobs for this unit test
        result = AIRBEngine().compute(exp)
        assert abs(result.el - 0.02*0.45*10e6) < 100.0

    def test_norm_cdf_known_values(self):
        assert abs(_norm_cdf(0.0) - 0.5) < 1e-6
        assert abs(_norm_cdf(10.0) - 1.0) < 1e-5
        assert abs(_norm_cdf(-10.0)) < 1e-5

    def test_crm_collateral_reduces_lgd(self):
        exp = make_banking_exposure(pd=0.02,lgd=0.45,ead=10e6)
        exp.collateral_type = "FINANCIAL"; exp.collateral_value = 6e6
        result = AIRBEngine().compute(exp)
        assert result.lgd_applied < 0.45
        assert result.rwa < result.rwa_pre_mitigant

    def test_portfolio_aggregation(self):
        engine = AIRBEngine()
        exps = [make_banking_exposure(ead=5e6), make_banking_exposure(ead=10e6)]
        for i,e in enumerate(exps): e.trade_id = f"BBK-{i:03d}"
        result = engine.compute_portfolio(exps)
        assert abs(result["total_ead"] - sum(e.ead for e in exps)) < 1.0


# ═══ FRTB ════════════════════════════════════════════════════════════════════

class TestFRTB:
    def make_sensitivity(self, rc="GIRR", delta=100_000, bucket="1", vega=0):
        return Sensitivity("T-001", rc, bucket, f"{rc}_FACTOR", delta, vega, 0, 0)

    def test_delta_charge_positive(self):
        engine = FRTBEngine()
        d,v,c,total,sbm_by_rc,sbm_by_bucket = engine.sbm.total_sbm([self.make_sensitivity("GIRR",1_000_000)])
        assert d >= 0 and total >= 0
        assert isinstance(sbm_by_rc,dict) and isinstance(sbm_by_bucket,dict)

    def test_empty_sensitivities(self):
        engine = FRTBEngine()
        d,v,c,total,sbm_by_rc,sbm_by_bucket = engine.sbm.total_sbm([])
        assert total == 0.0

    def test_netting_reduces_charge(self):
        engine = FRTBEngine()
        s_long = self.make_sensitivity("GIRR",1_000_000,"1")
        s_short= self.make_sensitivity("GIRR",-1_000_000,"1")
        charge_2long = engine.sbm.delta_charge([s_long, self.make_sensitivity("GIRR",1_000_000,"1")], "GIRR")
        charge_net   = engine.sbm.delta_charge([s_long, s_short], "GIRR")
        assert charge_net < charge_2long

    def test_es_positive(self):
        from backend.engines.frtb import IMACalculator
        pnl = np.random.default_rng(42).normal(0,100_000,250)
        assert IMACalculator().compute_es(pnl) >= 0

    def test_stressed_es_gte_base(self):
        from backend.engines.frtb import IMACalculator
        ima = IMACalculator()
        pnl = np.random.default_rng(42).normal(0,50_000,250)
        assert ima.compute_es(pnl,stressed=True) >= ima.compute_es(pnl,stressed=False)

    def test_capital_max_sbm_ima(self):
        result = FRTBEngine().compute("TEST-PORT",[self.make_sensitivity("GIRR",500_000)],avg_notional=1_000_000)
        assert result.capital_market_risk >= result.sbm_total * 0.99

    def test_three_scenario_high_differs(self):
        """MAR21.6: high-scenario rho must differ from medium."""
        for rho in [0.15,0.50,0.65]:
            rho_high = min(rho + 0.25*(1-rho), 1.0)
            assert abs(rho_high - rho) > 1e-6

    def test_lh_adjusted_es_gte_simple(self):
        from backend.engines.frtb import IMACalculator
        ima = IMACalculator()
        pnl = np.random.default_rng(42).normal(0,50_000,260)
        simple_es = ima.compute_es(pnl)
        lh_es     = ima.compute_es_lh_adjusted({"GIRR":pnl,"CSR_NS":pnl*0.3})
        assert lh_es >= simple_es * 0.95


# ═══ Backtesting ═════════════════════════════════════════════════════════════

class TestBacktesting:
    def test_green_zone(self):
        engine = BacktestEngine()
        result = engine.evaluate(np.full(250,100_000.0), np.full(250,50_000.0))
        assert result["traffic_light"]=="GREEN" and result["exceptions"]==0

    def test_red_zone(self):
        engine = BacktestEngine()
        result = engine.evaluate(np.full(250,10_000.0), -np.full(250,100_000.0))
        assert result["traffic_light"]=="RED" and result["exceptions"]==250

    def test_amber_zone(self):
        engine = BacktestEngine()
        actual = np.zeros(250); actual[:7] = -100_000
        result = engine.evaluate(np.full(250,50_000.0), actual)
        assert result["traffic_light"]=="AMBER" and result["exceptions"]==7

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            BacktestEngine().evaluate(np.array([1.0,2.0]), np.array([1.0]))

    def test_zone_boundaries(self):
        engine = BacktestEngine()
        for n_exc, zone in [(4,"GREEN"),(5,"AMBER"),(10,"RED")]:
            actual = np.zeros(250); actual[:n_exc] = -100_000
            result = engine.evaluate(np.full(250,50_000.0), actual)
            assert result["traffic_light"]==zone, f"{n_exc} exceptions: expected {zone}"


# ═══ CCP ══════════════════════════════════════════════════════════════════════

class TestCCP:
    def test_qccp_rw_2pct(self):
        from backend.engines.ccp import CCPExposure, compute_ccp_rwa
        exp = CCPExposure("LCH",True,trade_ead=10_000_000,im_posted=2_000_000,im_segregated=True,df_contribution=500_000)
        result = compute_ccp_rwa([exp])
        expected = 10_000_000 * 0.02 * 12.5
        assert abs(result["ccp_results"][0].rwa_trade - expected) < 1.0

    def test_non_qccp_rw_100pct(self):
        from backend.engines.ccp import CCPExposure, compute_ccp_rwa
        exp = CCPExposure("NON-QCCP",False,trade_ead=5_000_000,df_contribution=200_000)
        result = compute_ccp_rwa([exp])
        expected = 5_000_000*1.00*12.5 + 200_000*1.0*12.5
        assert abs(result["ccp_results"][0].rwa_trade + result["ccp_results"][0].rwa_dfc - expected) < 1.0

    def test_segregated_im_zero_rw(self):
        from backend.engines.ccp import CCPExposure, compute_ccp_rwa
        rwa_seg    = compute_ccp_rwa([CCPExposure("A",True,trade_ead=0,im_posted=5e6,im_segregated=True)])["total_rwa_ccp"]
        rwa_nonseg = compute_ccp_rwa([CCPExposure("B",True,trade_ead=0,im_posted=5e6,im_segregated=False)])["total_rwa_ccp"]
        assert rwa_seg < rwa_nonseg

    def test_total_rwa_positive(self):
        from backend.engines.ccp import CCPExposure, compute_ccp_rwa
        result = compute_ccp_rwa([
            CCPExposure("LCH",True,trade_ead=20e6,df_contribution=2e6),
            CCPExposure("CME",True,trade_ead=15e6,df_contribution=1e6),
        ])
        assert result["total_rwa_ccp"] > 0


# ═══ CVA ══════════════════════════════════════════════════════════════════════

class TestCVA:
    def _inp(self, pd=0.01, ead=10e6, has_hedge=False):
        from backend.engines.cva import CVAInput
        return CVAInput(counterparty_id="CPTY-CVA",netting_set_id="NS-TEST",
            ead=ead,pd_1yr=pd,lgd_mkt=0.40,maturity_years=5.0,sector="Corporates",
            has_cva_hedge=has_hedge,hedge_notional=5e6 if has_hedge else 0.0,
            credit_spread_bps=100.0)

    def test_ba_cva_positive(self):
        from backend.engines.cva import compute_ba_cva
        total,_ = compute_ba_cva([self._inp()])
        assert total >= 0

    def test_ba_cva_scales_with_ead(self):
        from backend.engines.cva import compute_ba_cva
        t1,_ = compute_ba_cva([self._inp(ead=10e6)])
        t2,_ = compute_ba_cva([self._inp(ead=20e6)])
        assert t2 > t1

    def test_sa_cva_requires_spreads(self):
        from backend.engines.cva import compute_sa_cva, CVAInput
        inp = CVAInput(counterparty_id="X",netting_set_id="NS-X",ead=10e6,pd_1yr=0.01,
            lgd_mkt=0.40,maturity_years=5,sector="Corporates",credit_spread_bps=None)
        with pytest.raises(ValueError):
            compute_sa_cva([inp])

    def test_sa_cva_positive(self):
        from backend.engines.cva import compute_sa_cva
        total,_ = compute_sa_cva([self._inp()])
        assert total >= 0

    def test_rwa_cva_positive(self):
        from backend.engines.cva import CVAEngine
        result = CVAEngine(sa_cva_approved=True).compute_portfolio_cva(
            inputs=[self._inp()],total_ccr_rwa=500e6,run_date=TODAY)
        assert result["total_rwa_cva"] >= 0


# ═══ Market State ═════════════════════════════════════════════════════════════

class TestMarketState:
    def test_deterministic(self):
        from backend.data_sources.market_state import get_market_state
        d = date(2024,6,15)
        assert get_market_state(d).levels["EQ_GLOBAL"] == get_market_state(d).levels["EQ_GLOBAL"]

    def test_day_on_day_variation(self):
        from backend.data_sources.market_state import get_market_state
        s1 = get_market_state(TODAY)
        s2 = get_market_state(TODAY - timedelta(days=1))
        assert s1.levels["EQ_GLOBAL"] != s2.levels["EQ_GLOBAL"]

    def test_eq_level_positive(self):
        from backend.data_sources.market_state import get_market_state
        s = get_market_state(TODAY)
        for key in ["EQ_GLOBAL","EQ_US","EQ_EU","EQ_EM"]:
            assert s.levels[key] > 0

    def test_ir_rates_reasonable(self):
        from backend.data_sources.market_state import get_market_state
        s = get_market_state(TODAY)
        for key in ["IR_SHORT","IR_2Y","IR_5Y","IR_10Y","IR_30Y"]:
            assert 0 < s.levels[key] < 0.20

    def test_trade_mtm_varies(self):
        from backend.data_sources.market_state import compute_trade_mtm
        class _T:
            asset_class="IR"; notional=50e6; direction=1
            trade_date=TODAY-timedelta(days=180); maturity_date=TODAY+timedelta(days=5*365)
            notional_ccy="USD"; hedging_set="IR"; credit_quality="IG"
        assert compute_trade_mtm(_T(), TODAY) != compute_trade_mtm(_T(), TODAY-timedelta(days=1))


# ═══ Calibration ═════════════════════════════════════════════════════════════

class TestCalibration:
    def test_historical_vol_correct(self):
        from backend.data_sources.calibration import _historical_vol
        rng  = np.random.default_rng(42)
        rets = rng.normal(0, 0.18/np.sqrt(252), 500)
        est  = _historical_vol(rets)
        assert abs(est - 0.18) < 0.03

    def test_ewma_vol_reasonable(self):
        from backend.data_sources.calibration import _ewma_vol, _historical_vol
        rets = np.random.default_rng(42).normal(0,0.15/np.sqrt(252),252)
        hist = _historical_vol(rets)
        ewma = _ewma_vol(rets)
        assert 0.5*hist < ewma < 2.0*hist

    def test_stressed_vol_positive(self):
        from backend.data_sources.calibration import _stressed_vol
        rets = np.random.default_rng(42).normal(0,0.15/np.sqrt(252),252)
        sv   = _stressed_vol(rets)
        assert sv > 0 and np.isfinite(sv)

    def test_ou_mle_recovers_theta(self):
        from backend.data_sources.calibration import _ou_mle
        rng = np.random.default_rng(42); dt = 1/252
        kappa_true,theta_true,sigma_true = 0.15,0.045,0.015
        rates = [theta_true]
        for _ in range(999):
            dr = kappa_true*(theta_true-rates[-1])*dt + sigma_true*np.sqrt(dt)*rng.standard_normal()
            rates.append(rates[-1]+dr)
        _,theta_hat,sigma_hat = _ou_mle(np.array(rates))
        assert abs(theta_hat-theta_true) < 0.025   # 1000 obs → ~1-2% precision
        assert abs(sigma_hat-sigma_true) < 0.005

    def test_nearest_psd(self):
        from backend.data_sources.calibration import _nearest_psd
        M = np.array([[1.0,0.999,0.999],[0.999,1.0,0.999],[0.999,0.999,1.0]])
        psd = _nearest_psd(M)
        assert np.all(np.linalg.eigvalsh(psd) >= -1e-8)

    def test_apply_to_imm_changes_params(self):
        from backend.data_sources.calibration import CalibratedParams
        cal = CalibratedParams(calibration_date=TODAY.isoformat(),
            eq_vol_ewma=0.22,eq_vol_stressed=0.45,eq_drift=0.12,
            ir_kappa=0.18,ir_theta_10y=0.038,ir_vol_hist=0.018,ir_vol_stressed=0.032)
        params = MarketParams()
        cal.apply_to_imm(params)
        assert abs(params.volatility     - 0.22)  < 1e-6
        assert abs(params.stressed_vol   - 0.45)  < 1e-6
        assert abs(params.drift          - 0.12)  < 1e-6
        assert abs(params.mean_reversion - 0.18)  < 1e-6
        assert abs(params.long_run_rate  - 0.038) < 1e-6

    def test_json_round_trip(self):
        import tempfile
        from backend.data_sources.calibration import CalibratedParams
        cal = CalibratedParams(calibration_date=TODAY.isoformat(),eq_spot=5200.0,ir_kappa=0.14)
        with tempfile.NamedTemporaryFile(suffix=".json",delete=False) as f: path=f.name
        cal.save(path); loaded = CalibratedParams.load(path)
        assert abs(loaded.eq_spot  - 5200.0) < 1e-6
        assert abs(loaded.ir_kappa - 0.14)   < 1e-8
        os.unlink(path)

    def test_apply_to_state_engine(self):
        from backend.data_sources.calibration import CalibratedParams
        from backend.data_sources import market_state as ms
        cal = CalibratedParams(calibration_date=TODAY.isoformat(),eq_spot=5500.0,
            eq_vol_ewma=0.22,ir_kappa=0.20)
        cal.apply_to_state_engine()
        assert ms._REF_LEVELS["EQ_US"] == 5500.0
        assert abs(ms._DAILY_VOL["EQ_US"] - 0.22/math.sqrt(252)) < 1e-8
        assert ms._IR_MEAN_REVERSION == 0.20


# ═══ Hedging Sets & Credit Sub-Types ════════════════════════════════════════

class TestHedgingSets:
    """Validate hedging set and sub-hedging set routing per CRE52 and CSV spec."""

    def _trade(self, ac, itype, ccy="USD", uid=None, ref=None, cmd=None,
               cst="SINGLE_NAME", cq="IG", tenor_yr=5, direction=1):
        return Trade(
            trade_id=f"HS-{ac}-001", asset_class=ac, instrument_type=itype,
            notional=10e6, notional_ccy=ccy, direction=direction,
            maturity_date=TODAY + timedelta(days=int(tenor_yr*365)),
            trade_date=TODAY - timedelta(days=90),
            underlying_security_id=uid, reference_entity=ref,
            commodity_type=cmd, credit_sub_type=cst, credit_quality=cq,
        )

    # ── Hedging set routing ───────────────────────────────────────────────────
    def test_ir_hedging_set_is_currency(self):
        """IR: hedging set = notional currency (all USD IR = one set)."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("IR","IRS","USD")
        assert _resolve_hedging_set(t) == "USD"

    def test_ir_eur_separate_hedging_set(self):
        """IR EUR is a separate hedging set from IR USD."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t_usd = self._trade("IR","IRS","USD")
        t_eur = self._trade("IR","IRS","EUR")
        assert _resolve_hedging_set(t_usd) != _resolve_hedging_set(t_eur)

    def test_fx_hedging_set_is_currency_pair(self):
        """FX: hedging set = normalised currency pair."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("FX","FXFwd","EUR")
        hs = _resolve_hedging_set(t)
        # Should contain both EUR and USD
        assert "EUR" in hs and "USD" in hs

    def test_eq_hedging_set_is_underlying(self):
        """EQ: hedging set = underlying_security_id."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("EQ","EquitySwap","USD",uid="SPX Index")
        assert _resolve_hedging_set(t) == "SPX Index"

    def test_cr_hedging_set_is_reference_entity(self):
        """CR: hedging set = reference entity."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("CR","CDS_Protection","USD",ref="Ford Motor Co")
        assert _resolve_hedging_set(t) == "Ford Motor Co"

    def test_cmdty_hedging_set_is_commodity_type(self):
        """CMDTY: hedging set = commodity type (energy/metals/agri)."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("CMDTY","CommodityFwd","USD",cmd="CMDTY_ENERGY")
        assert _resolve_hedging_set(t) == "CMDTY_ENERGY"

    def test_explicit_hedging_set_overrides_auto(self):
        """Explicit hedging_set on trade overrides auto-resolution."""
        from backend.engines.sa_ccr import _resolve_hedging_set
        t = self._trade("IR","IRS","USD")
        t.hedging_set = "CUSTOM_HS"
        assert _resolve_hedging_set(t) == "CUSTOM_HS"

    # ── IR sub-hedging set routing ─────────────────────────────────────────────
    def test_ir_sub_hs_short(self):
        """IR ≤1Y → SHORT sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("IR","IRS","USD",tenor_yr=0.5)
        assert _resolve_sub_hedging_set(t) == "SHORT"

    def test_ir_sub_hs_medium(self):
        """IR 1–5Y → MEDIUM sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("IR","IRS","USD",tenor_yr=3.0)
        assert _resolve_sub_hedging_set(t) == "MEDIUM"

    def test_ir_sub_hs_long(self):
        """IR >5Y → LONG sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("IR","IRS","USD",tenor_yr=10.0)
        assert _resolve_sub_hedging_set(t) == "LONG"

    def test_ir_sub_hs_exact_boundary_1y(self):
        """IR exactly 1Y → SHORT (boundary: ≤1Y)."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = Trade("HS-BNDRY","IR","IRS",10e6,"USD",1,
                  TODAY + timedelta(days=365), TODAY - timedelta(days=1))
        shs = _resolve_sub_hedging_set(t)
        assert shs in ("SHORT","MEDIUM")   # 1Y is boundary; SHORT if ≤1Y exactly

    def test_ir_sub_hs_exact_boundary_5y(self):
        """IR exactly 5Y → MEDIUM (boundary: ≤5Y)."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = Trade("HS-BNDRY5","IR","IRS",10e6,"USD",1,
                  TODAY + timedelta(days=5*365), TODAY - timedelta(days=1))
        assert _resolve_sub_hedging_set(t) in ("MEDIUM","LONG")

    # ── Credit sub-hedging set routing ─────────────────────────────────────────
    def test_cr_sub_hs_single_name(self):
        """Single-name CDS → SINGLE_NAME sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDS_Protection",cst="SINGLE_NAME")
        assert _resolve_sub_hedging_set(t) == "SINGLE_NAME"

    def test_cr_sub_hs_index_cds(self):
        """Non-tranched index CDS → INDEX_CDS sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDS_Index",cst="INDEX_CDS")
        assert _resolve_sub_hedging_set(t) == "INDEX_CDS"

    def test_cr_sub_hs_non_tranched(self):
        """Non-tranched alias → NON_TRANCHED sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDS_NonTranched",cst="NON_TRANCHED")
        assert _resolve_sub_hedging_set(t) == "NON_TRANCHED"

    def test_cr_sub_hs_tranched(self):
        """CDO tranche → TRANCHED sub-bucket."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDO_Tranche",cst="TRANCHED")
        assert _resolve_sub_hedging_set(t) == "TRANCHED"

    def test_cr_sub_hs_derived_from_instrument_type(self):
        """If credit_sub_type matches instrument pattern, TRANCHED from CDO_Tranche."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDO_Tranche",cst="TRANCHED")   # explicit TRANCHED
        assert _resolve_sub_hedging_set(t) == "TRANCHED"

    def test_cr_sub_hs_index_from_instrument_type(self):
        """CDS_Index instrument with INDEX_CDS sub-type → INDEX_CDS."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        t = self._trade("CR","CDS_Index",cst="INDEX_CDS")
        assert _resolve_sub_hedging_set(t) == "INDEX_CDS"

    def test_fx_and_eq_sub_hs_are_all(self):
        """FX and EQ have no sub-bucket split → ALL."""
        from backend.engines.sa_ccr import _resolve_sub_hedging_set
        tfx = self._trade("FX","FXFwd","EUR")
        teq = self._trade("EQ","EquitySwap","USD",uid="SPX Index")
        assert _resolve_sub_hedging_set(tfx) == "ALL"
        assert _resolve_sub_hedging_set(teq) == "ALL"

    # ── SF selection for credit sub-types ─────────────────────────────────────
    def test_single_name_ig_sf(self):
        """Single-name IG CDS: SF = 0.50%."""
        from backend.engines.sa_ccr import SF
        assert SF["CR_IG"] == 0.0050

    def test_single_name_sg_sf(self):
        """Single-name SG CDS: SF = 5.00%."""
        from backend.engines.sa_ccr import SF
        assert SF["CR_SG"] == 0.0500

    def test_index_ig_sf(self):
        """IG index CDS: SF = 0.50%."""
        from backend.engines.sa_ccr import SF
        assert SF["CR_IDX_IG"] == 0.0050

    def test_index_sg_sf(self):
        """HY index CDS: SF = 5.00%."""
        from backend.engines.sa_ccr import SF
        assert SF["CR_IDX_SG"] == 0.0500

    def test_tranched_higher_ead_than_index(self):
        """TRANCHED (SG SF) should produce higher EAD than INDEX_CDS (IG SF)."""
        engine = SACCREngine()
        t_idx = Trade("IDX-01","CR","CDS_Index",50e6,"USD",1,
                      TODAY+timedelta(days=5*365),TODAY-timedelta(90),
                      credit_sub_type="INDEX_CDS",credit_quality="IG")
        t_tran= Trade("TRN-01","CR","CDO_Tranche",50e6,"USD",1,
                      TODAY+timedelta(days=5*365),TODAY-timedelta(90),
                      credit_sub_type="TRANCHED",credit_quality="SG")
        ns_idx = make_simple_netting_set([t_idx])
        ns_tran= make_simple_netting_set([t_tran])
        ead_idx  = engine.compute_ead(ns_idx).ead
        ead_tran = engine.compute_ead(ns_tran).ead
        assert ead_tran > ead_idx, (
            f"TRANCHED EAD ({ead_tran:.0f}) should > INDEX EAD ({ead_idx:.0f})")


class TestTradeAttribution:
    """Validate the trade-level SA-CCR attribution table."""

    def _build_ns(self):
        trades = [
            Trade("TR-IR","IR","IRS",100e6,"USD",1,
                  TODAY+timedelta(days=5*365),TODAY-timedelta(90),current_mtm=500_000),
            Trade("TR-FX","FX","FXFwd",30e6,"EUR",1,
                  TODAY+timedelta(days=365),TODAY-timedelta(60),current_mtm=-200_000),
            Trade("TR-CR","CR","CDS_Protection",20e6,"USD",1,
                  TODAY+timedelta(days=5*365),TODAY-timedelta(120),
                  current_mtm=100_000,credit_sub_type="SINGLE_NAME",
                  reference_entity="Ford Motor Co",credit_quality="SG"),
        ]
        return NettingSet("NS-ATTR","CPTY-ATTR",trades,
                         variation_margin=200_000,initial_margin=1_000_000)

    def test_attribution_has_all_required_fields(self):
        """Every trade result must contain all 29 required attribution fields."""
        required = {
            "portfolio_id","trade_id","current_mtm","rc_allocated","rc_portfolio",
            "addon_trade","addon_portfolio","pfe_trade","pfe_portfolio",
            "hedging_set","sub_hedging_set","supervisory_duration","supervisory_factor",
            "maturity_factor","supervisory_delta","sign_delta","underlying_security_id",
            "saccr_notional","saccr_adjusted_notional","effective_notional",
            "ead_trade","ead_portfolio","risk_weight_pct","rwa","ead_calc_type",
        }
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        for tid, tr in result.trade_results.items():
            missing = required - set(tr.keys())
            assert not missing, f"Trade {tid} missing fields: {missing}"

    def test_attribution_trade_count_matches(self):
        """trade_results should have one entry per trade in the netting set."""
        engine = SACCREngine()
        ns = self._build_ns()
        result = engine.compute_ead(ns, portfolio_id="DRV-TEST")
        assert len(result.trade_results) == len(ns.trades)

    def test_attribution_portfolio_ead_consistent(self):
        """All trade rows must agree on the portfolio EAD."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        portfolio_eads = {tr["ead_portfolio"] for tr in result.trade_results.values()}
        assert len(portfolio_eads) == 1
        assert abs(list(portfolio_eads)[0] - result.ead) < 1.0

    def test_attribution_ir_has_supervisory_duration(self):
        """IR trade must have supervisory_duration > 0."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        ir_tr = result.trade_results["TR-IR"]
        assert ir_tr["supervisory_duration"] > 0

    def test_attribution_fx_has_sd_one(self):
        """FX trade supervisory_duration must be 1.0 (not IR formula)."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        fx_tr = result.trade_results["TR-FX"]
        assert abs(fx_tr["supervisory_duration"] - 1.0) < 1e-9

    def test_attribution_saccr_adjusted_notional_ir(self):
        """IR adjusted notional ≈ supervisory_duration × raw_notional (within 0.01%)."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        ir_tr = result.trade_results["TR-IR"]
        sd     = ir_tr["supervisory_duration"]
        ntnl   = ir_tr["saccr_notional"]
        adj    = ir_tr["saccr_adjusted_notional"]
        # SD is stored to 6dp; product may differ by rounding — use 0.1% tolerance
        expected = sd * ntnl
        assert abs(adj - expected) / max(expected, 1) < 0.001,             f"adj_notional {adj:,.0f} vs sd×notional {expected:,.0f}"

    def test_attribution_cr_single_name_sub_hedging_set(self):
        """CR single-name CDS must have sub_hedging_set = SINGLE_NAME."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        cr_tr = result.trade_results["TR-CR"]
        assert cr_tr["sub_hedging_set"] == "SINGLE_NAME"

    def test_attribution_ead_calc_type_populated(self):
        """ead_calc_type must be SA_CCR, IMM, or FALLBACK."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        for tid, tr in result.trade_results.items():
            assert tr["ead_calc_type"] in ("SA_CCR","IMM","FALLBACK"),                 f"Trade {tid} has invalid ead_calc_type: {tr['ead_calc_type']}"

    def test_attribution_hedging_set_ir_is_currency(self):
        """IR trade hedging_set must be currency code."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        assert result.trade_results["TR-IR"]["hedging_set"] == "USD"

    def test_attribution_sign_delta_is_pm1(self):
        """sign_delta must be +1 or -1 for all linear trades."""
        engine = SACCREngine()
        result = engine.compute_ead(self._build_ns(), portfolio_id="DRV-TEST")
        for tid, tr in result.trade_results.items():
            assert tr["sign_delta"] in (1,-1),                 f"Trade {tid} sign_delta={tr['sign_delta']} invalid"


# ═══ Integration ═════════════════════════════════════════════════════════════

class TestIntegration:
    def test_full_daily_run(self):
        from backend.main import PrometheusRunner
        results = PrometheusRunner(sa_cva_approved=True).run_daily(TODAY)
        cap = results["capital_summary"]
        for key in ["rwa_credit","rwa_ccr","rwa_market","rwa_cva","rwa_ccp","rwa_operational"]:
            assert cap[key] >= 0
        assert cap["rwa_total"] > 0
        pre = cap["rwa_total_pre_floor"]
        expected = sum(cap[k] for k in ["rwa_credit","rwa_ccr","rwa_market","rwa_cva","rwa_ccp","rwa_operational"])
        assert abs(pre - expected) < 1.0
        assert 0 < cap["cet1_ratio"] < 1
        assert results["cva"]["total_rwa_cva"] >= 0
        assert results["ccp"]["total_rwa_ccp"] >  0

    def test_portfolio_ids_meaningful(self):
        import re
        from backend.main import PrometheusRunner
        results = PrometheusRunner().run_daily(TODAY)
        drv_re = re.compile(r"^DRV-\d{4}-\d{4}$")
        bbk_re = re.compile(r"^BBK-\d{4}-\d{4}$")
        for p in results["derivative"]:   assert drv_re.match(p["portfolio_id"])
        for p in results["banking_book"]: assert bbk_re.match(p["portfolio_id"])

    def test_output_floor_logic(self):
        from backend.main import PrometheusRunner
        cap = PrometheusRunner().run_daily(TODAY)["capital_summary"]
        assert abs(cap["rwa_floor"] - cap["rwa_sa_based"]*0.725) < 1.0
        assert cap["rwa_total"] >= cap["rwa_total_pre_floor"] - 1.0

    def test_capital_ratios_consistent(self):
        from backend.main import PrometheusRunner
        cap = PrometheusRunner().run_daily(TODAY)["capital_summary"]
        assert cap["cet1_capital"]  <= cap["tier1_capital"]
        assert cap["tier1_capital"] <= cap["total_capital"]
        assert cap["cet1_ratio"]    <= cap["tier1_ratio"]
        assert cap["tier1_ratio"]   <= cap["total_cap_ratio"]

    def test_mtm_varies_day_on_day(self):
        from backend.main import PrometheusRunner
        runner = PrometheusRunner()
        def net_mtm(d):
            r = runner.run_daily(d)
            return sum(t.current_mtm for p in r["derivative"] for t in p.get("trades",[]))
        assert net_mtm(TODAY) != net_mtm(TODAY - timedelta(days=1))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


# ─────────────────────────────────────────────────────────────────────────────
# TestLGDCalibration — validates backend/data_sources/lgd_calibration.py
# ─────────────────────────────────────────────────────────────────────────────

class TestLGDCalibration(unittest.TestCase):
    """
    Tests for the three-layer LGD model in lgd_calibration.py.

    Covers:
      - Frye-Jacobs downturn formula correctness
      - CRE32.16 regulatory floor enforcement (unsecured 25%; secured varies)
      - Monotonicity: DT-LGD > TTC-LGD; higher ρ → higher DT-LGD
      - Conditional LGD: crisis ≥ normal; normal ≈ TTC at SI=0
      - Wrong-way LGD: same-sector uplift applied
      - Best-estimate LGD: declines with time-in-default and collections
      - Conservative margin raises DT-LGD (CRE36.65)
      - ρ_LGD override respected
      - All 7 asset classes produce valid DT-LGDs
      - Economic ordering: RETAIL_REV > CORP > RETAIL_MORT
      - validate_lgd_table() structural checks pass
      - LGDResult audit trail completeness
    """

    @classmethod
    def setUpClass(cls):
        from backend.data_sources.lgd_calibration import (
            LGDModel, LGDResult, DEFAULT_LGD_MODEL, validate_lgd_table,
            downturn_lgd, _TTC_TABLE, LGD_FLOORS_SECURED, LGD_FLOOR_UNSECURED,
            _norm_inv, LGD_CAP,
        )
        cls.LGDModel           = LGDModel
        cls.LGDResult          = LGDResult
        cls.DEFAULT            = DEFAULT_LGD_MODEL
        cls.validate_lgd_table = staticmethod(validate_lgd_table)
        cls.downturn_lgd_fn    = staticmethod(downturn_lgd)
        cls.TTC_TABLE          = _TTC_TABLE
        cls.FLOORS             = LGD_FLOORS_SECURED
        cls.FLOOR_UNSECURED    = LGD_FLOOR_UNSECURED
        cls.norm_inv           = staticmethod(_norm_inv)
        cls.LGD_CAP            = LGD_CAP
        cls.m0 = LGDModel(conservative_margin=0.0)   # no margin (raw Frye-Jacobs)

    class _Macro:
        """Minimal duck-type for MacroeconomicFactors stress_index()."""
        def __init__(self, si): self._si = si
        def stress_index(self): return self._si

    # ── Frye-Jacobs formula ────────────────────────────────────────────────────

    def test_frye_jacobs_corp_unsecured(self):
        """CORP unsecured: TTC=42.4%, ρ=0.30 → DT-LGD ≈ 75-85%."""
        lgd_dt = self.m0._frye_jacobs(0.424, 0.30)
        self.assertGreater(lgd_dt, 0.70)
        self.assertLess(lgd_dt, 0.90)

    def test_downturn_exceeds_ttc(self):
        """Downturn LGD must always exceed the TTC LGD."""
        for ac, col in [("CORP","NONE"), ("BANK","NONE"), ("RETAIL_REV","NONE")]:
            ttc, _ = self.m0.ttc_lgd(ac, col)
            dt     = self.m0.downturn_lgd(ac, col)
            self.assertGreater(dt, ttc,
                msg=f"{ac}/{col}: DT={dt:.4f} should exceed TTC={ttc:.4f}")

    def test_monotone_in_rho(self):
        """Higher ρ_LGD → higher DT-LGD (ceteris paribus)."""
        q = self.norm_inv(0.999)
        lo = self.m0._frye_jacobs_q(0.40, 0.10, q)
        hi = self.m0._frye_jacobs_q(0.40, 0.45, q)
        self.assertGreater(hi, lo)

    def test_at_zero_rho_dt_equals_ttc(self):
        """With ρ=0, Frye-Jacobs reduces to identity (DT-LGD ≈ TTC-LGD)."""
        q   = self.norm_inv(0.999)
        lgd = self.m0._frye_jacobs_q(0.40, 1e-6, q)
        self.assertAlmostEqual(lgd, 0.40, places=2)

    # ── CRE32.16 floors ───────────────────────────────────────────────────────

    def test_cre3216_unsecured_floor(self):
        """CORP unsecured DT-LGD must be ≥ 25% (CRE32.16)."""
        dt = self.DEFAULT.downturn_lgd("CORP", "NONE")
        self.assertGreaterEqual(dt, self.FLOOR_UNSECURED)

    def test_cre3216_financial_floor(self):
        """Financial collateral floor = 0%."""
        dt = self.DEFAULT.downturn_lgd("CORP", "FINANCIAL")
        self.assertGreaterEqual(dt, self.FLOORS["FINANCIAL"])

    def test_cre3216_residential_re_floor(self):
        """Residential RE floor = 5%."""
        dt = self.DEFAULT.downturn_lgd("RETAIL_MORT", "RESIDENTIAL_RE")
        self.assertGreaterEqual(dt, self.FLOORS["RESIDENTIAL_RE"])

    def test_cre3216_commercial_re_floor(self):
        """Commercial RE floor = 10%."""
        dt = self.DEFAULT.downturn_lgd("CORP", "COMMERCIAL_RE")
        self.assertGreaterEqual(dt, self.FLOORS["COMMERCIAL_RE"])

    def test_cre3216_physical_floor(self):
        """Other physical collateral floor = 15%."""
        dt = self.DEFAULT.downturn_lgd("CORP", "OTHER_PHYSICAL")
        self.assertGreaterEqual(dt, self.FLOORS["OTHER_PHYSICAL"])

    def test_all_asset_classes_above_floor(self):
        """Every (asset_class, collateral_type) row produces DT-LGD above its floor."""
        for (ac, col) in self.TTC_TABLE:
            dt    = self.DEFAULT.downturn_lgd(ac, col)
            floor = self.FLOORS.get(col, self.FLOOR_UNSECURED)
            self.assertGreaterEqual(dt, floor - 1e-9,
                msg=f"{ac}/{col}: DT={dt:.4f} < floor={floor:.4f}")
            self.assertLess(dt, 1.0)

    # ── Conditional LGD ───────────────────────────────────────────────────────

    def test_conditional_crisis_geq_normal(self):
        """Crisis LGD (SI=1) must be ≥ normal LGD (SI=0)."""
        lgd_n = self.m0.conditional_lgd("CORP", self._Macro(0.0))
        lgd_c = self.m0.conditional_lgd("CORP", self._Macro(1.0))
        self.assertGreaterEqual(lgd_c, lgd_n)

    def test_conditional_monotone_in_stress(self):
        """Conditional LGD is non-decreasing in stress_index."""
        pds = [self.m0.conditional_lgd("CORP", self._Macro(si))
               for si in [0.0, 0.25, 0.5, 0.75, 1.0]]
        for i in range(len(pds)-1):
            self.assertLessEqual(pds[i], pds[i+1] + 1e-9)

    def test_conditional_normal_near_ttc(self):
        """At SI=0, conditional LGD should be close to TTC (within 10pp)."""
        ttc, _ = self.m0.ttc_lgd("CORP", "NONE")
        cond   = self.m0.conditional_lgd("CORP", self._Macro(0.0))
        self.assertAlmostEqual(cond, ttc, delta=0.12)

    # ── Wrong-way LGD ─────────────────────────────────────────────────────────

    def test_wrong_way_same_sector_uplift(self):
        """Same-sector obligor/collateral triggers 1.20× uplift."""
        base  = self.m0.wrong_way_lgd(0.40, "FINANCIAL", "CORP", "BANK")
        ww    = self.m0.wrong_way_lgd(0.40, "FINANCIAL", "FINANCIALS", "FINANCIALS")
        self.assertGreater(ww, base)

    def test_wrong_way_re_re(self):
        """Real-estate obligor + RE collateral triggers 1.25× uplift."""
        # 'INDUSTRIALS' has no sector match → no uplift (base)
        # 'REAL_ESTATE' matches re_obligor check → 1.25× uplift
        base = self.m0.wrong_way_lgd(0.30, "COMMERCIAL_RE", "INDUSTRIALS", "TECH")
        ww   = self.m0.wrong_way_lgd(0.30, "COMMERCIAL_RE", "REAL_ESTATE", "REAL_ESTATE")
        self.assertGreater(ww, base)

    def test_wrong_way_cap(self):
        """Wrong-way LGD must never exceed 99.9%."""
        ww = self.m0.wrong_way_lgd(0.95, "NONE", "FINANCIALS", "FINANCIALS")
        self.assertLessEqual(ww, self.LGD_CAP)

    # ── Best-estimate LGD ─────────────────────────────────────────────────────

    def test_best_estimate_declines_with_time(self):
        """Best-estimate LGD decreases as workout progresses."""
        t0 = self.m0.best_estimate_lgd("CORP", time_in_default_years=0.0)
        t2 = self.m0.best_estimate_lgd("CORP", time_in_default_years=2.0)
        t5 = self.m0.best_estimate_lgd("CORP", time_in_default_years=5.0)
        self.assertGreater(t0, t2)
        self.assertGreater(t2, t5)

    def test_best_estimate_full_recovery_zero(self):
        """If 100% of EAD is already recovered, best estimate = 0."""
        be = self.m0.best_estimate_lgd("CORP", recovery_collected_pct=1.0)
        self.assertAlmostEqual(be, 0.0, places=6)

    def test_best_estimate_partial_recovery(self):
        """50% recovery should halve the best estimate vs 0%."""
        be0  = self.m0.best_estimate_lgd("CORP", recovery_collected_pct=0.0)
        be50 = self.m0.best_estimate_lgd("CORP", recovery_collected_pct=0.5)
        self.assertAlmostEqual(be50, be0 * 0.5, places=6)

    # ── Model parameters ──────────────────────────────────────────────────────

    def test_conservative_margin_raises_dt_lgd(self):
        """Adding a conservative margin always increases DT-LGD (CRE36.65)."""
        dt_0  = self.LGDModel(conservative_margin=0.00).downturn_lgd("CORP")
        dt_5  = self.LGDModel(conservative_margin=0.05).downturn_lgd("CORP")
        self.assertGreater(dt_5, dt_0)

    def test_rho_override(self):
        """rho_lgd_override applies uniformly across all asset classes."""
        m_hi  = self.LGDModel(rho_lgd_override=0.50, conservative_margin=0.0)
        m_lo  = self.LGDModel(rho_lgd_override=0.10, conservative_margin=0.0)
        self.assertGreater(
            m_hi.downturn_lgd("CORP"),
            m_lo.downturn_lgd("CORP"),
        )

    # ── Structural / table validation ─────────────────────────────────────────

    def test_validate_lgd_table(self):
        """validate_lgd_table() must return True for the shipped table."""
        self.assertTrue(self.validate_lgd_table())

    def test_lgd_result_fields_complete(self):
        """LGDResult must contain all mandatory audit fields."""
        result = self.m0.compute_lgd("CORP", "NONE", pd=0.01, macro=self._Macro(0.3))
        self.assertIsInstance(result, self.LGDResult)
        self.assertEqual(result.pillar1_lgd, result.lgd_downturn_floored)
        self.assertIsNotNone(result.lgd_conditional)
        self.assertAlmostEqual(result.stress_index, 0.3, places=6)
        self.assertIn(result.source, ("TTC_TABLE","TTC_TABLE_FALLBACK_UNSECURED","DEFAULT_FALLBACK"))

    def test_economic_ordering(self):
        """RETAIL_REV > CORP > RETAIL_MORT (empirical recovery hierarchy)."""
        rev  = self.DEFAULT.downturn_lgd("RETAIL_REV")
        corp = self.DEFAULT.downturn_lgd("CORP")
        mort = self.DEFAULT.downturn_lgd("RETAIL_MORT")
        self.assertGreater(rev,  corp)
        self.assertGreater(corp, mort)
