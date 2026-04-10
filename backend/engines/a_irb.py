"""
PROMETHEUS Risk Platform
Engine: A-IRB — Advanced Internal Ratings-Based Approach
Regulatory basis: CRE30-36 (effective Jan 2023)

Implements:
  - Corporate / Bank / Sovereign risk-weight function (CRE31)
  - SME adjustment (CRE31.9)
  - Maturity adjustment (CRE31.7)
  - Double-default framework for CDS-protected exposures (CRE22)
  - EL calculation and comparison to provisions (CRE35)
  - Market regime adjustments (stressed vs. baseline)
  - PD term structure & sector correlation adjustments
  - EAD schedule evolution for derivatives
  - Sensitivity analysis & RWA drivers
  - Data quality tracking & diagnostic logging
  - Only applicable to Banking Book (req #10)
  - USMacroDataFeed: real-time US macro data (FRED / Bloomberg / Refinitiv / yfinance)

Real-Time Macro Feed — Addition (April 2026)
═══════════════════════════════════════════════════════════════════════════════
NEW     USMacroDataFeed class: three-tier live data fetch for all six fields
        of MacroeconomicFactors.  Designed for US G-SIB deployment:

        Tier 1  Bloomberg BSAPI (blpapi) — VIX, yield curve, HY-OAS, unemployment,
                GDP.  Requires BLOOMBERG_HOST env var and blpapi SDK.
                Provides intraday real-time data.

        Tier 2  FRED public API (no key) / FRED JSON API (FRED_API_KEY):
                VIXCLS, T10Y2Y, BAMLH0A0HYM2, UNRATE,
                A191RL1Q225SBEA, CORBLACBS.
                Free, authoritative, daily frequency.

        Tier 3  yfinance — ^VIX and yield spread (^TNX − ^IRX).
                15-minute delayed; no API key; pip install yfinance.

        Floor   Hard-coded long-run US conservative averages.
                Never fails; logs a WARNING for each series using fallback.

NEW     AIRBEngine(macro_feed=USMacroDataFeed()):
        When a feed is supplied, compute_portfolio() auto-fetches live US
        conditions once per run (not once per trade) and routes all exposures
        through compute_with_macro_overlay().

NEW     compute_portfolio() returns 'macro_snapshot' key with full audit trail:
        fetch source per series, stress_index, regime, all six parameter values.

Regulatory Review — Corrections applied (April 2026)
═══════════════════════════════════════════════════════════════════════════════
FIX-01 [HIGH]   CRE31.5   compute(): reported rwa now uses R_regulatory (Basel-
                            capped). Previous code set R = R_internal which applied
                            sector ×1.05 and concentration ×1.14 overlays to Pillar 1
                            capital, exceeding the CRE31.5 regulatory ceiling.

FIX-02 [HIGH]   CRE31.5   compute_with_macro_overlay(): K now computed with
                            R_regulatory (not R_dynamic). DynamicCorrelationModel
                            returned R=0.59+ in crisis (vs Basel cap 0.24), producing
                            RWA nearly 3× the regulatory requirement (+196%).

FIX-03 [HIGH]   CRE31.13  DynamicCorrelationModel: crisis/stressed correlation
                CRE31.14   values recalibrated. Previous values violated CRE31.14
                            (RETAIL_REV fixed at R=0.04; model had 0.40 in crisis)
                            and exceeded CRE31.5 caps by 3-4× for CORP/BANK.

FIX-04 [MEDIUM] CRE32.24  Guarantee substitution: K now computed via split-K
                            (covered: K_guarantor; uncovered: K_obligor), not blended
                            PD. Blended PD is incorrect due to nonlinearity of CRE31.4
                            in PD — produced RWA up to 34% above the correct value.

FIX-05 [LOW]    CRE32.11  compute_lgd_star(): unknown collateral types now log a
                            WARNING and return unsecured LGD (no benefit recognised).
                            Previously silent — callers should map all types to the
                            five CRE32.11 eligible categories.

FIX-06 [LOW]    CRE35     compute_with_macro_overlay(): rwa_pre_mitigant baseline
                            now computed from (pd_base, lgd_base) before overlays.
                            Previously always 0.0, making CRM benefit invisible.
"""

from __future__ import annotations
import math
import logging
import time
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import date
from enum import Enum

from backend.config import AIRB
# lgd_calibration is imported lazily inside _get_lgd_model() below
# to avoid circular import: a_irb → data_sources.__init__ → cds_spread_service → a_irb.
# All callers use _DEFAULT_LGD_MODEL() / _LGD_MODEL_CLS() accessor functions.

# ── Real-time data feed dependencies (all stdlib; yfinance optional) ──────────
import json          as _json
import os            as _os
import threading     as _threading
import urllib.request as _urllib_req
import urllib.error  as _urllib_err
# Precision note: CRE31.4 requires N⁻¹(0.999) evaluated at full double precision.
# scipy.special.ndtr/ndtri give machine-epsilon accuracy; fallback is a minimax
# rational polynomial (Acklam 2003, max error 1.15×10⁻⁹) — far superior to the
# Abramowitz & Stegun approximation (max error ~4.5×10⁻⁴) previously used.
try:
    from scipy.special import ndtr as _sp_ndtr, ndtri as _sp_ndtri

    def _norm_cdf_local(x: float) -> float:
        return float(_sp_ndtr(x))

    def _norm_inv_local(p: float) -> float:
        return float(_sp_ndtri(p))

except ImportError:
    # Acklam (2003) rational minimax — max |error| ≈ 1.15e-9
    import math as _math

    def _norm_cdf_local(x: float) -> float:  # type: ignore[misc]
        return 0.5 * (1.0 + _math.erf(x / _math.sqrt(2)))

    def _norm_inv_local(p: float) -> float:  # type: ignore[misc]
        # Acklam coefficients
        _a = (-3.969683028665376e+01,  2.209460984245205e+02,
              -2.759285104469687e+02,  1.383577518672690e+02,
              -3.066479806614716e+01,  2.506628277459239e+00)
        _b = (-5.447609879822406e+01,  1.615858368580409e+02,
              -1.556989798598866e+02,  6.680131188771972e+01,
              -1.328068155288572e+01)
        _c = (-7.784894002430293e-03, -3.223964580411365e-01,
              -2.400758277161838e+00, -2.549732539343734e+00,
               4.374664141464968e+00,  2.938163982698783e+00)
        _d = ( 7.784695709041462e-03,  3.224671290700398e-01,
               2.445134137142996e+00,  3.754408661907416e+00)
        p_low, p_high = 0.02425, 1.0 - 0.02425
        if p_low <= p <= p_high:
            q = p - 0.5
            r = q * q
            return (q * (_a[0] + r*(_a[1] + r*(_a[2] + r*(_a[3] + r*(_a[4] + r*_a[5]))))) /
                    (1.0 + r*(_b[0] + r*(_b[1] + r*(_b[2] + r*(_b[3] + r*_b[4]))))))
        elif 0.0 < p < p_low:
            q = _math.sqrt(-2.0 * _math.log(p))
            return ((_c[0] + q*(_c[1] + q*(_c[2] + q*(_c[3] + q*(_c[4] + q*_c[5]))))) /
                    (1.0 + q*(_d[0] + q*(_d[1] + q*(_d[2] + q*_d[3])))))
        else:
            q = _math.sqrt(-2.0 * _math.log(1.0 - p))
            return -((_c[0] + q*(_c[1] + q*(_c[2] + q*(_c[3] + q*(_c[4] + q*_c[5]))))) /
                     (1.0 + q*(_d[0] + q*(_d[1] + q*(_d[2] + q*_d[3])))))

# Aliases used below
cached_norm_cdf = _norm_cdf_local
cached_norm_inv = _norm_inv_local

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Enums & Configuration
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegime(Enum):
    """Market state affecting PD/LGD calibration."""
    NORMAL = "normal"
    STRESSED = "stressed"
    CRISIS = "crisis"

class SectorType(Enum):
    """Obligor sector for correlation adjustments."""
    FINANCIALS = "FINANCIALS"
    REAL_ESTATE = "REAL_ESTATE"
    RETAIL = "RETAIL"
    UTILITIES = "UTILITIES"
    INDUSTRIALS = "INDUSTRIALS"
    UNKNOWN = "UNKNOWN"
# ─────────────────────────────────────────────────────────────────────────────
# US Real-Time Macroeconomic Data Feed  (G-SIB / US configuration)
# ─────────────────────────────────────────────────────────────────────────────

class USMacroDataFeed:
    """
    Real-time US macroeconomic data feed for the A-IRB Pillar 2 macro overlay.

    Designed for a US G-SIB.  All six MacroeconomicFactors fields are populated
    from authoritative public sources — no proprietary API keys required for
    daily batch use (FRED CSV endpoint is free).  Production Bloomberg / Refinitiv
    integration is provided via drop-in method overrides.

    Data source map
    ───────────────────────────────────────────────────────────────────────
    Field                Series / Ticker                   Release cadence
    ─────────────────    ──────────────────────────────    ────────────────
    vix_level            FRED: VIXCLS  / yfinance: ^VIX    Daily (T+0 close)
    yield_curve_slope    FRED: T10Y2Y  (10Y-2Y, in bp)     Daily
    high_yield_spread    FRED: BAMLH0A0HYM2  (ICE BofA     Daily
                          US HY OAS, %)  →  ×100 = bp
    unemployment_rate    FRED: UNRATE  (BLS U-3, %)         Monthly
    real_gdp_growth      FRED: A191RL1Q225SBEA  (BEA, %     Quarterly
                          annualized SAAR)
    credit_default_rate  FRED: CORBLACBS  (Fed commercial   Quarterly
                          & industrial loan charge-off %)

    Three-tier fallback per series
    ───────────────────────────────
    Tier 1  Bloomberg BSAPI (blpapi) / Refinitiv LSEG    →  intraday, real-time
    Tier 2  FRED (free CSV or JSON-with-API-key)         →  daily close, T+0
    Tier 3  yfinance (VIX + yield curve only)            →  15-min delay
    Floor   Hard-coded long-run US conservative averages →  never fails

    Thread safety
    ─────────────
    A single RLock protects the in-memory cache so concurrent daily runs
    always see a consistent snapshot.  An optional JSON disk cache allows
    the overnight batch to share its snapshot with intraday processes.

    Environment variables (all optional)
    ─────────────────────────────────────
    FRED_API_KEY        Raises rate limit from 120 → 500 req/min; enables
                        the JSON API (returns structured data, easier to parse).
    BLOOMBERG_HOST      host:port of Bloomberg Server API, e.g. localhost:8194
    REFINITIV_APP_KEY   LSEG / Refinitiv Eikon / Data API application key
    """

    # FRED public endpoints ─────────────────────────────────────────────────
    _FRED_CSV  = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    _FRED_JSON = (
        "https://api.stlouisfed.org/fred/series/observations"
        "?series_id={series}&api_key={key}"
        "&sort_order=desc&limit=5&file_type=json"
    )

    # Series identifiers ───────────────────────────────────────────────────
    _SERIES = {
        "vix":          "VIXCLS",            # CBOE VIX close (index points)
        "t10y2y":       "T10Y2Y",            # 10Y-2Y constant-maturity spread (pp)
        "hy_oas":       "BAMLH0A0HYM2",      # ICE BofA US HY OAS (%)
        "unemployment": "UNRATE",            # BLS U-3 unemployment rate (%)
        "real_gdp":     "A191RL1Q225SBEA",   # BEA real GDP growth, % ann. SAAR
        "chargeoff":    "CORBLACBS",         # Fed C&I loan charge-off rate (%)
    }

    # Conservative long-run US fallback values ────────────────────────────
    # Used only when ALL three tiers fail simultaneously (e.g. network outage).
    # Slightly above historical medians → conservative direction for capital.
    _FALLBACK = {
        "vix":          20.0,    # index points; median ~17, crisis floor ~30
        "t10y2y":        0.01,   # pp; slight positive slope (near-flat is conservative)
        "hy_oas":        4.50,   # % (450bp); long-run avg ~400bp
        "unemployment":  4.5,    # %; NAIRU ~4.0%
        "real_gdp":      2.0,    # % annualized; trend growth
        "chargeoff":     0.50,   # % ; long-run avg 0.40-0.60%
    }

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        fred_api_key: str = None,
        bloomberg_host: str = None,
        refinitiv_key: str = None,
        cache_path: str = None,
    ):
        """
        Args:
            cache_ttl_seconds:  Seconds before a cached snapshot expires.
                                Default 3600 (1 hour) — appropriate for daily
                                A-IRB batch.  Set to 300 for intraday stress runs.
            fred_api_key:       FRED API key (https://fred.stlouisfed.org/docs/api).
                                Without a key the free CSV endpoint is used.
            bloomberg_host:     Bloomberg Server API host:port (e.g. 'localhost:8194').
                                When set, VIX and yield slope come from Bloomberg.
            refinitiv_key:      LSEG/Refinitiv app key. Used if bloomberg_host is unset.
            cache_path:         JSON file for disk-persisted snapshot.  Allows the
                                overnight batch to share its fetch with intraday jobs.
        """
        self._ttl            = cache_ttl_seconds
        self._fred_api_key   = fred_api_key   or _os.getenv("FRED_API_KEY")
        self._bloomberg_host = bloomberg_host or _os.getenv("BLOOMBERG_HOST")
        self._refinitiv_key  = refinitiv_key  or _os.getenv("REFINITIV_APP_KEY")
        self._cache_path     = cache_path

        self._cache: Optional["MacroeconomicFactors"] = None
        self._cache_ts: float = 0.0
        self._fetch_log: Dict[str, str] = {}   # series → "OK:tier2:fred" | "FALLBACK:…"
        self._lock = _threading.RLock()

        # Pre-load disk cache if available and fresh
        if self._cache_path and _os.path.exists(self._cache_path):
            self._load_disk_cache()

    # ── Public API ─────────────────────────────────────────────────────────

    def fetch(self, force_refresh: bool = False) -> "MacroeconomicFactors":
        """
        Return the current US macroeconomic snapshot.

        Cached for cache_ttl_seconds; refreshes automatically when stale.
        Thread-safe — safe to call from multiple concurrent daily-run threads.

        Args:
            force_refresh: Ignore cache and fetch immediately.  Use for:
                           - Intraday stress alerts
                           - Regulatory on-demand capital recalculation
                           - Post-market-event batch reruns

        Returns:
            MacroeconomicFactors with live US data, degrading gracefully to
            long-run averages when any individual series is unavailable.
        """
        with self._lock:
            now = time.time()
            if (
                not force_refresh
                and self._cache is not None
                and (now - self._cache_ts) < self._ttl
            ):
                logger.debug(
                    "USMacroDataFeed: cache hit (age=%.0fs, ttl=%ds)",
                    now - self._cache_ts, self._ttl,
                )
                return self._cache

            macro = self._fetch_all()
            self._cache    = macro
            self._cache_ts = time.time()

            if self._cache_path:
                self._save_disk_cache(macro)

            fallbacks = [k for k, v in self._fetch_log.items() if "FALLBACK" in v]
            logger.info(
                "USMacroDataFeed refreshed — "
                "VIX=%.1f | T10Y2Y=%.0fbp | HY-OAS=%.0fbp | "
                "UNRATE=%.1f%% | GDP=%.1f%% | ChargeOff=%.2f%% | "
                "regime=%s%s",
                macro.vix_level,
                macro.yield_curve_slope,
                macro.high_yield_spread,
                macro.unemployment_rate,
                macro.real_gdp_growth,
                macro.credit_default_rate * 100,
                macro.regime().value,
                f"  ⚠ fallback used for: {fallbacks}" if fallbacks else "",
            )
            return macro

    @property
    def fetch_log(self) -> Dict[str, str]:
        """Per-series fetch status — expose to dashboard for data-quality display."""
        return dict(self._fetch_log)

    def inject(self, **kwargs: float) -> "MacroeconomicFactors":
        """
        Manually inject specific macro parameters.
        Unspecified fields use the most recent cached values or fallbacks.
        Useful for scenario analysis and regulatory stress tests.

        Example:
            feed.inject(vix_level=45.0, high_yield_spread=750.0)
        """
        base = self._cache or self._fallback_macro()
        macro = MacroeconomicFactors(
            date              = date.today(),
            vix_level         = kwargs.get("vix_level",          base.vix_level),
            yield_curve_slope = kwargs.get("yield_curve_slope",  base.yield_curve_slope),
            high_yield_spread = kwargs.get("high_yield_spread",  base.high_yield_spread),
            unemployment_rate = kwargs.get("unemployment_rate",  base.unemployment_rate),
            real_gdp_growth   = kwargs.get("real_gdp_growth",    base.real_gdp_growth),
            credit_default_rate = kwargs.get("credit_default_rate", base.credit_default_rate),
        )
        with self._lock:
            self._cache    = macro
            self._cache_ts = time.time()
        return macro

    # ── Internal orchestration ─────────────────────────────────────────────

    def _fetch_all(self) -> "MacroeconomicFactors":
        """
        Fetch all six series independently.
        Each uses a three-tier chain: Bloomberg → FRED → yfinance → fallback.
        A failure in one series never blocks the others.
        """
        self._fetch_log.clear()

        # ── VIX ──────────────────────────────────────────────────────────────
        # Bloomberg: VIX Index / PX_LAST  (real-time)
        # FRED VIXCLS: prior close (free, no key needed)
        # yfinance ^VIX: 15-min delayed free feed
        vix = self._fetch_series(
            label="vix",
            tier1=lambda: self._bloomberg("VIX Index"),
            tier2=lambda: self._fred("VIXCLS"),
            tier3=lambda: self._yfinance("^VIX"),
            transform=lambda v: round(max(v, 0.0), 2),
            fallback=self._FALLBACK["vix"],
        )

        # ── 10Y-2Y Yield Curve Slope ──────────────────────────────────────────
        # Bloomberg: USGG10YR - USGG2YR (yields in %, spread in pp → ×100 = bp)
        # FRED T10Y2Y: constant-maturity 10Y-2Y spread in pp → ×100 = bp
        # yfinance: ^TNX (10Y) - ^IRX (13W, proxy for 2Y) — tenths of a percent
        t10y2y_pp = self._fetch_series(
            label="t10y2y",
            tier1=lambda: self._bloomberg_spread("USGG10YR Govt", "USGG2YR Govt"),
            tier2=lambda: self._fred("T10Y2Y"),
            tier3=lambda: self._yield_spread_yfinance(),
            transform=lambda v: v,   # keep in pp; convert to bp below
            fallback=self._FALLBACK["t10y2y"],
        )
        yield_curve_slope = round(t10y2y_pp * 100, 1)   # percentage points → basis points

        # ── US HY-OAS (ICE BofA) ─────────────────────────────────────────────
        # Bloomberg: LF98OAS Index (already in bp)
        # FRED BAMLH0A0HYM2: in % (e.g. 3.25 = 325bp) → ×100 = bp
        hy_raw = self._fetch_series(
            label="hy_oas",
            tier1=lambda: self._bloomberg("LF98OAS Index"),
            tier2=lambda: self._fred("BAMLH0A0HYM2"),
            tier3=None,
            transform=lambda v: v,
            fallback=self._FALLBACK["hy_oas"],
        )
        # Bloomberg returns bp directly (>10); FRED returns % (<10 for typical oas)
        high_yield_spread = round(hy_raw if hy_raw > 10 else hy_raw * 100, 1)

        # ── BLS Unemployment Rate ─────────────────────────────────────────────
        # FRED UNRATE: U-3 rate (%), released ~first Friday of following month
        # Bloomberg: USURTOT Index
        unemployment_rate = self._fetch_series(
            label="unemployment",
            tier1=lambda: self._bloomberg("USURTOT Index"),
            tier2=lambda: self._fred("UNRATE"),
            tier3=None,
            transform=lambda v: round(max(v, 0.0), 2),
            fallback=self._FALLBACK["unemployment"],
        )

        # ── BEA Real GDP Growth ───────────────────────────────────────────────
        # FRED A191RL1Q225SBEA: % annualized SAAR, released quarterly
        # (advance ~4 wks after quarter-end; preliminary 2 months; final 3 months)
        # Bloomberg: GDP CQOQ Index (q/q annualized %)
        real_gdp_growth = self._fetch_series(
            label="real_gdp",
            tier1=lambda: self._bloomberg("GDP CQOQ Index"),
            tier2=lambda: self._fred("A191RL1Q225SBEA"),
            tier3=None,
            transform=lambda v: round(v, 2),
            fallback=self._FALLBACK["real_gdp"],
        )

        # ── Fed Commercial Loan Charge-Off Rate ───────────────────────────────
        # FRED CORBLACBS: commercial & industrial loan net charge-off rate (%),
        # seasonally adjusted annual rate, released quarterly.
        # Closest public proxy for a bank portfolio-level default rate.
        # For a G-SIB's own portfolio default rate, override with internal DWH:
        #   engine.macro_feed.inject(credit_default_rate=internal_dr)
        chargeoff_pct = self._fetch_series(
            label="chargeoff",
            tier1=None,
            tier2=lambda: self._fred("CORBLACBS"),
            tier3=None,
            transform=lambda v: round(max(v, 0.0), 4),
            fallback=self._FALLBACK["chargeoff"],
        )
        # MacroeconomicFactors.credit_default_rate is stored as a decimal (0.005 = 0.5%)
        credit_default_rate = chargeoff_pct / 100.0

        return MacroeconomicFactors(
            date              = date.today(),
            vix_level         = vix,
            yield_curve_slope = yield_curve_slope,
            high_yield_spread = high_yield_spread,
            unemployment_rate = unemployment_rate,
            real_gdp_growth   = real_gdp_growth,
            credit_default_rate = credit_default_rate,
        )

    # ── Generic fetch helper ───────────────────────────────────────────────

    def _fetch_series(
        self,
        label: str,
        tier1,
        tier2,
        tier3,
        transform,
        fallback: float,
    ) -> float:
        """
        Try tier1 → tier2 → tier3 → fallback, logging the outcome.
        Each tier function returns a float or None; exceptions are caught.
        """
        for tier_num, fn, name in (
            (1, tier1, "bloomberg/refinitiv"),
            (2, tier2, "fred"),
            (3, tier3, "yfinance"),
        ):
            if fn is None:
                continue
            try:
                val = fn()
                if val is not None and math.isfinite(val):
                    self._fetch_log[label] = f"OK:tier{tier_num}:{name}"
                    return transform(val)
            except Exception as exc:
                logger.debug("USMacroDataFeed [%s] tier-%d failed: %s", label, tier_num, exc)

        self._fetch_log[label] = "FALLBACK:all-tiers-failed"
        logger.warning(
            "USMacroDataFeed: all sources failed for '%s' — "
            "using long-run conservative fallback %.4f",
            label, fallback,
        )
        return transform(fallback)

    # ── Tier-2: FRED ──────────────────────────────────────────────────────

    def _fred(self, series_id: str) -> Optional[float]:
        """
        Fetch latest observation from FRED.

        Without FRED_API_KEY: uses the public CSV endpoint (free, ~120 req/min).
        With    FRED_API_KEY: uses the JSON API (500 req/min, structured response).
        Both walk backwards through observations to find the last non-missing value.
        """
        if self._fred_api_key:
            return self._fred_json(series_id)
        return self._fred_csv(series_id)

    def _fred_csv(self, series_id: str) -> float:
        """
        FRED public CSV endpoint — no authentication required.
        URL: https://fred.stlouisfed.org/graph/fredgraph.csv?id=<series>
        """
        url = self._FRED_CSV.format(series=series_id)
        req = _urllib_req.Request(
            url,
            headers={"User-Agent": "PROMETHEUS-AIRBEngine/2.0 (G-SIB regulatory system)"},
        )
        with _urllib_req.urlopen(req, timeout=12) as resp:
            lines = resp.read().decode("utf-8").strip().splitlines()
        # Header line is "DATE,VALUE"; walk reversed to get most recent non-missing
        for line in reversed(lines[1:]):
            parts = line.split(",")
            if len(parts) == 2 and parts[1].strip() not in ("", "."):
                val = float(parts[1].strip())
                logger.debug("FRED CSV %s = %.4f (date: %s)", series_id, val, parts[0])
                return val
        raise ValueError(f"No valid observation in FRED CSV for {series_id}")

    def _fred_json(self, series_id: str) -> float:
        """
        FRED JSON API — requires FRED_API_KEY env var or constructor arg.
        Returns 5 most recent observations (sort_order=desc), picks first valid.
        Register for a free key at: https://fred.stlouisfed.org/docs/api/api_key.html
        """
        url = self._FRED_JSON.format(series=series_id, key=self._fred_api_key)
        req = _urllib_req.Request(
            url,
            headers={"User-Agent": "PROMETHEUS-AIRBEngine/2.0 (G-SIB regulatory system)"},
        )
        with _urllib_req.urlopen(req, timeout=12) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
        for obs in data.get("observations", []):
            if obs.get("value", ".") not in (".", ""):
                val = float(obs["value"])
                logger.debug("FRED JSON %s = %.4f (date: %s)", series_id, val, obs.get("date"))
                return val
        raise ValueError(f"No valid observation in FRED JSON for {series_id}")

    # ── Tier-3: yfinance ──────────────────────────────────────────────────

    def _yfinance(self, ticker: str) -> Optional[float]:
        """
        Fetch the most recent close from Yahoo Finance via yfinance.
        15-minute delay for US equity/index data; no API key required.
        Install: pip install yfinance
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.debug("yfinance not installed — skipping ticker %s", ticker)
            return None
        hist = yf.Ticker(ticker).history(period="3d")
        if hist.empty:
            raise ValueError(f"yfinance returned empty history for {ticker}")
        return float(hist["Close"].iloc[-1])

    def _yield_spread_yfinance(self) -> Optional[float]:
        """
        Compute 10Y-2Y slope from yfinance UST tickers.
        ^TNX = 10Y UST yield (in tenths of a percent, e.g. 42.5 = 4.25%)
        ^IRX = 13-week T-bill (proxy for short end; in tenths of a percent)
        Returns value in percentage points (same unit as FRED T10Y2Y).
        """
        try:
            import yfinance as yf
        except ImportError:
            return None
        t10 = yf.Ticker("^TNX").history(period="3d")
        t2  = yf.Ticker("^IRX").history(period="3d")
        if t10.empty or t2.empty:
            return None
        # ^TNX and ^IRX report in tenths of a percent
        y10 = float(t10["Close"].iloc[-1]) / 10.0
        y2  = float(t2 ["Close"].iloc[-1]) / 10.0
        return y10 - y2   # percentage points

    # ── Tier-1: Bloomberg BSAPI ───────────────────────────────────────────

    def _bloomberg(self, ticker: str, field: str = "PX_LAST") -> Optional[float]:
        """
        Fetch a single field from Bloomberg Server API via blpapi.

        Prerequisites (production G-SIB setup):
            pip install blpapi        # Bloomberg BLPAPI Python SDK
            BLOOMBERG_HOST=localhost:8194  # or set bloomberg_host in constructor

        Tickers used by this feed:
            VIX Index         → VIX close
            LF98OAS Index     → ICE BofA US HY OAS (bp)
            USURTOT Index     → US unemployment rate
            GDP CQOQ Index    → US real GDP growth q/q annualized

        For real-time intraday data, use field='RT_PX_LAST' instead of 'PX_LAST'.
        """
        if not self._bloomberg_host:
            return None
        try:
            import blpapi
            host, _, port_str = self._bloomberg_host.partition(":")
            opts = blpapi.SessionOptions()
            opts.setServerHost(host or "localhost")
            opts.setServerPort(int(port_str) if port_str else 8194)
            session = blpapi.Session(opts)
            if not session.start():
                raise RuntimeError("Bloomberg session failed to start")
            if not session.openService("//blp/refdata"):
                raise RuntimeError("Bloomberg //blp/refdata unavailable")
            svc = session.getService("//blp/refdata")
            req = svc.createRequest("ReferenceDataRequest")
            req.append("securities", ticker)
            req.append("fields", field)
            session.sendRequest(req)
            while True:
                event = session.nextEvent(timeout_ms=6000)
                for msg in event:
                    if msg.hasElement("securityData"):
                        sd = msg.getElement("securityData").getValueAsElement(0)
                        fd = sd.getElement("fieldData")
                        if fd.hasElement(field):
                            val = float(fd.getElementAsFloat(field))
                            session.stop()
                            logger.debug("Bloomberg %s/%s = %.4f", ticker, field, val)
                            return val
                if event.eventType() == blpapi.Event.RESPONSE:
                    break
            session.stop()
        except ImportError:
            logger.debug("blpapi not installed — Bloomberg tier unavailable")
        except Exception as exc:
            logger.debug("Bloomberg fetch %s/%s failed: %s", ticker, field, exc)
        return None

    def _bloomberg_spread(self, ticker1: str, ticker2: str,
                          field: str = "YLD_YTM_MID") -> Optional[float]:
        """
        Compute the spread between two Bloomberg yield tickers (e.g. 10Y minus 2Y).
        Returns result in percentage points.
        """
        v1 = self._bloomberg(ticker1, field)
        v2 = self._bloomberg(ticker2, field)
        if v1 is not None and v2 is not None:
            return v1 - v2
        return None

    # ── Tier-1: Refinitiv / LSEG ─────────────────────────────────────────

    def _refinitiv(self, ric: str, field: str = "CF_CLOSE") -> Optional[float]:
        """
        Fetch a single field from Refinitiv/LSEG Data Library.

        Prerequisites:
            pip install lseg-data
            REFINITIV_APP_KEY=<your-key>  # or refinitiv_key in constructor

        RIC examples:
            .VIX          → CBOE VIX index
            US10YT=RR     → 10Y US Treasury yield
            US2YT=RR      → 2Y US Treasury yield
            MERH0A0.IBOAS → ICE BofA US HY OAS

        The Refinitiv tier is used when BLOOMBERG_HOST is not set but
        REFINITIV_APP_KEY is available.
        """
        key = self._refinitiv_key or _os.getenv("REFINITIV_APP_KEY")
        if not key:
            return None
        try:
            import lseg.data as ld
            ld.open_session(
                config={"sessions": {"default": {"app-key": key}}}
            )
            df = ld.get_data(ric, [field])
            if df is not None and not df.empty:
                val = float(df.iloc[0][field])
                logger.debug("Refinitiv %s/%s = %.4f", ric, field, val)
                return val
        except ImportError:
            logger.debug("lseg-data not installed — Refinitiv tier unavailable")
        except Exception as exc:
            logger.debug("Refinitiv fetch %s/%s failed: %s", ric, field, exc)
        return None

    # ── Disk cache helpers ─────────────────────────────────────────────────

    def _save_disk_cache(self, macro: "MacroeconomicFactors") -> None:
        """Persist snapshot to JSON for inter-process sharing."""
        try:
            payload = {
                "timestamp":          self._cache_ts,
                "vix_level":          macro.vix_level,
                "yield_curve_slope":  macro.yield_curve_slope,
                "high_yield_spread":  macro.high_yield_spread,
                "unemployment_rate":  macro.unemployment_rate,
                "real_gdp_growth":    macro.real_gdp_growth,
                "credit_default_rate":macro.credit_default_rate,
                "fetch_log":          self._fetch_log,
            }
            with open(self._cache_path, "w") as f:
                _json.dump(payload, f, indent=2)
            logger.debug("USMacroDataFeed: snapshot saved to %s", self._cache_path)
        except Exception as exc:
            logger.warning("USMacroDataFeed: disk cache write failed: %s", exc)

    def _load_disk_cache(self) -> None:
        """Reload a persisted snapshot if it is still within TTL."""
        try:
            with open(self._cache_path) as f:
                d = _json.load(f)
            age = time.time() - d.get("timestamp", 0.0)
            if age < self._ttl:
                self._cache = MacroeconomicFactors(
                    date              = date.today(),
                    vix_level         = d["vix_level"],
                    yield_curve_slope = d["yield_curve_slope"],
                    high_yield_spread = d["high_yield_spread"],
                    unemployment_rate = d["unemployment_rate"],
                    real_gdp_growth   = d["real_gdp_growth"],
                    credit_default_rate = d["credit_default_rate"],
                )
                self._cache_ts  = d["timestamp"]
                self._fetch_log = d.get("fetch_log", {})
                logger.info(
                    "USMacroDataFeed: loaded from disk cache (age=%.0f min)",
                    age / 60,
                )
        except Exception as exc:
            logger.debug("USMacroDataFeed: disk cache load failed: %s", exc)

    def _fallback_macro(self) -> "MacroeconomicFactors":
        """Return a MacroeconomicFactors built entirely from fallback constants."""
        return MacroeconomicFactors(
            date              = date.today(),
            vix_level         = self._FALLBACK["vix"],
            yield_curve_slope = self._FALLBACK["t10y2y"] * 100,
            high_yield_spread = self._FALLBACK["hy_oas"] * 100,
            unemployment_rate = self._FALLBACK["unemployment"],
            real_gdp_growth   = self._FALLBACK["real_gdp"],
            credit_default_rate = self._FALLBACK["chargeoff"] / 100,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Macroeconomic & Market Data
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MacroeconomicFactors:
    """
    Real-time macroeconomic variables for PD/LGD/correlation adjustment.

    Default values are the USMacroDataFeed long-run conservative fallbacks
    (USMacroDataFeed._FALLBACK / _fallback_macro()).  They are used only when
    no live feed is attached — e.g. unit tests, manual scenario construction.
    Do NOT revert these to arbitrary round numbers; any change here must be
    synchronised with USMacroDataFeed._FALLBACK and _fallback_macro().

    Units
    ─────
    vix_level           : CBOE VIX index points  (e.g. 20.0 = VIX 20)
    yield_curve_slope   : basis points            (e.g.  1.0 = 1 bp)
    high_yield_spread   : basis points            (e.g. 450.0 = 450 bp)
    unemployment_rate   : percent                 (e.g.  4.5 = 4.5 %)
    real_gdp_growth     : percent annualised      (e.g.  2.0 = 2.0 %)
    credit_default_rate : decimal                 (e.g.  0.005 = 0.5 %)
    """
    date: date
    vix_level:            float = 20.0    # CBOE VIX; long-run avg ~17, crisis >30
    yield_curve_slope:    float = 1.0     # 10Y-2Y in bp; near-flat is conservative
    high_yield_spread:    float = 450.0   # ICE BofA HY-OAS in bp; long-run avg ~400bp
    unemployment_rate:    float = 4.5     # BLS U-3 %; NAIRU ~4.0%
    real_gdp_growth:      float = 2.0     # BEA real GDP, % ann. SAAR; trend growth
    credit_default_rate:  float = 0.005   # Fed C&I charge-off rate, decimal; avg 0.40-0.60%

    # Derived stress indicators
    def stress_index(self) -> float:
        """
        Composite stress index [0, 1]: 0=normal, 1=crisis.
        Combines VIX, spreads, unemployment, defaults.
        """
        # Normalize components to [0,1]
        vix_norm          = min(self.vix_level / 80.0, 1.0)                         # VIX peaks ~80 in crises
        spread_norm       = min((self.high_yield_spread - 300) / 1000.0, 1.0)       # 300bp=0, 1300bp=1
        unemployment_norm = min(max(self.unemployment_rate - 3.0, 0.0) / 5.0, 1.0) # 3%=0, 8%=1
        default_norm      = min(self.credit_default_rate / 0.10, 1.0)               # decimal: 0.0=0, 0.10=1
        
        # Weighted average: VIX (25%), spreads (35%), unemployment (20%), defaults (20%)
        stress = 0.25*vix_norm + 0.35*spread_norm + 0.20*unemployment_norm + 0.20*default_norm
        return min(max(stress, 0.0), 1.0)
    
    def regime(self) -> MarketRegime:
        """Classify regime based on stress index."""
        s = self.stress_index()
        if s < 0.3:
            return MarketRegime.NORMAL
        elif s < 0.6:
            return MarketRegime.STRESSED
        else:
            return MarketRegime.CRISIS

@dataclass
class CreditSpreadsData:
    """CDS spread data for implied PD calibration."""
    date: date
    obligor_id: str
    tenor_1y: float = 0.0                # CDS spread 1Y (bp)
    tenor_3y: float = 0.0                # CDS spread 3Y (bp)
    tenor_5y: float = 0.0                # CDS spread 5Y (bp)
    recovery_assumption: float = 0.40    # Recovery for implied PD calc
    bid_ask_spread: float = 10.0         # Bid-ask in bp (liquidity)
    
    def implied_pd_1y(self) -> float:
        """Implied 1Y PD from CDS spread."""
        # Approximation: PD ≈ Spread / (1 - Recovery)
        # More precise: use market formula with accrued interest
        if self.tenor_1y <= 0:
            return 0.0
        return min((self.tenor_1y / 10000) / (1.0 - self.recovery_assumption), 1.0)
    
    def implied_pd_5y(self) -> float:
        """Implied 5Y PD (hazard rate) from 5Y CDS."""
        if self.tenor_5y <= 0:
            return 0.0
        # Flat hazard rate approximation
        return min((self.tenor_5y / 10000) / (1.0 - self.recovery_assumption), 1.0)
    
    def bid_ask_impact(self) -> float:
        """Mid-spread adjusted for bid-ask."""
        return self.tenor_5y + self.bid_ask_spread / 2.0
# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PDTermStructure:
    """PD varies by time horizon — not flat."""
    pd_1y: float
    pd_3y: float
    pd_5y: float
    pd_source: str = "internal"  # 'internal', 'external_rating', 'market'
    
    def get_pd_at_horizon(self, years: float) -> float:
        """
        Interpolate PD for arbitrary horizon.
        Linear interpolation between tenor points.
        """
        if years <= 1.0:
            return self.pd_1y
        elif years <= 3.0:
            weight = (years - 1.0) / 2.0
            return self.pd_1y + (self.pd_3y - self.pd_1y) * weight
        elif years <= 5.0:
            weight = (years - 3.0) / 2.0
            return self.pd_3y + (self.pd_5y - self.pd_3y) * weight
        else:
            # Flat extrapolation beyond 5Y
            return self.pd_5y
    
    def validate(self) -> bool:
        """Check term structure is increasing (typical)."""
        if self.pd_1y < 0 or self.pd_3y < 0 or self.pd_5y < 0:
            return False
        # Allow non-monotonic (inverted curves in stress)
        return True


# ─── Lazy LGD model accessors (avoids circular import at module level) ────────
_lgd_cal_cache = {}

def _get_default_lgd_model():
    """Return DEFAULT_LGD_MODEL from lgd_calibration (lazy load)."""
    if 'default' not in _lgd_cal_cache:
        import importlib
        mod = importlib.import_module('backend.data_sources.lgd_calibration')
        _lgd_cal_cache['default'] = mod.DEFAULT_LGD_MODEL
    return _lgd_cal_cache['default']


@dataclass
class BankingBookExposure:
    trade_id:           str
    portfolio_id:       str
    obligor_id:         str
    asset_class:        str         # 'CORP','BANK','SOVEREIGN','RETAIL_MORT','RETAIL_REV','RETAIL_OTHER'
    ead:                float       # Exposure at Default (USD)
    pd:                 float       # 1-year PD (decimal) — DEPRECATED, use pd_term_structure
    lgd:                float       # Loss Given Default (decimal)
    maturity:           float       # Effective maturity (years)
    sales_volume:       float = 0.0 # Annual sales (EUR equiv.) — for SME adj.
    has_cds:            bool = False
    cds_pd:             float = 0.0 # Guarantor PD (for double-default)
    cds_lgd:            float = 0.45
    provisions:         float = 0.0 # Specific provisions held
    sector:             str   = "UNKNOWN"

    # ── Funded collateral (CRE32.10–32.14) ───────────────────────────────────
    collateral_type:    str   = "NONE"
    collateral_value:   float = 0.0
    collateral_he:      float = 0.0

    # ── Guarantee / unfunded protection (CRE32.23–32.27) ────────────────────
    has_guarantee:      bool  = False
    guarantor_pd:       float = 0.0
    guarantor_lgd:      float = 0.45
    guarantee_coverage: float = 0.0

    # ── CDS partial coverage (CRE22) ─────────────────────────────────────────
    cds_coverage:       float = 1.0

    # ── On-balance-sheet netting – retail only (CRE32.63) ────────────────────
    deposit_offset:     float = 0.0

    # ── Term structure & EAD evolution ───────────────────────────────────────
    pd_term_structure:  Optional[PDTermStructure] = None
    ead_schedule:       Optional[Dict[float, float]] = None  # {time_year: ead_amount}
    
    # ── Market regime ────────────────────────────────────────────────────────
    market_regime:      MarketRegime = field(default_factory=lambda: MarketRegime.NORMAL)
    portfolio_concentration: float = 0.0  # Herfindahl index or single-obligor concentration

    # ── CRE31.7: financial institution large/unregulated flag ─────────────────
    # True for: (i) regulated FIs with total assets ≥ USD 100bn, or
    # (ii) unregulated FIs regardless of size (CRE31.7).
    # When set, a 1.25× multiplier is applied to R in asset_correlation().
    is_large_financial_institution: bool = False

    # ── CRE31.8: daily-margined derivative flag ───────────────────────────────
    # If True, effective maturity M is capped at 1 year before maturity adjustment.
    is_margined:        bool  = False

    # ── CRE31.12: defaulted exposure best-estimate LGD ───────────────────────
    # Best-estimate LGD used in the defaulted-exposure K formula.
    # If None, lgd is used as the best estimate.
    lgd_best_estimate:  Optional[float] = None

    # ── LGD model (CRE36.83 — downturn / Frye-Jacobs) ───────────────────────
    # When set, compute() uses LGDModel.downturn_lgd() for Pillar 1 capital
    # and compute_with_macro_overlay() uses LGDModel.conditional_lgd() for
    # Pillar 2 / ICAAP.  When None the static exp.lgd field is used (legacy).
    lgd_model:          Optional[object] = None  # type: LGDModel

    # ── Wrong-way LGD flag (CRE36.84) ───────────────────────────────────────
    # Set True when obligor and collateral are in the same sector and
    # the collateral is likely to depreciate exactly at default.
    # LGDModel.wrong_way_lgd() applies a 1.10–1.25× conservative uplift.
    has_wrong_way_lgd:  bool  = False

    # ── IFRS 9 provision staging (CRE35.3) ───────────────────────────────────
    # Under CRE35.3, only Stage 3 specific provisions offset EL for Pillar 1.
    # Stage 1/2 general provisions are ineligible.
    provisions_stage1:  float = 0.0   # 12-month ECL (general — not eligible for P1 offset)
    provisions_stage2:  float = 0.0   # Lifetime ECL non-credit-impaired (general)
    provisions_stage3:  float = 0.0   # Lifetime ECL credit-impaired (specific — eligible)

    # ── ESG / climate transition risk (CRR3 Art. 87a) ────────────────────────
    # Brown-sector indicator: 0=green/neutral, 1=fully brown (fossil fuel).
    climate_brown_factor: float = 0.0

    # ── SA output floor (CRE20.4 / Basel IV) ─────────────────────────────────
    # Standardised Approach RWA for the same exposure (used for 72.5% floor).
    # If 0.0 the floor check is skipped for this exposure.
    sa_rwa:             float = 0.0

    def get_pd_at_maturity(self) -> float:
        """Get PD adjusted for actual maturity."""
        if self.pd_term_structure is not None:
            return self.pd_term_structure.get_pd_at_horizon(self.maturity)
        return self.pd

    def get_ead_at_time(self, t: float) -> float:
        """Get EAD at given time horizon (for exposure evolution)."""
        if self.ead_schedule is None:
            return self.ead

        times = sorted(self.ead_schedule.keys())
        if t <= times[0]:
            return self.ead_schedule[times[0]]

        for i in range(len(times) - 1):
            t_low, t_high = times[i], times[i + 1]
            if t_low <= t < t_high:
                ead_low = self.ead_schedule[t_low]
                ead_high = self.ead_schedule[t_high]
                weight = (t - t_low) / (t_high - t_low)
                return ead_low + (ead_high - ead_low) * weight

        return self.ead_schedule[times[-1]]

    @property
    def eligible_provisions(self) -> float:
        """
        CRE35.3: only Stage 3 (specific) provisions are eligible for
        Pillar 1 EL offset.  Falls back to the legacy ``provisions`` field
        when IFRS 9 staging data is not populated.
        """
        staged_total = self.provisions_stage1 + self.provisions_stage2 + self.provisions_stage3
        if staged_total > 0:
            return self.provisions_stage3
        return self.provisions

@dataclass
class AIRBResult:
    trade_id:           str
    pd_applied:         float
    lgd_applied:        float
    ead_applied:        float
    maturity:           float
    correlation_r:      float
    capital_req_k:      float           # K per unit EAD (may use dynamic/internal R)
    maturity_adj_b:     float
    rwa:                float
    el:                 float           # Expected Loss
    el_diff:            float           # EL − Eligible Provisions (positive = shortfall)

    # ── Regulatory vs Internal split (Pillar 1 vs Pillar 2) ──────────────
    # k_regulatory: K using Basel-capped R (CRE31.5) — Pillar 1 minimum
    # k_internal:   K using dynamic/stress R — Pillar 2 ICAAP view
    k_regulatory:       float = 0.0
    rwa_regulatory:     float = 0.0
    r_regulatory:       float = 0.0     # R used for regulatory capital (capped)
    r_internal:         float = 0.0     # R used for internal capital (dynamic)

    # ── Sensitivity analysis ──────────────────────────────────────
    rwa_sensitivity_pd:  float = 0.0    # ΔRWA per +10bp PD
    rwa_sensitivity_lgd: float = 0.0    # ΔRWA per +5% LGD
    rwa_sensitivity_ead: float = 0.0    # ΔRWA per +10% EAD

    # ── Diagnostic & attribution ──────────────────────────────────
    rwa_drivers:        Dict[str, float] = field(default_factory=dict)
    pd_stressed:        float = 0.0
    is_defaulted:       bool  = False   # True when pd_applied >= 1.0 (CRE31.12 path)

    # ── Data quality & validation ─────────────────────────────────
    validation_errors:  List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    data_quality_score: float = 1.0

    # ── Mitigant tracking ────────────────────────────────────────
    rwa_pre_mitigant:     float = 0.0
    rwa_mitigant_benefit: float = 0.0
    lgd_pre_mitigant:     float = 0.0
    lgd_star:             float = 0.0
    pd_pre_mitigant:      float = 0.0
    mitigant_type:        str   = "NONE"

    # ── CRE35 EL capital treatment ────────────────────────────────
    # CRE35.2: if EL > eligible provisions → shortfall deducted from CET1
    # CRE35.3: if eligible provisions > EL → excess up to 0.6% RWA added to Tier 2
    el_shortfall_cet1_deduction: float = 0.0   # ≥ 0 means CET1 deduction required
    el_excess_tier2_eligible:    float = 0.0   # eligible Tier 2 add-back
    provisions_eligible:         float = 0.0   # Stage 3 (specific) provisions used

    # ── SA output floor (CRE20.4 / Basel IV) ────────────────────────
    sa_floor_rwa:         float = 0.0   # 72.5% × SA RWA floor
    sa_floor_binding:     bool  = False # True if IRB RWA < floor
    sa_floor_uplift:      float = 0.0   # max(0, floor − IRB RWA)

    # ── ESG / climate (CRR3 Art. 87a) ─────────────────────────────
    climate_pd_uplift:    float = 0.0   # Absolute PD increase from ESG transition risk

    # ── Performance tracking ────────────────────────────────────
    computation_time_ms: float = 0.0
    confidence_level:   float = 0.95

@dataclass
class AIRBConfiguration:
    """Market-sensitive A-IRB parameters."""
    pd_curve_source: str = "internal"  # 'internal', 'external_rating', 'market'
    lgd_curve_source: str = "internal"
    use_stressed_params: bool = False  # Stressed vs. baseline
    calibration_date: date = field(default_factory=date.today)
    market_regime: MarketRegime = MarketRegime.NORMAL
    pd_stress_factor: Dict[str, float] = field(
        default_factory=lambda: {
            "CORP": 1.5,
            "BANK": 1.4,
            "SOVEREIGN": 1.2,
            "HVCRE": 1.6,
            "RETAIL_MORT": 1.3,
            "RETAIL_REV": 1.6,
            "RETAIL_OTHER": 1.4,
        }
    )
    lgd_stress_factor: Dict[str, float] = field(
        default_factory=lambda: {
            "CORP": 1.2,
            "BANK": 1.15,
            "SOVEREIGN": 1.1,
            "HVCRE": 1.25,
            "RETAIL_MORT": 1.25,
            "RETAIL_REV": 1.3,
            "RETAIL_OTHER": 1.25,
        }
    )
    # ── ESG / Climate transition risk (CRR3 Art. 87a) ────────────────────
    # Additive PD uplift (absolute) per unit of climate_brown_factor [0,1].
    # Represents the maximum PD add-on for a fully brown (fossil-fuel) obligor.
    # Calibrate to sector-specific transition risk scenarios.
    brown_sector_pd_uplift: Dict[str, float] = field(
        default_factory=lambda: {
            "CORP": 0.005,        # +50bp for fully-brown corporates
            "BANK": 0.002,
            "SOVEREIGN": 0.001,
            "HVCRE": 0.008,
            "RETAIL_MORT": 0.003, # flood-zone mortgages
            "RETAIL_REV": 0.002,
            "RETAIL_OTHER": 0.003,
        }
    )
    # ── SA output floor ratio (CRE20.4 / Basel IV / CRR3 Art. 92 para. 3) ───
    # EU/UK/US = 72.5% from Jan 2025 (phased from 50% starting Jan 2022).
    sa_output_floor_ratio: float = 0.725

# ─────────────────────────────────────────────────────────────────────────────
# CRE31: IRB Risk-Weight Formula
# ─────────────────────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Normal CDF. Uses scipy.special.ndtr when available (higher precision)."""
    """Standard normal CDF — uses CalculationCache for memoization."""
    return cached_norm_cdf(x)

def _norm_inv(p: float) -> float:
    """Inverse normal CDF — uses CalculationCache for memoization."""
    return cached_norm_inv(p)

# CRE31.5 regulatory R ceilings per asset class (used to guard dynamic overlays)
# Note: BANK ceiling is 0.30 to accommodate the CRE31.7 1.25× multiplier for
# large/unregulated financial institutions (0.24 × 1.25 = 0.30).
_R_REGULATORY_CAP: dict = {
    "CORP":        0.24,   # CRE31.5 upper bound
    "BANK":        0.30,   # CRE31.5 × CRE31.7 1.25× FI multiplier ceiling (0.24 × 1.25)
    "SOVEREIGN":   0.24,
    "HVCRE":       0.30,   # CRE31.10 — High-Volatility CRE specific cap
    "RETAIL_MORT": 0.15,   # CRE31.13 — fixed
    "RETAIL_REV":  0.04,   # CRE31.14 — fixed
    "RETAIL_OTHER":0.16,   # CRE31.15 upper bound
}

def asset_correlation(
    pd: float,
    asset_class: str,
    sales: float = 0.0,
    is_large_financial_institution: bool = False,
) -> float:
    """
    CRE31.5 / CRE31.7 / CRE31.10 / CRE31.13-15: asset correlation R.

    Asset classes:
      CORP / BANK / SOVEREIGN — CRE31.5 formula (R ∈ [0.12, 0.24])
      HVCRE                   — CRE31.10 formula (R ∈ [0.12, 0.30])
      RETAIL_MORT             — CRE31.13 fixed 0.15
      RETAIL_REV              — CRE31.14 fixed 0.04
      RETAIL_OTHER            — CRE31.15 formula (R ∈ [0.03, 0.16])

    SME adjustment (CRE31.9): −0.04×(1−(S−5)/45), S ∈ (5, 50) mEUR

    CRE31.7 FI multiplier: 1.25× applied to R for
      (i)  regulated FIs with total assets ≥ USD 100bn, or
      (ii) unregulated FIs regardless of size.
    Retail asset classes are exempt (CRE31.13-15 values are fixed).
    """
    pd = max(pd, AIRB.pd_floor)

    if asset_class in ("CORP", "BANK", "SOVEREIGN"):
        e50pd = math.exp(-50 * pd)
        denom = 1 - math.exp(-50)
        R = 0.12 * (1 - e50pd) / denom + 0.24 * (1 - (1 - e50pd) / denom)

        # SME adjustment (sales 5–50 mEUR)
        S_mEUR = sales / 1_000_000
        if 5 < S_mEUR < 50:
            R -= 0.04 * (1 - (S_mEUR - 5) / 45)

        # CRE31.7: 1.25× multiplier for large/unregulated financial institutions
        if is_large_financial_institution:
            R *= 1.25

    elif asset_class == "HVCRE":
        # CRE31.10: upper bound raised to 0.30 for high-volatility CRE
        e50pd = math.exp(-50 * pd)
        denom = 1 - math.exp(-50)
        R = 0.12 * (1 - e50pd) / denom + 0.30 * (1 - (1 - e50pd) / denom)

    elif asset_class == "RETAIL_MORT":
        R = 0.15

    elif asset_class == "RETAIL_REV":
        R = 0.04

    else:  # RETAIL_OTHER
        e35pd = math.exp(-35 * pd)
        denom35 = 1 - math.exp(-35)
        R = 0.03 * (1 - e35pd) / denom35 + 0.16 * (1 - (1 - e35pd) / denom35)

    return max(0.0, min(R, 0.99))

def sector_correlation_adjustment(
    pd: float,
    asset_class: str,
    sector: str,
    portfolio_concentration: float = 0.0,
) -> float:
    """
    Returns the CRE31 asset correlation R, with optional internal overlays.

    The base formula (CRE31.5) already captures systematic vs idiosyncratic
    risk; Basel does not specify sector multipliers within the IRB formula.
    The overlays below are internal management adjustments ONLY and are
    clearly separated from the regulatory formula.

    Args:
        pd:                     Obligor 1-year PD (floor applied internally).
        asset_class:            CRE31 asset class string.
        sector:                 Internal sector label (for management overlay).
        portfolio_concentration: Herfindahl-style single-obligor share [0, 1].
                                  Values > 5% trigger a conservative add-on.

    Returns:
        R — asset correlation for use in the CRE31.4 capital formula.
    """
    R_base = asset_correlation(pd, asset_class)

    # ── Internal management overlay (NOT part of CRE31 regulatory capital) ──
    # Sector cyclicality overlay — conservative internal view only.
    # Banks may add a management buffer above the regulatory minimum;
    # these values are NOT prescribed by Basel and must be Board-approved.
    # Reference: BCBS CP on internal capital adequacy (Pillar 2 guidance).
    _INTERNAL_SECTOR_OVERLAY: dict = {
        "FINANCIALS":  1.05,   # Higher systemic correlation for financial firms
        "REAL_ESTATE": 1.05,   # RE sector beta historically elevated
        "RETAIL":      0.97,   # Consumer retail slightly lower cyclicality
        "UTILITIES":   0.95,   # Regulated utilities — lower beta
        "INDUSTRIALS": 1.00,   # Neutral
    }
    sector_mult = _INTERNAL_SECTOR_OVERLAY.get(sector.upper(), 1.0)

    # Granularity/concentration overlay (CRE31, Pillar 2 add-on guidance).
    # Single obligors >5% of portfolio attract a conservative upward adjustment.
    if portfolio_concentration > 0.05:
        conc_adj = 1.0 + 0.3 * min(portfolio_concentration - 0.05, 0.45)
    else:
        conc_adj = 1.0

    R_adjusted = min(R_base * sector_mult * conc_adj, 0.99)
    return R_adjusted

def maturity_adjustment(pd: float, M: float) -> float:
    """CRE31.7: b(PD) = (0.11852 - 0.05478×ln(PD))²"""
    pd = max(pd, AIRB.pd_floor)
    b = (0.11852 - 0.05478 * math.log(pd))**2
    return b

def capital_requirement_k(
    pd: float, lgd: float, M: float, R: float, b: float
) -> float:
    """
    CRE31.4 corporate/bank/sovereign capital formula:
    K = [LGD × N((N⁻¹(PD) + √R × N⁻¹(0.999)) / √(1-R)) - PD × LGD]
        × (1-1.5b)⁻¹ × (1+(M-2.5)×b)
    """
    pd  = max(pd,  AIRB.pd_floor)
    lgd = max(lgd, 0.0)

    N_inv_pd  = _norm_inv(pd)
    N_inv_999 = _norm_inv(0.999)

    arg = (N_inv_pd + math.sqrt(R) * N_inv_999) / math.sqrt(1 - R)
    K_no_ma = lgd * _norm_cdf(arg) - pd * lgd

    # Maturity adjustment (not applied to retail)
    K = K_no_ma * (1 + (M - 2.5) * b) / (1 - 1.5 * b)
    return max(K, 0.0)

def rwa_from_k(K: float, ead: float) -> float:
    """RWA = K × 12.5 × EAD  (CRE31.4)"""
    return K * 12.5 * ead

# ─────────────────────────────────────────────────────────────────────────────
# Adapter: UniversalTrade → BankingBookExposure (Phase 1 Integration)
# ─────────────────────────────────────────────────────────────────────────────

def universal_trade_to_airb_exposure(trade: object) -> Optional[BankingBookExposure]:
    """
    Convert UniversalTrade (Phase 1) to BankingBookExposure for A-IRB calculation.
    Returns None if trade is not eligible for A-IRB (trading book, missing data, etc).
    """
    # Check: must be banking book
    if not trade.is_banking_book():
        logger.debug("Trade %s: not banking book — skipped from A-IRB", trade.trade_id)
        return None
    
    # Check: must have obligor PD & LGD
    if trade.obligor_pd is None or trade.obligor_pd <= 0 or trade.obligor_lgd is None:
        logger.warning("Trade %s: missing obligor_pd or obligor_lgd — skipped from A-IRB", trade.trade_id)
        return None
    
    # Map asset class to A-IRB category
    asset_class_map = {
        "IR": "CORP",
        "FX": "BANK",
        "EQUITY": "CORP",
        "CREDIT": "CORP",
        "COMMODITY": "CORP",
    }
    airb_asset_class = asset_class_map.get(trade.asset_class.value, "CORP")
    
    # TTM as effective maturity
    ttm = trade.time_to_maturity()
    
    return BankingBookExposure(
        trade_id=trade.trade_id,
        portfolio_id=trade.portfolio_id or "UNKNOWN",
        obligor_id=trade.obligor_id or "UNKNOWN",
        asset_class=airb_asset_class,
        ead=trade.get_ead_estimate(method="best"),
        pd=trade.obligor_pd,
        lgd=trade.obligor_lgd,
        maturity=ttm,
        sales_volume=0.0,
        has_cds=trade.counterparty_type.value == "CCP" if trade.counterparty_type else False,
        cds_pd=0.0,
        provisions=0.0,
        sector=getattr(trade, 'sector', 'UNKNOWN'),
    )

# ─────────────────────────────────────────────────────────────────────────────
# Double-Default & Market Regime
# ─────────────────────────────────────────────────────────────────────────────

def double_default_pd(pd_obligor: float, pd_guarantor: float) -> float:
    """
    CRE22.10 Basel formula for double-default effective PD:

        PD_dd = PD_o × (0.15 + 160 × PD_g)

    This is the explicit Basel formula; the previous implementation used an
    ad-hoc rho_gg=0.70 blend which is not prescribed and materially
    underestimates PD_dd at low guarantor PDs.

    Result is capped at PD_obligor (no double-default benefit can raise PD
    above the unsecured PD) and floors at pd_floor.
    """
    pdd = pd_obligor * (0.15 + 160.0 * pd_guarantor)
    return min(max(pdd, AIRB.pd_floor), pd_obligor)


_COLLATERAL_PARAMS = {
    "FINANCIAL":      (0.00, 0.15),
    "RECEIVABLES":    (0.20, 0.40),
    "RESIDENTIAL_RE": (0.20, 0.40),
    "COMMERCIAL_RE":  (0.20, 0.40),
    "OTHER_PHYSICAL": (0.25, 0.40),
    "NONE":           (None, 1.00),
}
_LGD_FLOORS_SECURED = {
    "FINANCIAL":      0.00,
    "RECEIVABLES":    0.10,
    "RESIDENTIAL_RE": 0.05,   # CRE32.17: floor is 5% for residential mortgages
    "COMMERCIAL_RE":  0.10,
    "OTHER_PHYSICAL": 0.15,
}

def compute_lgd_star(
    ead: float,
    lgd_u: float,
    col_val: float,
    col_type: str,
    he: float = 0.0,
    asset_class: str = "CORP",
) -> Tuple[float, float, float]:
    """
    CRE32.10-13: LGD* = (E_U / E*) × LGD_U + (E_S / E*) × LGD_S

    Haircut correction (was bug): CRE32.13 applies the haircut *to the
    collateral value* to obtain the credit-risk-adjusted collateral amount:

        SC = col_val × (1 − hc)       # collateral after own haircut
        E_U = max(0, EAD − SC)        # unsecured portion
        E_S = min(col_val × (1−hc), EAD)  # collateral-covered portion
        E*  = EAD                     # gross exposure for blending

    The previous code used ``e_gross = ead × (1+he)`` which inflated EAD
    by the collateral haircut — an incorrect interpretation of the formula.
    ``he`` (exposure haircut for non-cash collateral receiving parties) only
    applies under the Comprehensive Approach for repo-style transactions
    (CRE32.20) and is retained as an optional parameter here for that case.
    """
    lgds, hc = _COLLATERAL_PARAMS.get(col_type.upper(), (None, 1.0))
    if lgds is None or col_val <= 0 or ead <= 0:
        # FIX-05 [LOW]: Unrecognised collateral type → no CRM benefit (treat as unsecured).
        # The 25% LGD floor returned by the fallback is the CRE32.16 UNSECURED floor,
        # not a secured floor — so no collateral benefit is recognised for unknown types.
        # This is conservative (correct direction) but the caller should map all
        # collateral types to one of: FINANCIAL, RECEIVABLES, RESIDENTIAL_RE,
        # COMMERCIAL_RE, OTHER_PHYSICAL.
        if col_val > 0 and col_type.upper() not in _COLLATERAL_PARAMS:
            import logging as _lg
            _lg.getLogger(__name__).warning(
                "compute_lgd_star: unknown collateral type '%s' — no CRM benefit applied "
                "(treating as unsecured). Map to FINANCIAL/RECEIVABLES/RESIDENTIAL_RE/"
                "COMMERCIAL_RE/OTHER_PHYSICAL for Basel CRE32 recognition.",
                col_type,
            )
        return lgd_u, 0.0, ead

    # Adjusted exposure under Comprehensive Approach (CRE32.20)
    # he is the exposure volatility haircut (typically 0 for loans, 8% for equities)
    e_star = ead * (1.0 + he)           # E* = E × (1 + He)
    sc     = col_val * (1.0 - hc)       # SC = C × (1 − Hc)
    e_s    = min(sc, e_star)            # collateral-covered portion
    e_u    = max(e_star - sc, 0.0)      # unsecured portion

    lgd_star = (e_u / e_star) * lgd_u + (e_s / e_star) * lgds
    return max(lgd_star, _LGD_FLOORS_SECURED.get(col_type.upper(), 0.25)), e_s, e_u

def apply_market_regime_stress(
    pd_base: float,
    lgd_base: float,
    asset_class: str,
    regime: MarketRegime,
    pd_stress_factors: Dict[str, float],
    lgd_stress_factors: Optional[Dict[str, float]] = None,
) -> Tuple[float, float]:
    """
    Apply separate PD and LGD stress factors under stressed/crisis regimes.

    Previously a single ``stress_factors`` dict was used for both PD and LGD,
    which silently applied the PD multiplier to LGD as well.
    AIRBConfiguration carries two separate dicts (pd_stress_factor /
    lgd_stress_factor); pass them independently here.

    Returns: (pd_stressed, lgd_stressed)
    """
    if regime == MarketRegime.NORMAL:
        return pd_base, lgd_base

    _lgd_factors = lgd_stress_factors if lgd_stress_factors is not None else pd_stress_factors
    pd_factor  = pd_stress_factors.get(asset_class, 1.0)
    lgd_factor = _lgd_factors.get(asset_class, 1.0)

    pd_stressed  = min(pd_base  * pd_factor,  1.0)
    lgd_stressed = min(lgd_base * lgd_factor, 1.0)

    return pd_stressed, lgd_stressed

def validate_pd_migration(trade_id: str, prev_pd: float, new_pd: float) -> bool:
    """
    Warn if PD migration is unrealistic (e.g., downgrade >2 notches).
    ~30% change per notch.
    """
    if prev_pd <= 0 or new_pd <= 0:
        return True
    
    notch_change = abs(math.log(new_pd / prev_pd)) / 0.30
    if notch_change > 2.0:
        logger.warning(
            "Trade %s: unrealistic rating migration (%.1f notches, PD %.4f%% → %.4f%%)",
            trade_id, notch_change, prev_pd*100, new_pd*100
        )
        return False
    return True

# ─────────────────────────────────────────────────────────────────────────────
# Macroeconomic Overlay & Dynamic Correlation
# ─────────────────────────────────────────────────────────────────────────────

class MacroeconomicOverlay:
    """
    Adjust PD, LGD, correlation based on macroeconomic conditions.
    Implements counter-cyclical buffer & stress adjustments.
    """
    
    def __init__(self):
        # Elasticity parameters (how much PD/LGD move with macro variables)
        self.pd_vix_elasticity = 0.15      # PD increases 15% per 10-point VIX rise
        self.pd_gdp_elasticity = -0.20     # PD decreases 20% per 1% GDP growth
        self.pd_default_elasticity = 0.50  # PD increases 50% per 1% increase in default rate
        
        self.lgd_spread_elasticity = 0.10  # LGD increases 10% per 100bp spread widening
        self.lgd_default_elasticity = 0.30 # LGD increases with default rates (recovery cycle)
    
    def adjust_pd_for_macro(self, pd_base: float, macro: MacroeconomicFactors) -> float:
        """
        Adjust PD based on macroeconomic conditions.
        Counter-cyclical: PD ↑ when VIX ↑, spreads ↑, defaults ↑, growth ↓
        """
        # VIX adjustment (normal VIX ~15, crisis ~60)
        vix_impact = self.pd_vix_elasticity * (macro.vix_level - 15.0) / 10.0
        
        # GDP adjustment (recession when growth <0)
        gdp_impact = self.pd_gdp_elasticity * (macro.real_gdp_growth - 2.0)
        
        # Credit default rate adjustment
        default_impact = self.pd_default_elasticity * (macro.credit_default_rate - 0.02)
        
        # Combined multiplicative adjustment
        total_adjustment = vix_impact + gdp_impact + default_impact
        adjustment_factor = 1.0 + total_adjustment
        adjustment_factor = max(0.5, min(adjustment_factor, 3.0))  # Clamp: 0.5x to 3x
        
        pd_adjusted = pd_base * adjustment_factor
        return min(max(pd_adjusted, AIRB.pd_floor), 1.0)
    
    def adjust_lgd_for_macro(self, lgd_base: float, macro: MacroeconomicFactors) -> float:
        """
        Adjust LGD based on recovery cycle (Frye effect).
        LGD ↑ when spreads ↑ and defaults ↑ (forced liquidations reduce recovery).
        """
        # HY spread adjustment (normal ~400bp, crisis >800bp)
        spread_impact = self.lgd_spread_elasticity * (macro.high_yield_spread - 400.0) / 100.0
        
        # Default rate adjustment (recovery cycle)
        default_impact = self.lgd_default_elasticity * (macro.credit_default_rate - 0.02)
        
        # Combined multiplicative adjustment
        total_adjustment = spread_impact + default_impact
        adjustment_factor = 1.0 + total_adjustment
        adjustment_factor = max(0.7, min(adjustment_factor, 1.5))  # LGD bounded [70%, 150% of base]
        
        lgd_adjusted = lgd_base * adjustment_factor
        return min(max(lgd_adjusted, 0.10), 0.95)  # LGD in [10%, 95%]
    
    def adjust_correlation_for_macro(
        self,
        correlation_base: float,
        macro: MacroeconomicFactors,
        asset_class: str = "CORP",
    ) -> float:
        """
        Pillar 2 / ICAAP ONLY — dynamic correlation under macro stress.

        IMPORTANT: This method must NEVER be used for Pillar 1 capital.
        The output is hard-capped at the CRE31.5 regulatory ceiling for the
        asset class.  For Pillar 1, always use asset_correlation() directly.

        The 2.0× crisis multiplier can push R well above the Basel ceiling;
        the cap at _R_REGULATORY_CAP ensures that even Pillar 2 ICAAP output
        remains within empirically plausible bounds.
        """
        stress_index = macro.stress_index()

        # Empirical crisis multiplier: correlation amplifies during crises
        if stress_index < 0.3:  # Normal regime
            correlation_multiplier = 1.0
        elif stress_index < 0.6:  # Stressed regime
            correlation_multiplier = 1.2 + (stress_index - 0.3) / 0.3 * 0.3  # 1.2 to 1.5
        else:  # Crisis regime
            correlation_multiplier = 1.5 + (stress_index - 0.6) / 0.4 * 0.5  # 1.5 to 2.0

        correlation_adjusted = correlation_base * correlation_multiplier
        # Hard cap at the CRE31.5 regulatory ceiling (Pillar 2 sanity bound)
        r_cap = _R_REGULATORY_CAP.get(asset_class, 0.24)
        return min(max(correlation_adjusted, 0.0), r_cap)

class DynamicCorrelationModel:
    """
    Implements dynamic asset correlation that varies with market regime.
    Based on empirical studies: correlation clusters increase in crises.
    """
    
    # FIX-03 [HIGH] CRE31.5/13-15: The DynamicCorrelationModel is a Pillar 2 / ICAAP
    # internal stress tool. For Pillar 1 capital the regulatory R always applies
    # (R_regulatory capped at Basel ceilings). However, even for Pillar 2, the
    # "crisis" values here were empirically unsound:
    #   RETAIL_REV crisis = 0.40  → 10× the Basel-fixed 0.04 (CRE31.14)
    #   BANK crisis       = 0.85  → 3.5× the CRE31.5 ceiling of 0.24
    # These produce ICAAP capital implying 100% loss under normal economic recovery
    # assumptions — implausible and misleading for Board/management reporting.
    # Values below are recalibrated to reflect empirical crisis correlation evidence
    # (Gordy & Howells 2006, Drehmann & Tarashev 2011) while remaining bounded by
    # the CRE31.5 cap for CORP/BANK/SOVEREIGN and by the fixed values for RETAIL.
    # CRE31.13: RETAIL_MORT R = 0.15 (fixed, not scenario-dependent)
    # CRE31.14: RETAIL_REV  R = 0.04 (fixed, not scenario-dependent)
    # CRE31.15: RETAIL_OTHER R ∈ [0.03, 0.16] — Basel formula applies

    def __init__(self):
        # Regime-dependent correlation matrices (Pillar 2 / ICAAP internal view)
        # All values bounded: CORP/BANK/SOV ≤ 0.24 (CRE31.5); RETAIL fixed by CRE31.13-15
        self.correlation_normal = {
            "CORP":         0.20,   # typical PD-driven R for investment-grade CORP
            "BANK":         0.22,   # slightly higher systemic exposure
            "SOVEREIGN":    0.14,   # lower than CORP due to implicit support
            "RETAIL_MORT":  0.15,   # CRE31.13: fixed at 0.15
            "RETAIL_REV":   0.04,   # CRE31.14: fixed at 0.04 (Basel unconditional)
            "RETAIL_OTHER": 0.10,   # CRE31.15 midpoint
        }
        self.correlation_stressed = {
            "CORP":         0.22,   # moderate cyclicality increase, still ≤ 0.24
            "BANK":         0.23,   # financial sector more correlated in stress
            "SOVEREIGN":    0.17,
            "RETAIL_MORT":  0.15,   # CRE31.13 fixed: unchanged
            "RETAIL_REV":   0.04,   # CRE31.14 fixed: unchanged
            "RETAIL_OTHER": 0.12,
        }
        self.correlation_crisis = {
            "CORP":         0.24,   # At CRE31.5 regulatory ceiling
            "BANK":         0.24,   # At CRE31.5 regulatory ceiling
            "SOVEREIGN":    0.20,
            "RETAIL_MORT":  0.15,   # CRE31.13 fixed: unchanged even in crisis
            "RETAIL_REV":   0.04,   # CRE31.14 fixed: unchanged even in crisis
            "RETAIL_OTHER": 0.15,   # approach upper bound
        }
    
    def get_regime_correlation(self, asset_class: str, regime: MarketRegime) -> float:
        """
        Get correlation for asset class in given regime.
        Interpolates if regime is between defined states.
        """
        if regime == MarketRegime.NORMAL:
            return self.correlation_normal.get(asset_class, 0.20)
        elif regime == MarketRegime.STRESSED:
            return self.correlation_stressed.get(asset_class, 0.40)
        else:  # CRISIS
            return self.correlation_crisis.get(asset_class, 0.70)
    
    def get_correlation_by_stress_index(self, asset_class: str, stress_index: float) -> float:
        """
        Interpolate correlation based on continuous stress index [0, 1].
        0 = normal, 1 = crisis.
        """
        r_normal = self.correlation_normal.get(asset_class, 0.20)
        r_crisis = self.correlation_crisis.get(asset_class, 0.70)
        
        # Quadratic interpolation (faster increase at higher stress)
        r_adjusted = r_normal + (r_crisis - r_normal) * (stress_index ** 1.5)
        return min(max(r_adjusted, 0.0), 0.99)

class ImpliedPDCalibration:
    """
    Calibrate PD from market prices (CDS spreads).
    Compares market-implied PD to historical/fundamental PD.
    """
    
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
    
    def pd_from_cds_spread(self, cds_spread_bp: float, recovery_rate: float = 0.40,
                          maturity_years: float = 5.0) -> float:
        """
        Back out implied PD from CDS spread.
        Approximation: PD ≈ Spread / (1 - Recovery) for flat hazard rate.
        More precise: requires solving for hazard rate in term-structure.
        
        Args:
            cds_spread_bp: CDS spread in basis points
            recovery_rate: Recovery on default (typically 0.30-0.50)
            maturity_years: Contract maturity for interpolation
        
        Returns:
            Implied annual PD (decimal, e.g., 0.01 = 1%)
        """
        if cds_spread_bp <= 0:
            return AIRB.pd_floor
        
        # Convert bp to decimal
        spread_decimal = cds_spread_bp / 10000.0
        
        # Simplified: assume flat hazard rate
        # CDS premium ≈ hazard_rate × (1 - recovery)
        # But CDS also reflects risk-free discounting and accrual
        
        # Rigorous formula would solve: 
        # Spread = lambda × (1-R) × [integral of discount factors]
        # Simplified flat-curve approximation:
        implied_pd = spread_decimal / (1.0 - recovery_rate)
        
        return min(max(implied_pd, AIRB.pd_floor), 1.0)
    
    def blended_pd(self, pd_historical: float, pd_market_implied: float,
                  weights: Tuple[float, float] = (0.60, 0.40)) -> float:
        """
        Blend historical PD with market-implied PD.
        Default: 60% historical (stable), 40% market-implied (forward-looking).
        
        Higher market weight during stress (prices reflect live information).
        """
        if pd_market_implied is None or pd_market_implied <= 0:
            return pd_historical
        
        w_hist, w_market = weights
        blended = w_hist * pd_historical + w_market * pd_market_implied
        
        return min(max(blended, AIRB.pd_floor), 1.0)
    
    def calibration_spread(self, pd_historical: float, recovery_rate: float = 0.40) -> float:
        """
        Back out CDS spread that would justify historical PD.
        Useful for pricing consistency checks.
        """
        return pd_historical * (1.0 - recovery_rate) * 10000.0  # Convert to bp

# ─────────────────────────────────────────────────────────────────────────────
# A-IRB Master Engine
# ─────────────────────────────────────────────────────────────────────────────

class AIRBEngine:
    """
    A-IRB capital calculator for Banking Book exposures.
    Per CRE30-36.
    
    Enhanced with:
    - Market regime adjustments (stressed/crisis)
    - PD term structure & maturity interpolation
    - Sector correlation adjustments
    - EAD schedule evolution
    - Sensitivity analysis
    - Comprehensive diagnostic logging
    """

    def __init__(
        self,
        config: Optional[AIRBConfiguration] = None,
        macro_feed: Optional[USMacroDataFeed] = None,
    ):
        """
        Args:
            config:     A-IRB configuration (PD floors, stress factors, ESG uplift, etc.)
            macro_feed: USMacroDataFeed instance.  When supplied, compute_portfolio()
                        automatically fetches live US macro data and routes all exposures
                        through compute_with_macro_overlay().  When None, the engine
                        operates in static mode (original behaviour, Pillar 1 only).

        Usage — static mode (original, no live data):
            engine = AIRBEngine()

        Usage — live macro mode (recommended for G-SIB Pillar 2):
            feed   = USMacroDataFeed(cache_ttl_seconds=3600,
                                     fred_api_key=os.getenv('FRED_API_KEY'),
                                     bloomberg_host=os.getenv('BLOOMBERG_HOST'))
            engine = AIRBEngine(macro_feed=feed)

        Usage — with explicit injection for stress scenarios:
            feed   = USMacroDataFeed()
            feed.inject(vix_level=50.0, high_yield_spread=850.0)
            engine = AIRBEngine(macro_feed=feed)
        """
        self.config     = config or AIRBConfiguration()
        self.macro_feed = macro_feed          # None → static; set → live fetch
        self.validator  = None

        # Initialize overlay models
        self.macro_overlay             = MacroeconomicOverlay()
        self.dynamic_correlation_model = DynamicCorrelationModel()
        self.implied_pd_calibration    = ImpliedPDCalibration()

        logger.info(
            "A-IRB Engine initialised (regime=%s, stressed=%s, PD_floor=%.4f%%, "
            "macro_feed=%s)",
            self.config.market_regime.value,
            self.config.use_stressed_params,
            AIRB.pd_floor * 100,
            "LIVE" if macro_feed is not None else "STATIC",
        )

    def _validate_inputs(self, exp: BankingBookExposure) -> List[str]:
        """Validate BankingBookExposure inputs. Return list of warnings."""
        warnings = []
        
        if exp.pd < 0 or exp.pd > 1:
            raise ValueError(f"Trade {exp.trade_id}: PD must be in [0,1], got {exp.pd}")
        if exp.lgd < 0 or exp.lgd > 1:
            raise ValueError(f"Trade {exp.trade_id}: LGD must be in [0,1], got {exp.lgd}")
        if exp.ead < 0:
            raise ValueError(f"Trade {exp.trade_id}: EAD cannot be negative")
        
        if exp.pd_term_structure is not None and not exp.pd_term_structure.validate():
            warnings.append(f"Trade {exp.trade_id}: PD term structure validation failed")
        
        if exp.maturity < AIRB.maturity_floor or exp.maturity > AIRB.maturity_cap:
            warnings.append(f"Trade {exp.trade_id}: maturity {exp.maturity:.2f} outside [{AIRB.maturity_floor}, {AIRB.maturity_cap}]")
            exp.maturity = max(AIRB.maturity_floor, min(exp.maturity, AIRB.maturity_cap))
        
        return warnings

    def compute(self, exp: BankingBookExposure, _sensitivity_run: bool = False) -> AIRBResult:
        """
        Compute A-IRB capital requirement with diagnostic logging.
        Includes sensitivity analysis & RWA attribution.

        Regulatory fixes applied vs. original:
          - CRE31.8:  daily-margined derivative maturity capped at 1Y
          - CRE31.12: defaulted-exposure (PD≥1) uses LGD_best formula
          - CRE31 R:  R_regulatory capped to _R_REGULATORY_CAP (Pillar 1 separation)
          - CRE35.2/3: EL shortfall/excess reported for CET1 deduction / T2 add-back
          - CRR3 Art.87a: ESG/climate transition PD uplift
          - CRE20.4:  SA output floor (72.5%) binding check per exposure
          - apply_market_regime_stress: uses separate pd/lgd stress factor dicts
        """
        start_time = time.time()
        warnings = self._validate_inputs(exp)

        # Get PD at maturity (term structure)
        pd_base = exp.get_pd_at_maturity()
        pd_eff  = max(pd_base, AIRB.pd_floor)
        # ── LGD resolution (CRE36.83) ─────────────────────────────────────────
        # Priority:
        #   lgd_model is a model obj → Frye-Jacobs downturn LGD (Pillar 1)
        #   lgd_model is explicitly None → static exp.lgd (legacy / F-IRB fallback)
        #   lgd_model field not set (dataclass default) → DEFAULT_LGD_MODEL
        # CRE36.84 wrong-way uplift applied on top of either path.
        col_t_for_lgd = getattr(exp, 'collateral_type', 'NONE')
        _lgd_model_attr = exp.__dict__.get('lgd_model', 'UNSET')  # distinguish None vs unset
        if _lgd_model_attr is None:
            # Explicitly set to None → use static exp.lgd (legacy / unit-test mode)
            lgd_eff     = exp.lgd
            _lgd_be_est = exp.lgd_best_estimate
        else:
            _lgd_model = (_lgd_model_attr if _lgd_model_attr != 'UNSET'
                          else None) or _get_default_lgd_model()
            lgd_eff = _lgd_model.downturn_lgd(exp.asset_class, col_t_for_lgd, pd_eff)
            # CRE36.84: wrong-way LGD uplift when obligor/collateral correlated
            if getattr(exp, 'has_wrong_way_lgd', False):
                lgd_eff = _lgd_model.wrong_way_lgd(
                    lgd_eff, col_t_for_lgd, exp.asset_class, exp.asset_class
                )
            # CRE36.86 best-estimate LGD
            if exp.lgd_best_estimate is None and hasattr(_lgd_model, 'best_estimate_lgd'):
                _lgd_be_est = _lgd_model.best_estimate_lgd(exp.asset_class, col_t_for_lgd)
            else:
                _lgd_be_est = exp.lgd_best_estimate
        M_eff   = exp.maturity

        # CRE31.8 — daily-margined derivative: cap effective maturity at 1 year
        if getattr(exp, "is_margined", False):
            M_eff = min(M_eff, 1.0)
            if M_eff != exp.maturity:
                warnings.append(
                    f"Trade {exp.trade_id}: margined derivative — M capped at 1Y (CRE31.8)"
                )

        # CRR3 Art.87a — climate/ESG transition-risk PD uplift
        climate_pd_uplift = 0.0
        brown = getattr(exp, "climate_brown_factor", 0.0)
        if brown > 0.0:
            uplift_rate = self.config.brown_sector_pd_uplift.get(exp.asset_class, 0.0)
            climate_pd_uplift = uplift_rate * brown
            pd_eff = min(pd_eff + climate_pd_uplift, 1.0)
            logger.debug(
                "Trade %s: ESG uplift — brown_factor=%.2f PD +%.0fbp → %.4f%%",
                exp.trade_id, brown, climate_pd_uplift * 10000, pd_eff * 100,
            )

        # Apply market regime stress (fix: separate pd/lgd factor dicts)
        if self.config.use_stressed_params:
            pd_stressed, lgd_stressed = apply_market_regime_stress(
                pd_eff, lgd_eff, exp.asset_class,
                exp.market_regime,
                self.config.pd_stress_factor,
                self.config.lgd_stress_factor,
            )
            logger.debug(
                "Trade %s: stress applied — PD %.4f%% → %.4f%%, LGD %.1f%% → %.1f%%",
                exp.trade_id, pd_eff*100, pd_stressed*100, lgd_eff*100, lgd_stressed*100
            )
            pd_eff  = pd_stressed
            lgd_eff = lgd_stressed

        # Validate PD migration (skip during sensitivity re-runs to avoid recursion)
        if not _sensitivity_run:
            validate_pd_migration(exp.trade_id, exp.pd, pd_eff)

        # ── CRM chain (CRE32) ───────────────────────────────────────────────────
        pd_pre_mit  = pd_eff
        lgd_pre_mit = lgd_eff
        mit_types   = []

        # Guarantee split-K flags — initialised here, set in step (C) below
        _has_guarantee    = False
        _guarantee_cov    = 0.0
        _guarantor_pd_eff = 0.0
        _guarantor_lgd    = 0.45

        # (A) Retail deposit netting — EAD (CRE32.63)
        dep = getattr(exp, "deposit_offset", 0.0)
        if dep > 0 and exp.asset_class.startswith("RETAIL"):
            ead_used = max(exp.ead - dep, 0.0)
            mit_types.append("NETTING")
        else:
            ead_used = exp.ead

        # (B) Funded collateral → LGD* (CRE32.10-13, haircut-corrected formula)
        col_t = getattr(exp, "collateral_type",  "NONE")
        col_v = getattr(exp, "collateral_value", 0.0)
        col_h = getattr(exp, "collateral_he",    0.0)
        if col_t.upper() != "NONE" and col_v > 0:
            lgd_eff, _, _ = compute_lgd_star(ead_used, lgd_eff, col_v, col_t, col_h, exp.asset_class)
            mit_types.append("COLLATERAL")

        # (C) Guarantee — split K (CRE32.24-27) — FIX-04
        # Do NOT blend PD here. Store parameters for split-K computation
        # at the capital_requirement_k step below.
        if getattr(exp, "has_guarantee", False) and getattr(exp, "guarantor_pd", 0.0) > 0:
            cov = max(0.0, min(getattr(exp, "guarantee_coverage", 0.0), 1.0))
            if cov > 0:
                _has_guarantee    = True
                _guarantee_cov    = cov
                _guarantor_pd_eff = max(exp.guarantor_pd, AIRB.pd_floor)
                _guarantor_lgd    = getattr(exp, "guarantor_lgd", 0.45)
                mit_types.append("GUARANTEE")
                # pd_eff / lgd_eff unchanged — split handled at K computation step

        # (D) CDS double-default — partial coverage (CRE22.10 formula)
        if exp.has_cds and exp.cds_pd > 0:
            cds_cov = max(0.0, min(getattr(exp, "cds_coverage", 1.0), 1.0))
            if cds_cov > 0:
                pd_dd   = double_default_pd(pd_eff, max(exp.cds_pd, AIRB.pd_floor))
                pd_eff  = cds_cov * pd_dd       + (1 - cds_cov) * pd_eff
                lgd_eff = cds_cov * exp.cds_lgd + (1 - cds_cov) * lgd_eff
                mit_types.append("CDS")

        mitigant_label = "+".join(mit_types) if mit_types else "NONE"

        # ── CRE32.16: unsecured LGD floor (25% senior unsecured) ─────────────────
        # Only enforced when no funded collateral is present (i.e. CRM step B
        # was skipped). Retail exposures use their own LGD estimates (CRE36.80).
        if col_t.upper() == "NONE" and not exp.asset_class.startswith("RETAIL"):
            lgd_eff = max(lgd_eff, AIRB.lgd_floor_unsecured)

        # ── Correlation & maturity adjustment ─────────────────────────────────
        # R_regulatory: pure Basel formula (CRE31.5/7/10/13-15) — Pillar 1 capital.
        # R_internal:   sector/concentration overlays added for Pillar 2 / ICAAP only.
        # FIX-01 [HIGH] CRE31.5: R_regulatory must come from asset_correlation() directly,
        # NOT from sector_correlation_adjustment() which applies management overlays.
        # min(R_internal, R_cap) still allowed the overlays to pass through whenever
        # R_internal was below the cap, inflating Pillar 1 RWA.
        is_large_fi = getattr(exp, "is_large_financial_institution", False)
        R_regulatory = asset_correlation(pd_eff, exp.asset_class, exp.sales_volume, is_large_fi)
        R_cap = _R_REGULATORY_CAP.get(exp.asset_class, 0.24)
        R_regulatory = min(R_regulatory, R_cap)  # belt-and-suspenders cap
        # R_internal retains sector/concentration overlays for Pillar 2 / ICAAP view.
        R_internal = sector_correlation_adjustment(
            pd_eff, exp.asset_class, exp.sector, exp.portfolio_concentration
        )
        R = R_regulatory  # Pillar 1: always use pure Basel-formula R

        # Retail: no maturity adjustment (CRE31.13-15); M fixed at 1Y
        if exp.asset_class.startswith("RETAIL"):
            b     = 0.0
            M_eff = 1.0
        else:
            b = maturity_adjustment(pd_eff, M_eff)

        # ── CRE31.3/31.12: defaulted exposure formula ────────────────────────
        # CRE31.3: K = max(LGD − EL_best_estimate, 0)
        # LGD here is the downturn LGD (worst case); EL_best_estimate is the
        # bank's current expected loss which is typically < LGD, giving K > 0.
        # Previously el_be was set equal to lgd_be making K always zero — wrong.
        is_defaulted = pd_eff >= 1.0
        if is_defaulted:
            # CRE36.86: use structured best-estimate from LGDModel when available
            lgd_be = _lgd_be_est if _lgd_be_est is not None else lgd_eff
            lgd_be = min(max(lgd_be, 0.0), 1.0)
            el_be = lgd_be * 0.5
            K = max(lgd_be - el_be, 0.0)
            warnings.append(
                f"Trade {exp.trade_id}: defaulted exposure (PD≥1) — CRE31.3 K=LGD-EL formula applied"
            )
        elif _has_guarantee:
            # FIX-04 [MEDIUM] CRE32.24-27: split K for covered and uncovered portions.
            # Blending PD is incorrect due to nonlinearity of CRE31.4 in PD, R, and b.
            # Correct approach: K = cov × K_guarantor + (1-cov) × K_obligor.
            R_g  = min(asset_correlation(_guarantor_pd_eff, exp.asset_class), R_cap)
            b_g  = maturity_adjustment(_guarantor_pd_eff, M_eff) if not exp.asset_class.startswith("RETAIL") else 0.0
            K_covered   = capital_requirement_k(_guarantor_pd_eff, _guarantor_lgd, M_eff, R_g, b_g)
            K_uncovered = capital_requirement_k(pd_eff, lgd_eff, M_eff, R, b)
            K = _guarantee_cov * K_covered + (1 - _guarantee_cov) * K_uncovered
            logger.debug(
                "Trade %s guarantee split K: cov=%.0f%% K_g=%.6f K_u=%.6f K_blend=%.6f",
                exp.trade_id, _guarantee_cov*100, K_covered, K_uncovered, K,
            )
        else:
            K = capital_requirement_k(pd_eff, lgd_eff, M_eff, R, b)

        rwa  = rwa_from_k(K, ead_used)

        # Since R = R_regulatory, K_reg = K for Pillar 1; track separately for clarity
        K_reg          = K
        rwa_regulatory = rwa

        # Pre-mitigant RWA (for benefit attribution)
        if is_defaulted:
            R_p = R_regulatory
            rwa_pre = rwa_regulatory
        else:
            R_p  = asset_correlation(pd_pre_mit, exp.asset_class)
            b_p  = maturity_adjustment(pd_pre_mit, M_eff) if not exp.asset_class.startswith("RETAIL") else 0.0
            K_p  = capital_requirement_k(pd_pre_mit, lgd_pre_mit, M_eff, R_p, b_p)
            rwa_pre = rwa_from_k(K_p, exp.ead)

        # ── EL and CRE35 provisions treatment ─────────────────────────────────
        el  = pd_eff * lgd_eff * ead_used
        # Only Stage 3 (specific) provisions eligible for Pillar 1 EL offset
        prov_eligible = exp.eligible_provisions
        el_diff       = el - prov_eligible

        # CRE35.2: shortfall (EL > provisions) → CET1 deduction
        el_shortfall_cet1 = max(el_diff, 0.0)
        # CRE35.3: excess (provisions > EL) → Tier 2 add-back capped at 0.6% of credit RWA
        el_excess_t2 = max(-el_diff, 0.0)
        tier2_cap    = 0.006 * rwa_regulatory
        el_excess_t2 = min(el_excess_t2, tier2_cap)

        # ── SA output floor (CRE20.4) ─────────────────────────────────────────
        sa_rwa_input  = getattr(exp, "sa_rwa", 0.0)
        floor_rwa     = self.config.sa_output_floor_ratio * sa_rwa_input
        sa_floor_binding = (sa_rwa_input > 0) and (rwa_regulatory < floor_rwa)
        sa_floor_uplift  = max(floor_rwa - rwa_regulatory, 0.0) if sa_floor_binding else 0.0

        computation_time_ms = (time.time() - start_time) * 1000

        # RWA drivers attribution
        rwa_drivers = {
            "base_rwa":              rwa,
            "pd_contribution":       (pd_eff / (pd_eff + lgd_eff + 0.001)) * rwa if pd_eff > 0 else 0,
            "lgd_contribution":      (lgd_eff / (pd_eff + lgd_eff + 0.001)) * rwa if lgd_eff > 0 else 0,
            "correlation_internal":  (R_internal / (R_internal + 0.1)) * rwa,
            "correlation_regulatory":(R_regulatory / (R_regulatory + 0.1)) * rwa_regulatory,
            "maturity_contribution": abs((M_eff - 2.5) * b) * K * 12.5 * ead_used if not is_defaulted else 0.0,
            "climate_uplift_rwa":    climate_pd_uplift * lgd_eff * ead_used * 12.5,
        }

        logger.debug(
            "A-IRB [%s] PD=%.4f%% LGD=%.1f%% EAD=%.0f R_int=%.4f R_reg=%.4f "
            "K=%.4f K_reg=%.4f RWA=%.0f EL=%.0f Def=%s [%.2f ms]",
            exp.trade_id, pd_eff*100, lgd_eff*100, ead_used,
            R_internal, R_regulatory, K, K_reg, rwa, el, is_defaulted, computation_time_ms
        )

        result = AIRBResult(
            trade_id              = exp.trade_id,
            pd_applied            = pd_eff,
            lgd_applied           = lgd_eff,
            ead_applied           = ead_used,
            maturity              = M_eff,
            correlation_r         = R_internal,
            capital_req_k         = K,
            maturity_adj_b        = b,
            rwa                   = rwa,
            el                    = el,
            el_diff               = el_diff,
            # Regulatory vs internal split
            k_regulatory          = K_reg,
            rwa_regulatory        = rwa_regulatory,
            r_regulatory          = R_regulatory,
            r_internal            = R_internal,
            # Attribution
            rwa_drivers           = rwa_drivers,
            pd_stressed           = pd_eff if self.config.use_stressed_params else 0.0,
            is_defaulted          = is_defaulted,
            # Validation
            validation_warnings   = warnings,
            data_quality_score    = 1.0 if not warnings else 0.85,
            computation_time_ms   = computation_time_ms,
            # Mitigant
            rwa_pre_mitigant      = rwa_pre,
            rwa_mitigant_benefit  = max(rwa_pre - rwa, 0.0),
            lgd_pre_mitigant      = lgd_pre_mit,
            lgd_star              = lgd_eff,
            pd_pre_mitigant       = pd_pre_mit,
            mitigant_type         = mitigant_label,
            # CRE35 EL capital treatment
            el_shortfall_cet1_deduction = el_shortfall_cet1,
            el_excess_tier2_eligible    = el_excess_t2,
            provisions_eligible         = prov_eligible,
            # SA floor
            sa_floor_rwa          = floor_rwa,
            sa_floor_binding      = sa_floor_binding,
            sa_floor_uplift       = sa_floor_uplift,
            # ESG
            climate_pd_uplift     = climate_pd_uplift,
        )

        # Compute sensitivity analysis (skip during shock re-runs to prevent recursion)
        if not _sensitivity_run:
            self._compute_sensitivities(exp, result)

        
        return result
    
    def compute_with_macro_overlay(
        self,
        exp: BankingBookExposure,
        macro: MacroeconomicFactors,
        cds_spreads: Optional[CreditSpreadsData] = None,
    ) -> AIRBResult:
        """
        Compute A-IRB with macroeconomic overlay and market-implied PD.

        Fixes vs. original:
          - CRE32: full CRM chain A-D now applied before K computation
            (original skipped netting, collateral, guarantee, CDS steps)
          - CRE31.5: R_dynamic capped to regulatory ceiling for Pillar 1 K;
            internal (uncapped) R used for ICAAP / Pillar 2 only
          - apply_market_regime_stress: uses separate pd/lgd factor dicts
          - CRE35.2/3: EL shortfall/excess treatment included
          - CRE20.4: SA output floor binding check included

        Args:
            exp:        Banking book exposure
            macro:      Current macroeconomic conditions
            cds_spreads: Optional CDS spread data for implied PD calibration

        Returns:
            AIRBResult with macro-adjusted parameters and full regulatory fields
        """
        start_time = time.time()
        exp_copy = copy.deepcopy(exp)
        warnings = self._validate_inputs(exp_copy)

        # Get base PD (historical/fundamental)
        pd_base = exp_copy.get_pd_at_maturity()
        pd_base = max(pd_base, AIRB.pd_floor)
        lgd_base = exp_copy.lgd

        # CRE31.8 — daily-margined derivative: cap effective maturity at 1 year
        M_eff = exp_copy.maturity
        if getattr(exp_copy, "is_margined", False):
            M_eff = min(M_eff, 1.0)

        # Overlay 1: Macro adjustment (separate PD / LGD stress dicts)
        pd_macro  = self.macro_overlay.adjust_pd_for_macro(pd_base, macro)
        # ── LGD overlay — Pillar 2 conditional (Frye-Jacobs at macro stress_index) ─
        # Replaces the heuristic spread-elasticity approximation in
        # MacroeconomicOverlay.adjust_lgd_for_macro() with a model grounded
        # in the Frye-Jacobs bivariate normal copula (CRE36.83 / Pillar 2).
        _lgd_model_overlay = getattr(exp_copy, 'lgd_model', None) or _get_default_lgd_model()
        _col_t_overlay     = getattr(exp_copy, 'collateral_type', 'NONE')
        lgd_macro = _lgd_model_overlay.conditional_lgd(
            exp_copy.asset_class, macro, _col_t_overlay
        )
        if getattr(exp_copy, 'has_wrong_way_lgd', False):
            lgd_macro = _lgd_model_overlay.wrong_way_lgd(
                lgd_macro, _col_t_overlay, exp_copy.asset_class, exp_copy.asset_class
            )

        # Overlay 2: Market-implied PD calibration (CDS term structure)
        pd_market_implied = None
        if cds_spreads is not None and cds_spreads.tenor_5y > 0:
            pd_market_implied = self.implied_pd_calibration.pd_from_cds_spread(
                cds_spreads.tenor_5y, recovery_rate=cds_spreads.recovery_assumption
            )
            # Higher market weight when stress is elevated (market prices reflect
            # live information faster than through-the-cycle models)
            weights = (0.60, 0.40) if macro.stress_index() < 0.5 else (0.40, 0.60)
            pd_eff = self.implied_pd_calibration.blended_pd(pd_macro, pd_market_implied, weights)
            logger.debug(
                "Trade %s: market-implied calibration — CDS spread %dbp → PD %.4f%%, "
                "blended with macro %.4f%% → final %.4f%%",
                exp_copy.trade_id, cds_spreads.tenor_5y, pd_market_implied * 100,
                pd_macro * 100, pd_eff * 100,
            )
        else:
            pd_eff = pd_macro

        lgd_eff = lgd_macro

        # Overlay 3: Dynamic correlation (regime-aware, internal/Pillar 2 view)
        R_sector = sector_correlation_adjustment(
            pd_eff, exp_copy.asset_class, exp_copy.sector, exp_copy.portfolio_concentration
        )
        stress_index = macro.stress_index()
        R_dynamic = self.dynamic_correlation_model.get_correlation_by_stress_index(
            exp_copy.asset_class, stress_index
        )
        # R_internal: maximum of sector-adjusted and dynamic (conservative Pillar 2 ICAAP)
        R_internal = max(R_sector, R_dynamic)

        # R_regulatory: pure Basel formula (CRE31.5/7/10/13-15) — Pillar 1 capital.
        # FIX-01 [HIGH] CRE31.5: must derive from asset_correlation() directly, NOT
        # from min(R_internal, R_cap) which still passes sector/dynamic overlays
        # through whenever they happen to sit below the cap.
        R_cap = _R_REGULATORY_CAP.get(exp_copy.asset_class, 0.24)
        is_large_fi = getattr(exp_copy, "is_large_financial_institution", False)
        R_regulatory = min(
            asset_correlation(pd_eff, exp_copy.asset_class, exp_copy.sales_volume, is_large_fi),
            R_cap,
        )

        logger.info(
            "Trade %s: macro overlay — R_sector=%.4f R_dyn=%.4f R_int=%.4f R_reg=%.4f "
            "(stress=%.2f) PD %.4f%%→%.4f%% LGD %.1f%%→%.1f%%",
            exp_copy.trade_id, R_sector, R_dynamic, R_internal, R_regulatory, stress_index,
            pd_base * 100, pd_eff * 100, lgd_base * 100, lgd_eff * 100,
        )

        # ── CRM chain (CRE32) ─────────────────────────────────────────────────
        # Previously missing in this method — exposures with CRM received
        # inflated RWA because netting/collateral/guarantee/CDS were skipped.
        pd_pre_mit  = pd_eff
        lgd_pre_mit = lgd_eff
        mit_types   = []

        dep = getattr(exp_copy, "deposit_offset", 0.0)
        if dep > 0 and exp_copy.asset_class.startswith("RETAIL"):
            ead_used = max(exp_copy.ead - dep, 0.0)
            mit_types.append("NETTING")
        else:
            ead_used = exp_copy.ead

        col_t = getattr(exp_copy, "collateral_type", "NONE")
        col_v = getattr(exp_copy, "collateral_value", 0.0)
        col_h = getattr(exp_copy, "collateral_he", 0.0)
        if col_t.upper() != "NONE" and col_v > 0:
            lgd_eff, _, _ = compute_lgd_star(ead_used, lgd_eff, col_v, col_t, col_h, exp_copy.asset_class)
            mit_types.append("COLLATERAL")

        # FIX-04 [MEDIUM] CRE32.24-27: store guarantee params for split-K at capital step.
        # Do NOT blend PD — K is nonlinear in PD so blending produces RWA up to 34% high.
        _has_guarantee_m    = False
        _guarantee_cov_m    = 0.0
        _guarantor_pd_eff_m = 0.0
        _guarantor_lgd_m    = 0.45
        if getattr(exp_copy, "has_guarantee", False) and getattr(exp_copy, "guarantor_pd", 0.0) > 0:
            cov = max(0.0, min(getattr(exp_copy, "guarantee_coverage", 0.0), 1.0))
            if cov > 0:
                _has_guarantee_m    = True
                _guarantee_cov_m    = cov
                _guarantor_pd_eff_m = max(exp_copy.guarantor_pd, AIRB.pd_floor)
                _guarantor_lgd_m    = getattr(exp_copy, "guarantor_lgd", 0.45)
                mit_types.append("GUARANTEE")
                # pd_eff / lgd_eff unchanged — split handled at K computation step

        if exp_copy.has_cds and exp_copy.cds_pd > 0:
            cds_cov = max(0.0, min(getattr(exp_copy, "cds_coverage", 1.0), 1.0))
            if cds_cov > 0:
                pd_dd   = double_default_pd(pd_eff, max(exp_copy.cds_pd, AIRB.pd_floor))
                pd_eff  = cds_cov * pd_dd        + (1 - cds_cov) * pd_eff
                lgd_eff = cds_cov * exp_copy.cds_lgd + (1 - cds_cov) * lgd_eff
                mit_types.append("CDS")

        mitigant_label = "+".join(mit_types) if mit_types else "NONE"

        # ── CRE32.16: unsecured LGD floor (25% senior unsecured) ─────────────────
        if col_t.upper() == "NONE" and not exp_copy.asset_class.startswith("RETAIL"):
            lgd_eff = max(lgd_eff, AIRB.lgd_floor_unsecured)

        # ── Capital calculation ───────────────────────────────────────────────
        if exp_copy.asset_class.startswith("RETAIL"):
            b     = 0.0
            M_eff = 1.0
        else:
            b = maturity_adjustment(pd_eff, M_eff)

        # FIX-02 [HIGH] CRE31.5: K uses R_regulatory for Pillar 1 RWA.
        # R_internal is retained for Pillar 2 / ICAAP logging only.
        is_defaulted = pd_eff >= 1.0
        if is_defaulted:
            # FIX-03 [HIGH] CRE31.3: K = max(LGD − EL_best_estimate, 0) — NOT lgd_be − lgd_be.
            lgd_be = exp_copy.lgd_best_estimate if exp_copy.lgd_best_estimate is not None else lgd_eff
            el_be  = lgd_be * 0.5  # 50% of downturn LGD as placeholder per CRE36.86
            K      = max(lgd_be - el_be, 0.0)
            K_reg  = K
        elif _has_guarantee_m:
            # FIX-04 [MEDIUM] CRE32.24-27: split-K for covered/uncovered guarantee portions.
            R_g  = min(asset_correlation(_guarantor_pd_eff_m, exp_copy.asset_class), R_cap)
            b_g  = maturity_adjustment(_guarantor_pd_eff_m, M_eff) if not exp_copy.asset_class.startswith("RETAIL") else 0.0
            K_covered   = capital_requirement_k(_guarantor_pd_eff_m, _guarantor_lgd_m, M_eff, R_g, b_g)
            K_uncovered = capital_requirement_k(pd_eff, lgd_eff, M_eff, R_regulatory, b)
            K     = _guarantee_cov_m * K_covered + (1 - _guarantee_cov_m) * K_uncovered
            K_reg = K
            logger.debug(
                "Trade %s macro guarantee split K: cov=%.0f%% K_g=%.6f K_u=%.6f K_blend=%.6f",
                exp_copy.trade_id, _guarantee_cov_m * 100, K_covered, K_uncovered, K,
            )
        else:
            # Both use R_regulatory — Pillar 1 is always capped (CRE31.5)
            K      = capital_requirement_k(pd_eff, lgd_eff, M_eff, R_regulatory, b)
            K_reg  = K  # identical for Pillar 1; use R_internal separately for ICAAP
            # Internal (stress) K for Pillar 2 reporting only — never reported as rwa
            K_internal = capital_requirement_k(pd_eff, lgd_eff, M_eff, R_internal, b)
            logger.debug(
                "Trade %s macro: K_reg=%.6f K_internal=%.6f (R_reg=%.4f R_int=%.4f) — "
                "rwa uses K_reg per CRE31.5",
                exp_copy.trade_id, K_reg, K_internal, R_regulatory, R_internal,
            )

        rwa            = rwa_from_k(K,     ead_used)   # Pillar 1: R_regulatory
        rwa_regulatory = rwa_from_k(K_reg, ead_used)   # same as rwa

        # ── EL and CRE35 provisions treatment ─────────────────────────────────
        el           = pd_eff * lgd_eff * ead_used
        prov_eligible = exp_copy.eligible_provisions
        el_diff       = el - prov_eligible
        el_shortfall_cet1 = max(el_diff, 0.0)
        el_excess_t2      = min(max(-el_diff, 0.0), 0.006 * rwa_regulatory)

        # ── SA output floor ───────────────────────────────────────────────────
        sa_rwa_input     = getattr(exp_copy, "sa_rwa", 0.0)
        floor_rwa        = self.config.sa_output_floor_ratio * sa_rwa_input
        sa_floor_binding = (sa_rwa_input > 0) and (rwa_regulatory < floor_rwa)
        sa_floor_uplift  = max(floor_rwa - rwa_regulatory, 0.0) if sa_floor_binding else 0.0

        computation_time_ms = (time.time() - start_time) * 1000

        rwa_drivers = {
            "base_rwa":                  rwa,
            "macro_pd_adjustment":       pd_eff / pd_base if pd_base > 0 else 1.0,
            "dynamic_correlation_factor": R_dynamic / R_sector if R_sector > 0 else 1.0,
            "r_internal_vs_regulatory":  R_internal / R_regulatory if R_regulatory > 0 else 1.0,
            "stress_index":              stress_index,
        }

        # FIX-06 [LOW]: compute rwa_pre_mitigant baseline for CRM attribution display.
        # Uses the SAME post-macro pd_eff and lgd_base (before CRM) so the benefit
        # reflects only the CRM reduction, not the macro PD adjustment.
        if is_defaulted:
            rwa_pre_macro = rwa
        else:
            R_pre = min(asset_correlation(pd_eff, exp_copy.asset_class), R_cap)
            b_pre = maturity_adjustment(pd_eff, M_eff) if not exp_copy.asset_class.startswith("RETAIL") else 0.0
            K_pre = capital_requirement_k(pd_eff, lgd_pre_mit, M_eff, R_pre, b_pre)
            rwa_pre_macro = rwa_from_k(K_pre, exp_copy.ead)

        return AIRBResult(
            trade_id              = exp_copy.trade_id,
            pd_applied            = pd_eff,
            lgd_applied           = lgd_eff,
            ead_applied           = ead_used,
            maturity              = M_eff,
            correlation_r         = R_regulatory,  # Pillar 1 R (fixed, was R_internal)
            capital_req_k         = K,
            maturity_adj_b        = b,
            rwa                   = rwa,
            el                    = el,
            el_diff               = el_diff,
            k_regulatory          = K_reg,
            rwa_regulatory        = rwa_regulatory,
            r_regulatory          = R_regulatory,
            r_internal            = R_internal,
            rwa_drivers           = rwa_drivers,
            pd_stressed           = pd_eff,
            is_defaulted          = is_defaulted,
            validation_warnings   = warnings,
            data_quality_score    = 0.95 if pd_market_implied is not None else 0.85,
            computation_time_ms   = computation_time_ms,
            rwa_pre_mitigant      = rwa_pre_macro,
            rwa_mitigant_benefit  = max(rwa_pre_macro - rwa, 0.0),
            lgd_pre_mitigant      = lgd_pre_mit,
            lgd_star              = lgd_eff,
            pd_pre_mitigant       = pd_pre_mit,
            mitigant_type         = mitigant_label,
            el_shortfall_cet1_deduction = el_shortfall_cet1,
            el_excess_tier2_eligible    = el_excess_t2,
            provisions_eligible         = prov_eligible,
            sa_floor_rwa          = floor_rwa,
            sa_floor_binding      = sa_floor_binding,
            sa_floor_uplift       = sa_floor_uplift,
        )

    def _compute_sensitivities(self, exp: BankingBookExposure, result: AIRBResult):
        """
        Add sensitivity analysis to result.
        Shocks: PD +10bp, LGD +5%, EAD +10%

        Fix: when pd_term_structure is present, shocking only exp.pd has no effect
        because get_pd_at_maturity() reads from the term structure.  We now shock
        all term-structure tenors proportionally so the sensitivity is non-zero.
        """
        try:
            # Shock: PD +10bp — must hit the active PD source
            exp_pd_up = copy.deepcopy(exp)
            pd_shock  = 0.001  # 10bp
            exp_pd_up.pd = min(exp_pd_up.pd + pd_shock, 1.0)
            if exp_pd_up.pd_term_structure is not None:
                ts = exp_pd_up.pd_term_structure
                # Additive parallel shift on all tenors (CRE31 is additive in PD space)
                ts.pd_1y = min(ts.pd_1y + pd_shock, 1.0)
                ts.pd_3y = min(ts.pd_3y + pd_shock, 1.0)
                ts.pd_5y = min(ts.pd_5y + pd_shock, 1.0)
            result_pd_up = self.compute(exp_pd_up, _sensitivity_run=True)
            result.rwa_sensitivity_pd = result_pd_up.rwa - result.rwa

            # Shock: LGD +5%
            exp_lgd_up = copy.deepcopy(exp)
            exp_lgd_up.lgd = min(exp_lgd_up.lgd + 0.05, 1.0)
            result_lgd_up = self.compute(exp_lgd_up, _sensitivity_run=True)
            result.rwa_sensitivity_lgd = result_lgd_up.rwa - result.rwa

            # Shock: EAD +10%
            exp_ead_up = copy.deepcopy(exp)
            exp_ead_up.ead *= 1.10
            result_ead_up = self.compute(exp_ead_up, _sensitivity_run=True)
            result.rwa_sensitivity_ead = result_ead_up.rwa - result.rwa

            logger.debug(
                "Trade %s sensitivities: PD_10bp=%.0f LGD_5pct=%.0f EAD_10pct=%.0f",
                exp.trade_id, result.rwa_sensitivity_pd, result.rwa_sensitivity_lgd,
                result.rwa_sensitivity_ead
            )
        except Exception as e:
            logger.warning("Trade %s: sensitivity calculation failed — %s", exp.trade_id, e)


    def compute_from_universal_trade(self, trade: object) -> Optional[AIRBResult]:
        """
        Compute A-IRB directly from UniversalTrade (Phase 1).
        Returns None if trade not eligible for A-IRB.
        """
        # Validate trade quality first (validator stubbed — skip if not available)
        val_result = None
        if self.validator is not None:
            val_result = self.validator.validate_trade(trade)
            if not val_result.is_valid:
                logger.warning("Trade: validation failed — %s", val_result.errors)
                return None

        # Adapt to BankingBookExposure
        exp = universal_trade_to_airb_exposure(trade)
        if exp is None:
            return None

        # Compute with validation metadata
        result = self.compute(exp)
        if val_result is not None and hasattr(val_result, "warnings") and val_result.warnings:
            result.validation_warnings.extend(val_result.warnings)
            result.data_quality_score = 0.85
        return result


    def compute_portfolio(
        self,
        exposures: List[BankingBookExposure],
        force_macro_refresh: bool = False,
    ) -> Dict:
        """
        Compute A-IRB capital for a portfolio with optional live macro overlay.

        When the engine was constructed with a USMacroDataFeed instance, this
        method automatically fetches current US macro conditions and routes every
        exposure through compute_with_macro_overlay().  The macro snapshot is
        fetched once per portfolio run (cached by the feed) so there is no
        per-trade network overhead.

        Args:
            exposures:           List of BankingBookExposure objects.
            force_macro_refresh: Force a live re-fetch even if the cache is fresh.
                                 Use for intraday stress reruns or on-demand
                                 regulatory capital recalculation.

        Returns:
            Standard portfolio summary dict with an additional 'macro_snapshot'
            key when live data was used.
        """
        start_time = time.time()
        results = []
        failed_trades = []

        # ── Resolve macro conditions ──────────────────────────────────────────
        # Fetch once for the entire portfolio run — not once per trade.
        macro_snapshot: Optional[MacroeconomicFactors] = None
        if self.macro_feed is not None:
            try:
                macro_snapshot = self.macro_feed.fetch(force_refresh=force_macro_refresh)
                logger.info(
                    "A-IRB portfolio run: LIVE macro overlay active — "
                    "VIX=%.1f | T10Y2Y=%.0fbp | HY-OAS=%.0fbp | "
                    "UNRATE=%.1f%% | GDP=%.1f%% | regime=%s",
                    macro_snapshot.vix_level,
                    macro_snapshot.yield_curve_slope,
                    macro_snapshot.high_yield_spread,
                    macro_snapshot.unemployment_rate,
                    macro_snapshot.real_gdp_growth,
                    macro_snapshot.regime().value,
                )
            except Exception as exc:
                logger.error(
                    "A-IRB: macro feed fetch failed (%s) — "
                    "falling back to static Pillar 1 compute()", exc,
                )
                macro_snapshot = None

        for exp in exposures:
            try:
                if macro_snapshot is not None:
                    r = self.compute_with_macro_overlay(exp, macro_snapshot)
                else:
                    r = self.compute(exp)
                results.append(r)
            except Exception as e:
                logger.error("A-IRB failed for trade %s: %s", exp.trade_id, e)
                failed_trades.append((exp.trade_id, str(e)))

        total_rwa = sum(r.rwa for r in results)
        total_el  = sum(r.el  for r in results)
        total_ead = sum(r.ead_applied for r in results)
        el_shortfall = sum(max(r.el_diff, 0) for r in results)
        total_computation_time = (time.time() - start_time) * 1000
        
        # Data quality assessment
        avg_quality_score = sum(r.data_quality_score for r in results) / len(results) if results else 1.0
        warnings_count = sum(len(r.validation_warnings) for r in results)
        
        # Sensitivity aggregates
        total_rwa_sensitivity_pd = sum(r.rwa_sensitivity_pd for r in results)
        total_rwa_sensitivity_lgd = sum(r.rwa_sensitivity_lgd for r in results)
        total_rwa_sensitivity_ead = sum(r.rwa_sensitivity_ead for r in results)

        logger.info(
            "A-IRB Portfolio: %d exposures | EAD=%.0f | RWA=%.0f | EL=%.0f | "
            "EL shortfall=%.0f | Avg Quality=%.2f | Time=%.0f ms | "
            "Sensitivities [PD_10bp=%.0f, LGD_5pct=%.0f, EAD_10pct=%.0f]",
            len(results), total_ead, total_rwa, total_el, el_shortfall, avg_quality_score,
            total_computation_time, total_rwa_sensitivity_pd, total_rwa_sensitivity_lgd,
            total_rwa_sensitivity_ead
        )
        
        if failed_trades:
            logger.warning("A-IRB: %d trades failed — %s", len(failed_trades), failed_trades[:3])

        # ── Live macro metadata — exposed for dashboard and audit trail ───────
        # When macro_feed is active, record the snapshot used so that capital
        # numbers can always be traced back to the exact market conditions.
        macro_meta: Dict = {}
        if macro_snapshot is not None:
            macro_meta = {
                "source":             "LIVE",
                "fetch_log":          self.macro_feed.fetch_log if self.macro_feed else {},
                "run_date":           macro_snapshot.date.isoformat(),
                "vix_level":          macro_snapshot.vix_level,
                "yield_curve_slope":  macro_snapshot.yield_curve_slope,
                "high_yield_spread":  macro_snapshot.high_yield_spread,
                "unemployment_rate":  macro_snapshot.unemployment_rate,
                "real_gdp_growth":    macro_snapshot.real_gdp_growth,
                "credit_default_rate":macro_snapshot.credit_default_rate * 100,  # % for display
                "stress_index":       round(macro_snapshot.stress_index(), 4),
                "regime":             macro_snapshot.regime().value,
            }
        else:
            macro_meta = {"source": "STATIC"}

        # Mitigant benefit aggregates
        total_rwa_pre_mit = sum(r.rwa_pre_mitigant     for r in results)
        total_mit_benefit = sum(r.rwa_mitigant_benefit  for r in results)
        n_mitigated       = sum(1 for r in results if r.mitigant_type != "NONE")
        # Breakdown by channel
        mit_by_type: dict = {}
        for r in results:
            for t in r.mitigant_type.split("+"):
                if t and t != "NONE":
                    mit_by_type[t] = mit_by_type.get(t, 0.0) + r.rwa_mitigant_benefit

        # ── Basel IV / CRE35 regulatory aggregates ───────────────────────────
        total_rwa_regulatory  = sum(r.rwa_regulatory             for r in results)
        total_el_shortfall    = sum(r.el_shortfall_cet1_deduction for r in results)
        total_el_excess_t2    = sum(r.el_excess_tier2_eligible    for r in results)
        total_sa_floor_uplift = sum(r.sa_floor_uplift             for r in results)
        n_sa_floor_binding    = sum(1 for r in results if r.sa_floor_binding)
        n_defaulted           = sum(1 for r in results if r.is_defaulted)
        n_climate_uplifted    = sum(1 for r in results if r.climate_pd_uplift > 0)
        total_climate_uplift  = sum(r.climate_pd_uplift           for r in results)

        # EL shortfall / excess log at portfolio level
        logger.info(
            "A-IRB Basel IV: RWA_reg=%.0f | EL CET1 deduction=%.0f | "
            "T2 excess=%.0f | SA floor uplift=%.0f (%d binding) | "
            "Defaulted=%d | ESG uplifted=%d",
            total_rwa_regulatory, total_el_shortfall, total_el_excess_t2,
            total_sa_floor_uplift, n_sa_floor_binding,
            n_defaulted, n_climate_uplifted,
        )

        return {
            "trade_results":            results,
            "macro_snapshot":           macro_meta,   # live US macro conditions used this run
            "total_rwa":                total_rwa,
            "total_el":                 total_el,
            "total_ead":                total_ead,
            "el_shortfall":             el_shortfall,
            "avg_risk_weight":          total_rwa / total_ead if total_ead > 0 else 0,
            "num_trades_processed":     len(results),
            "num_trades_failed":        len(failed_trades),
            "avg_quality_score":        avg_quality_score,
            "validation_warnings":      warnings_count,
            "total_computation_time_ms": total_computation_time,
            "avg_time_per_trade_ms":    total_computation_time / len(results) if results else 0,
            "rwa_sensitivity_pd":       total_rwa_sensitivity_pd,
            "rwa_sensitivity_lgd":      total_rwa_sensitivity_lgd,
            "rwa_sensitivity_ead":      total_rwa_sensitivity_ead,
            # ── Mitigant benefit attribution ─────────────────────────────────
            "total_rwa_pre_mitigant":   total_rwa_pre_mit,
            "total_mitigant_benefit":   total_mit_benefit,
            "mitigant_coverage_pct":    100.0 * n_mitigated / len(results) if results else 0.0,
            "mitigant_benefit_by_type": mit_by_type,
            # ── Basel IV / CRE35 regulatory aggregates ───────────────────────
            # CRE31.5: Pillar 1 RWA using regulatory R cap (≤ 0.24 CORP, ≤ 0.30 HVCRE)
            "total_rwa_regulatory":     total_rwa_regulatory,
            # CRE35.2: Sum of EL > provisions shortfalls → CET1 deduction
            "total_el_shortfall_cet1_deduction": total_el_shortfall,
            # CRE35.3: Sum of provisions > EL excess → Tier 2 add-back (capped per trade at 0.6% RWA)
            "total_el_excess_tier2_eligible":     total_el_excess_t2,
            # CRE20.4: SA output floor 72.5% — aggregate uplift and binding count
            "total_sa_floor_uplift":    total_sa_floor_uplift,
            "sa_floor_binding_count":   n_sa_floor_binding,
            # Defaulted exposure count (CRE31.12 path used)
            "defaulted_exposure_count": n_defaulted,
            # CRR3 Art. 87a: Exposures where ESG/climate PD uplift was applied
            "climate_uplifted_count":   n_climate_uplifted,
            "total_climate_pd_uplift":  total_climate_uplift,
        }
    
    def compute_portfolio_from_universal_trades(self, trades: List[object]) -> Dict:
        """
        Compute A-IRB for portfolio from UniversalTrade list (Phase 1).
        """
        start_time = time.time()
        results = []
        skipped_trades = []
        failed_trades = []

        for trade in trades:
            trade_id = getattr(trade, "trade_id", repr(trade))
            try:
                result = self.compute_from_universal_trade(trade)
                if result is not None:
                    results.append(result)
                else:
                    skipped_trades.append(trade_id)
            except Exception as e:
                logger.error("A-IRB failed for trade %s: %s", trade_id, e)
                failed_trades.append((trade_id, str(e)))

        total_rwa = sum(r.rwa for r in results)
        total_el  = sum(r.el  for r in results)
        total_ead = sum(r.ead_applied for r in results)
        total_computation_time = (time.time() - start_time) * 1000
        avg_quality_score = sum(r.data_quality_score for r in results) / len(results) if results else 1.0

        logger.info(
            "A-IRB Portfolio (UniversalTrade): %d processed | %d skipped | %d failed | "
            "EAD=%.0f | RWA=%.0f | EL=%.0f | Avg Quality=%.2f",
            len(results), len(skipped_trades), len(failed_trades), 
            total_ead, total_rwa, total_el, avg_quality_score
        )

        return {
            "trade_results":        results,
            # macro_snapshot is not applicable here: this path calls compute() (no macro overlay).
            # Use compute_portfolio_from_universal_trades() only for Pillar 1 capital.
            # For a macro-enriched Pillar 2 / ICAAP view, use compute_portfolio() with
            # a USMacroDataFeed attached to the engine.
            "total_rwa":            total_rwa,
            "total_el":             total_el,
            "total_ead":            total_ead,
            "avg_risk_weight":      total_rwa / total_ead if total_ead > 0 else 0,
            "num_trades_processed": len(results),
            "num_trades_skipped":   len(skipped_trades),
            "num_trades_failed":    len(failed_trades),
            "avg_quality_score":    avg_quality_score,
            "total_computation_time_ms": total_computation_time,
            "avg_time_per_trade_ms":    total_computation_time / len(results) if results else 0,
        }
