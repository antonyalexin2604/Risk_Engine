"""
PROMETHEUS — Regulatory Fix Validation Tests
─────────────────────────────────────────────
Validates all seven critical Basel fixes. Run with:
  pytest tests/test_regulatory_fixes.py -v
"""
from __future__ import annotations
import math, inspect
import pytest
import numpy as np
from datetime import date, timedelta


# ─── helpers ──────────────────────────────────────────────────────────────────

def make_trade(ac="IR", notional=5_000_000, days=1825, direction=1):
    from backend.engines.sa_ccr import Trade
    return Trade(
        trade_id=f"T_{ac}_{days}",
        asset_class=ac,
        instrument_type="IRS" if ac == "IR" else ("FXFwd" if ac == "FX" else "EquitySwap"),
        notional=float(notional),
        notional_ccy="USD",
        direction=direction,
        maturity_date=date.today() + timedelta(days=days),
        trade_date=date.today(),
    )


def make_cva_input(cp_id="CP1", ead=100_000_000, M=5.0, pd=0.005):
    from backend.engines.cva import CVAInput
    return CVAInput(
        counterparty_id=cp_id,
        netting_set_id=f"NS_{cp_id}",
        ead=ead,
        pd_1yr=pd,
        lgd_mkt=0.60,
        maturity_years=M,
        sector="Corporates",
        credit_quality="IG",
    )


# ─── Fix 1 + Fix 2: IMM dual-run + EEPE one-year window ──────────────────────

class TestFix1Fix2:
    def setup_method(self):
        from backend.engines.imm import IMMEngine
        self.eng = IMMEngine(use_antithetic=False)

    def test_eepe_one_year_method_exists(self):
        assert hasattr(self.eng, "_eepe_one_year"), "Fix 2: _eepe_one_year must exist on IMMEngine"

    def test_eepe_one_year_clips_beyond_1yr(self):
        """Back-loaded profile: full-grid mean >> first-year average."""
        tg  = np.linspace(5/60, 5.0, 60)                # 5-year grid
        eee = np.linspace(100.0, 1000.0, 60)             # rising
        eepe = self.eng._eepe_one_year(eee, tg)
        full_mean = float(eee.mean())
        assert eepe < full_mean * 0.55, (
            f"Fix 2: EEPE ({eepe:.1f}) must be well below full mean ({full_mean:.1f}) for back-loaded profile")

    def test_eepe_one_year_flat_profile(self):
        tg  = np.linspace(0.1, 1.0, 10)
        eee = np.full(10, 500.0)
        assert abs(self.eng._eepe_one_year(eee, tg) - 500.0) < 1.0

    def test_compute_rwa_uses_stressed_when_higher(self):
        from backend.engines.imm import ExposureProfile
        p = ExposureProfile(
            time_grid=np.array([0.5, 1.0]),
            ee_profile=np.array([100.0, 80.0]),
            eee_profile=np.array([100.0, 100.0]),
            pfe_95=np.array([150.0, 120.0]),
            epe=90.0, eepe=100.0, ead=140.0,
            stressed_eepe=180.0, stressed_ead=252.0,
        )
        rwa = self.eng.compute_rwa(p)
        assert abs(rwa - 252.0 * 12.5 * 0.08) < 1.0, "Fix 1: stressed EAD must bind"

    def test_compute_rwa_uses_current_when_higher(self):
        from backend.engines.imm import ExposureProfile
        p = ExposureProfile(
            time_grid=np.array([0.5, 1.0]),
            ee_profile=np.array([200.0, 180.0]),
            eee_profile=np.array([200.0, 200.0]),
            pfe_95=np.array([250.0, 220.0]),
            epe=190.0, eepe=200.0, ead=280.0,
            stressed_eepe=100.0, stressed_ead=140.0,
        )
        rwa = self.eng.compute_rwa(p)
        assert abs(rwa - 280.0 * 12.5 * 0.08) < 1.0, "Fix 1: current EAD must bind when higher"

    def test_run_for_portfolio_exposes_ead_regulatory(self):
        trades = [make_trade("EQ", days=365)]
        result = self.eng.run_for_portfolio(trades)
        assert "ead_regulatory" in result, "Fix 1: ead_regulatory must be in result"
        assert "stressed_binding" in result, "Fix 1: stressed_binding must be in result"
        assert result["ead_regulatory"] >= result["ead_imm"]


# ─── Fix 3: CVA discount factor ──────────────────────────────────────────────

class TestFix3:
    def test_imm_bank_df_is_one(self):
        from backend.engines.cva import _effective_maturity_discount
        for M in [0.5, 1.0, 3.0, 5.0, 10.0]:
            assert _effective_maturity_discount(M, imm_bank=True) == 1.0, \
                f"Fix 3: IMM DF must be 1.0 for M={M}"

    def test_non_imm_df_formula_matches_basel(self):
        from backend.engines.cva import _effective_maturity_discount
        for M in [1.0, 2.0, 5.0]:
            got      = _effective_maturity_discount(M, imm_bank=False)
            expected = (1.0 - math.exp(-0.05 * M)) / (0.05 * M)
            assert abs(got - expected) < 1e-10, f"Fix 3: non-IMM DF mismatch at M={M}"

    def test_non_imm_uses_5pct_not_market_rate(self):
        """Basel footnote 3: r=5% is hardcoded, not live OIS."""
        from backend.engines.cva import _effective_maturity_discount
        M = 5.0
        df_5pct  = (1.0 - math.exp(-0.05 * M)) / (0.05 * M)
        df_sofr  = (1.0 - math.exp(-0.043 * M)) / (0.043 * M)
        got      = _effective_maturity_discount(M, imm_bank=False)
        assert abs(got - df_5pct) < 1e-10, "Fix 3: must use Basel r=0.05, not live SOFR"
        assert abs(got - df_sofr) > 0.001, "Fix 3: result must differ from SOFR-based calc"

    def test_imm_scva_higher_than_non_imm(self):
        from backend.engines.cva import _scva_c
        inp = make_cva_input()
        rmap = {"CP1": "BBB"}
        sc_imm    = _scva_c(inp, rmap, 0.05, imm_bank=True)
        sc_nonimm = _scva_c(inp, rmap, 0.05, imm_bank=False)
        assert sc_imm > sc_nonimm, "Fix 3: IMM SCVA must be > non-IMM (DF=1 vs DF<1)"

    def test_ba_cva_accepts_imm_flag(self):
        from backend.engines.cva import compute_ba_cva
        inputs = [make_cva_input()]
        cap_imm, _    = compute_ba_cva(inputs, imm_bank=True)
        cap_nonimm, _ = compute_ba_cva(inputs, imm_bank=False)
        assert cap_imm > cap_nonimm, "Fix 3: IMM BA-CVA capital must exceed non-IMM"

    def test_ba_cva_default_imm_is_true(self):
        from backend.engines.cva import compute_ba_cva
        sig = inspect.signature(compute_ba_cva)
        param = sig.parameters.get("imm_bank")
        assert param is not None and param.default is True, \
            "Fix 3: imm_bank default must be True in compute_ba_cva"


# ─── Fix 4: output floor ─────────────────────────────────────────────────────

class TestFix4:
    def _src(self):
        from backend.main import PrometheusRunner
        return inspect.getsource(PrometheusRunner.run_daily)

    def test_rwa_ccr_saccr_variable_exists(self):
        assert "rwa_ccr_saccr" in self._src(), "Fix 4: rwa_ccr_saccr must exist in run_daily"

    def test_floor_base_includes_saccr_not_imm(self):
        src = self._src()
        # rwa_floor_base_sa must sum rwa_ccr_saccr, not rwa_ccr
        floor_section = src[src.find("rwa_floor_base_sa"):][:200]
        assert "rwa_ccr_saccr" in floor_section, \
            "Fix 4: rwa_floor_base_sa must include rwa_ccr_saccr (SA-CCR), not IMM rwa_ccr"

    def test_cva_excluded_from_floor(self):
        src = self._src()
        floor_section = src[src.find("rwa_floor_base_sa"):][:300]
        assert "rwa_cva" not in floor_section, \
            "Fix 4: rwa_cva must NOT appear in rwa_floor_base_sa (CAP10 FAQ1)"

    def test_floor_factor_is_72_5_pct(self):
        assert "0.725" in self._src(), "Fix 4: floor factor must be 0.725 (RBC20.11)"

    def test_total_rwa_uses_max(self):
        assert "max(rwa_total_pre_floor, rwa_floor)" in self._src(), \
            "Fix 4: rwa_total = max(pre_floor, floor)"

    def test_capital_summary_exposes_floor_base(self):
        assert "rwa_floor_base_sa" in self._src(), \
            "Fix 4: rwa_floor_base_sa must be exposed in capital_summary"


# ─── Fix 5: FRTB LH + 60d rolling IMCC ──────────────────────────────────────

class TestFix5:
    def setup_method(self):
        from backend.engines.frtb import IMACalculator, FRTBConfig, FRTBEngine
        self.ima = IMACalculator(FRTBConfig())
        self.eng = FRTBEngine()

    def test_csr_ns_lh_is_120(self):
        assert self.ima.LIQUIDITY_HORIZONS.get("CSR_NS") == 120, \
            "Fix 5a: CSR_NS must be LH=120 (was 40)"

    def test_csr_sec_lh_is_120(self):
        assert self.ima.LIQUIDITY_HORIZONS.get("CSR_SEC") == 120, \
            "Fix 5a: CSR_SEC must be LH=120 (was 60)"

    def test_girr_lh_unchanged(self):
        assert self.ima.LIQUIDITY_HORIZONS.get("GIRR") == 10, "GIRR must stay 10"

    def test_fx_lh_unchanged(self):
        assert self.ima.LIQUIDITY_HORIZONS.get("FX") == 10, "FX must stay 10"

    def test_csr_ns_ig_lh_is_60(self):
        assert self.ima.LIQUIDITY_HORIZONS.get("CSR_NS_IG") == 60, \
            "Fix 5a: CSR_NS_IG must be 60 (j=4 bucket)"

    def test_lh_buckets_values(self):
        assert self.ima.LH_BUCKETS == [10, 20, 40, 60, 120], \
            "LH_BUCKETS must be [10,20,40,60,120] per MAR33.4"

    def test_ima_register_on_engine(self):
        assert hasattr(self.eng, "ima_register"), "Fix 5b: FRTBEngine must have ima_register"

    def test_mc_floor_is_1_5(self):
        from backend.engines.frtb import IMACapitalRegister
        reg = IMACapitalRegister()
        assert reg.mc >= 1.5, f"Fix 5b: mc floor is 1.5, got {reg.mc}"

    def test_5_exceptions_gives_mc_1_90(self):
        from backend.engines.frtb import IMACapitalRegister
        reg = IMACapitalRegister()
        reg.set_exceptions(5)
        assert abs(reg.mc - 1.90) < 1e-9, f"5 exceptions → mc=1.90, got {reg.mc}"

    def test_today_es_binds_when_highest(self):
        from backend.engines.frtb import IMACapitalRegister
        reg = IMACapitalRegister()
        for _ in range(60): reg.push(100.0)
        imcc, binding = reg.regulatory_imcc(500.0)
        assert imcc == 500.0 and binding == "today"

    def test_60d_avg_binds_after_es_drop(self):
        from backend.engines.frtb import IMACapitalRegister
        reg = IMACapitalRegister()
        for _ in range(60): reg.push(400.0)
        imcc, binding = reg.regulatory_imcc(50.0)
        expected = reg.mc * 400.0
        assert abs(imcc - expected) < 1.0 and binding == "60d_avg"

    def test_persistence_roundtrip(self):
        from backend.engines.frtb import IMACapitalRegister
        reg = IMACapitalRegister()
        for v in [100.0, 200.0, 300.0]: reg.push(v)
        reg.set_exceptions(7)
        reg2 = IMACapitalRegister.from_dict(reg.to_dict())
        assert abs(reg2.avg_60d - reg.avg_60d) < 1e-9
        assert reg2._bt_ex == 7


# ─── Fix 6: G-SIB capital ────────────────────────────────────────────────────

class TestFix6:
    def test_surcharge_by_bucket(self):
        from backend.engines.gsib_capital import GSIBProfile
        for bucket, surcharge in {1:0.010,2:0.015,3:0.020,4:0.025,5:0.035}.items():
            g = GSIBProfile(gsib_bucket=bucket)
            assert abs(g.gsib_surcharge - surcharge) < 1e-9, \
                f"Bucket {bucket}: expected {surcharge:.1%}, got {g.gsib_surcharge:.1%}"

    def test_cet1_min_includes_surcharge(self):
        from backend.engines.gsib_capital import GSIBProfile
        g = GSIBProfile(gsib_bucket=2, ccyb_rate=0.01)
        assert abs(g.total_cet1_minimum - (0.045+0.025+0.01+0.015)) < 1e-9

    def test_three_tier_keys_present(self):
        from backend.engines.gsib_capital import compute_capital_adequacy, DEFAULT_GSIB
        r = compute_capital_adequacy(500e9, gsib=DEFAULT_GSIB)
        for k in ["cet1_capital","at1_capital","tier2_capital","tier1_capital","total_capital"]:
            assert k in r, f"Fix 6: '{k}' must be in result"

    def test_tier_consistency(self):
        from backend.engines.gsib_capital import compute_capital_adequacy, DEFAULT_GSIB
        r = compute_capital_adequacy(400e9, gsib=DEFAULT_GSIB)
        assert abs(r["tier1_capital"] - (r["cet1_capital"]+r["at1_capital"])) < 1.0
        assert abs(r["total_capital"] - (r["tier1_capital"]+r["tier2_capital"])) < 1.0

    def test_mda_trigger_fires(self):
        from backend.engines.gsib_capital import compute_capital_adequacy, GSIBProfile, CapitalBase
        gsib = GSIBProfile(gsib_bucket=1, ccyb_rate=0.0)  # min CET1 = 8.0%
        rwa  = 100e9
        cap  = CapitalBase(cet1_actual=rwa*0.079, at1_actual=rwa*0.015, tier2_actual=rwa*0.020)
        r    = compute_capital_adequacy(rwa, gsib=gsib, capital=cap)
        assert r["mda_trigger"] is True

    def test_no_breach_well_capitalised(self):
        from backend.engines.gsib_capital import compute_capital_adequacy, DEFAULT_GSIB
        r = compute_capital_adequacy(500e9, gsib=DEFAULT_GSIB)
        assert r["any_breach"] is False

    def test_gsib_module_imported_in_main(self):
        from backend.main import compute_capital_adequacy
        assert callable(compute_capital_adequacy)


# ─── Fix 7: TtC PD calibration ───────────────────────────────────────────────

class TestFix7:
    def test_lra_pd_ttc_exists(self):
        from backend.data_sources.credit_calibration import LRA_PD_TTC
        for r in ["AAA","AA","A","BBB","BB","B","CCC"]:
            assert r in LRA_PD_TTC, f"LRA_PD_TTC missing '{r}'"

    def test_pd_from_rating_ttc_exists(self):
        from backend.data_sources.credit_calibration import pd_from_rating_ttc
        assert callable(pd_from_rating_ttc)

    def test_pd_floor_applied(self):
        from backend.data_sources.credit_calibration import pd_from_rating_ttc
        assert pd_from_rating_ttc("AAA") >= 0.0003, "CRE31.17: PD floor 3bp"

    def test_pd_monotone_by_rating(self):
        from backend.data_sources.credit_calibration import pd_from_rating_ttc
        ratings = ["AAA","AA","A","BBB","BB","B","CCC"]
        pds     = [pd_from_rating_ttc(r) for r in ratings]
        for i in range(1, len(pds)):
            assert pds[i] >= pds[i-1], f"{ratings[i]} PD must be >= {ratings[i-1]} PD"

    def test_ttc_stable_vs_pit_spike(self):
        from backend.data_sources.credit_calibration import pd_from_rating_ttc, LRA_PD_TTC
        ttc = pd_from_rating_ttc("BBB", pit_pd=0.05)
        assert ttc < 0.05, "Fix 7: TtC PD must be < stressed PiT spike"
        assert ttc > LRA_PD_TTC["BBB"], "Fix 7: TtC must be > LRA when PiT elevated"

    def test_horizon_survival_probability(self):
        from backend.data_sources.credit_calibration import pd_from_rating_ttc
        p1 = pd_from_rating_ttc("BB", horizon_years=1.0)
        p5 = pd_from_rating_ttc("BB", horizon_years=5.0)
        expected = 1.0 - (1.0 - p1)**5
        assert abs(p5 - expected) < 0.001, "Fix 7: 5yr PD must follow survival-prob formula"

    def test_airb_blended_pd_leans_ttc(self):
        from backend.engines.a_irb import ImpliedPDCalibration
        from backend.data_sources.credit_calibration import LRA_PD_TTC
        cal    = ImpliedPDCalibration()
        result = cal.blended_pd(0.0021, 0.0100, rating="BBB")
        lra    = LRA_PD_TTC["BBB"]
        assert abs(result - lra) < abs(result - 0.0100), \
            "Fix 7 (CRE36.77): blended_pd must be closer to TtC/LRA than to PiT"


# ─── Cross-cutting: smoke test ────────────────────────────────────────────────

class TestIntegrationSmoke:
    def test_all_modules_import_cleanly(self):
        import backend.engines.imm
        import backend.engines.cva
        import backend.engines.frtb
        import backend.engines.gsib_capital
        import backend.data_sources.credit_calibration
        import backend.main

    def test_imm_pipeline_end_to_end(self):
        from backend.engines.imm import IMMEngine
        eng    = IMMEngine(use_antithetic=False)
        trades = [make_trade("IR"), make_trade("FX", days=730, direction=-1)]
        result = eng.run_for_portfolio(trades)
        assert result["ead_regulatory"] == max(result["ead_imm"], result["stressed_ead"])
        assert result["rwa_imm"] > 0

    def test_gsib_capital_in_main_run(self):
        """Fix 6: run_daily must produce G-SIB enriched capital_summary."""
        from backend.main import PrometheusRunner
        src = inspect.getsource(PrometheusRunner.run_daily)
        assert "gsib_surcharge" in src or "compute_capital_adequacy" in src, \
            "Fix 6: run_daily must use G-SIB capital framework"


# ─── Fix 1 (extended) + Fix B: GFC vol calibration floors ────────────────────

class TestGFCVolCalibration:
    """Fix B: GFC stressed vols must survive the calibration pipeline."""

    GFC_FLOORS = {
        "EQ":    ("stressed_vol",       0.38),
        "IR":    ("ir_stressed_vol",     0.020),
        "FX":    ("fx_stressed_vol",     0.18),
        "CR":    ("cr_stressed_vol",     0.65),
        "CMDTY": ("cmdty_stressed_vol",  0.58),
    }

    def _apply_calibration(self):
        from backend.engines.imm import MarketParams
        from backend.data_sources.calibration import calibrate_and_apply
        p = MarketParams()
        calibrate_and_apply(p)
        return p

    def test_eq_stressed_vol_gfc_floor_survives_calibration(self):
        p = self._apply_calibration()
        assert p.stressed_vol >= 0.38, (
            f"EQ stressed vol {p.stressed_vol:.3f} < GFC floor 0.38 — calibration overrode Fix B")

    def test_ir_stressed_vol_gfc_floor_survives_calibration(self):
        p = self._apply_calibration()
        assert p.ir_stressed_vol >= 0.020, (
            f"IR stressed vol {p.ir_stressed_vol:.4f} < GFC floor 0.020 — calibration overrode Fix B")

    def test_fx_stressed_vol_gfc_floor_survives_calibration(self):
        p = self._apply_calibration()
        assert p.fx_stressed_vol >= 0.18, (
            f"FX stressed vol {p.fx_stressed_vol:.3f} < GFC floor 0.18")

    def test_cr_stressed_vol_gfc_floor_survives_calibration(self):
        p = self._apply_calibration()
        assert p.cr_stressed_vol >= 0.65, (
            f"CR stressed vol {p.cr_stressed_vol:.3f} < GFC floor 0.65")

    def test_cmdty_stressed_vol_gfc_floor_survives_calibration(self):
        p = self._apply_calibration()
        assert p.cmdty_stressed_vol >= 0.58, (
            f"CMDTY stressed vol {p.cmdty_stressed_vol:.3f} < GFC floor 0.58")

    def test_stressed_vol_always_gte_base_vol(self):
        """CRE53: stressed must be >= base for all asset classes."""
        p = self._apply_calibration()
        pairs = [
            ("EQ",    p.volatility,  p.stressed_vol),
            ("IR",    p.ir_vol,      p.ir_stressed_vol),
            ("FX",    p.fx_vol,      p.fx_stressed_vol),
            ("CR",    p.cr_vol,      p.cr_stressed_vol),
            ("CMDTY", p.cmdty_vol,   p.cmdty_stressed_vol),
        ]
        for ac, base, stress in pairs:
            assert stress >= base, (
                f"{ac}: stressed ({stress:.4f}) < base ({base:.4f}) — violates CRE53 stress requirement")

    def test_regulatory_ead_uses_max_after_calibration(self):
        """Fix 1 + Fix B: EAD_regulatory = max(current, stressed) with GFC vols active."""
        from datetime import date, timedelta
        import backend.engines.imm as _imm_mod
        from backend.engines.imm import IMMEngine, MarketParams
        from backend.data_sources.calibration import calibrate_and_apply
        from backend.engines.sa_ccr import Trade

        # Apply GFC-calibrated params into module DEFAULT_PARAMS in place —
        # mirrors how run_daily() patches the live module globals at startup.
        _original = _imm_mod.DEFAULT_PARAMS
        p = MarketParams()
        calibrate_and_apply(p)
        _imm_mod.DEFAULT_PARAMS = p

        try:
            eng = IMMEngine(use_antithetic=False)
            today = date.today()
            trades = [
                Trade(trade_id="T_IR", asset_class="IR", instrument_type="IRS",
                      notional=50_000_000, notional_ccy="USD", direction=1,
                      maturity_date=today+timedelta(days=3650), trade_date=today,
                      current_mtm=100_000, fixed_rate=0.035, reference_period=10.0),
            ]
            result = eng.run_for_portfolio(trades)
            assert result["ead_regulatory"] == max(result["ead_imm"], result["stressed_ead"]), \
                "Fix 1: EAD_regulatory must equal max(current, stressed)"
            assert result["stressed_ead"] > result["ead_imm"], \
                "With GFC vols active, stressed EAD should exceed current EAD for IR"
        finally:
            _imm_mod.DEFAULT_PARAMS = _original  # restore to avoid test pollution


# ─── CRE53 §margined EEPE — path-level CSA collateral tests ──────────────────

class TestMargined_EEPE_PathLevel:
    """CRE53 §margined EEPE: VM/IM path-level collateral simulation."""

    def setup_method(self):
        from backend.engines.imm import IMMEngine
        from backend.engines.sa_ccr import NettingSet
        from datetime import date, timedelta
        from backend.engines.sa_ccr import Trade
        self.eng = IMMEngine(use_antithetic=False)
        today = date.today()
        self.trades = [
            Trade(trade_id="T_IR", asset_class="IR", instrument_type="IRS",
                  notional=50_000_000, notional_ccy="USD", direction=1,
                  maturity_date=today+timedelta(days=1825), trade_date=today,
                  current_mtm=200_000, fixed_rate=0.035, reference_period=5.0),
            Trade(trade_id="T_EQ", asset_class="EQ", instrument_type="EquitySwap",
                  notional=20_000_000, notional_ccy="USD", direction=1,
                  maturity_date=today+timedelta(days=1095), trade_date=today,
                  current_mtm=80_000, underlying_security_id="SPX Index"),
        ]
        self.ns = NettingSet(
            netting_id="NS_CSA_TEST", counterparty_id="CP_A", trades=self.trades,
            initial_margin=1_500_000, variation_margin=280_000,
            threshold=500_000, mta=100_000, has_csa=True, mpor_days=10)
        self.ns.haircut = 0.02

    def test_simulate_vm_paths_shape(self):
        """VM paths shape must match exposure_paths (N, T)."""
        import numpy as np
        exp = np.random.rand(100, 52) * 1e6
        vm  = self.eng._simulate_vm_paths(exp, threshold=500_000, mta=100_000,
                                           haircut=0.02, mpor_days=10)
        assert vm.shape == exp.shape, "VM paths must match exposure shape"

    def test_simulate_vm_paths_mpor_lag(self):
        """VM at t=0 must be zero — lag not yet elapsed."""
        import numpy as np
        exp = np.ones((50, 52)) * 2_000_000   # always above threshold
        vm  = self.eng._simulate_vm_paths(exp, threshold=0, mta=0,
                                           haircut=0.0, mpor_days=10)
        assert vm[:, 0].sum() == 0.0, "VM at t=0 must be zero (MPOR lag)"

    def test_simulate_vm_paths_below_threshold_is_zero(self):
        """No VM should be called when exposure < threshold + MTA."""
        import numpy as np
        exp = np.ones((50, 52)) * 100_000     # below threshold 500K
        vm  = self.eng._simulate_vm_paths(exp, threshold=500_000, mta=100_000,
                                           haircut=0.02, mpor_days=10)
        assert vm.sum() == 0.0, "No VM when exposure below threshold"

    def test_simulate_im_paths_fixed(self):
        """Fixed IM must appear as constant at all nodes."""
        import numpy as np
        exp = np.random.rand(50, 52) * 1e6
        im  = self.eng._simulate_im_paths(exp, im_fixed=1_500_000, im_fraction=0.0)
        assert im.shape == exp.shape
        assert abs(im.mean() - 1_500_000) < 1.0, "Fixed IM must be constant 1.5M"

    def test_margined_ead_less_than_gross(self):
        """Path-level margined EAD must be below gross EAD (collateral reduces exposure)."""
        profile = self.eng.compute_exposure_profile(self.trades)
        ead_csa, pct, _, _, method = self.eng.compute_csa_ead_regulatory(profile, self.ns)
        assert ead_csa < profile.ead, (
            f"Margined EAD ({ead_csa:.0f}) must be < gross EAD ({profile.ead:.0f})")
        assert pct > 0, "CSA reduction must be positive"

    def test_method_trace_is_path_level(self):
        """With exposure_paths available, method must be CRE53-PATH-LEVEL."""
        profile = self.eng.compute_exposure_profile(self.trades)
        assert profile.exposure_paths is not None
        _, _, _, _, method = self.eng.compute_csa_ead_regulatory(profile, self.ns)
        assert method == "CRE53-PATH-LEVEL", (
            f"Expected CRE53-PATH-LEVEL, got {method}")

    def test_tier2_fallback_when_no_paths(self):
        """Without exposure_paths, method falls back to CRE53-APPROX-FALLBACK."""
        profile = self.eng.compute_exposure_profile(self.trades)
        profile.exposure_paths = None   # simulate memory-saving mode
        _, _, _, _, method = self.eng.compute_csa_ead_regulatory(profile, self.ns)
        assert method == "CRE53-APPROX-FALLBACK", (
            f"Expected CRE53-APPROX-FALLBACK fallback, got {method}")

    def test_im_reduces_net_exposure(self):
        """Higher IM should produce lower margined EAD."""
        import copy
        from backend.engines.sa_ccr import NettingSet
        from datetime import date
        profile = self.eng.compute_exposure_profile(self.trades)
        # Low IM netting set
        ns_low = copy.copy(self.ns); ns_low.initial_margin = 100_000
        ns_low.haircut = 0.02
        ead_low, _, _, _, _ = self.eng.compute_csa_ead_regulatory(profile, ns_low)
        # High IM netting set
        ns_high = copy.copy(self.ns); ns_high.initial_margin = 5_000_000
        ns_high.haircut = 0.02
        ead_high, _, _, _, _ = self.eng.compute_csa_ead_regulatory(profile, ns_high)
        assert ead_high <= ead_low, (
            f"Higher IM ({ead_high:.0f}) should give lower EAD than low IM ({ead_low:.0f})")

    def test_simulate_margined_eepe_standalone(self):
        """simulate_margined_eepe returns ExposureProfile with margined fields."""
        m_profile = self.eng.simulate_margined_eepe(self.trades, self.ns, stressed=False)
        assert m_profile.margined_eepe > 0, "margined_eepe must be positive"
        assert m_profile.margined_ead  > 0, "margined_ead must be positive"
        assert m_profile.margined_ead < m_profile.ead * 2, \
            "margined_ead should be in a plausible range vs gross"

    def test_run_for_portfolio_exposes_margined_keys(self):
        """run_for_portfolio must expose eepe_margined, ead_margined, csa_method."""
        result = self.eng.run_for_portfolio(self.trades, netting_set=self.ns)
        for key in ["eepe_margined", "ead_margined", "csa_method", "csa_reduction_pct"]:
            assert key in result, f"run_for_portfolio must expose '{key}'"
        assert result["csa_method"] == "CRE53-PATH-LEVEL"
        assert result["ead_margined"] < result["ead_imm"], \
            "ead_margined must be less than gross ead_imm"
        assert 0 < result["csa_reduction_pct"] < 100, \
            "CSA reduction must be between 0% and 100%"

    def test_high_threshold_gives_less_relief(self):
        """Higher threshold means less VM is called → less CSA relief."""
        import copy
        profile = self.eng.compute_exposure_profile(self.trades)
        ns_low_th  = copy.copy(self.ns); ns_low_th.threshold  = 0;         ns_low_th.haircut  = 0.02
        ns_high_th = copy.copy(self.ns); ns_high_th.threshold = 5_000_000; ns_high_th.haircut = 0.02
        ead_low_th,  _, _, _, _ = self.eng.compute_csa_ead_regulatory(profile, ns_low_th)
        ead_high_th, _, _, _, _ = self.eng.compute_csa_ead_regulatory(profile, ns_high_th)
        assert ead_high_th >= ead_low_th, (
            f"Higher threshold ({ead_high_th:.0f}) should give >= EAD vs low threshold ({ead_low_th:.0f})")
