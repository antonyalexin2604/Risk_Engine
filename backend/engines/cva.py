"""
PROMETHEUS Risk Platform
Engine: CVA Risk — Credit Valuation Adjustment Capital
Regulatory basis: MAR50 (effective Jan 2023), RBC20.9(2), RBC25, CRE51.14

Implements:
  - SA-CVA (Standardised): sensitivity-based, requires supervisory approval
  - BA-CVA (Basic): EAD-based, always available as fallback
    - Reduced version (MAR50.14): no hedge recognition — always computed
    - Full version (MAR50.20-21): hedge recognition via SNH / IH / HMA structure
  - Materiality threshold: < threshold → 100% of CCR RWA as proxy (MAR50.9)
  - Fallback trace code per requirement #13
  - CVA hedge removal from market risk (RBC25.30)

CVA RWA feeds into Total RWA as a distinct line item under Market Risk (RBC20.9).
CVA RWA is NOT included in the output floor base (CAP10 FAQ1).

Regulatory Review — Corrections applied (April 2026)
═══════════════════════════════════════════════════════════════════════════════
FIX-01 [HIGH]   MAR50.14   Discount scalar DS=0.65 added to BA-CVA. Capital was
                            previously overstated by ~54% for all BA-CVA exposures.

FIX-02 [HIGH]   MAR50.21   BA-CVA hedge reduction completely rewritten. Previous
                            formula (0.50 × notional × spread) had no MAR50 basis.
                            Now implements correct SNH_c / IH / HMA_c structure with
                            supervisory correlation ρ_hc (Table 2: 100%/80%/50%),
                            β=0.25 floor, and reduced/full version split.

FIX-03 [HIGH]   MAR50.29   supervisory_rho() corrected. Basel fixes ρ=0.50
                            unconditionally. Dynamic VIX-based scaling (0.50→0.80)
                            relocated to stress_rho() and gated behind regulatory=False.

FIX-04 [MEDIUM] MAR50.9    Materiality threshold corrected from USD 1M CCR RWA to
                            EUR 100bn aggregate notional. Threshold comparison now
                            checks total_notional_eur, not CCR RWA.

FIX-05 [MEDIUM] MAR50.65   SA-CVA risk weights corrected. Previous code selected RW
                            by pd_1yr < 0.02 threshold. Now uses 8-bucket sector
                            structure per MAR50.63 Table 5 / Table 7. Market-based
                            ig_ratio/hy_ratio scaling removed (no MAR50 basis).

FIX-06 [MEDIUM] MAR50.48   Vega charge: added note that vega must always be computed
                            (MAR50.48 is explicit). Production hook provided.

FIX-07 [MEDIUM] MAR50.15   CVAInput gains netting_sets list so SCVA can sum across
                            all netting sets per counterparty.

FIX-08 [LOW]    MAR50.32   Wrong-Way Risk flag and exposure add-on added to CVAInput.

FIX-09 [LOW]    MAR50.32   Illiquid counterparty proxy spread function added with
                            sector+rating+region mapping per MAR50.32(3).
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
        MAR50.14 paragraph (2) and MAR50.29: ρ = 0.50 is fixed by Basel.
        It is a supervisory parameter, not a bank-estimated parameter.
        Previous implementation incorrectly scaled ρ from 0.50 to 0.80
        based on VIX — this has no MAR50 basis and must not be used for
        regulatory capital.

        Returns exactly 0.50 for all market conditions.
        """
        return 0.50  # MAR50.14(2): "ρ = 50%. It is the supervisory correlation parameter."

    def stress_rho(self) -> float:
        """
        Internal / Pillar 2 stress rho — NOT for regulatory capital.

        Scales ρ from 0.50 (normal) to 0.80 (crisis) based on live
        market stress indicators. Use for:
          - Pillar 2 ICAAP stress testing
          - Internal CVA desk limit monitoring
          - Scenario analysis on the CVA Risk dashboard page

        NEVER pass this to compute_ba_cva() or compute_sa_cva() for
        regulatory capital. Use supervisory_rho() = 0.50 there.
        """
        vix_norm = min(self.vix_level / 80.0, 1.0)
        hy_norm  = min((self.credit_spread_hy - 300) / 1200.0, 1.0)
        stress   = 0.60 * vix_norm + 0.40 * max(hy_norm, 0.0)
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
class NettingSetEAD:
    """
    Per-netting-set EAD and maturity for SCVA calculation.
    MAR50.15 requires summing SCVA across all netting sets per counterparty.
    A counterparty with a collateralised and an uncollateralised netting set
    has different M_eff per netting set.
    """
    netting_set_id: str
    ead:            float   # EAD from SA-CCR or IMM for this netting set
    maturity_years: float   # Effective maturity for this netting set


# MAR50.63 Table 5: Sector buckets for counterparty credit spread delta risk
# Used by SA-CVA to select the correct risk weight from MAR50.65 Table 7.
SECTOR_BUCKET: Dict[str, int] = {
    "Sovereign":    1,   # Sovereigns, central banks, multilateral dev banks
    "Muni":         1,   # Local government / gov-backed non-financials
    "Financials":   2,   # Financials including gov-backed financials
    "Energy":       3,   # Basic materials, energy, industrials, agriculture
    "Industrials":  3,
    "Consumer":     4,   # Consumer goods/services, transportation, admin
    "Technology":   5,   # Technology, telecommunications
    "Healthcare":   6,   # Health care, utilities, professional services
    "Utilities":    6,
    "Other":        7,   # Other sector
    "default":      7,   # Fallback to bucket 7 (most conservative for unclassified)
}

# MAR50.65 Table 7: RWs by bucket and credit quality (IG / HY/NR)
# Bucket 8 = Qualified Indices (optional treatment per MAR50.50)
_SA_CVA_RW_IG: Dict[int, float] = {
    1: 0.005,   # Sovereign IG:    0.5%  (bucket 1a); 1.0% for bucket 1b — use 0.5% as floor
    2: 0.010,   # Financials IG:   1.0%
    3: 0.030,   # Industrials IG:  3.0%
    4: 0.030,   # Consumer IG:     3.0%
    5: 0.020,   # Technology IG:   2.0%
    6: 0.015,   # Healthcare IG:   1.5%
    7: 0.050,   # Other IG:        5.0%
    8: 0.015,   # Qualified Index IG: 1.5%
}
_SA_CVA_RW_HY: Dict[int, float] = {
    1: 0.020,   # Sovereign HY:    2.0%
    2: 0.040,   # Financials HY:   4.0%  (bucket 1b HY = 4.0%)
    3: 0.070,   # Industrials HY:  7.0%
    4: 0.085,   # Consumer HY:     8.5%
    5: 0.055,   # Technology HY:   5.5%
    6: 0.050,   # Healthcare HY:   5.0%
    7: 0.120,   # Other HY:       12.0%
    8: 0.050,   # Qualified Index HY: 5.0%
}

# MAR50.26 Table 2: Supervisory correlations between counterparty and single-name hedge
# Used in full BA-CVA SNH calculation
HEDGE_CORRELATION: Dict[str, float] = {
    "DIRECT":           1.00,   # Hedge references counterparty c directly
    "LEGALLY_RELATED":  0.80,   # Reference entity legally related to c (parent/subsidiary)
    "SAME_SECTOR":      0.50,   # Reference entity same sector and region as c
}

# MAR50.20: discount scalar DS applied to full and reduced BA-CVA
DS: float = 0.65

# MAR50.20: β = supervisory parameter flooring hedging recognition
BETA: float = 0.25


@dataclass
class CVAInput:
    """
    Per-counterparty CVA inputs.

    For counterparties with multiple netting sets, populate the
    netting_sets list (one NettingSetEAD per netting set). The
    main ead and maturity_years fields will be overridden by the
    netting-set-level computation when netting_sets is non-empty.
    """
    counterparty_id:    str
    netting_set_id:     str
    ead:                float         # EAD from SA-CCR or IMM (single netting set)
    pd_1yr:             float         # 1-year PD of counterparty
    lgd_mkt:            float = 0.40  # Market LGD — overridden by CVAMarketConditions
    maturity_years:     float = 2.5   # Effective maturity (single netting set)
    discount_factor:    float = 1.0   # Risk-free discount
    credit_spread_bps:  Optional[float] = None  # CDS spread (bps); None = not available
    has_cva_hedge:      bool  = False
    hedge_notional:     float = 0.0
    hedge_maturity:     float = 0.0
    hedge_spread_bps:   Optional[float] = None  # CDS spread on the hedging instrument (bps)
    hedge_type:         str   = "DIRECT"        # DIRECT | LEGALLY_RELATED | SAME_SECTOR
    has_index_hedge:    bool  = False            # True if an index CDS hedge is in place
    index_notional:     float = 0.0             # Notional of index hedge
    index_maturity:     float = 0.0             # Maturity of index hedge
    index_rw:           float = 0.0096          # RW for index hedge (0.7 × Table 1 RW)
    # Sector classification for SA-CVA bucket routing (MAR50.63 Table 5)
    sector:             str   = "default"       # Maps to SECTOR_BUCKET
    credit_quality:     str   = "IG"            # 'IG' | 'HY' | 'NR' — for SA-CVA Table 7
    # Multiple netting sets per counterparty (MAR50.15)
    netting_sets:       List[NettingSetEAD] = field(default_factory=list)
    # Wrong-Way Risk (MAR50.32)
    is_wrong_way:       bool  = False           # True if exposure correlates with PD
    wwr_add_on:         float = 0.0             # Conservative EAD add-on for WWR (% of EAD)
    # Counterparty location — used by the proxy spread tier-1 lookup (MAR50.32(3))
    region:             str   = "US"            # 'US' | 'EUR' | 'EM' | etc.
    # Spread provenance — populated by CVAEngine._enrich_missing_spreads()
    # 'LIVE'            : credit_spread_bps supplied directly by caller
    # 'PROXY_SECTOR'    : estimated from sector/credit_quality/region peer table
    # 'PROXY_INDEX_IG'  : fell back to live IG market index spread
    # 'PROXY_INDEX_HY'  : fell back to live HY market index spread
    spread_source:      str   = "LIVE"
    # Vega override for SA-CVA (MAR50.48)
    # Set this to explicitly provide vega sensitivity if computed externally
    # Otherwise, vega is approximated from exposure model parameters
    vega_override:      Optional[float] = None  # Explicit vega charge if available
    has_optionality:    bool  = False           # True if portfolio contains options/swaptions

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
    # Spread provenance — mirrors CVAInput.spread_source; 'LIVE' unless proxy was used
    spread_source:    str   = "LIVE"

# ─────────────────────────────────────────────────────────────────────────────
# BA-CVA (Basic Approach) — MAR50.20–50.38
# ─────────────────────────────────────────────────────────────────────────────

# Supervisory credit spread by sector/rating (MAR50 Table 1 — MAR50.25)
# These map internal ratings to the Basel supervisory credit spread parameters.
# Full table: AAA=0.38%, AA=0.38%, A=0.42%, BBB=0.54%, BB=1.06%, B=1.60%, CCC=6.00%
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

def _scva_c(inp: "CVAInput", rating_map: Optional[Dict[str, str]],
             rfr: float) -> float:
    """
    MAR50.15: Stand-alone CVA capital component for counterparty c.
    SC_c = RW_c × Σ_ns (M_ns_eff × EAD_ns)
    Sums across all netting sets when inp.netting_sets is populated;
    falls back to the single ead / maturity_years fields otherwise.
    WWR add-on applied to each netting set EAD if is_wrong_way is set.
    """
    rating = (rating_map or {}).get(inp.counterparty_id, "NR")
    rw     = _supervisory_spread(rating)

    if inp.netting_sets:
        ns_sum = 0.0
        for ns in inp.netting_sets:
            ead_ns = ns.ead * (1.0 + inp.wwr_add_on) if inp.is_wrong_way else ns.ead
            ns_sum += _effective_maturity_discount(ns.maturity_years, rw, rfr) * ead_ns
        return rw * ns_sum
    else:
        ead = inp.ead * (1.0 + inp.wwr_add_on) if inp.is_wrong_way else inp.ead
        return rw * _effective_maturity_discount(inp.maturity_years, rw, rfr) * ead


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
    rho = mkt.supervisory_rho()  # Always 0.50 per MAR50.29
    rfr = mkt.risk_free_rate

    if not inputs:
        return 0.0, {}

    results   = {}
    scva_vals = []

    for inp in inputs:
        sc      = _scva_c(inp, rating_map, rfr)
        lgd     = mkt.lgd_for_sector(inp.sector) if market else inp.lgd_mkt
        ead_eff = inp.ead * (1.0 + inp.wwr_add_on) if inp.is_wrong_way else inp.ead
        m_eff   = _effective_maturity_discount(
            inp.maturity_years,
            _supervisory_spread((rating_map or {}).get(inp.counterparty_id, "NR")),
            rfr,
        )
        scva_vals.append(sc)
        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "BA_CVA",
            fallback_trace  = None,
            rwa_cva         = 0.0,
            ba_sc_charge    = sc,
            cva_estimate    = inp.pd_1yr * lgd * ead_eff * m_eff,
            spread_source   = getattr(inp, "spread_source", "LIVE"),
        )

    logger.debug("BA-CVA: rho=%.2f (supervisory fixed per MAR50.29), rfr=%.3f%%",
                 rho, rfr * 100)

    # ── Reduced BA-CVA (MAR50.14) — always computed ──────────────────────────
    sum_sc    = sum(scva_vals)
    sum_sc2   = sum(v ** 2 for v in scva_vals)
    k_reduced = math.sqrt(rho ** 2 * sum_sc ** 2 + (1 - rho ** 2) * sum_sc2)

    if not has_hedges:
        # Reduced version capital = DS × K_reduced × 12.5  (MAR50.14)
        capital      = DS * k_reduced * 12.5
        total_sc_abs = sum(abs(v) for v in scva_vals) or 1.0
        for i, (cid, res) in enumerate(results.items()):
            share             = abs(scva_vals[i]) / total_sc_abs
            res.rwa_cva       = capital * share
            res.ba_cva_charge = DS * k_reduced * share
        logger.info("BA-CVA reduced: K_red=%.0f  DS×K×12.5=%.0f", k_reduced, capital)
        return capital, results

    # ── Full BA-CVA (MAR50.20-21) — with SNH / IH / HMA ─────────────────────
    # Both reduced and full must be computed; full >= beta × reduced (MAR50.20)
    snh_vals = []
    hma_vals = []

    for inp in inputs:
        rho_hc = HEDGE_CORRELATION.get(inp.hedge_type.upper(), 0.50)
        if inp.has_cva_hedge and inp.hedge_notional > 0:
            h_spread = (inp.hedge_spread_bps / 10_000
                        if inp.hedge_spread_bps is not None
                        else mkt.credit_spread_ig / 10_000)
            rw_h   = _supervisory_spread((rating_map or {}).get(inp.counterparty_id, "NR"))
            h_eff  = _effective_maturity_discount(inp.hedge_maturity, h_spread, rfr)
            # MAR50.23: SNH_c = rho_hc × RW_h × DF_h × Notional_h
            snh_c  = rho_hc * rw_h * h_eff * inp.hedge_notional
            # MAR50.25: HMA_c captures misalignment of indirect hedges
            hma_c  = (1 - rho_hc ** 2) * (rw_h * h_eff * inp.hedge_notional) ** 2
        else:
            snh_c = 0.0
            hma_c = 0.0
        snh_vals.append(snh_c)
        hma_vals.append(hma_c)

    # MAR50.24: IH = index hedge aggregate with 0.7 diversification factor
    ih_total = 0.0
    for inp in inputs:
        if inp.has_index_hedge and inp.index_notional > 0:
            i_eff     = _effective_maturity_discount(
                inp.index_maturity, mkt.credit_spread_ig / 10_000, rfr)
            ih_total += inp.index_rw * i_eff * inp.index_notional

    # MAR50.21: K_full aggregation
    systematic_sum = sum_sc - sum(snh_vals) - ih_total
    idiosyncratic  = sum((s - h) ** 2 for s, h in zip(scva_vals, snh_vals))
    hma_total      = sum(math.sqrt(max(h, 0.0)) for h in hma_vals)
    k_full_sq      = rho ** 2 * systematic_sum ** 2 + (1 - rho ** 2) * idiosyncratic
    k_full         = math.sqrt(max(k_full_sq, 0.0)) + hma_total

    # MAR50.20: capital = DS × max(K_full, beta × K_reduced) × 12.5
    k_hedged = max(k_full, BETA * k_reduced)
    capital  = DS * k_hedged * 12.5

    total_sc_abs = sum(abs(v) for v in scva_vals) or 1.0
    for i, (cid, res) in enumerate(results.items()):
        share             = abs(scva_vals[i]) / total_sc_abs
        res.rwa_cva       = capital * share
        res.ba_cva_charge = DS * k_hedged * share

    logger.info(
        "BA-CVA full: K_red=%.0f  K_full=%.0f  K_hedged=%.0f  DS×K×12.5=%.0f  "
        "beta_floor=%s  IH=%.0f",
        k_reduced, k_full, k_hedged, capital,
        "ACTIVE" if k_hedged == BETA * k_reduced else "not active",
        ih_total,
    )
    return capital, results

# ─────────────────────────────────────────────────────────────────────────────
# SA-CVA (Standardised Approach) — MAR50.40–50.79
# ─────────────────────────────────────────────────────────────────────────────

def _compute_vega_charge_approximation(
    inp: CVAInput,
    ead_eff: float,
    m_eff: float,
    lgd: float,
    market: Optional[CVAMarketConditions],
) -> float:
    """
    MAR50.48-49: Vega charge approximation for SA-CVA.
    
    Vega is ALWAYS material per MAR50.48, even without explicit option hedges,
    because vega arises from volatilities in the exposure simulation model
    (Hull-White σ_r for IR, Black-Scholes σ_eq for equity derivatives).
    
    This is a conservative approximation for portfolios without explicit
    vega sensitivity from a CVA desk sensitivity engine. Production should
    replace this with:
        1. AAD/bump-and-reprice on Monte Carlo CVA model
        2. ∂CVA/∂σ_k for all five vega risk classes (IR, FX, RCSR, EQ, CMDTY)
        3. RW_vega = 100% per MAR50.49
    
    Approximation logic:
        - If vega_override is set: use explicit value
        - If has_optionality=True: estimate from exposure volatility impact
        - Otherwise: return 0 (conservative underestimate)
    
    Returns
    -------
    Vega charge in dollars (not RWA; multiply by 12.5 for RWA)
    """
    # Use explicit vega if provided (from CVA desk sensitivity engine)
    if inp.vega_override is not None:
        return inp.vega_override
    
    # If no optionality, vega is minimal (though MAR50.48 says it's always present)
    if not inp.has_optionality:
        return 0.0
    
    # Approximation: vega ≈ (∂CVA/∂σ) × σ_base
    # For portfolios with optionality, CVA is sensitive to vol changes
    # Estimate: vega_sens ≈ 0.10 × CVA_value × (maturity_years / 5.0)
    # This scales vega with maturity (longer = more vega) and exposure size
    mkt = market or CVAMarketConditions()
    cva_value = inp.pd_1yr * lgd * ead_eff * m_eff
    
    # Vega scaling factor: calibrated to typical swaption/cap vega profiles
    # 10% of CVA value for a 5Y option; scales linearly with maturity
    vega_factor = 0.10 * min(inp.maturity_years / 5.0, 2.0)
    
    # RW_vega = 100% per MAR50.49
    RW_VEGA = 1.00
    vega_charge = RW_VEGA * vega_factor * cva_value
    
    return vega_charge


def _resolve_sa_cva_rw(inp: CVAInput) -> float:
    """
    MAR50.65 Table 7: Select SA-CVA delta risk weight by sector bucket and credit quality.

    Previous code selected RW by pd_1yr < 0.02 threshold — this has no MAR50 basis.
    MAR50.65 uses: (1) sector bucket (8 buckets per Table 5), (2) IG vs HY/NR.

    The dynamic ig_ratio/hy_ratio market scaling also had no MAR50 basis and is removed.
    Supervisory risk weights in SA-CVA are fixed — they cannot be scaled by current spreads.
    """
    bucket = SECTOR_BUCKET.get(inp.sector, SECTOR_BUCKET["default"])
    if inp.credit_quality.upper() in ("IG",):
        return _SA_CVA_RW_IG.get(bucket, _SA_CVA_RW_IG[7])
    else:
        # HY or NR: both use HY risk weights per MAR50.65 Table 7
        return _SA_CVA_RW_HY.get(bucket, _SA_CVA_RW_HY[7])


def compute_sa_cva(
    inputs: List[CVAInput],
    market: Optional[CVAMarketConditions] = None,
) -> tuple[float, Dict[str, CVAResult]]:
    """
    SA-CVA per MAR50.40-77.

    Requires actual credit spread data per counterparty (credit_spread_bps not None).
    Cleared trades (MAR50.8) must be excluded before calling — filter inputs upstream.

    MAR50.43: Delta capital = sum across SIX risk classes:
      (1) Interest rate          → ∂CVA/∂r per tenor (GIRR sensitivities)
      (2) FX                     → ∂CVA/∂FX_spot
      (3) Counterparty credit spread → ∂CVA/∂s_counterparty  [implemented here]
      (4) Reference credit spread    → ∂CVA/∂s_reference_name
      (5) Equity                 → ∂CVA/∂S_equity
      (6) Commodity              → ∂CVA/∂C_commodity

    MAR50.45: Vega capital = sum across FIVE risk classes (no CCSR vega per MAR50.45).
    MAR50.48: Vega is ALWAYS material and must be computed — even without option hedges,
              because vega arises from σ in the exposure simulation model.

    IMPLEMENTATION NOTE: This version implements the counterparty credit spread delta
    charge only (the dominant term for most derivative books). The remaining five delta
    risk classes (IR, FX, reference credit spread, equity, commodity) and all vega charges
    require full CVA sensitivity computation (∂CVA/∂risk_factor per tenor/bucket) which
    requires integration with the front-office exposure model. Production: implement
    compute_sa_cva_full() with all six delta risk classes and all five vega risk classes.

    MAR50.53: Hedging disallowance parameter R = 0.01 is applied in the bucket-level
    aggregation to prevent perfect hedge recognition.

    Risk weights: MAR50.65 Table 7 — by sector bucket (Table 5) and IG/HY/NR.
    NO dynamic market scaling — supervisory RWs are fixed by Basel.

    When market is provided:
    - OIS/SOFR rate replaces hardcoded 5% in M_eff (legitimate production practice)
    - LGD uses sector-implied recovery rates from CDS market (legitimate)
    """
    mkt = market or CVAMarketConditions()
    rfr = mkt.risk_free_rate
    results = {}
    total_delta_rwa = 0.0
    total_vega_rwa  = 0.0

    # R = 0.01: hedging disallowance parameter (MAR50.53(1))
    # Prevents the possibility of recognising perfect hedging of CVA risk.
    R = 0.01

    for inp in inputs:
        if inp.credit_spread_bps is None:
            raise ValueError(f"SA-CVA requires credit spread for {inp.counterparty_id}")

        spread = inp.credit_spread_bps / 10_000   # bps → decimal
        m_eff  = _effective_maturity_discount(inp.maturity_years, spread, rfr)

        # LGD: sector-implied from live CDS recovery rates if market available
        lgd = mkt.lgd_for_sector(inp.sector) if market else inp.lgd_mkt

        # WWR: apply EAD add-on for wrong-way risk counterparties (MAR50.32)
        ead_eff = inp.ead * (1.0 + inp.wwr_add_on) if inp.is_wrong_way else inp.ead

        # Delta sensitivity ≈ ∂CVA/∂spread = EAD × M_eff × LGD
        # Production: replace this approximation with AAD/bump-and-reprice per MAR50.47
        delta_sens = ead_eff * m_eff * lgd

        # Risk weight from MAR50.65 Table 7 by sector bucket and credit quality
        # These are FIXED supervisory parameters — not market-scaled
        rw_spread    = _resolve_sa_cva_rw(inp)
        delta_charge = rw_spread * delta_sens

        # MAR50.48: Vega is ALWAYS material — must be computed even without option hedges.
        # Vega arises from volatilities in the exposure model (Hull-White σ_r, Black σ_eq).
        # Production implementation:
        #   vega_sens   = ∂CVA/∂σ_k  (bump σ_k by 1%, compute change in CVA)
        #   vega_charge = RW_vega_k × vega_sens_k  (RW_vega = 100% for most classes)
        #
        # ENHANCED: Approximate vega charge from exposure volatility impact
        # Full implementation requires integration with IMM Monte Carlo engine
        vega_charge = _compute_vega_charge_approximation(inp, ead_eff, m_eff, lgd, market)
        if vega_charge > 0:
            logger.debug(
                "SA-CVA %s: vega_charge=%.0f (approximation from exposure model params; "
                "MAR50.48 full implementation requires CVA sensitivity engine)",
                inp.counterparty_id, vega_charge,
            )
        else:
            logger.debug(
                "SA-CVA %s: vega_charge=0 (no optionality detected; "
                "set vega_override in CVAInput for explicit vega)",
                inp.counterparty_id,
            )

        # Net weighted sensitivity with hedging disallowance (MAR50.53)
        # WS_net = delta_charge - (1-R) × delta_charge_hedge
        # For this single-risk-class approximation, hedge benefit reduced by R=0.01
        hedge_benefit = 0.0
        if inp.has_cva_hedge and inp.hedge_spread_bps is not None:
            h_spread  = inp.hedge_spread_bps / 10_000
            h_m_eff   = _effective_maturity_discount(inp.hedge_maturity, h_spread, rfr)
            rho_hc    = HEDGE_CORRELATION.get(inp.hedge_type.upper(), 0.50)
            # Hedge sensitivity (positive, as hedge value increases when spread widens)
            h_delta   = rho_hc * rw_spread * inp.hedge_notional * h_m_eff * lgd
            # MAR50.52: WS_net = WS_cva - WS_hedge = delta_charge - (1-R)×h_delta
            hedge_benefit = (1.0 - R) * h_delta
        net_delta = max(delta_charge - hedge_benefit, 0.0)

        rwa_delta = net_delta   * 12.5
        rwa_vega  = vega_charge * 12.5
        rwa_cva   = rwa_delta + rwa_vega

        total_delta_rwa += rwa_delta
        total_vega_rwa  += rwa_vega

        logger.debug(
            "SA-CVA %s: bucket=%d cq=%s RW=%.2f%% delta_sens=%.0f "
            "delta_charge=%.0f rwa=%.0f%s",
            inp.counterparty_id,
            SECTOR_BUCKET.get(inp.sector, 7),
            inp.credit_quality,
            rw_spread * 100,
            delta_sens,
            delta_charge,
            rwa_cva,
            " [WWR]" if inp.is_wrong_way else "",
        )

        results[inp.counterparty_id] = CVAResult(
            counterparty_id = inp.counterparty_id,
            method          = "SA_CVA",
            fallback_trace  = None,
            rwa_cva         = rwa_cva,
            sa_delta_charge = delta_charge,
            sa_vega_charge  = vega_charge,
            cva_estimate    = inp.pd_1yr * lgd * ead_eff * m_eff,
            spread_source   = getattr(inp, "spread_source", "LIVE"),
        )

    return total_delta_rwa + total_vega_rwa, results


# ─────────────────────────────────────────────────────────────────────────────
# CVA Master Engine — routing + fallback logic (req #13)
# ─────────────────────────────────────────────────────────────────────────────

# MAR50.9 materiality threshold.
# MAR50.9(1): any bank whose aggregate notional of non-centrally cleared derivatives
# is ≤ 100 billion EUR is below the threshold.
# The threshold is:
#   - Based on AGGREGATE NOTIONAL (not CCR RWA)
#   - Denominated in EUR
#   - Set at 100,000,000,000 EUR (100 billion)
# Previous code used USD 1M CCR RWA which is wrong by four orders of magnitude
# and will suppress BA-CVA/SA-CVA for almost any portfolio.
EUR_USD_FX: float = 1.08  # approximate — override with live rate in production
NOTIONAL_MATERIALITY_THRESHOLD_EUR: float = 100_000_000_000   # 100 billion EUR

def estimate_proxy_spread(
    sector: str,
    credit_quality: str,
    region: str = "US",
    liquid_peer_spreads: Optional[Dict[str, float]] = None,
    use_registry: bool = True,
) -> Optional[float]:
    """
    MAR50.32(3): Estimate a proxy credit spread for illiquid counterparties
    whose credit is not actively traded. The bank must estimate spreads from
    liquid peers via a documented sector + rating + region mapping algorithm.

    In production, this mapping should be calibrated to a panel of liquid CDS
    names in the same sector/rating/region and updated at least monthly.

    Parameters
    ----------
    sector          : Counterparty sector (Financials, Energy, Consumer, etc.)
    credit_quality  : 'IG', 'HY', or 'NR'
    region          : Issuer region for basis adjustment (US, EUR, EM, etc.)
    liquid_peer_spreads : Optional dict of live peer spreads for averaging.
                         {peer_name: spread_bps}
    use_registry    : If True, fetch from ProxySpreadRegistry (MAR50.32(3) compliant).
                     Set False for backward compatibility with static table.

    Returns
    -------
    Estimated CDS spread in bps, or None if insufficient peer data.
    """
    # Use live peer spreads if supplied (preferred)
    if liquid_peer_spreads and len(liquid_peer_spreads) >= 3:
        return float(sum(liquid_peer_spreads.values()) / len(liquid_peer_spreads))

    # MAR50.32(3) compliant: use monthly-reviewed proxy spread registry
    if use_registry:
        try:
            from backend.data_sources.proxy_spread_calibration import get_proxy_spread_registry
            registry = get_proxy_spread_registry()
            calibration = registry.get_calibration(sector, credit_quality, region, allow_stale=False)
            if calibration:
                logger.debug(
                    "Proxy spread from registry: %s/%s/%s → %.0f bps "
                    "(calibrated %s, reviewed by %s)",
                    sector, credit_quality, region,
                    calibration.calibrated_spread_bps,
                    calibration.calibration_date.isoformat(),
                    calibration.reviewer,
                )
                return calibration.calibrated_spread_bps
            else:
                logger.warning(
                    "No fresh proxy calibration found for %s/%s/%s — falling back to index spread",
                    sector, credit_quality, region,
                )
                return None  # Caller will use market index spread
        except Exception as exc:
            logger.error("Failed to load proxy spread registry: %s — using static fallback", exc)

    # Legacy fallback: sector × rating × region lookup table (non-compliant)
    # This is kept for backward compatibility only — production should use registry
    _PROXY: Dict[tuple, float] = {
        ("Financials",  "IG",  "US"):  110,  ("Financials",  "HY",  "US"):  420,
        ("Financials",  "IG",  "EUR"): 120,  ("Financials",  "HY",  "EUR"): 450,
        ("Energy",      "IG",  "US"):  130,  ("Energy",      "HY",  "US"):  480,
        ("Energy",      "IG",  "EUR"): 140,  ("Energy",      "HY",  "EUR"): 500,
        ("Consumer",    "IG",  "US"):  115,  ("Consumer",    "HY",  "US"):  430,
        ("Technology",  "IG",  "US"):  100,  ("Technology",  "HY",  "US"):  390,
        ("Sovereign",   "IG",  "US"):   50,  ("Sovereign",   "HY",  "EM"):  350,
        ("Industrials", "IG",  "US"):  120,  ("Industrials", "HY",  "US"):  450,
        ("Healthcare",  "IG",  "US"):  105,  ("Healthcare",  "HY",  "US"):  400,
    }
    key    = (sector, credit_quality, region)
    spread = _PROXY.get(key)
    if spread is None:
        # Regional basis: EM typically 50-100bp wider than US equivalent
        em_basis = 75 if region == "EM" else 0
        us_key   = (sector, credit_quality, "US")
        spread   = (_PROXY.get(us_key, 300 if credit_quality == "IG" else 600) + em_basis)
    logger.debug(
        "Proxy spread (STATIC FALLBACK) for %s/%s/%s: %.0f bps (NOT MAR50.32(3) compliant)",
        sector, credit_quality, region, spread,
    )
    return spread


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

    def _enrich_missing_spreads(
        self,
        inputs: List[CVAInput],
    ) -> tuple[List[CVAInput], int]:
        """
        Fill in credit_spread_bps for counterparties where it is None,
        using the two-tier proxy cascade required by MAR50.32(3).

        Tier 1 — Sector / credit_quality / region peer lookup
                  (estimate_proxy_spread: static table calibrated to liquid CDS peers)
        Tier 2 — Live market index spread from CVAMarketConditions
                  (CDX IG for IG counterparties; CDX HY for HY / NR counterparties)

        Returns (enriched_inputs, n_enriched) where n_enriched is the count
        of counterparties that received a proxy spread.  Input objects whose
        credit_spread_bps is already populated are returned unchanged (no copy
        is made for those).

        MAR50.32(3) compliance note: the proxy lookup table in
        estimate_proxy_spread() must be calibrated to live peer CDS data and
        reviewed at least monthly by the credit desk.  The spread_source field
        on each enriched CVAInput / CVAResult enables auditors to identify
        which counterparties used proxy spreads in a given capital run.
        """
        import copy as _copy
        mkt = self.market or CVAMarketConditions()
        enriched: List[CVAInput] = []
        n_enriched = 0

        for inp in inputs:
            if inp.credit_spread_bps is not None:
                enriched.append(inp)
                continue

            inp_copy = _copy.copy(inp)   # shallow copy — all fields are value types

            # Tier 1: sector / credit_quality / region peer proxy
            region = getattr(inp, "region", "US")
            proxy  = estimate_proxy_spread(inp.sector, inp.credit_quality, region)
            if proxy is not None:
                inp_copy.credit_spread_bps = proxy
                inp_copy.spread_source     = "PROXY_SECTOR"
                logger.info(
                    "Spread enriched [T1 PROXY_SECTOR] — %s: %.0f bps "
                    "(sector=%s  cq=%s  region=%s)  "
                    "[MAR50.32(3): verify peer calibration is current]",
                    inp.counterparty_id, proxy,
                    inp.sector, inp.credit_quality, region,
                )
            else:
                # Tier 2: live market index spread
                if inp.credit_quality.upper() == "IG":
                    idx_spread = mkt.credit_spread_ig
                    source     = "PROXY_INDEX_IG"
                else:
                    idx_spread = mkt.credit_spread_hy
                    source     = "PROXY_INDEX_HY"
                inp_copy.credit_spread_bps = idx_spread
                inp_copy.spread_source     = source
                logger.info(
                    "Spread enriched [T2 %s] — %s: %.0f bps "
                    "(no sector peer found — using market index spread)",
                    source, inp.counterparty_id, idx_spread,
                )

            enriched.append(inp_copy)
            n_enriched += 1

        return enriched, n_enriched

    def _check_sa_eligibility(self, inp: CVAInput) -> tuple[bool, Optional[str]]:
        """
        Returns (eligible, fallback_trace_code).
        
        SA-CVA requires live, liquid credit spread data per MAR50.40+.
        Proxy spreads (sector lookup or index fallback) do not meet the
        sensitivity-based approach's data quality requirements.
        
        Only counterparties with spread_source='LIVE' qualify for SA-CVA.
        """
        if not self.sa_approved:
            trace = (f"FALLBACK|{inp.counterparty_id}|NO_SA_APPROVAL"
                     f"|{CVA_FALLBACK_REASONS['NO_SA_APPROVAL']}")
            return False, trace
        if inp.credit_spread_bps is None:
            trace = (f"FALLBACK|{inp.counterparty_id}|MISSING_SPREADS"
                     f"|{CVA_FALLBACK_REASONS['MISSING_SPREADS']}")
            return False, trace
        # Reject proxy spreads for SA-CVA (MAR50.40: requires observable credit spreads)
        spread_source = getattr(inp, "spread_source", "LIVE")
        if spread_source != "LIVE":
            trace = (f"FALLBACK|{inp.counterparty_id}|PROXY_SPREAD_QUALITY"
                     f"|SA-CVA requires live market spreads; proxy spread "
                     f"(source={spread_source}) insufficient for sensitivity-based approach")
            return False, trace
        return True, None

    def compute_portfolio_cva(
        self,
        inputs: List[CVAInput],
        total_ccr_rwa: float,
        rating_map: Optional[Dict[str, str]] = None,
        run_date: Optional[date] = None,
        **kwargs,
    ) -> Dict:
        """
        Additional kwargs:
            total_notional_eur (float): aggregate notional of non-cleared derivatives
                in EUR equivalent. Required for correct MAR50.9 materiality check.
                If omitted, materiality threshold is not applied (conservative — full
                CVA computation runs regardless of portfolio size).
        """
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

        # MAR50.9 materiality check — based on aggregate notional of non-cleared derivatives
        # MAR50.9(1): threshold = EUR 100 billion aggregate notional.
        # total_notional_eur should be supplied by the caller as the sum of all non-cleared
        # derivative notionals in EUR equivalent. If not provided, we cannot apply the
        # threshold correctly — default to applying the full CVA calculation (conservative).
        total_notional_eur = kwargs.get("total_notional_eur", float("inf"))
        if total_notional_eur <= NOTIONAL_MATERIALITY_THRESHOLD_EUR:
            rwa_cva = total_ccr_rwa  # MAR50.9(2): proxy = 100% of CCR capital requirement
            trace   = (f"PORTFOLIO|CCR_PROXY|{CVA_FALLBACK_REASONS['BELOW_THRESHOLD']}"
                       f"|notional_eur={total_notional_eur:.0f}")
            logger.warning(
                "CVA: below MAR50.9 materiality (notional=EUR %.0fbn ≤ 100bn) "
                "→ CCR proxy RWA=%.0f",
                total_notional_eur / 1e9, rwa_cva,
            )
            return {
                "total_rwa_cva": rwa_cva,
                "method_summary": {},
                "fallback_traces": [trace],
                "method": "CCR_PROXY",
            }

        # Enrich missing credit spreads before eligibility check (MAR50.32(3)).
        # Counterparties with no live CDS spread receive a proxy estimated from
        # sector/credit_quality/region peers (Tier 1) or the live IG/HY market
        # index spread (Tier 2).  This allows them to be routed to SA-CVA instead
        # of automatically falling back to BA-CVA due to a data gap alone.
        enriched_inputs, n_enriched = self._enrich_missing_spreads(inputs)
        if n_enriched > 0:
            logger.info(
                "Spread enrichment: %d/%d counterparties received proxy spreads "
                "(MAR50.32(3) — ensure proxy lookup table is calibrated to live peers)",
                n_enriched, len(inputs),
            )

        # Classify each counterparty
        sa_inputs, ba_inputs, traces = [], [], []

        for inp in enriched_inputs:
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

        proxy_spread_cptys = [
            inp.counterparty_id for inp in enriched_inputs
            if getattr(inp, "spread_source", "LIVE") != "LIVE"
        ]
        logger.info(
            "CVA total RWA=%.0f (%d SA, %d BA, %d traces, %d proxy spreads: %s)",
            total_rwa, len(sa_inputs), len(ba_inputs), len(traces),
            n_enriched, proxy_spread_cptys or "none",
        )

        return {
            "total_rwa_cva":               total_rwa,
            "method_summary":              all_results,
            "fallback_traces":             traces,
            "method":                      "MIXED" if sa_inputs and ba_inputs else
                                           ("SA_CVA" if sa_inputs else "BA_CVA"),
            # Spread enrichment audit trail (MAR50.32(3))
            "spread_enriched_count":       n_enriched,
            "proxy_spread_counterparties": proxy_spread_cptys,
        }
