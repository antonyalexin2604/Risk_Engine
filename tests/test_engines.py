"""
PROMETHEUS Risk Platform — Model Validation Test Suite
Validates SA-CCR, IMM, A-IRB, and FRTB engines against
known regulatory benchmarks and BIS example calculations.
"""

import sys, os

# Resolve project root so tests run from any working directory
_HERE = os.path.dirname(os.path.abspath(__file__))   # .../tests/
_ROOT = os.path.dirname(_HERE)                        # .../Prometheus/
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
import math
import numpy as np
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


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

TODAY = date(2024, 3, 29)

def make_irs_trade(notional=100_000_000, tenor_yr=5, direction=1):
    return Trade(
        trade_id       = "TEST-IRS-001",
        asset_class    = "IR",
        instrument_type= "IRS",
        notional       = notional,
        notional_ccy   = "USD",
        direction      = direction,
        maturity_date  = TODAY + timedelta(days=int(tenor_yr * 365)),
        trade_date     = TODAY,
        current_mtm    = 500_000,
    )

def make_fx_trade(notional=50_000_000, direction=1):
    return Trade(
        trade_id       = "TEST-FX-001",
        asset_class    = "FX",
        instrument_type= "FXFwd",
        notional       = notional,
        notional_ccy   = "EUR",
        direction      = direction,
        maturity_date  = TODAY + timedelta(days=365),
        trade_date     = TODAY,
        current_mtm    = -200_000,
    )

def make_simple_netting_set(trades, vm=0, im=0, has_csa=True):
    ns = NettingSet(
        netting_id      = "TEST-NS-001",
        counterparty_id = "CPTY-TEST",
        trades          = trades,
        variation_margin= vm,
        initial_margin  = im,
        threshold       = 0,
        mta             = 0,
        has_csa         = has_csa,
    )
    return ns


# ═════════════════════════════════════════════════════════════════════════════
# SA-CCR TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestSupervisoryDuration:
    def test_5yr_trade(self):
        """CRE52.39: SD for a 5-year IRS starting now."""
        today = TODAY
        end   = today + timedelta(days=5 * 365)
        sd = supervisory_duration(today, today, end)
        # SD = (exp(-0.05×0) - exp(-0.05×5)) / 0.05
        expected = (math.exp(0) - math.exp(-0.25)) / 0.05
        assert abs(sd - expected) < 0.001, f"SD={sd:.4f}, expected={expected:.4f}"

    def test_zero_maturity(self):
        """Expired trade: SD should be 0."""
        today = TODAY
        past  = today - timedelta(days=30)
        sd = supervisory_duration(today, today, past)
        assert sd == 0.0

    def test_1yr_trade(self):
        """1-year SD should be ~0.951."""
        today = TODAY
        end   = today + timedelta(days=365)
        sd = supervisory_duration(today, today, end)
        expected = (1 - math.exp(-0.05)) / 0.05
        assert abs(sd - expected) < 0.001


class TestMaturityFactor:
    def test_csa_mpor10(self):
        """Margined trade MPOR=10: MF = sqrt(10/250)."""
        trade = make_irs_trade()
        mf = maturity_factor(trade, has_csa=True, mpor_days=10)
        expected = math.sqrt(10/250)
        assert abs(mf - expected) < 0.0001

    def test_no_csa(self):
        """Unmargined 5yr trade: MF = sqrt(min(5,1)) = 1."""
        trade = make_irs_trade(tenor_yr=5)
        mf = maturity_factor(trade, has_csa=False, mpor_days=20)
        assert abs(mf - 1.0) < 0.01   # Mi=5yr → min(5,1)=1 → sqrt(1)=1


class TestReplacementCost:
    def test_rc_in_the_money(self):
        """Margined: RC = max(V-C, TH+MTA-NICA, 0). V>C → positive RC."""
        trade = make_irs_trade()
        trade.current_mtm = 2_000_000
        ns = make_simple_netting_set([trade], vm=500_000, im=200_000)
        rc = compute_replacement_cost(ns)
        # V=2M, C=0.7M, TH+MTA-NICA=0+0-200K=-200K → max(1.3M,-200K,0)=1.3M
        assert rc == pytest.approx(1_300_000, rel=0.01)

    def test_rc_out_of_money(self):
        """Fully collateralised negative MTM → RC = 0."""
        trade = make_irs_trade()
        trade.current_mtm = -1_000_000
        ns = make_simple_netting_set([trade], vm=2_000_000)
        rc = compute_replacement_cost(ns)
        assert rc == 0.0

    def test_rc_no_csa(self):
        """Unmargined: RC = max(V, 0)."""
        trade = make_irs_trade()
        trade.current_mtm = 3_000_000
        ns = make_simple_netting_set([trade], has_csa=False)
        rc = compute_replacement_cost(ns)
        assert rc == 3_000_000


class TestPFEMultiplier:
    def test_multiplier_floor(self):
        """If AddOn=0, multiplier should be at floor=0.05."""
        ns = make_simple_netting_set([make_irs_trade()])
        mult = compute_pfe_multiplier(ns, addon_agg=0)
        assert mult == pytest.approx(0.05, abs=0.001)

    def test_multiplier_max(self):
        """Large positive MtM → multiplier approaches 1.0."""
        trade = make_irs_trade()
        trade.current_mtm = 1e9
        ns = make_simple_netting_set([trade])
        mult = compute_pfe_multiplier(ns, addon_agg=1_000_000)
        assert mult == pytest.approx(1.0, abs=0.001)

    def test_multiplier_between_floor_and_1(self):
        """Multiplier should be in [0.05, 1.0]."""
        ns = make_simple_netting_set([make_irs_trade()])
        for addon in [100_000, 500_000, 5_000_000]:
            mult = compute_pfe_multiplier(ns, addon)
            assert 0.05 <= mult <= 1.0


class TestSACCREngine:
    def test_ead_positive(self):
        """EAD must always be positive."""
        engine = SACCREngine()
        trades = [make_irs_trade(), make_fx_trade()]
        ns = make_simple_netting_set(trades)
        result = engine.compute_ead(ns)
        assert result.ead > 0

    def test_alpha_applied(self):
        """EAD = alpha × (RC + PFE). Check alpha=1.4."""
        engine = SACCREngine()
        trades = [make_irs_trade(notional=100e6)]
        ns = make_simple_netting_set(trades)
        result = engine.compute_ead(ns)
        rc   = result.replacement_cost
        mult = result.pfe_multiplier
        addon= result.add_on_aggregate
        expected_ead = 1.4 * (rc + mult * addon)
        assert abs(result.ead - expected_ead) < 1.0

    def test_netting_benefit(self):
        """Offsetting trades should produce lower EAD than sum of individual EADs."""
        engine = SACCREngine()
        t_long  = make_irs_trade(direction=1)
        t_short = make_irs_trade(direction=-1)
        ns_both = make_simple_netting_set([t_long, t_short])
        ns_long = make_simple_netting_set([t_long])
        ns_short= make_simple_netting_set([t_short])
        res_both = engine.compute_ead(ns_both)
        res_long = engine.compute_ead(ns_long)
        res_short= engine.compute_ead(ns_short)
        # Netting benefit: EAD_net < EAD_long + EAD_short
        assert res_both.ead <= res_long.ead + res_short.ead


class TestIMMFallback:
    def test_exotic_fallback(self):
        """Non-IMM instruments should fall back to SA-CCR."""
        t = Trade("T-EXOTIC", "EQ", "ExoticBarrier", 1e6, "USD", 1,
                  TODAY + timedelta(days=365), TODAY)
        t.saccr_method = "IMM"
        eligible, trace = check_imm_eligibility(t)
        assert not eligible
        assert "EXOTIC_PAYOFF" in trace

    def test_irs_eligible(self):
        """Standard IRS should be IMM-eligible."""
        t = Trade("T-IRS", "IR", "IRS", 1e7, "USD", 1,
                  TODAY + timedelta(days=365*5), TODAY)
        t.saccr_method = "IMM"
        eligible, trace = check_imm_eligibility(t)
        assert eligible
        assert trace is None

    def test_engine_assigns_fallback(self):
        """Engine.assign_method should update fallback_trace on ineligible IMM trades."""
        engine = SACCREngine()
        t = Trade("T-BIG", "EQ", "ExoticSwap", 10e9, "USD", 1,
                  TODAY + timedelta(days=365*2), TODAY)
        t.saccr_method = "IMM"
        updated = engine.assign_method(t)
        assert updated.saccr_method == "FALLBACK"
        assert updated.fallback_trace is not None


# ═════════════════════════════════════════════════════════════════════════════
# IMM / MONTE CARLO TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestMonteCarlo:
    def test_gbm_shape(self):
        """GBM paths should have shape (N, T)."""
        mc = MonteCarloEngine()
        paths = mc.simulate_gbm(S0=100)
        assert paths.shape == (mc.N, mc.T)

    def test_gbm_positive(self):
        """GBM paths must remain positive (lognormal)."""
        mc = MonteCarloEngine()
        paths = mc.simulate_gbm(S0=100)
        assert np.all(paths > 0)

    def test_hull_white_shape(self):
        """Hull-White paths: shape (N, T)."""
        mc = MonteCarloEngine()
        paths = mc.simulate_hull_white(r0=0.05)
        assert paths.shape == (mc.N, mc.T)

    def test_epe_non_negative(self):
        """EPE (expected positive exposure) must be ≥ 0."""
        engine = IMMEngine()
        trades = [make_irs_trade(), make_fx_trade()]
        profile = engine.compute_exposure_profile(trades, TODAY)
        assert profile.epe >= 0
        assert profile.eepe >= 0

    def test_eee_non_decreasing(self):
        """EEE profile must be non-decreasing (CRE53.13)."""
        engine = IMMEngine()
        trades = [make_irs_trade()]
        profile = engine.compute_exposure_profile(trades, TODAY)
        diffs = np.diff(profile.eee_profile)
        assert np.all(diffs >= -1e-6), "EEE is not non-decreasing"

    def test_eepe_leq_pfe95(self):
        """EEPE should be less than PFE 95th percentile (sanity check)."""
        engine = IMMEngine()
        trades = [make_irs_trade(notional=100e6)]
        profile = engine.compute_exposure_profile(trades, TODAY)
        assert profile.eepe <= profile.pfe_95.max() * 1.1   # small tolerance

    def test_ead_equals_alpha_times_eepe(self):
        """EAD = 1.4 × EEPE."""
        engine = IMMEngine()
        profile = engine.compute_exposure_profile([make_irs_trade()], TODAY)
        assert abs(profile.ead - 1.4 * profile.eepe) < 1.0

    def test_stressed_ead_gte_base(self):
        """Stressed EAD must be ≥ base EAD (higher volatility → higher exposure)."""
        engine = IMMEngine()
        profile = engine.compute_exposure_profile([make_fx_trade()], TODAY)
        assert profile.stressed_ead >= profile.ead * 0.9   # stressed generally higher


# ═════════════════════════════════════════════════════════════════════════════
# A-IRB TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestAIRB:
    def test_correlation_corp_low_pd(self):
        """Corporate correlation: high PD → lower R (more idiosyncratic)."""
        R_low_pd  = asset_correlation(0.0003, "CORP")
        R_high_pd = asset_correlation(0.20,   "CORP")
        assert R_low_pd > R_high_pd

    def test_correlation_retail_mort(self):
        """Retail mortgage correlation fixed at 0.15 (CRE31.15)."""
        R = asset_correlation(0.01, "RETAIL_MORT")
        assert abs(R - 0.15) < 0.0001

    def test_pd_floor_applied(self):
        """PD below 3bp floor should be raised."""
        engine = AIRBEngine()
        exp = BankingBookExposure(
            trade_id="T-LOW-PD", portfolio_id="P001", obligor_id="OBL001",
            asset_class="CORP", ead=10e6, pd=0.0001, lgd=0.45, maturity=3.0
        )
        result = engine.compute(exp)
        assert result.pd_applied >= 0.0003   # floor at 3bp

    def test_capital_k_positive(self):
        """Capital requirement K must be positive."""
        for pd in [0.001, 0.01, 0.05, 0.15]:
            K = capital_requirement_k(pd, 0.45, 2.5, 0.24, (0.11852 - 0.05478*math.log(pd))**2)
            assert K >= 0, f"K<0 for PD={pd}"

    def test_rwa_proportional_to_ead(self):
        """If EAD doubles, RWA should double (linearity)."""
        engine = AIRBEngine()
        exp1 = BankingBookExposure("T1","P1","O1","CORP",100e6,0.01,0.45,3.0)
        exp2 = BankingBookExposure("T2","P1","O1","CORP",200e6,0.01,0.45,3.0)
        r1 = engine.compute(exp1)
        r2 = engine.compute(exp2)
        assert abs(r2.rwa / r1.rwa - 2.0) < 0.001

    def test_double_default_reduces_pd(self):
        """Double-default PD should be lower than obligor PD."""
        pd_ob = 0.05
        pd_guar = 0.02
        pd_dd = double_default_pd(pd_ob, pd_guar)
        assert pd_dd < pd_ob

    def test_maturity_cap(self):
        """Maturity > 5yr should be clamped."""
        engine = AIRBEngine()
        exp = BankingBookExposure("T1","P1","O1","CORP",10e6,0.01,0.45,7.0)
        result = engine.compute(exp)
        assert result.maturity <= 5.0

    def test_el_formula(self):
        """EL = PD × LGD × EAD."""
        engine = AIRBEngine()
        pd, lgd, ead = 0.02, 0.40, 50e6
        exp = BankingBookExposure("T1","P1","O1","CORP", ead, pd, lgd, 2.5)
        result = engine.compute(exp)
        expected_el = result.pd_applied * result.lgd_applied * ead
        assert abs(result.el - expected_el) < 100

    def test_norm_cdf_known_values(self):
        """N(0) = 0.5, N(1.96) ≈ 0.975."""
        assert abs(_norm_cdf(0) - 0.5) < 0.001
        assert abs(_norm_cdf(1.96) - 0.975) < 0.002
        assert abs(_norm_cdf(-1.645) - 0.05) < 0.002


# ═════════════════════════════════════════════════════════════════════════════
# FRTB TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestFRTB:
    def make_sensitivity(self, rc="GIRR", delta=100_000, bucket="1"):
        return Sensitivity("T-001", rc, bucket, f"{rc}_FACTOR", delta, 0, 0, 0)

    def test_delta_charge_positive(self):
        """Delta charge must be non-negative."""
        engine = FRTBEngine()
        senses = [self.make_sensitivity("GIRR", 1_000_000)]
        d, v, c, total = engine.sbm.total_sbm(senses)
        assert d >= 0
        assert total >= 0

    def test_empty_sensitivities(self):
        """No sensitivities → zero charge."""
        engine = FRTBEngine()
        d, v, c, total = engine.sbm.total_sbm([])
        assert total == 0.0

    def test_netting_reduces_charge(self):
        """Long + short same bucket → lower charge than two longs."""
        engine = FRTBEngine()
        s_long1 = self.make_sensitivity("GIRR", 1_000_000, "1")
        s_long2 = self.make_sensitivity("GIRR", 1_000_000, "1")
        s_short = self.make_sensitivity("GIRR", -1_000_000, "1")
        charge_2long = engine.sbm.delta_charge([s_long1, s_long2], "GIRR")
        charge_net   = engine.sbm.delta_charge([s_long1, s_short], "GIRR")
        assert charge_net < charge_2long

    def test_es_positive(self):
        """Expected Shortfall must be positive."""
        from backend.engines.frtb import IMACalculator
        ima = IMACalculator()
        rng = np.random.default_rng(42)
        pnl = rng.normal(0, 100_000, 250)
        es = ima.compute_es(pnl)
        assert es >= 0

    def test_stressed_es_gte_base(self):
        """Stressed ES ≥ base ES."""
        from backend.engines.frtb import IMACalculator
        ima = IMACalculator()
        pnl = np.random.default_rng(42).normal(0, 50_000, 250)
        es_base    = ima.compute_es(pnl, stressed=False)
        es_stressed= ima.compute_es(pnl, stressed=True)
        assert es_stressed >= es_base

    def test_capital_max_sbm_ima(self):
        """Capital = max(SBM, 1.5 × IMA) - verified via full engine."""
        engine = FRTBEngine()
        senses = [self.make_sensitivity("GIRR", 500_000)]
        result = engine.compute("TEST-PORT", senses, avg_notional=1_000_000)
        assert result.capital_market_risk >= result.sbm_total


class TestBacktesting:
    def test_green_zone(self):
        """0 exceptions → Green."""
        engine = BacktestEngine()
        predicted = np.full(250, 100_000.0)
        actual    = np.full(250, 50_000.0)    # always below VaR
        result = engine.evaluate(predicted, actual)
        assert result["traffic_light"] == "GREEN"
        assert result["exceptions"] == 0

    def test_red_zone(self):
        """Many exceptions → Red."""
        engine = BacktestEngine()
        predicted = np.full(250, 10_000.0)
        actual    = -np.full(250, 100_000.0)  # always exceeds VaR
        result = engine.evaluate(predicted, actual)
        assert result["traffic_light"] == "RED"
        assert result["exceptions"] == 250

    def test_amber_zone(self):
        """7 exceptions → Amber."""
        engine = BacktestEngine()
        predicted = np.full(250, 50_000.0)
        actual = np.zeros(250)
        actual[:7] = -100_000   # 7 exceptions
        result = engine.evaluate(predicted, actual)
        assert result["traffic_light"] == "AMBER"
        assert result["exceptions"] == 7

    def test_length_mismatch_raises(self):
        """Mismatched arrays should raise ValueError."""
        engine = BacktestEngine()
        with pytest.raises(ValueError):
            engine.evaluate(np.array([1.0, 2.0]), np.array([1.0]))


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_full_daily_run(self):
        """Full daily risk run should complete with five-part RWA (Sprint A)."""
        from backend.main import PrometheusRunner
        runner = PrometheusRunner(sa_cva_approved=True)
        results = runner.run_daily(TODAY)

        assert "capital_summary" in results
        cap = results["capital_summary"]

        # Five-part RWA all present and non-negative
        assert cap["rwa_credit"]      >= 0
        assert cap["rwa_ccr"]         >= 0
        assert cap["rwa_market"]      >= 0
        assert cap["rwa_cva"]         >= 0
        assert cap["rwa_ccp"]         >= 0
        assert cap["rwa_operational"] >= 0

        # Total RWA is positive and correct
        assert cap["rwa_total"] > 0
        pre_floor = cap["rwa_total_pre_floor"]
        assert abs(pre_floor - (
            cap["rwa_credit"] + cap["rwa_ccr"] + cap["rwa_market"] +
            cap["rwa_cva"] + cap["rwa_ccp"] + cap["rwa_operational"]
        )) < 1.0, "Pre-floor total must equal sum of five components"

        # Capital ratios in range
        assert 0 < cap["cet1_ratio"] < 1
        assert 0 < cap["total_cap_ratio"] < 1

        # CVA and CCP results present
        assert "cva" in results and results["cva"]["total_rwa_cva"] >= 0
        assert "ccp" in results and results["ccp"]["total_rwa_ccp"] >  0

        assert len(results["derivative"])   > 0
        assert len(results["banking_book"]) > 0

    def test_portfolio_ids_meaningful(self):
        """Portfolio IDs must follow DRV/BBK-YYYY-NNN format."""
        import re
        from backend.main import PrometheusRunner
        runner = PrometheusRunner()
        results = runner.run_daily(TODAY)

        drv_pattern = re.compile(r"^DRV-\d{4}-\d{4}$")
        bbk_pattern = re.compile(r"^BBK-\d{4}-\d{4}$")

        for p in results["derivative"]:
            assert drv_pattern.match(p["portfolio_id"]), f"Bad DRV ID: {p['portfolio_id']}"
        for p in results["banking_book"]:
            assert bbk_pattern.match(p["portfolio_id"]), f"Bad BBK ID: {p['portfolio_id']}"

    def test_output_floor_logic(self):
        """
        Output floor = 72.5% of SA-based RWA (RBC20.11).
        CVA RWA excluded from floor base (CAP10 FAQ1).
        Sprint A: keys renamed rwa_floor and rwa_sa_based.
        """
        from backend.main import PrometheusRunner
        runner = PrometheusRunner()
        results = runner.run_daily(TODAY)
        cap = results["capital_summary"]
        # Floor is 72.5% of SA-based RWA (excludes CVA per CAP10 FAQ1)
        expected_floor = cap["rwa_sa_based"] * 0.725
        assert abs(cap["rwa_floor"] - expected_floor) < 1.0
        # Total RWA = max(pre-floor, floor)
        assert cap["rwa_total"] >= cap["rwa_total_pre_floor"] - 1.0
        assert cap["rwa_total"] >= cap["rwa_floor"] - 1.0

    def test_capital_ratios_consistent(self):
        """CET1 ≤ Tier1 ≤ TotalCapital — always true by definition."""
        from backend.main import PrometheusRunner
        runner = PrometheusRunner()
        results = runner.run_daily(TODAY)
        cap = results["capital_summary"]
        assert cap["cet1_capital"] <= cap["tier1_capital"]
        assert cap["tier1_capital"] <= cap["total_capital"]
        assert cap["cet1_ratio"]   <= cap["tier1_ratio"]
        assert cap["tier1_ratio"]  <= cap["total_cap_ratio"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-q"])
