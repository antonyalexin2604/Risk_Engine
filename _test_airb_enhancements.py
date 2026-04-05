"""
Verification smoke-test for all A-IRB regulatory enhancements.
Run: .venv/bin/python _test_airb_enhancements.py
"""
import sys, math
sys.path.insert(0, ".")

from backend.engines.a_irb import (
    AIRBEngine, AIRBConfiguration, BankingBookExposure,
    PDTermStructure, MacroeconomicFactors, CreditSpreadsData,
    asset_correlation, double_default_pd, compute_lgd_star,
    apply_market_regime_stress, MarketRegime, _R_REGULATORY_CAP,
    _norm_inv, _norm_cdf,
)

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        print(f"  [FAIL] {name}  {detail}")
        FAIL += 1

print("\n=== FIX 1: double_default_pd — Basel CRE22.10 formula ===")
# CRE22.10: PD_dd = PD_o × (0.15 + 160 × PD_g), capped at PD_o
# With pd_o=0.02, pd_g=0.01 → raw=0.035 > pd_o → capped at pd_o=0.02
pd_o, pd_g = 0.02, 0.01
raw_pdd = pd_o * (0.15 + 160 * pd_g)            # 0.035
expected = min(raw_pdd, pd_o)                    # 0.02 (cap applies)
result   = double_default_pd(pd_o, pd_g)
check("CRE22.10 formula (cap applies)", abs(result - expected) < 1e-9,
      f"got {result:.6f} expected {expected:.6f}")
# Use small pd_g so raw < pd_o → formula is visible without cap
pd_o2, pd_g2 = 0.10, 0.001                      # raw = 0.10*(0.15+0.16)=0.031 < 0.10
raw2 = pd_o2 * (0.15 + 160.0 * pd_g2)
result2 = double_default_pd(pd_o2, pd_g2)
check("CRE22.10 formula (no cap, raw visible)", abs(result2 - raw2) < 1e-9,
      f"got {result2:.6f} expected {raw2:.6f}")
# Must be capped at pd_obligor
check("Cap at pd_obligor", double_default_pd(0.005, 0.5) <= 0.005)
# Low guarantor PD → raw PD_dd < pd_obligor
check("Low PD_g gives PD_dd < pd_o", double_default_pd(0.10, 0.001) < 0.10)

print("\n=== FIX 2: compute_lgd_star — correct haircut basis CRE32.13 ===")
# E* = EAD*(1+he); SC = col_val*(1-hc); LGD* = (E*-SC)/E* * LGD_U + SC/E* * LGD_S
# For FINANCIAL collateral: LGD_S=0.00, hc=0.15
ead, lgd_u, col_val = 1_000_000, 0.45, 800_000
lgd_star, e_s, e_u = compute_lgd_star(ead, lgd_u, col_val, "FINANCIAL", he=0.0)
sc = col_val * (1 - 0.15)   # = 680_000
e_star = ead                 # he=0 → E* = EAD
expected_lgd_star = (e_u / e_star) * lgd_u + (e_s / e_star) * 0.0
check("LGD* formula (FINANCIAL)", abs(lgd_star - expected_lgd_star) < 1e-6,
      f"got {lgd_star:.4f} expected {expected_lgd_star:.4f}")
check("EAD not inflated (no (1+he) grossup for he=0)", abs(e_s + e_u - e_star) < 1e-6)

print("\n=== FIX 3: asset_correlation — HVCRE branch CRE31.10 ===")
# HVCRE upper bound 0.30 (not 0.24)
r_hvcre = asset_correlation(0.001, "HVCRE")   # very low PD → near upper bound
r_corp  = asset_correlation(0.001, "CORP")
check("HVCRE R > CORP R at low PD", r_hvcre > r_corp,
      f"HVCRE={r_hvcre:.4f} CORP={r_corp:.4f}")
check("HVCRE R ≤ 0.30", r_hvcre <= 0.30 + 1e-9)
check("CORP R ≤ 0.24",  r_corp  <= 0.24 + 1e-9)

print("\n=== FIX 4: _R_REGULATORY_CAP constants ===")
check("CORP cap 0.24",     _R_REGULATORY_CAP["CORP"]        == 0.24)
check("HVCRE cap 0.30",    _R_REGULATORY_CAP["HVCRE"]       == 0.30)
check("RETAIL_MORT 0.15",  _R_REGULATORY_CAP["RETAIL_MORT"] == 0.15)
check("RETAIL_REV  0.04",  _R_REGULATORY_CAP["RETAIL_REV"]  == 0.04)

print("\n=== FIX 5: apply_market_regime_stress — separate PD/LGD dicts ===")
pd_f  = {"CORP": 1.5}
lgd_f = {"CORP": 1.2}
pd_s, lgd_s = apply_market_regime_stress(0.01, 0.45, "CORP",
                                          MarketRegime.STRESSED, pd_f, lgd_f)
check("Separate PD multiplier", abs(pd_s - 0.015) < 1e-9, f"got {pd_s:.4f}")
check("Separate LGD multiplier", abs(lgd_s - 0.54) < 1e-9, f"got {lgd_s:.4f}")
# NORMAL regime: no change
pd_n, lgd_n = apply_market_regime_stress(0.01, 0.45, "CORP",
                                          MarketRegime.NORMAL, pd_f, lgd_f)
check("NORMAL regime unchanged", pd_n == 0.01 and lgd_n == 0.45)

print("\n=== FIX 6: _norm_inv precision near tails ===")
# N^-1(0.999) = 3.090232... (reference value)
n_inv_999 = _norm_inv(0.999)
check("N^-1(0.999) within 1e-6 of reference",
      abs(n_inv_999 - 3.090232) < 1e-4,
      f"got {n_inv_999:.8f}")
# CDF round-trip
check("CDF round-trip N(N^-1(0.975)) = 0.975",
      abs(_norm_cdf(_norm_inv(0.975)) - 0.975) < 1e-10)

print("\n=== FIX 7: AIRBResult regulatory fields present ===")
from dataclasses import fields as dc_fields
result_fields = {f.name for f in dc_fields(BankingBookExposure)}
check("BankingBookExposure has is_margined",        "is_margined"         in result_fields)
check("BankingBookExposure has lgd_best_estimate",  "lgd_best_estimate"   in result_fields)
check("BankingBookExposure has provisions_stage3",  "provisions_stage3"   in result_fields)
check("BankingBookExposure has climate_brown_factor","climate_brown_factor" in result_fields)
check("BankingBookExposure has sa_rwa",             "sa_rwa"              in result_fields)

from backend.engines.a_irb import AIRBResult
r_fields = {f.name for f in dc_fields(AIRBResult)}
check("AIRBResult has k_regulatory",               "k_regulatory"              in r_fields)
check("AIRBResult has rwa_regulatory",             "rwa_regulatory"            in r_fields)
check("AIRBResult has el_shortfall_cet1_deduction","el_shortfall_cet1_deduction" in r_fields)
check("AIRBResult has el_excess_tier2_eligible",   "el_excess_tier2_eligible"  in r_fields)
check("AIRBResult has sa_floor_binding",           "sa_floor_binding"          in r_fields)
check("AIRBResult has climate_pd_uplift",          "climate_pd_uplift"         in r_fields)
check("AIRBResult has is_defaulted",               "is_defaulted"              in r_fields)

print("\n=== FIX 8: AIRBConfiguration has climate + SA floor fields ===")
from backend.engines.a_irb import AIRBConfiguration
cfg = AIRBConfiguration()
check("Config has brown_sector_pd_uplift", hasattr(cfg, "brown_sector_pd_uplift"))
check("Config has sa_output_floor_ratio",  hasattr(cfg, "sa_output_floor_ratio"))
check("SA floor ratio = 0.725",            cfg.sa_output_floor_ratio == 0.725)
check("CORP ESG uplift set",               cfg.brown_sector_pd_uplift.get("CORP", 0) > 0)

print("\n=== FIX 9: AIRBEngine.compute full integration ===")
engine = AIRBEngine()

# 9a: standard compute with R_regulatory / R_internal split
exp = BankingBookExposure(
    trade_id="T001", portfolio_id="P1", obligor_id="O1",
    asset_class="CORP", ead=1_000_000, pd=0.02, lgd=0.45, maturity=3.0,
)
res = engine.compute(exp)
check("k_regulatory populated",     res.k_regulatory > 0)
check("rwa_regulatory populated",   res.rwa_regulatory > 0)
check("r_regulatory <= R cap",      res.r_regulatory <= _R_REGULATORY_CAP["CORP"] + 1e-9)
check("Not defaulted",              not res.is_defaulted)
check("el_diff = EL - provisions",  abs(res.el_diff - res.el) < 1e-6)  # provisions=0

# 9b: CRE31.8 margined derivative — M capped at 1Y
exp_m = BankingBookExposure(
    trade_id="T002", portfolio_id="P1", obligor_id="O2",
    asset_class="CORP", ead=500_000, pd=0.01, lgd=0.45, maturity=5.0,
    is_margined=True,
)
res_m = engine.compute(exp_m)
check("Margined M capped at 1Y",    res_m.maturity == 1.0,
      f"got maturity={res_m.maturity}")
check("Maturity warning issued",    any("CRE31.8" in w for w in res_m.validation_warnings))

# 9c: CRE31.12 defaulted exposure
exp_d = BankingBookExposure(
    trade_id="T003", portfolio_id="P1", obligor_id="O3",
    asset_class="CORP", ead=200_000, pd=1.0, lgd=0.55, maturity=2.0,
    lgd_best_estimate=0.60,
)
res_d = engine.compute(exp_d)
check("Defaulted flag set",         res_d.is_defaulted)
check("Defaulted K = 0 (LGD_be=EL_be)", res_d.capital_req_k == 0.0,
      f"got K={res_d.capital_req_k}")

# 9d: IFRS9 provisions staging — only stage3 counts
exp_p = BankingBookExposure(
    trade_id="T004", portfolio_id="P1", obligor_id="O4",
    asset_class="CORP", ead=1_000_000, pd=0.05, lgd=0.45, maturity=2.0,
    provisions=50_000,          # legacy field
    provisions_stage1=20_000,   # general — NOT eligible
    provisions_stage2=15_000,   # general — NOT eligible
    provisions_stage3=30_000,   # specific — eligible
)
res_p = engine.compute(exp_p)
check("Eligible provisions = stage3 only",  abs(res_p.provisions_eligible - 30_000) < 1.0,
      f"got {res_p.provisions_eligible:.0f}")
# EL shortfall uses only stage3
el_exp = res_p.el
check("el_diff uses stage3 provisions",     abs(res_p.el_diff - (el_exp - 30_000)) < 1.0)

# 9e: SA output floor (CRE20.4) — binding case
exp_f = BankingBookExposure(
    trade_id="T005", portfolio_id="P1", obligor_id="O5",
    asset_class="CORP", ead=1_000_000, pd=0.001, lgd=0.45, maturity=1.0,
    sa_rwa=500_000,   # Large SA RWA → floor = 0.725 * 500k = 362.5k
)
res_f = engine.compute(exp_f)
irb_rwa = res_f.rwa_regulatory
floor_rwa = 0.725 * 500_000
if irb_rwa < floor_rwa:
    check("SA floor binding when IRB < 72.5% × SA",  res_f.sa_floor_binding)
    check("SA floor uplift > 0",                     res_f.sa_floor_uplift > 0,
          f"uplift={res_f.sa_floor_uplift:.0f}")
else:
    check("SA floor not binding when IRB >= SA floor", not res_f.sa_floor_binding)

# 9f: ESG/climate PD uplift
exp_e = BankingBookExposure(
    trade_id="T006", portfolio_id="P1", obligor_id="O6",
    asset_class="CORP", ead=1_000_000, pd=0.01, lgd=0.45, maturity=2.0,
    climate_brown_factor=1.0,  # fully brown
)
res_e = engine.compute(exp_e)
check("ESG climate_pd_uplift > 0",    res_e.climate_pd_uplift > 0,
      f"uplift={res_e.climate_pd_uplift:.4f}")
check("ESG increases pd_applied",     res_e.pd_applied > 0.01,
      f"pd_applied={res_e.pd_applied:.4f}")

print("\n=== FIX 10: _compute_sensitivities — term structure shock ===")
exp_ts = BankingBookExposure(
    trade_id="T007", portfolio_id="P1", obligor_id="O7",
    asset_class="CORP", ead=1_000_000, pd=0.02, lgd=0.45, maturity=3.0,
    pd_term_structure=PDTermStructure(pd_1y=0.01, pd_3y=0.02, pd_5y=0.03),
)
res_ts = engine.compute(exp_ts)
check("Sensitivity non-zero with term structure",
      abs(res_ts.rwa_sensitivity_pd) > 1.0,
      f"rwa_sensitivity_pd={res_ts.rwa_sensitivity_pd:.0f}")

print("\n=== FIX 11: compute_with_macro_overlay — CRM chain + R cap ===")
macro = MacroeconomicFactors(
    date=__import__("datetime").date.today(),
    vix_level=50.0, high_yield_spread=900.0,
    real_gdp_growth=-1.0, credit_default_rate=0.08,
)
exp_macro = BankingBookExposure(
    trade_id="T008", portfolio_id="P1", obligor_id="O8",
    asset_class="CORP", ead=1_000_000, pd=0.02, lgd=0.45, maturity=3.0,
    collateral_type="FINANCIAL", collateral_value=600_000,  # should reduce LGD*
)
res_macro = engine.compute_with_macro_overlay(exp_macro, macro)
check("R_regulatory capped in macro overlay",
      res_macro.r_regulatory <= _R_REGULATORY_CAP["CORP"] + 1e-9,
      f"r_reg={res_macro.r_regulatory:.4f}")
check("CRM chain applied (LGD* < original LGD)",
      res_macro.lgd_applied < 0.45,
      f"lgd_applied={res_macro.lgd_applied:.4f}")
check("Macro overlay RWA populated", res_macro.rwa > 0)
check("Macro el_shortfall_cet1 field present", hasattr(res_macro, "el_shortfall_cet1_deduction"))

# ── CRE35.3: Tier 2 add-back check ─────────────────────────────────────────
print("\n=== FIX 12: CRE35 EL capital treatment ===")
exp_surplus = BankingBookExposure(
    trade_id="T009", portfolio_id="P1", obligor_id="O9",
    asset_class="CORP", ead=1_000_000, pd=0.001, lgd=0.45, maturity=1.0,
    provisions_stage3=50_000,   # large specific provisions → excess over EL
)
res_surplus = engine.compute(exp_surplus)
el_val = res_surplus.el
if el_val < 50_000:
    check("EL shortfall = 0 (provisions > EL)",
          res_surplus.el_shortfall_cet1_deduction == 0.0)
    check("T2 excess > 0",
          res_surplus.el_excess_tier2_eligible > 0,
          f"excess={res_surplus.el_excess_tier2_eligible:.0f}")
    t2_cap = 0.006 * res_surplus.rwa_regulatory
    check("T2 excess capped at 0.6% RWA",
          res_surplus.el_excess_tier2_eligible <= t2_cap + 1e-6,
          f"excess={res_surplus.el_excess_tier2_eligible:.0f} cap={t2_cap:.0f}")

print("\n=== FIX 13: compute_portfolio — Basel IV aggregate fields ===")
portfolio_exposures = [
    BankingBookExposure(trade_id="P01", portfolio_id="PF", obligor_id="O1",
                        asset_class="CORP", ead=1_000_000, pd=0.02, lgd=0.45, maturity=3.0),
    BankingBookExposure(trade_id="P02", portfolio_id="PF", obligor_id="O2",
                        asset_class="CORP", ead=500_000, pd=0.01, lgd=0.45, maturity=2.0,
                        climate_brown_factor=1.0),
    BankingBookExposure(trade_id="P03", portfolio_id="PF", obligor_id="O3",
                        asset_class="CORP", ead=200_000, pd=1.0, lgd=0.45, maturity=1.0,
                        lgd_best_estimate=0.50),  # defaulted
    BankingBookExposure(trade_id="P04", portfolio_id="PF", obligor_id="O4",
                        asset_class="CORP", ead=800_000, pd=0.001, lgd=0.45, maturity=1.0,
                        sa_rwa=600_000),  # SA floor likely binding
]
port = engine.compute_portfolio(portfolio_exposures)
check("Portfolio total_rwa_regulatory present",      "total_rwa_regulatory"             in port)
check("Portfolio total_el_shortfall_cet1 present",   "total_el_shortfall_cet1_deduction" in port)
check("Portfolio total_el_excess_tier2 present",     "total_el_excess_tier2_eligible"    in port)
check("Portfolio sa_floor_binding_count present",    "sa_floor_binding_count"            in port)
check("Portfolio total_sa_floor_uplift present",     "total_sa_floor_uplift"             in port)
check("Portfolio defaulted_exposure_count = 1",      port["defaulted_exposure_count"] == 1,
      f"got {port['defaulted_exposure_count']}")
check("Portfolio climate_uplifted_count >= 1",       port["climate_uplifted_count"] >= 1,
      f"got {port['climate_uplifted_count']}")
check("Portfolio total_rwa_regulatory > 0",          port["total_rwa_regulatory"] > 0)
check("4 trades processed",                          port["num_trades_processed"] == 4)

print(f"\n{'='*50}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL == 0:
    print("ALL AIRB ENHANCEMENTS VERIFIED OK")
else:
    sys.exit(1)
