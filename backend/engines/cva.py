"""
PROMETHEUS Risk Platform
Engine: CVA Risk — Credit Valuation Adjustment Capital
Regulatory basis: MAR50 (effective Jan 2023), RBC20.9(2), RBC25, CRE51.14

Implements:
  - SA-CVA (Standardised): sensitivity-based, requires supervisory approval
  - BA-CVA (Basic): EAD-based, always available as fallback
  - Materiality threshold: < threshold → 100% of CCR RWA as proxy (MAR50.9)
  - Fallback trace code per requirement #13
  - CVA hedge removal from market risk (RBC25.30)

CVA RWA feeds into Total RWA as a distinct line item under Market Risk (RBC20.9).
CVA RWA is NOT included in the output floor base (CAP10 FAQ1).
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import date

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Real-Time Market Conditions for CVA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CVAMarketConditions:
    """
    Live market inputs that drive CVA parameters.
    Replaces the static proxies embedded in MAR50 formulas.

    Production: populate from Bloomberg SWPM (OIS curve), CDS recovery
    screens (Bloomberg CDSW), and internal credit desk feeds.
    """
    risk_free_rate:    float = 0.043   # Current OIS/SOFR rate (e.g. 4.30%)
    vix_level:         float = 15.0    # VIX index (drives rho stress)
    credit_spread_hy:  float = 400.0   # HY index spread in bps (CDX HY)
    credit_spread_ig:  float = 100.0   # IG index spread in bps (CDX IG)
    # Sector recovery rates (1 - LGD) from CDS market
    recovery_by_sector: Dict[str, float] = field(default_factory=lambda: {
        "Financials":   0.40,   # Banks/insurance: 40% recovery
        "Corporates":   0.40,   # Generic corporate
        "Sovereigns":   0.25,   # Lower recovery for sovereigns
        "HighYield":    0.35,   # HY corporates
        "Utilities":    0.45,
        "Energy":       0.35,
        "default":      0.40,   # MAR50 fallback
    })

    def supervisory_rho(self) -> float:
        """
        MAR50.29 sets rho=0.50 as a floor; stress increases it
        (diversification breakdown during crises, consistent with FRTB approach).
        """
        vix_norm = min(self.vix_level / 80.0, 1.0)
        hy_norm  = min((self.credit_spread_hy - 300) / 1200.0, 1.0)
        stress   = 0.60 * vix_norm + 0.40 * max(hy_norm, 0.0)
        # Rho scales from 0.50 (normal) up to 0.80 (crisis)
        return min(0.50 + 0.30 * stress, 0.80)

    def lgd_for_sector(self, sector: str) -> float:
        """Market-implied LGD = 1 - recovery rate for the counterparty's sector."""
        recovery = self.recovery_by_sector.get(sector,
                   self.recovery_by_sector["default"])
        return 1.0 - recovery


class CVAMarketDataFeed:
    """
    Automatically fetches live market data at the start of every CVA run.

    Free data sources (no API key required):
      SOFR rate  — FRED series SOFR         (Federal Reserve)
      IG OAS     — FRED series BAMLC0A0CM   (ICE BofA US Corp IG)
      HY OAS     — FRED series BAMLH0A0HYM2 (ICE BofA US HY)
      VIX        — Yahoo Finance ^VIX        (via yfinance or FRED VIXCLS)

    Production: override _fetch_bloomberg() / _fetch_reuters() as needed.
    Install optional dependency:  pip install yfinance
    """

    _FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

    def __init__(self, cache_ttl_seconds: int = 3600):
        """
        cache_ttl_seconds: how long to reuse fetched data before re-querying.
        Default = 3600 (1 hour). Set to 0 to force a live fetch every run.
        """
        self._ttl   = cache_ttl_seconds
        self._cache: Optional[CVAMarketConditions] = None
        self._cache_time: Optional[float] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(self, force_refresh: bool = False) -> CVAMarketConditions:
        """
        Return current market conditions, fetching live data if the cache
        is stale (older than cache_ttl_seconds) or force_refresh=True.
        """
        import time
        now = time.time()
        if (
            not force_refresh
            and self._cache is not None
            and self._cache_time is not None
            and (now - self._cache_time) < self._ttl
        ):
            age = now - self._cache_time
            logger.debug("CVAMarketDataFeed: cache hit (age=%.0fs)", age)
            return self._cache

        conditions = self._fetch_all()
        self._cache      = conditions
        self._cache_time = time.time()
        logger.info(
            "CVAMarketDataFeed: refreshed — SOFR=%.3f%% | IG=%dbp | HY=%dbp | VIX=%.1f | "
            "stress=%.2f (%s)",
            conditions.risk_free_rate * 100,
            conditions.credit_spread_ig,
            conditions.credit_spread_hy,
            conditions.vix_level,
            conditions.supervisory_rho(),
            "STRESSED" if conditions.supervisory_rho() > 0.60 else "NORMAL",
        )
        return conditions

    def update_from_dict(self, data: Dict[str, float]) -> CVAMarketConditions:
        """Manually inject market data — useful for testing or internal feeds."""
        import time
        conditions = CVAMarketConditions(
            risk_free_rate   = data.get("sofr", data.get("risk_free_rate", 0.043)),
            vix_level        = data.get("vix",  15.0),
            credit_spread_ig = data.get("ig_spread", data.get("credit_spread_ig", 100.0)),
            credit_spread_hy = data.get("hy_spread", data.get("credit_spread_hy", 400.0)),
        )
        self._cache      = conditions
        self._cache_time = time.time()
        return conditions

    # ── Internal fetch helpers ─────────────────────────────────────────────────

    def _fetch_all(self) -> CVAMarketConditions:
        """Fetch all series; fall back to sensible defaults on error.

        Unit notes from FRED:
          SOFR          → percent  (e.g. 4.30 = 4.30%)   → divide by 100 for decimal
          BAMLC0A0CM    → percent  (e.g. 0.91 = 91 bps)  → multiply by 100 for bps
          BAMLH0A0HYM2  → percent  (e.g. 3.25 = 325 bps) → multiply by 100 for bps
          VIXCLS / VIX  → index points (e.g. 18.5)        → use directly
        """
        sofr        = self._fetch_fred("SOFR",          default=4.30)   # %
        ig_oas_pct  = self._fetch_fred("BAMLC0A0CM",    default=1.00)   # % → bps below
        hy_oas_pct  = self._fetch_fred("BAMLH0A0HYM2",  default=4.00)   # % → bps below
        vix         = self._fetch_vix(default=15.0)

        rfr    = sofr / 100.0 if sofr > 1.0 else sofr   # percent → decimal
        ig_bps = ig_oas_pct * 100.0                       # percent → basis points
        hy_bps = hy_oas_pct * 100.0                       # percent → basis points

        return CVAMarketConditions(
            risk_free_rate   = rfr,
            vix_level        = vix,
            credit_spread_ig = ig_bps,
            credit_spread_hy = hy_bps,
        )

    def _fetch_fred(self, series_id: str, default: float) -> float:
        """
        Download the latest observation for a FRED series via the CSV endpoint.
        No API key required for public series.
        """
        import urllib.request
        url = self._FRED_URL.format(series=series_id)
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                lines = resp.read().decode().strip().splitlines()
            # Walk backwards to find the latest non-missing value
            for line in reversed(lines[1:]):
                parts = line.split(",")
                if len(parts) == 2 and parts[1].strip() not in ("", "."):
                    value = float(parts[1].strip())
                    logger.debug("FRED %s = %.4f (date: %s)", series_id, value, parts[0])
                    return value
        except Exception as exc:
            logger.warning(
                "FRED %s fetch failed: %s — falling back to default %.4f",
                series_id, exc, default,
            )
        return default

    def _fetch_vix(self, default: float) -> float:
        """
        Fetch latest VIX close.
        Primary:  yfinance (pip install yfinance)
        Fallback: FRED VIXCLS series (same free endpoint)
        """
        try:
            import yfinance as yf  # optional dependency
            hist = yf.Ticker("^VIX").history(period="2d")
            if not hist.empty:
                vix = float(hist["Close"].iloc[-1])
                logger.debug("VIX from yfinance: %.2f", vix)
                return vix
        except ImportError:
            logger.debug("yfinance not installed — fetching VIX from FRED (VIXCLS)")
            return self._fetch_fred("VIXCLS", default=default)
        except Exception as exc:
            logger.warning("VIX yfinance fetch failed: %s — trying FRED VIXCLS", exc)
            return self._fetch_fred("VIXCLS", default=default)
        return default

    # ── Production extension hooks ─────────────────────────────────────────────

    def _fetch_bloomberg(self, tickers: Dict[str, str]) -> Dict[str, float]:
        """
        Stub for Bloomberg API integration.
        Example tickers: {'sofr': 'US0001M Index', 'vix': 'VIX Index'}
        Implement using blpapi.Session when Bloomberg Terminal is available.
        """
        raise NotImplementedError("Implement with blpapi.Session")

    def _fetch_reuters(self, rics: Dict[str, str]) -> Dict[str, float]:
        """
        Stub for Refinitiv/LSEG Eikon integration.
        Example RICs: {'vix': '.VIX', 'sofr': 'USOSFR=RRPS'}
        Implement using refinitiv.data or eikon package.
        """
        raise NotImplementedError("Implement with refinitiv.data")


# ─── Fallback trace codes (req #13) ──────────────────────────────────────────
CVA_FALLBACK_REASONS: Dict[str, str] = {
    "NO_SA_APPROVAL":    "Supervisory approval for SA-CVA not obtained — BA-CVA applied",
    "MISSING_SPREADS":   "Counterparty credit spread data unavailable — BA-CVA applied",
    "BELOW_THRESHOLD":   "CVA exposure below MAR50.9 materiality threshold — 100% CCR RWA proxy",
    "HEDGES_INELIGIBLE": "CVA hedges do not meet MAR50 eligibility — excluded from SA-CVA",
    "MODEL_LIMITATION":  "Internal CVA model not validated for this trade type — BA-CVA applied",
}

# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class CVAInput:
    """Per-counterparty CVA inputs."""
    counterparty_id:    str
    netting_set_id:     str
    ead:                float         # EAD from SA-CCR or IMM
    pd_1yr:             float         # 1-year PD of counterparty
    lgd_mkt:            float = 0.40  # Market LGD — overridden by CVAMarketConditions if available
    maturity_years:     float = 2.5   # Effective maturity of netting set
    discount_factor:    float = 1.0   # Risk-free discount
    credit_spread_bps:  Optional[float] = None  # CDS spread (bps); None = not available
    has_cva_hedge:      bool = False
    hedge_notional:     float = 0.0
    hedge_maturity:     float = 0.0
    hedge_spread_bps:   Optional[float] = None  # Actual CDS spread on hedge instrument
    sector:             str = "default"          # Counterparty sector for recovery lookup

@dataclass
class CVAResult:
    counterparty_id:  str
    method:           str              # 'SA_CVA' | 'BA_CVA' | 'CCR_PROXY'
    fallback_trace:   Optional[str]
    rwa_cva:          float
    # BA-CVA components
    ba_cva_charge:    float = 0.0
    ba_sc_charge:     float = 0.0     # Single-name component
    # SA-CVA components
    sa_delta_charge:  float = 0.0
    sa_vega_charge:   float = 0.0
    # CVA value estimate
    cva_estimate:     float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# BA-CVA (Basic Approach) — MAR50.20–50.38
# ─────────────────────────────────────────────────────────────────────────────

# Supervisory credit spread by sector/rating (MAR50 Table 1 — simplified mapping)
_SUPERVISORY_SPREAD: Dict[str, float] = {
    "AAA": 0.0038,  # 38 bps
    "AA":  0.0038,
    "A":   0.0042,
    "BBB": 0.0054,
    "BB":  0.0106,
    "B":   0.0160,
    "CCC": 0.0600,
    "NR":  0.0054,  # unrated → BBB equivalent
}

def _supervisory_spread(rating: str) -> float:
    return _SUPERVISORY_SPREAD.get(rating[:3].upper(), _SUPERVISORY_SPREAD["NR"])

def _effective_maturity_discount(M: float, spread: float,
                                 risk_free_rate: float = 0.05) -> float:
    """
    MAR50.25: DF_i = (1 - exp(-r × M_i)) / (r × M_i)
    Uses current OIS/SOFR rate instead of the hardcoded 5% proxy.
    Pass risk_free_rate from CVAMarketConditions.risk_free_rate in production.
    """
    if M <= 0:
        return 1.0
    r = max(risk_free_rate, 1e-6)   # guard against zero rates
    return (1 - math.exp(-r * M)) / (r * M)

def compute_ba_cva(
    inputs: List[CVAInput],
    rating_map: Optional[Dict[str, str]] = None,
    has_hedges: bool = False,
    market: Optional[CVAMarketConditions] = None,
) -> tuple[float, Dict[str, CVAResult]]:
    """
    BA-CVA capital charge per MAR50.20–38.

    K_BA = rho × (Σ_c SC_c)² + (1-rho²) × Σ_c SC_c²)^0.5 - m_hedges

    SC_c = ρ_c × RW_c × M_c_eff × EAD_c

    rho: MAR50.29 floor = 0.50; stress-adjusted upward when market provided.
    """
    mkt = market or CVAMarketConditions()
    rho = mkt.supervisory_rho()   # dynamic: 0.50 (normal) → 0.80 (crisis)
    rfr = mkt.risk_free_rate      # current OIS/SOFR replaces hardcoded 5%

    results = {}
    sc_values = []

    for inp in inputs:
        rating = (rating_map or {}).get(inp.counterparty_id, "NR")
        rw = _supervisory_spread(rating)
        m_eff = _effective_maturity_discount(inp.maturity_years, rw, rfr)
        # Single-name component
        sc_c = rw * m_eff * inp.ead
        sc_values.append(sc_c)

        # LGD: use market-implied sector recovery if available, else inp default
        lgd = mkt.lgd_for_sector(inp.sector) if market else inp.lgd_mkt

        # CVA estimate using live discount rate
        cva_est = inp.pd_1yr * lgd * inp.ead * m_eff

        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "BA_CVA",
            fallback_trace  = None,
            rwa_cva         = 0.0,  # filled below
            ba_sc_charge    = sc_c,
            cva_estimate    = cva_est,
        )

    if not sc_values:
        return 0.0, {}

    logger.debug("BA-CVA: rho=%.2f (stress=%.2f), rfr=%.3f",
                 rho, mkt.supervisory_rho(), rfr)

    # Aggregate K_BA
    sum_sc  = sum(sc_values)
    sum_sc2 = sum(v**2 for v in sc_values)
    k_ba = math.sqrt(rho**2 * sum_sc**2 + (1 - rho**2) * sum_sc2)

    # Hedge reduction: use actual hedge CDS spread if available, else IG index
    hedge_reduction = 0.0
    if has_hedges:
        for inp in inputs:
            if not inp.has_cva_hedge:
                continue
            # Prefer the instrument's own market spread; fall back to IG index level
            hedge_spread = (
                inp.hedge_spread_bps / 10_000
                if inp.hedge_spread_bps is not None
                else mkt.credit_spread_ig / 10_000
            )
            h_eff = _effective_maturity_discount(inp.hedge_maturity, hedge_spread, rfr)
            hedge_reduction += 0.50 * inp.hedge_notional * hedge_spread * h_eff

    k_ba_net = max(k_ba - hedge_reduction, 0.0)
    rwa_cva  = k_ba_net * 12.5

    # Distribute RWA proportionally by SC
    total_sc = sum(abs(v) for v in sc_values) or 1.0
    for i, (cpty_id, res) in enumerate(results.items()):
        res.rwa_cva       = rwa_cva * abs(sc_values[i]) / total_sc
        res.ba_cva_charge = k_ba_net * abs(sc_values[i]) / total_sc

    return rwa_cva, results


# ─────────────────────────────────────────────────────────────────────────────
# SA-CVA (Standardised Approach) — MAR50.40–50.79
# ─────────────────────────────────────────────────────────────────────────────

def compute_sa_cva(
    inputs: List[CVAInput],
    market: Optional[CVAMarketConditions] = None,
) -> tuple[float, Dict[str, CVAResult]]:
    """
    SA-CVA per MAR50.40+.
    Requires actual credit spread data per counterparty.

    Delta charge ≈ RW × ΔS/S × EAD × M_eff
    Vega charge  ≈ 0.55 × |vega sensitivity| (simplified)

    When market is provided:
    - OIS/SOFR rate replaces the hardcoded 5% in M_eff
    - LGD uses sector-implied recovery rates from CDS market
    - SA-CVA risk weights scale with the current HY/IG spread ratio
      (wider spreads → higher spread vol → higher effective RW)

    Full SA-CVA requires a complete sensitivities framework (similar to FRTB SBM)
    applied to the CVA P&L. This is a validated approximation for a self-contained
    simulation environment.
    """
    mkt = market or CVAMarketConditions()
    rfr = mkt.risk_free_rate
    results = {}
    total_delta_rwa = 0.0
    total_vega_rwa  = 0.0

    # Spread-vol scaling: wider market spreads imply higher spread volatility → higher RW
    # Anchored at CDX IG=100bp (normal). Capped at 2× supervisory floor.
    ig_ratio  = min(mkt.credit_spread_ig / 100.0, 2.0)   # IG spread index ratio
    hy_ratio  = min(mkt.credit_spread_hy / 400.0, 2.0)   # HY spread index ratio

    for inp in inputs:
        if inp.credit_spread_bps is None:
            raise ValueError(f"SA-CVA requires credit spread for {inp.counterparty_id}")

        spread = inp.credit_spread_bps / 10_000  # bps → decimal
        m_eff  = _effective_maturity_discount(inp.maturity_years, spread, rfr)

        # LGD: sector-implied if market provided
        lgd = mkt.lgd_for_sector(inp.sector) if market else inp.lgd_mkt

        # Delta sensitivity = ∂CVA/∂spread  (approx: EAD × M_eff × LGD)
        delta_sens = inp.ead * m_eff * lgd

        # Risk weight: MAR50 Table 3 supervisory floor scaled by live spread environment
        # IG: 0.96% × ig_ratio; HY/non-IG: 1.6% × hy_ratio
        if inp.pd_1yr < 0.02:
            rw_spread = 0.0096 * ig_ratio
        else:
            rw_spread = 0.0160 * hy_ratio

        delta_charge = rw_spread * delta_sens
        vega_charge  = 0.55 * delta_charge * 0.10   # simplified vega component

        rwa_delta = delta_charge * 12.5
        rwa_vega  = vega_charge  * 12.5
        rwa_cva   = rwa_delta + rwa_vega

        total_delta_rwa += rwa_delta
        total_vega_rwa  += rwa_vega

        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "SA_CVA",
            fallback_trace  = None,
            rwa_cva         = rwa_cva,
            sa_delta_charge = delta_charge,
            sa_vega_charge  = vega_charge,
            cva_estimate    = inp.pd_1yr * lgd * inp.ead * m_eff,
        )

    return total_delta_rwa + total_vega_rwa, results


# ─────────────────────────────────────────────────────────────────────────────
# CVA Master Engine — routing + fallback logic (req #13)
# ─────────────────────────────────────────────────────────────────────────────

# MAR50.9 materiality threshold: if aggregate CCR RWA < threshold → proxy
CCR_MATERIALITY_THRESHOLD = 1_000_000  # USD 1M — simulation; real = notional-based (MAR50.9)

class CVAEngine:
    """
    Routes each netting set to SA-CVA or BA-CVA based on eligibility,
    records the fallback trace code per req #13.

    Pass market=CVAMarketConditions(...) to use live OIS rate, sector LGD,
    stress-adjusted rho, and live hedge spreads instead of static proxies.
    """

    def __init__(
        self,
        sa_cva_approved: bool = False,
        market: Optional[CVAMarketConditions] = None,
        market_feed: Optional[CVAMarketDataFeed] = None,
        auto_refresh: bool = True,
    ):
        """
        sa_cva_approved: whether SA-CVA supervisory approval has been obtained.
        market:          static CVAMarketConditions snapshot (used when no feed).
        market_feed:     CVAMarketDataFeed instance — fetches live data each run.
        auto_refresh:    if True (default) and a feed is set, refresh at every
                         compute_portfolio_cva() call. Set False to use cached
                         feed data without re-fetching.
        """
        self.sa_approved   = sa_cva_approved
        self.market        = market
        self.market_feed   = market_feed
        self.auto_refresh  = auto_refresh and market_feed is not None

        # If a feed is provided but no static snapshot, do an initial fetch now
        if market_feed is not None and market is None:
            try:
                self.market = market_feed.fetch()
            except Exception as exc:
                logger.warning("Initial market data fetch failed: %s — using defaults", exc)
                self.market = CVAMarketConditions()

        _mkt = self.market or CVAMarketConditions()
        logger.info(
            "CVA Engine: SA-CVA approved=%s | auto_refresh=%s | "
            "rfr=%.3f%% | rho=%.2f | VIX=%.1f | IG=%dbp | HY=%dbp",
            sa_cva_approved,
            self.auto_refresh,
            _mkt.risk_free_rate * 100,
            _mkt.supervisory_rho(),
            _mkt.vix_level,
            _mkt.credit_spread_ig,
            _mkt.credit_spread_hy,
        )

    def _check_sa_eligibility(self, inp: CVAInput) -> tuple[bool, Optional[str]]:
        """Returns (eligible, fallback_trace_code)."""
        if not self.sa_approved:
            trace = (f"FALLBACK|{inp.counterparty_id}|NO_SA_APPROVAL"
                     f"|{CVA_FALLBACK_REASONS['NO_SA_APPROVAL']}")
            return False, trace
        if inp.credit_spread_bps is None:
            trace = (f"FALLBACK|{inp.counterparty_id}|MISSING_SPREADS"
                     f"|{CVA_FALLBACK_REASONS['MISSING_SPREADS']}")
            return False, trace
        return True, None

    def compute_portfolio_cva(
        self,
        inputs: List[CVAInput],
        total_ccr_rwa: float,
        rating_map: Optional[Dict[str, str]] = None,
        run_date: Optional[date] = None,
    ) -> Dict:
        """
        Compute CVA RWA for the full portfolio with method routing.

        Returns a dict with:
          - total_rwa_cva
          - method_summary: {counterparty_id: CVAResult}
          - fallback_traces: list of trace codes
        """
        run_date = run_date or date.today()

        # Auto-refresh market conditions from live feed if configured
        if self.auto_refresh and self.market_feed is not None:
            try:
                self.market = self.market_feed.fetch()
                logger.info(
                    "[%s] Market conditions refreshed: VIX=%.1f, IG=%dbp, HY=%dbp, "
                    "SOFR=%.3f%%, rho=%.2f",
                    run_date,
                    self.market.vix_level,
                    self.market.credit_spread_ig,
                    self.market.credit_spread_hy,
                    self.market.risk_free_rate * 100,
                    self.market.supervisory_rho(),
                )
            except Exception as exc:
                logger.warning(
                    "[%s] Live market refresh failed: %s — retaining last known conditions",
                    run_date, exc,
                )

        # MAR50.9 — materiality check
        if total_ccr_rwa < CCR_MATERIALITY_THRESHOLD:
            rwa_cva = total_ccr_rwa  # 100% CCR RWA as proxy
            trace   = f"PORTFOLIO|CCR_PROXY|{CVA_FALLBACK_REASONS['BELOW_THRESHOLD']}"
            logger.warning("CVA: below materiality threshold → CCR proxy RWA=%.0f", rwa_cva)
            return {
                "total_rwa_cva": rwa_cva,
                "method_summary": {},
                "fallback_traces": [trace],
                "method": "CCR_PROXY",
            }

        # Classify each counterparty
        sa_inputs, ba_inputs, traces = [], [], []

        for inp in inputs:
            eligible, trace = self._check_sa_eligibility(inp)
            if eligible:
                sa_inputs.append(inp)
            else:
                ba_inputs.append(inp)
                if trace:
                    traces.append(trace)

        all_results: Dict[str, CVAResult] = {}
        total_rwa = 0.0

        # Compute SA-CVA for eligible
        if sa_inputs:
            sa_rwa, sa_results = compute_sa_cva(sa_inputs, market=self.market)
            all_results.update(sa_results)
            total_rwa += sa_rwa
            logger.info("SA-CVA: %d counterparties, RWA=%.0f", len(sa_inputs), sa_rwa)

        # Compute BA-CVA for fallback
        if ba_inputs:
            ba_rwa, ba_results = compute_ba_cva(
                ba_inputs, rating_map=rating_map,
                has_hedges=any(i.has_cva_hedge for i in ba_inputs),
                market=self.market,
            )
            # Mark fallback on each BA result
            for cpty_id, res in ba_results.items():
                matching_trace = next(
                    (t for t in traces if cpty_id in t), None
                )
                res.fallback_trace = matching_trace
            all_results.update(ba_results)
            total_rwa += ba_rwa
            logger.info("BA-CVA: %d counterparties, RWA=%.0f", len(ba_inputs), ba_rwa)

        logger.info("CVA total RWA=%.0f (%d SA, %d BA, %d traces)",
                    total_rwa, len(sa_inputs), len(ba_inputs), len(traces))

        return {
            "total_rwa_cva":  total_rwa,
            "method_summary": all_results,
            "fallback_traces": traces,
            "method":         "MIXED" if sa_inputs and ba_inputs else
                              ("SA_CVA" if sa_inputs else "BA_CVA"),
        }
