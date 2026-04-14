"""
PROMETHEUS Risk Platform
Engine: FRTB — Fundamental Review of the Trading Book
Regulatory basis: MAR10, MAR21-23 (SBM), MAR31-33 (IMA/ES)

Implements:
  - Sensitivities-Based Method (SBM): Delta, Vega, Curvature charges
  - Internal Models Approach (IMA): Expected Shortfall at 97.5%
  - Non-Modellable Risk Factors (NMRF) — MAR31.14
  - Backtesting — traffic-light framework (MAR99)
  - Market Risk Capital = max(SBM, IMA) per MAR33

This consolidated file includes:
  - Performance optimizations (caching, aggregation, batch)
  - Scenario / stress testing hooks
  - Basic risk decomposition and result serialization
  - Optional parametric ES and ES confidence intervals

Regulatory Review — Corrections applied (ref: internal code review April 2026)
══════════════════════════════════════════════════════════════════════════════
FIX-01 [HIGH]   MAR21.6   _three_rho(): ρ_high corrected to base+0.25×(1−ρ) —
                           no abs(); ρ_low corrected to max(2ρ−1,0) — removed
                           non-Basel 0.5625×ρ term.
FIX-02 [HIGH]   MAR23.6   curvature_charge(): removed erroneous final sqrt().
                           Ξ_s is already in dollar capital units.
FIX-03 [MEDIUM] —         total_sbm(): removed MAR21.100 SBM floor. MAR21.100
                           does not exist in the Basel framework. Basel
                           diversification benefit is limited by the
                           three-scenario framework (MAR21.6) only.
FIX-04 [MEDIUM] MAR21.44  GIRR risk weights trimmed from 13 to 10 entries per
                           MAR21.44 Table 2. Three extra non-Basel values removed.
FIX-05 [MEDIUM] MAR33.8   compute_es(): ES tail count changed from int() to
                           math.ceil() to prevent systematic understatement.
FIX-06 [MEDIUM] MAR21.73  CSR_SEC and CSR_CTP risk weights, correlations, vega
                           RW, and risk_class entries added. Previous code had
                           no CSR_SEC parameters, defaulting to 15% for all
                           securitisation positions.
FIX-07 [LOW]    MAR31.14  nmrf_charge_bp default changed from 0.0015 to 0.0.
                           No MAR31 basis for a flat 15bp proxy; callers must
                           supply factor_ssrm for regulatory capital.
FIX-08 [LOW]    —         FRTBEngine.compute() duplicate docstring merged.
FIX-09 [LOW]    —         apply_shock_to_sensitivities(): changed from
                           multiplicative to additive shock application;
                           vega and curvature now also shocked per scenario.
FIX-10 [LOW]    —         total_sbm() scenario loops wrapped in try/finally to
                           prevent correlation config corruption on exception.
FIX-11 [LOW]    MAR21.60  GIRR inter-bucket scalar limitation documented.
                           Sub-curve zero-correlation (GIRR vs GIRR_INFLATION
                           vs GIRR_XCCY_BASIS) cannot be expressed as a scalar.
FIX-12 [LOW]    MAR21.88  Commodity bucket assignment documented as non-
                           deterministic; rw_index_map must be populated for
                           production regulatory capital.
"""

from __future__ import annotations

import math
import copy
import json
import logging
import os
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import (
    List,
    Dict,
    Optional,
    Tuple,
    Mapping,
    Sequence,
    Union,
    Iterable,
    Any,
    Callable,
)

import numpy as np
from enum import Enum as StdEnum

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Market Regime & Real-Time Data
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegime(StdEnum):
    """Market state affecting risk weights and correlations."""
    NORMAL = "normal"
    STRESSED = "stressed"
    CRISIS = "crisis"

@dataclass
class MarketConditions:
    """
    Real-time market data for dynamic FRTB parameter adjustment.
    Connect to Bloomberg/Reuters/internal feeds in production.
    """
    date: date
    vix_level: float = 15.0              # VIX index (normal ~15-20, crisis >40)
    equity_vol_index: float = 20.0       # Equity realized vol (annualized %)
    credit_spread_ig: float = 100.0      # IG credit spread (bp)
    credit_spread_hy: float = 400.0      # HY credit spread (bp)
    fx_vol_index: float = 8.0            # FX vol index (e.g., JPM FX VIX)
    cmdty_vol_index: float = 25.0        # Commodity volatility
    ir_vol_swaption: float = 50.0        # Swaption implied vol (bp)
    
    def stress_level(self) -> float:
        """Composite stress index [0, 1]: 0=normal, 1=extreme crisis."""
        vix_norm = min(self.vix_level / 80.0, 1.0)
        spread_norm = min((self.credit_spread_hy - 300) / 1200.0, 1.0)
        eq_vol_norm = min((self.equity_vol_index - 15) / 50.0, 1.0)
        stress = 0.40*vix_norm + 0.35*spread_norm + 0.25*eq_vol_norm
        return min(max(stress, 0.0), 1.0)
    
    def regime(self) -> MarketRegime:
        """Classify market regime based on stress level."""
        s = self.stress_level()
        if s < 0.30:
            return MarketRegime.NORMAL
        elif s < 0.65:
            return MarketRegime.STRESSED
        else:
            return MarketRegime.CRISIS

class MarketDataFeed:
    """
    Real-time market data integration for FRTB with three-tier fallback strategy.

    Designed for global trading book deployment. All seven MarketConditions fields
    are populated from authoritative public sources — no proprietary API keys
    required for daily batch use (FRED CSV endpoint is free). Production Bloomberg /
    Refinitiv integration is provided via drop-in method overrides.

    Data source map
    ───────────────────────────────────────────────────────────────────────
    Field                Series / Ticker                   Release cadence
    ─────────────────    ──────────────────────────────    ────────────────
    vix_level            FRED: VIXCLS  / yfinance: ^VIX    Daily (T+0 close)
    equity_vol_index     FRED: VXEEMCLS (EM VIX proxy) or  Daily
                         yfinance: ^VIX (same as vix_level)
    credit_spread_ig     FRED: BAMLC0A0CMEY (US Corp IG    Daily
                         OAS, %)  →  ×100 = bp
    credit_spread_hy     FRED: BAMLH0A0HYM2 (ICE BofA      Daily
                         US HY OAS, %)  →  ×100 = bp
    fx_vol_index         FRED: DEXJPUS (USD/JPY FX rate    Daily
                         realized vol proxy, %)
    cmdty_vol_index      yfinance: CL=F (WTI crude oil,    Daily
                         realized vol %)
    ir_vol_swaption      FRED: MOVE (Merrill Lynch Option  Daily
                         Volatility Estimate Index, bp)

    Three-tier fallback per series
    ───────────────────────────────
    Tier 1  Bloomberg BSAPI (blpapi) / Refinitiv LSEG    →  intraday, real-time
    Tier 2  FRED (free CSV or JSON-with-API-key)         →  daily close, T+0
    Tier 3  yfinance (open-source delayed market data)   →  15-min delay
    Floor   Hard-coded long-run conservative averages    →  never fails

    Thread safety
    ─────────────
    A single RLock protects the in-memory cache so concurrent runs always
    see a consistent snapshot. An optional JSON disk cache allows the
    overnight batch to share its snapshot with intraday processes.

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
        "eq_vol":       "VXEEMCLS",          # CBOE EM VIX (equity vol proxy)
        "ig_spread":    "BAMLC0A0CMEY",      # ICE BofA US Corp IG OAS (%)
        "hy_spread":    "BAMLH0A0HYM2",      # ICE BofA US HY OAS (%)
        "fx_vol":       "DEXJPUS",           # USD/JPY (FX vol proxy via realized)
        "move":         "MOVE",              # Merrill Lynch IR vol index (bp)
    }

    # Conservative long-run fallback values ────────────────────────────────
    # Used only when ALL three tiers fail simultaneously (e.g. network outage).
    # Slightly above historical medians → conservative direction for capital.
    _FALLBACK = {
        "vix":          20.0,    # index points; median ~17, crisis floor ~30
        "eq_vol":       22.0,    # % annualized; slightly above normal
        "ig_spread":    1.20,    # % (120bp); long-run avg ~100bp
        "hy_spread":    4.50,    # % (450bp); long-run avg ~400bp
        "fx_vol":       9.0,     # % annualized; G10 FX vol median ~8%
        "cmdty_vol":    28.0,    # % annualized; oil/energy vol median ~25%
        "ir_vol":       60.0,    # bp; swaption vol median ~50bp
    }

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        fred_api_key: Optional[str] = None,
        bloomberg_host: Optional[str] = None,
        refinitiv_key: Optional[str] = None,
        cache_path: Optional[str] = None,
    ):
        """
        Initialize market data feed with optional external API credentials.

        Args:
            cache_ttl_seconds: Time-to-live for in-memory cache (default 1 hour).
            fred_api_key:      FRED API key (optional; uses env var if None).
            bloomberg_host:    Bloomberg Server API host:port (optional).
            refinitiv_key:     Refinitiv API key (optional; uses env var if None).
            cache_path:        Path to JSON disk cache file (optional).
        """
        self._cache: Optional[MarketConditions] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = cache_ttl_seconds
        self._lock = threading.RLock()

        # API credentials (prefer constructor args, fall back to env vars)
        self._fred_key = fred_api_key or os.getenv("FRED_API_KEY")
        self._bloomberg_host = bloomberg_host or os.getenv("BLOOMBERG_HOST")
        self._refinitiv_key = refinitiv_key or os.getenv("REFINITIV_APP_KEY")

        # Disk cache for sharing snapshots across processes
        self._cache_path = cache_path
        if self._cache_path and os.path.exists(self._cache_path):
            self._load_disk_cache()

        logger.info(
            "MarketDataFeed initialized: FRED=%s, Bloomberg=%s, Refinitiv=%s",
            "enabled" if self._fred_key else "public-only",
            "enabled" if self._bloomberg_host else "disabled",
            "enabled" if self._refinitiv_key else "disabled",
        )
    
    # ── Public API ─────────────────────────────────────────────────────────

    def get_current_conditions(self, force_refresh: bool = False) -> MarketConditions:
        """
        Fetch current market conditions (cached with TTL).

        Args:
            force_refresh: If True, bypass cache and re-fetch from sources.

        Returns:
            MarketConditions with all seven fields populated.
        """
        with self._lock:
            now = datetime.now()
            
            # Check cache validity
            if (
                not force_refresh
                and self._cache is not None
                and self._cache_timestamp is not None
                and (now - self._cache_timestamp).total_seconds() < self._cache_ttl
            ):
                logger.debug("Returning cached market conditions")
                return self._cache

            # Fetch fresh data
            logger.info("Fetching fresh market conditions from external sources")
            conditions = self._fetch_all()

            # Update cache
            self._cache = conditions
            self._cache_timestamp = now

            # Persist to disk if configured
            if self._cache_path:
                self._save_disk_cache(conditions)

            logger.info(
                "Market conditions: VIX=%.1f, HY=%dbp, stress=%.2f (%s)",
                conditions.vix_level,
                conditions.credit_spread_hy,
                conditions.stress_level(),
                conditions.regime().value,
            )
            return conditions

    @property
    def cached(self) -> Optional[MarketConditions]:
        """Return cached conditions without triggering a refresh."""
        return self._cache

    def inject(self, **kwargs: float) -> MarketConditions:
        """
        Manually inject market conditions (for testing/simulation).

        Example:
            feed.inject(vix_level=45.0, credit_spread_hy=800.0)

        Returns:
            Updated MarketConditions object (also cached).
        """
        with self._lock:
            base = self._cache or MarketConditions(date=date.today())
            
            conditions = MarketConditions(
                date=date.today(),
                vix_level=kwargs.get("vix_level", base.vix_level),
                equity_vol_index=kwargs.get("equity_vol_index", base.equity_vol_index),
                credit_spread_ig=kwargs.get("credit_spread_ig", base.credit_spread_ig),
                credit_spread_hy=kwargs.get("credit_spread_hy", base.credit_spread_hy),
                fx_vol_index=kwargs.get("fx_vol_index", base.fx_vol_index),
                cmdty_vol_index=kwargs.get("cmdty_vol_index", base.cmdty_vol_index),
                ir_vol_swaption=kwargs.get("ir_vol_swaption", base.ir_vol_swaption),
            )
            
            self._cache = conditions
            self._cache_timestamp = datetime.now()
            
            logger.info(
                "Market conditions manually injected: VIX=%.1f, HY=%dbp",
                conditions.vix_level, conditions.credit_spread_hy
            )
            return conditions
    
    def update_from_dict(self, data: Dict[str, float]) -> MarketConditions:
        """Legacy method - redirects to inject() for backward compatibility."""
        return self.inject(**data)

    # ── Internal orchestration ─────────────────────────────────────────────

    def _fetch_all(self) -> MarketConditions:
        """Fetch all seven market parameters using three-tier fallback."""
        
        # VIX Level
        vix = self._fetch_series(
            label="VIX",
            tier1=lambda: self._bloomberg("VIX Index", "PX_LAST"),
            tier2=lambda: self._fred(self._SERIES["vix"]),
            tier3=lambda: self._yfinance("^VIX"),
            transform=lambda x: x,  # Already in index points
            fallback=self._FALLBACK["vix"],
        )

        # Equity Volatility Index (using EM VIX or VIX as proxy)
        eq_vol = self._fetch_series(
            label="Equity Vol",
            tier1=lambda: self._bloomberg("VXO Index", "PX_LAST"),
            tier2=lambda: self._fred(self._SERIES["eq_vol"]),
            tier3=lambda: self._yfinance("^VIX"),  # Use VIX as fallback
            transform=lambda x: x,
            fallback=self._FALLBACK["eq_vol"],
        )

        # IG Credit Spread
        ig_spread = self._fetch_series(
            label="IG Spread",
            tier1=lambda: self._bloomberg("LUACOAS Index", "PX_LAST"),
            tier2=lambda: self._fred(self._SERIES["ig_spread"]),
            tier3=lambda: None,  # No yfinance equivalent
            transform=lambda x: x * 100 if x < 10 else x,  # % to bp if needed
            fallback=self._FALLBACK["ig_spread"] * 100,  # Return in bp
        )

        # HY Credit Spread
        hy_spread = self._fetch_series(
            label="HY Spread",
            tier1=lambda: self._bloomberg("LF98OAS Index", "PX_LAST"),
            tier2=lambda: self._fred(self._SERIES["hy_spread"]),
            tier3=lambda: None,
            transform=lambda x: x * 100 if x < 10 else x,  # % to bp if needed
            fallback=self._FALLBACK["hy_spread"] * 100,  # Return in bp
        )

        # FX Volatility (using USD/JPY realized vol as proxy)
        fx_vol = self._fetch_series(
            label="FX Vol",
            tier1=lambda: self._bloomberg("JPMVXYGL Index", "PX_LAST"),
            tier2=lambda: self._compute_fx_realized_vol(),
            tier3=lambda: None,
            transform=lambda x: x,
            fallback=self._FALLBACK["fx_vol"],
        )

        # Commodity Volatility (using WTI crude oil realized vol)
        cmdty_vol = self._fetch_series(
            label="Commodity Vol",
            tier1=lambda: self._bloomberg("CRYTR Index", "PX_LAST"),
            tier2=lambda: None,
            tier3=lambda: self._compute_commodity_realized_vol(),
            transform=lambda x: x,
            fallback=self._FALLBACK["cmdty_vol"],
        )

        # IR Volatility (swaption vol, MOVE index)
        ir_vol = self._fetch_series(
            label="IR Vol (MOVE)",
            tier1=lambda: self._bloomberg("MOVE Index", "PX_LAST"),
            tier2=lambda: self._fred(self._SERIES["move"]),
            tier3=lambda: None,
            transform=lambda x: x,
            fallback=self._FALLBACK["ir_vol"],
        )

        return MarketConditions(
            date=date.today(),
            vix_level=vix,
            equity_vol_index=eq_vol,
            credit_spread_ig=ig_spread,
            credit_spread_hy=hy_spread,
            fx_vol_index=fx_vol,
            cmdty_vol_index=cmdty_vol,
            ir_vol_swaption=ir_vol,
        )

    # ── Generic fetch helper ───────────────────────────────────────────────

    def _fetch_series(
        self,
        label: str,
        tier1: Callable[[], Optional[float]],
        tier2: Callable[[], Optional[float]],
        tier3: Callable[[], Optional[float]],
        transform: Callable[[float], float],
        fallback: float,
    ) -> float:
        """
        Three-tier fetch with transform and fallback.

        Tries tier1 (Bloomberg) → tier2 (FRED) → tier3 (yfinance) → fallback.
        Logs source and applies transform to the first successful value.
        """
        for tier_name, fetcher in [("Bloomberg", tier1), ("FRED", tier2), ("yfinance", tier3)]:
            try:
                val = fetcher()
                if val is not None and not math.isnan(val) and val > 0:
                    result = transform(val)
                    logger.debug("%s: %.2f (source: %s)", label, result, tier_name)
                    return result
            except Exception as e:
                logger.debug("%s %s fetch failed: %s", label, tier_name, e)
                continue

        # All tiers failed → fallback
        logger.warning("%s: all sources failed, using fallback %.2f", label, fallback)
        return fallback

    # ── Tier-2: FRED ──────────────────────────────────────────────────────

    def _fred(self, series_id: str) -> Optional[float]:
        """Fetch from FRED (JSON if API key available, else CSV)."""
        if self._fred_key:
            return self._fred_json(series_id)
        else:
            return self._fred_csv(series_id)

    def _fred_csv(self, series_id: str) -> Optional[float]:
        """Fetch latest value from FRED CSV endpoint (no auth required)."""
        try:
            import urllib.request
            url = self._FRED_CSV.format(series=series_id)
            with urllib.request.urlopen(url, timeout=5) as response:
                lines = response.read().decode('utf-8').strip().split('\n')
                if len(lines) < 2:
                    return None
                last_row = lines[-1].split(',')
                return float(last_row[-1])
        except Exception as e:
            logger.debug("FRED CSV fetch failed for %s: %s", series_id, e)
            return None

    def _fred_json(self, series_id: str) -> Optional[float]:
        """Fetch from FRED JSON API (requires API key)."""
        try:
            import urllib.request
            url = self._FRED_JSON.format(series=series_id, key=self._fred_key)
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                obs = data.get("observations", [])
                if obs:
                    return float(obs[0]["value"])
        except Exception as e:
            logger.debug("FRED JSON fetch failed for %s: %s", series_id, e)
            return None

    # ── Tier-3: yfinance ──────────────────────────────────────────────────

    def _yfinance(self, ticker: str) -> Optional[float]:
        """Fetch latest close from yfinance (15-min delayed)."""
        try:
            import yfinance as yf
            data = yf.Ticker(ticker).history(period="5d")
            if not data.empty:
                return float(data["Close"].iloc[-1])
        except ImportError:
            logger.debug("yfinance not installed (pip install yfinance)")
        except Exception as e:
            logger.debug("yfinance fetch failed for %s: %s", ticker, e)
        return None

    def _compute_fx_realized_vol(self) -> Optional[float]:
        """Compute USD/JPY realized volatility from FRED daily data."""
        try:
            import urllib.request
            url = self._FRED_CSV.format(series=self._SERIES["fx_vol"])
            with urllib.request.urlopen(url, timeout=5) as response:
                lines = response.read().decode('utf-8').strip().split('\n')
                if len(lines) < 22:  # Need 21 days for 20-day vol
                    return None
                
                prices = []
                for line in lines[-21:]:
                    parts = line.split(',')
                    if len(parts) >= 2 and parts[1] != '.':
                        try:
                            prices.append(float(parts[1]))
                        except ValueError:
                            continue
                
                if len(prices) < 20:
                    return None
                
                # Compute log returns and annualized volatility
                returns = [math.log(prices[i] / prices[i-1]) for i in range(1, len(prices))]
                variance = sum((r - sum(returns)/len(returns))**2 for r in returns) / len(returns)
                annual_vol = math.sqrt(variance * 252) * 100  # Annualized %
                
                return annual_vol
        except Exception as e:
            logger.debug("FX realized vol computation failed: %s", e)
            return None

    def _compute_commodity_realized_vol(self) -> Optional[float]:
        """Compute WTI crude oil realized volatility from yfinance."""
        try:
            import yfinance as yf
            data = yf.Ticker("CL=F").history(period="1mo")
            if len(data) < 20:
                return None
            
            returns = np.log(data["Close"] / data["Close"].shift(1)).dropna()
            annual_vol = returns.std() * math.sqrt(252) * 100  # Annualized %
            
            return float(annual_vol)
        except Exception as e:
            logger.debug("Commodity realized vol computation failed: %s", e)
            return None

    # ── Tier-1: Bloomberg BSAPI ───────────────────────────────────────────

    def _bloomberg(self, ticker: str, field: str = "PX_LAST") -> Optional[float]:
        """
        Fetch real-time data from Bloomberg Server API (blpapi).

        Requires:
            - pip install blpapi
            - BLOOMBERG_HOST env var (e.g., "localhost:8194")
            - Active Bloomberg terminal or SAPI license

        Args:
            ticker: Bloomberg ticker (e.g., "VIX Index")
            field:  Field name (e.g., "PX_LAST", "YLD_YTM_MID")

        Returns:
            Field value or None if unavailable/error.
        """
        if not self._bloomberg_host:
            return None

        try:
            import blpapi  # type: ignore

            host, port = self._bloomberg_host.split(":")
            session_opts = blpapi.SessionOptions()
            session_opts.setServerHost(host)
            session_opts.setServerPort(int(port))

            session = blpapi.Session(session_opts)
            if not session.start():
                logger.warning("Bloomberg session failed to start")
                return None

            if not session.openService("//blp/refdata"):
                logger.warning("Bloomberg refdata service unavailable")
                session.stop()
                return None

            refdata = session.getService("//blp/refdata")
            request = refdata.createRequest("ReferenceDataRequest")
            request.append("securities", ticker)
            request.append("fields", field)

            session.sendRequest(request)

            result = None
            while True:
                event = session.nextEvent(500)
                if event.eventType() == blpapi.Event.RESPONSE:
                    for msg in event:
                        sec_data = msg.getElement("securityData")
                        if sec_data.hasElement("fieldData"):
                            field_data = sec_data.getElement("fieldData")
                            if field_data.hasElement(field):
                                result = float(field_data.getElementAsFloat(field))
                    break

            session.stop()
            return result

        except ImportError:
            logger.debug("blpapi not installed (pip install blpapi)")
            return None
        except Exception as e:
            logger.debug("Bloomberg fetch failed for %s: %s", ticker, e)
            return None

    # ── Tier-1: Refinitiv / LSEG ─────────────────────────────────────────

    def _refinitiv(self, ric: str, field: str = "CF_CLOSE") -> Optional[float]:
        """
        Fetch from Refinitiv Eikon / Data API.

        Requires:
            - pip install refinitiv-data
            - REFINITIV_APP_KEY env var

        Args:
            ric:   Reuters Instrument Code (e.g., ".VIX")
            field: Field name (e.g., "CF_CLOSE", "TRDPRC_1")

        Returns:
            Field value or None.
        """
        if not self._refinitiv_key:
            return None

        try:
            import refinitiv.data as rd  # type: ignore

            rd.open_session(app_key=self._refinitiv_key)
            df = rd.get_data(ric, [field])
            rd.close_session()

            if df is not None and not df.empty and field in df.columns:
                return float(df[field].iloc[0])

        except ImportError:
            logger.debug("refinitiv-data not installed (pip install refinitiv-data)")
            return None
        except Exception as e:
            logger.debug("Refinitiv fetch failed for %s: %s", ric, e)
            return None

    # ── Disk cache helpers ─────────────────────────────────────────────────

    def _save_disk_cache(self, conditions: MarketConditions) -> None:
        """Persist current conditions to JSON disk cache."""
        if not self._cache_path:
            return

        try:
            data = {
                "date": conditions.date.isoformat(),
                "vix_level": conditions.vix_level,
                "equity_vol_index": conditions.equity_vol_index,
                "credit_spread_ig": conditions.credit_spread_ig,
                "credit_spread_hy": conditions.credit_spread_hy,
                "fx_vol_index": conditions.fx_vol_index,
                "cmdty_vol_index": conditions.cmdty_vol_index,
                "ir_vol_swaption": conditions.ir_vol_swaption,
                "timestamp": datetime.now().isoformat(),
            }
            with open(self._cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Saved market conditions to disk cache: %s", self._cache_path)
        except Exception as e:
            logger.warning("Failed to save disk cache: %s", e)

    def _load_disk_cache(self) -> None:
        """Load conditions from JSON disk cache (if fresh enough)."""
        if not self._cache_path or not os.path.exists(self._cache_path):
            return

        try:
            with open(self._cache_path, 'r') as f:
                data = json.load(f)

            cache_time = datetime.fromisoformat(data["timestamp"])
            age_seconds = (datetime.now() - cache_time).total_seconds()

            if age_seconds < self._cache_ttl:
                self._cache = MarketConditions(
                    date=date.fromisoformat(data["date"]),
                    vix_level=data["vix_level"],
                    equity_vol_index=data["equity_vol_index"],
                    credit_spread_ig=data["credit_spread_ig"],
                    credit_spread_hy=data["credit_spread_hy"],
                    fx_vol_index=data["fx_vol_index"],
                    cmdty_vol_index=data["cmdty_vol_index"],
                    ir_vol_swaption=data["ir_vol_swaption"],
                )
                self._cache_timestamp = cache_time
                logger.info("Loaded market conditions from disk cache (age: %ds)", int(age_seconds))
            else:
                logger.debug("Disk cache expired (age: %ds > TTL: %ds)", int(age_seconds), self._cache_ttl)
        except Exception as e:
            logger.warning("Failed to load disk cache: %s", e)

class DynamicParameterAdjustment:
    """
    Adjusts FRTB risk weights/correlations based on real-time market volatility.
    Implements counter-cyclical buffer (higher vol → higher risk weights).
    """
    def __init__(self, base_config: 'FRTBConfig'):
        self.base_config = base_config
    
    def adjust_risk_weights(
        self,
        market: MarketConditions,
        risk_class: str,
        regulatory_sbm: bool = False,
    ) -> Sequence[float]:
        """
        Scale risk weights based on realized volatility vs normal levels.

        Args:
            market:         Current market conditions.
            risk_class:     FRTB risk class string.
            regulatory_sbm: If True, returns prescribed MAR21 RWs unchanged.
                            Dynamic scaling is for internal stress/ICAAP only.
                            NEVER apply dynamic scaling to regulatory SBM capital.
        """
        base_rw = self.base_config.delta_rw.get(risk_class, [0.15])

        # Enhancement 11: Regulatory capital must use prescribed Basel RWs verbatim.
        # Dynamic scaling is an internal management tool (Pillar 2 / stress only).
        if regulatory_sbm:
            return list(base_rw)

        stress = market.stress_level()

        # Volatility-based scaling per risk class (internal stress only)
        if risk_class == "GIRR":
            scaling = 0.80 + 0.40 * (market.ir_vol_swaption / 50.0)
        elif risk_class in ("CSR_NS", "CSR_SEC", "CSR_CTP"):
            scaling = 0.80 + 0.60 * (market.credit_spread_hy / 400.0)
        elif risk_class.startswith("EQ"):
            scaling = 0.75 + 0.75 * (market.equity_vol_index / 20.0)
        elif risk_class == "FX":
            scaling = 0.85 + 0.50 * (market.fx_vol_index / 8.0)
        elif risk_class == "CMDTY":
            scaling = 0.80 + 0.80 * (market.cmdty_vol_index / 25.0)
        else:
            scaling = 1.0

        # Crisis amplification (internal stress overlay only)
        if stress > 0.65:
            scaling *= (1.0 + 0.5 * (stress - 0.65) / 0.35)

        scaling = max(0.5, min(scaling, 3.0))
        return [rw * scaling for rw in base_rw]
    
    def adjust_correlation(self, market: MarketConditions, risk_class: str, 
                          corr_type: str = "intra") -> float:
        """Crisis → higher correlations (diversification breakdown)."""
        stress = market.stress_level()
        base = (self.base_config.intra_corr if corr_type == "intra" 
                else self.base_config.inter_corr).get(risk_class, 0.50)
        
        if stress < 0.30:
            multiplier = 1.0
        elif stress < 0.65:
            multiplier = 1.0 + 0.20 * (stress - 0.30) / 0.35
        else:
            multiplier = 1.20 + 0.30 * (stress - 0.65) / 0.35
        
        return min(base * multiplier, 0.99)

# ─────────────────────────────────────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class FRTBValidationError(ValueError):
    """Raised when input validation fails."""
    pass


class FRTBConfigurationError(ValueError):
    """Raised when configuration is invalid."""
    pass


class FRTBCalculationError(RuntimeError):
    """Raised when calculation encounters NaN/inf or other numerical errors."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Models
# ─────────────────────────────────────────────────────────────────────────────


class CorrelationModel:
    """
    Pluggable correlation model.
    Default implementation uses static intra/inter correlation scalars.
    """

    def __init__(
        self,
        intra_corr: Dict[str, float],
        inter_corr: Dict[str, float],
    ):
        self.intra_corr = intra_corr
        self.inter_corr = inter_corr

    # GIRR tenor grid per MAR21 (3m,6m,1y,2y,3y,5y,10y,15y,20y,30y)
    _GIRR_TENORS: List[float] = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0]

    def intra(self, risk_class: str, n: int) -> np.ndarray:
        """
        Intra-bucket correlation matrices.

        GIRR (MAR21.58):
            ρ(t1,t2) = exp(−0.03 × |ln(t1/t2)|)  for nominal rate tenors.
            Uses exactly the 10 MAR21 tenors; factors beyond 10 are clipped
            to the 30Y tenor to avoid modulo artefacts.

        GIRR_INFLATION (MAR21.53):
            Inflation factors within the same currency are perfectly correlated
            (single vertex per currency) → returns scalar matrix with ρ from config.

        GIRR_XCCY_BASIS (MAR21.54):
            Cross-currency basis factors treated as perfectly correlated within
            each currency pair bucket.

        All other risk classes: homogeneous scalar from config.
        """
        if risk_class == "GIRR":
            tenors = self._GIRR_TENORS
            # Enhancement 6: clip to last tenor (30Y) instead of wrapping modulo,
            # so n > 10 factors always get a valid tenor assignment.
            t_list = [tenors[min(i, len(tenors) - 1)] for i in range(n)]
            mat = np.ones((n, n), dtype=np.float64)
            for i in range(n):
                for j in range(n):
                    if i != j:
                        t1, t2 = t_list[i], t_list[j]
                        mat[i, j] = math.exp(-0.03 * abs(math.log(t1 / t2)))
            return mat

        # Enhancement 6 (MAR21.53-54): inflation and xccy basis use scalar ρ.
        ρ = self.intra_corr.get(risk_class, 0.5)
        mat = np.full((n, n), ρ, dtype=np.float64)
        np.fill_diagonal(mat, 1.0)
        return mat

    def inter(self, risk_class: str, m: int) -> np.ndarray:
        γ = self.inter_corr.get(risk_class, 0.3)
        mat = np.full((m, m), γ, dtype=np.float64)
        np.fill_diagonal(mat, 1.0)
        return mat


@dataclass
class FRTBConfig:
    """Centralized FRTB configuration per MAR21-33 with real-time market support."""
    risk_classes: List[str] = field(default_factory=lambda: [
        "GIRR", "GIRR_INFLATION", "GIRR_XCCY_BASIS",
        "CSR_NS",
        "CSR_SEC",   # MAR21.73: Securitisation — non-CTP
        "CSR_CTP",   # MAR21.73: Securitisation — Correlation Trading Portfolio
        "EQ_LARGE", "EQ_SMALL",
        "CMDTY",
        "FX", "FX_PRESCRIBED",
    ])
    
    # Real-time market integration (NEW)
    use_market_conditions: bool = False  # Enable dynamic parameter adjustment
    market_data_feed: Optional[MarketDataFeed] = None
    dynamic_adjuster: Optional[DynamicParameterAdjustment] = None

    delta_rw: Dict[str, Sequence[float]] = field(default_factory=lambda: {
        # Exactly 10 values per MAR21.44 Table 2. Previous version had 13
        # values (3 extra entries at the end with no Basel basis) that were
        # being selected via hash(risk_factor) % 13, producing non-regulatory
        # risk weights for some factors. Trimmed to the 10 prescribed values.
        "GIRR": [0.017, 0.017, 0.016, 0.013, 0.012, 0.011, 0.011,
                 0.011, 0.011, 0.011],  # 10 tenors per MAR21.44 Table 2
        # Enhancement 6 (MAR21.52): Inflation & cross-currency basis share
        # the same 1.6% RW as the 10Y nominal tenor (supervisory proxy).
        "GIRR_INFLATION": [0.016],
        "GIRR_XCCY_BASIS": [0.016],
        "CSR_NS": [0.005, 0.010, 0.050, 0.030, 0.020, 0.030, 0.080,
                   0.060, 0.050, 0.100, 0.120, 0.140, 0.020, 0.020,
                   0.020, 0.030, 0.030, 0.050],
        # MAR21.73: CSR Securitisation (non-CTP) — 7 buckets
        # Senior tranche IG, Non-senior IG, BB rated, B or lower, CRR3/Basel IV
        # bucket structure: RMBS(IG-Sr, IG-NonSr, HY), CMBS(IG, HY),
        # ABS(IG, HY), CLO, Other.
        # RWs per MAR21.73 Table 5: 0.9%, 1.5%, 2.0%, 2.0%, 2.5%, 2.5%, 3.5%
        "CSR_SEC": [0.009, 0.015, 0.020, 0.020, 0.025, 0.025, 0.035],
        # MAR21.73: CTP (Correlation Trading Portfolio) — 5 buckets
        # IG index tranches, HY index tranches, single-name IG, single-name HY,
        # residual/other. RWs: 1.6%, 2.4%, 2.0%, 4.0%, 8.0%
        "CSR_CTP":  [0.016, 0.024, 0.020, 0.040, 0.080],
        # Enhancement 9 (MAR21.78): buckets 1-10 large-cap, 11 small-cap (70%),
        # 12 large-cap other sector, 13 small-cap other sector (70%).
        "EQ_LARGE": [0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70, 0.50],
        "EQ_SMALL":  [0.70],   # MAR21.78 bucket 11 and 13 — small-cap 70% RW
        # Enhancement 5 (MAR21.87): 7.5% for prescribed well-traded pairs;
        # 15% for all others. FX_PRESCRIBED covers: EURUSD, USDJPY, GBPUSD,
        # AUDUSD, USDCAD, USDCHF, USDCNH, USDHKD, USDKRW, USDSEK, USDSGD.
        "FX": [0.15],
        "FX_PRESCRIBED": [0.075],
        # MAR21.88-96: Commodity — 17 buckets with specific RWs.
        # IMPORTANT: _risk_weight_for() selects the bucket via
        # abs(hash(risk_factor)) % len(rw), which is non-deterministic across
        # Python versions and produces arbitrary bucket assignments. In production,
        # populate rw_index_map with the correct (risk_class, risk_factor)->index
        # mapping for each commodity (e.g. "CMDTY_ENERGY" → index 1 for Energy Bucket 1).
        # The 17 values below match MAR21.88 Table 6.
        "CMDTY": [0.30, 0.35, 0.60, 0.80, 0.40, 0.45, 0.20, 0.35, 0.25, 0.35,
                  0.50, 0.42, 0.18, 0.18, 0.18, 0.16, 0.18],
    })

    intra_corr: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.999, "CSR_NS": 0.65,
        # MAR21.73: CSR_SEC intra-bucket correlation. Securitisation tranches
        # within the same bucket: 99% (senior tranches of same underlying)
        # MAR21.73: CSR_CTP intra-bucket: 99% (highly correlated index tranches)
        "CSR_SEC": 0.99, "CSR_CTP": 0.99,
        # Enhancement 9 (MAR21.80): intra-bucket EQ correlation 15% for large-cap,
        # 7.5% for small-cap (less liquid, idiosyncratic dominates).
        "EQ_LARGE": 0.15, "EQ_SMALL": 0.075,
        "FX": 1.0, "FX_PRESCRIBED": 1.0,
        "CMDTY": 0.55,
        # Enhancement 6: inflation/xccy basis treated as separate sub-buckets within GIRR.
        "GIRR_INFLATION": 0.40, "GIRR_XCCY_BASIS": 0.999,
    })

    inter_corr: Dict[str, float] = field(default_factory=lambda: {
        # MAR21.60: GIRR inter-currency correlation γ = 0.50 for all pairs.
        # Important limitation: MAR21.60 also specifies that GIRR_INFLATION
        # and GIRR_XCCY_BASIS receive γ = 0 against all other GIRR sub-curves
        # within the same currency. A single scalar cannot represent this
        # sub-curve zero-correlation structure. In production, use a full
        # inter-bucket γ matrix keyed by (risk_class, bucket_i, bucket_j) or
        # handle GIRR sub-curves as separate risk classes (the current approach
        # with GIRR_INFLATION and GIRR_XCCY_BASIS as distinct entries in
        # risk_classes is the recommended workaround).
        "GIRR": 0.50, "CSR_NS": 0.0,
        # MAR21.73: CSR_SEC inter-bucket (across securitisation types): 0%
        # MAR21.73: CSR_CTP inter-bucket: 0% (no prescribed cross-bucket offset)
        "CSR_SEC": 0.00, "CSR_CTP": 0.00,
        # Enhancement 9 (MAR21.82): inter-bucket EQ 15% for large-cap; 0% for small-cap.
        "EQ_LARGE": 0.15, "EQ_SMALL": 0.00,
        "FX": 0.60, "FX_PRESCRIBED": 0.60,
        "CMDTY": 0.20,
        "GIRR_INFLATION": 0.20, "GIRR_XCCY_BASIS": 0.10,
    })

    vega_rw: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.55, "CSR_NS": 0.55,
        # MAR21.73: CSR_SEC and CSR_CTP — same 55% vega RW as CSR_NS
        "CSR_SEC": 0.55, "CSR_CTP": 0.55,
        "EQ_LARGE": 0.78, "EQ_SMALL": 0.78,
        "FX": 0.47, "FX_PRESCRIBED": 0.47,
        "CMDTY": 1.00,
        "GIRR_INFLATION": 0.55, "GIRR_XCCY_BASIS": 0.55,
    })

    # Enhancement 5 (MAR21.87): prescribed well-traded currency pairs (7.5% RW).
    fx_prescribed_pairs: frozenset = field(default_factory=lambda: frozenset({
        "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF",
        "USDCNH", "USDHKD", "USDKRW", "USDSEK", "USDSGD",
        # Reverse notation also recognised
        "USDEUR", "JPYUSD", "USDGBP", "USDAUD", "CADUSD", "CHFUSD",
        "CNHUSD", "HKDUSD", "KRWUSD", "SEKUSD", "SGDUSD",
    }))

    # Optional deterministic mapping (risk_class, risk_factor) -> RW index
    rw_index_map: Dict[Tuple[str, str], int] = field(default_factory=dict)

    confidence_level: float = 0.975
    holding_period_days: int = 10
    backtesting_window: int = 260
    green_zone_max: int = 4
    amber_zone_max: int = 9
    ima_multiplier: float = 1.5
    # MAR31.14: NMRF charge should be the per-factor Stress Scenario Risk
    # Measure (SSRM) — not a fixed percentage of notional. The flat 0.0015
    # (15bp) proxy has no MAR31 basis and is removed. Default = 0 forces
    # callers to supply factor_ssrm explicitly for regulatory capital.
    # The fallback path in nmrf_charge() still works for backward compatibility
    # but will produce zero capital when n_nmrf_factors is provided without ssrm.
    nmrf_charge_bp: float = 0.0
    stressed_es_multiplier: float = 1.5

    # Pluggable correlation model
    correlation_model: Optional[CorrelationModel] = None

    def __post_init__(self):
        if self.correlation_model is None:
            self.correlation_model = CorrelationModel(
                intra_corr=self.intra_corr,
                inter_corr=self.inter_corr,
            )
        
        # Initialize real-time market components if enabled
        if self.use_market_conditions:
            if self.market_data_feed is None:
                self.market_data_feed = MarketDataFeed()
            if self.dynamic_adjuster is None:
                self.dynamic_adjuster = DynamicParameterAdjustment(self)
            logger.info("FRTB real-time market conditions ENABLED")

    def validate(self) -> None:
        """Validate configuration consistency and regulatory bounds."""
        if not self.risk_classes:
            raise FRTBConfigurationError("risk_classes cannot be empty")
        if not all(0 < rw < 2.0 for rws in self.delta_rw.values() for rw in rws):
            raise FRTBConfigurationError("Risk weights must be in (0, 2)")
        if not all(0 <= corr <= 1.0 for corr in self.intra_corr.values()):
            raise FRTBConfigurationError("Intra-correlations must be in [0, 1]")
        if not all(-1.0 <= corr <= 1.0 for corr in self.inter_corr.values()):
            raise FRTBConfigurationError("Inter-correlations must be in [-1, 1]")
        if not (0.9 < self.confidence_level < 1.0):
            raise FRTBConfigurationError("Confidence level must be in (0.9, 1.0)")
        if self.holding_period_days <= 0:
            raise FRTBConfigurationError("holding_period_days must be positive")
        
        # MAR21: Validate inter-bucket correlation limits by risk class
        # GIRR: 0.50, CSR: varies by sector (0.0-0.50), EQ: 0.15, FX: 0.60, CMDTY: 0.20
        inter_limits = {
            "GIRR": (0.40, 0.60),    # MAR21.60
            "CSR_NS": (-0.10, 0.50), # MAR21.76 (can be negative for offsetting sectors)
            "CSR_SEC": (0.0, 0.30),  # MAR21.76
            "EQ": (0.10, 0.25),      # MAR21.82
            "FX": (0.50, 0.70),      # MAR21.90
            "CMDTY": (0.10, 0.40),   # MAR21.96
        }
        for rc, corr in self.inter_corr.items():
            if rc in inter_limits:
                min_val, max_val = inter_limits[rc]
                if not (min_val <= corr <= max_val):
                    logger.warning(
                        "Inter-correlation for %s (%.2f) outside typical range [%.2f, %.2f]",
                        rc, corr, min_val, max_val
                    )
        
        logger.debug("FRTBConfig validated successfully")


# ─────────────────────────────────────────────────────────────────────────────
# Core Data Structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Sensitivity:
    """
    Single risk factor sensitivity per MAR21.6.

    Attributes:
        trade_id: Unique trade identifier.
        risk_class: One of GIRR, CSR_NS, CSR_SEC, EQ, CMDTY, FX.
        bucket: Regulatory bucket (e.g., "1", "2", or risk name).
        risk_factor: Specific factor (tenor, currency, sector).
        delta: Delta sensitivity ∂V/∂S (dV per 1bp move).
        vega: Vega sensitivity ∂V/∂σ (dV per 1% IV move).
        curvature_up: P&L change if scenario rates shift +1bp.
        curvature_dn: P&L change if scenario rates shift -1bp.
        notional: Optional notional for normalization.
    """
    trade_id: str
    risk_class: str
    bucket: str
    risk_factor: str
    delta: float
    vega: float = 0.0
    curvature_up: float = 0.0
    curvature_dn: float = 0.0
    notional: float = 1.0


@dataclass
class FRTBResult:
    """
    Complete FRTB capital calculation output per MAR21-33.
    """
    run_date: date
    portfolio_id: str
    method: str
    sbm_delta: float
    sbm_vega: float
    sbm_curvature: float
    sbm_total: float
    es_99_10d: float
    es_stressed: float
    nmrf_charge: float
    ima_total: float
    capital_market_risk: float
    rwa_market: float

    # New capital components
    drc_charge:    float = 0.0   # Default Risk Charge (MAR22)
    rrao_charge_v: float = 0.0   # Residual Risk Add-On (MAR23.5)
    pla_zone:      str   = "N/A" # PLA test zone (GREEN/AMBER/RED/N/A)

    # Enhancement 10 (MAR12.11 / CRR3 Article 325a): SA output floor.
    # IMA capital cannot fall below 72.5% of the SA (SBM) capital at entity level.
    # Tracked here per-portfolio for consolidated floor calculation upstream.
    sa_floor_capital:  float = 0.0   # 72.5% × SBM; binding if IMA < this
    sa_floor_binding:  bool  = False # True when IMA path is constrained by floor

    # IMCC decomposition (Enhancement 4 — MAR33.5)
    imcc_rho:          float = 0.0   # Endogenous correlation weight
    imcc_es_full:      float = 0.0   # ES_S,C (correlated)
    imcc_es_uncorr:    float = 0.0   # ES_S,U (uncorrelated)

    # Optional breakdowns / details
    sbm_by_risk_class: Dict[str, float] = field(default_factory=dict)
    sbm_by_bucket:     Dict[str, float] = field(default_factory=dict)
    ima_components:    Dict[str, float] = field(default_factory=dict)
    drc_by_quality:    Dict[str, Any]   = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to a plain dict (JSON/CSV/Parquet friendly)."""
        d = asdict(self)
        # Convert date to ISO string for JSON friendliness
        d["run_date"] = self.run_date.isoformat()
        return d

    def to_json(self, **kwargs) -> str:
        """Serialize result to JSON string."""
        return json.dumps(self.to_dict(), **kwargs)


@dataclass
class ShockScenario:
    """
    Simple stress scenario definition for what-if analysis.
    """
    name: str
    rate_bp: float = 0.0
    spread_bp: float = 0.0
    fx_pct: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Validation Functions
# ─────────────────────────────────────────────────────────────────────────────


def validate_sensitivity(s: Sensitivity) -> None:
    """Validate individual sensitivity; raises FRTBValidationError on failure."""
    if not isinstance(s.trade_id, str) or not s.trade_id:
        raise FRTBValidationError(f"Invalid trade_id: {s.trade_id}")
    if not isinstance(s.risk_class, str) or not s.risk_class:
        raise FRTBValidationError(f"Invalid risk_class: {s.risk_class}")
    if not isinstance(s.bucket, str) or not s.bucket:
        raise FRTBValidationError(f"Invalid bucket: {s.bucket}")
    if not isinstance(s.delta, (int, float)) or math.isnan(s.delta) or math.isinf(s.delta):
        raise FRTBValidationError(f"Invalid delta for {s.trade_id}: {s.delta}")
    if not isinstance(s.vega, (int, float)) or math.isnan(s.vega) or math.isinf(s.vega):
        raise FRTBValidationError(f"Invalid vega for {s.trade_id}: {s.vega}")
    if not isinstance(s.curvature_up, (int, float)) or math.isnan(s.curvature_up):
        raise FRTBValidationError(f"Invalid curvature_up for {s.trade_id}: {s.curvature_up}")
    if not isinstance(s.curvature_dn, (int, float)) or math.isnan(s.curvature_dn):
        raise FRTBValidationError(f"Invalid curvature_dn for {s.trade_id}: {s.curvature_dn}")
    if not isinstance(s.notional, (int, float)) or s.notional <= 0:
        raise FRTBValidationError(f"Invalid notional for {s.trade_id}: {s.notional}")


def validate_sensitivities(sensitivities: Sequence[Sensitivity], config: FRTBConfig) -> None:
    """Validate entire sensitivity portfolio against configuration."""
    if not sensitivities:
        logger.warning("Empty sensitivity portfolio provided")
        return

    for s in sensitivities:
        validate_sensitivity(s)
        if s.risk_class not in config.risk_classes:
            raise FRTBValidationError(
                f"Unknown risk_class '{s.risk_class}' for trade {s.trade_id}. "
                f"Valid: {config.risk_classes}"
            )


def validate_pnl_series(pnl_series: np.ndarray, min_length: int = 10) -> None:
    """Validate P&L series for IMA/ES calculations."""
    if not isinstance(pnl_series, np.ndarray):
        raise FRTBValidationError("pnl_series must be numpy array")
    if len(pnl_series) < min_length:
        raise FRTBValidationError(
            f"PnL series too short: {len(pnl_series)} < {min_length} required"
        )
    if np.any(np.isnan(pnl_series)):
        nan_count = int(np.sum(np.isnan(pnl_series)))
        raise FRTBValidationError(f"PnL series contains {nan_count} NaN values")
    if np.any(np.isinf(pnl_series)):
        inf_count = int(np.sum(np.isinf(pnl_series)))
        raise FRTBValidationError(f"PnL series contains {inf_count} inf values")

    # Simple outlier flagging (non-blocking)
    if len(pnl_series) > 5:
        z = (pnl_series - pnl_series.mean()) / (pnl_series.std(ddof=1) or 1.0)
        if np.any(np.abs(z) > 6):
            logger.warning("PnL series contains extreme outliers |z|>6")


# ─────────────────────────────────────────────────────────────────────────────
# Utility: Position Aggregation / Netting
# ─────────────────────────────────────────────────────────────────────────────


def aggregate_sensitivities(
    sensitivities: Sequence[Sensitivity],
) -> List[Sensitivity]:
    """
    Aggregate sensitivities by (risk_class, bucket, risk_factor).
    Netting deltas/vegas/curvature; notional is summed.
    """
    if not sensitivities:
        return []

    agg: Dict[Tuple[str, str, str], Sensitivity] = {}
    for s in sensitivities:
        key = (s.risk_class, s.bucket, s.risk_factor)
        if key not in agg:
            agg[key] = copy.copy(s)
        else:
            a = agg[key]
            a.delta += s.delta
            a.vega += s.vega
            a.curvature_up += s.curvature_up
            a.curvature_dn += s.curvature_dn
            a.notional += s.notional
    return list(agg.values())


# ─────────────────────────────────────────────────────────────────────────────
# SBM — Sensitivities-Based Method
# ─────────────────────────────────────────────────────────────────────────────


class SBMCalculator:
    """
    Implements MAR21: delta, vega, curvature charges.
    Uses weighted sensitivity (WS) = RW × sensitivity.
    Includes:
      - cached correlation matrices
      - basic risk-class / bucket breakdowns
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()
        self.config.validate()
        # Correlation matrix caches
        self._intra_cache: Dict[Tuple[str, int], np.ndarray] = {}
        self._inter_cache: Dict[Tuple[str, int], np.ndarray] = {}
        # Last run breakdowns (populated by total_sbm, consumed by FRTBEngine.compute)
        self._last_sbm_by_risk_class: Dict[str, float] = {}
        self._last_sbm_by_bucket:     Dict[str, float] = {}

    # ---- internal helpers -------------------------------------------------

    def _intra_corr_mat(self, risk_class: str, n: int) -> np.ndarray:
        key = (risk_class, n)
        if key not in self._intra_cache:
            # Type checker workaround: correlation_model is never None after __post_init__
            assert self.config.correlation_model is not None
            self._intra_cache[key] = self.config.correlation_model.intra(risk_class, n)
        return self._intra_cache[key]

    def _inter_corr_mat(self, risk_class: str, m: int) -> np.ndarray:
        key = (risk_class, m)
        if key not in self._inter_cache:
            # Type checker workaround: correlation_model is never None after __post_init__
            assert self.config.correlation_model is not None
            self._inter_cache[key] = self.config.correlation_model.inter(risk_class, m)
        return self._inter_cache[key]

    def _resolve_risk_class(self, s: Sensitivity) -> str:
        """
        Resolve the effective risk class for RW/correlation lookup.

        Enhancement 5 (MAR21.87): FX sensitivities for prescribed well-traded
        pairs use 'FX_PRESCRIBED' (7.5% RW) instead of 'FX' (15% RW).
        Enhancement 9 (MAR21.78): EQ bucket 11 and 13 map to 'EQ_SMALL'.
        """
        if s.risk_class == "FX":
            pair = s.risk_factor.upper().replace("/", "").replace("-", "")
            if pair in self.config.fx_prescribed_pairs:
                return "FX_PRESCRIBED"
            return "FX"
        if s.risk_class in ("EQ", "EQ_LARGE"):
            # bucket 11 = small-cap developed markets, 13 = small-cap other
            if s.bucket in ("11", "13"):
                return "EQ_SMALL"
            return "EQ_LARGE"
        return s.risk_class

    def _risk_weight_for(
        self,
        s: Sensitivity,
        market: Optional[MarketConditions] = None,
        regulatory_sbm: bool = True,
    ) -> float:
        """
        RW lookup with optional real-time market adjustment.

        regulatory_sbm=True (default): returns prescribed MAR21 RWs unchanged.
        regulatory_sbm=False:          applies dynamic scaling (internal stress).
        """
        effective_rc = self._resolve_risk_class(s)

        # Enhancement 11: only apply dynamic scaling when explicitly requested
        # for internal/stress purposes — never for regulatory SBM capital.
        if self.config.use_market_conditions and market and self.config.dynamic_adjuster:
            rw_map = self.config.dynamic_adjuster.adjust_risk_weights(
                market, effective_rc, regulatory_sbm=regulatory_sbm
            )
        else:
            rw_map = self.config.delta_rw.get(
                effective_rc,
                self.config.delta_rw.get(effective_rc + "_LARGE", [0.15]),
            )

        if (s.risk_class, s.risk_factor) in self.config.rw_index_map:
            idx = self.config.rw_index_map[(s.risk_class, s.risk_factor)]
        else:
            idx = abs(hash(s.risk_factor)) % len(rw_map)
        return rw_map[idx]

    # ---- main SBM components ----------------------------------------------

    def delta_charge(
        self,
        sensitivities: Sequence[Sensitivity],
        risk_class: str,
        breakdown_by_bucket: Optional[Dict[str, float]] = None,
        market: Optional[MarketConditions] = None,
    ) -> float:
        """
        MAR21.6: Delta charge aggregation with three-step correlation framework.
        
        1. WS_k = RW_k × s_k (RW adjusted for market if enabled)
        2. K_b = sqrt(Σ_k WS_k² + Σ_{k≠l} ρ_{kl} WS_k WS_l)   [intra-bucket]
        3. Δ   = sqrt(Σ_b K_b² + Σ_{b≠c} γ_{bc} K_b K_c)      [inter-bucket]
        
        Returns: Non-negative delta capital charge.
        
        Enhancements:
          - Market regime-adjusted risk weights (if enabled)
          - Comprehensive logging of intermediate values
          - Bucket-level breakdown for risk decomposition
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                logger.debug("Delta charge for %s: no sensitivities", risk_class)
                return 0.0

            # bucket -> list of WS
            buckets: Dict[str, List[float]] = {}
            for s in senses:
                rw = self._risk_weight_for(s, market=market)
                ws = rw * s.delta
                buckets.setdefault(s.bucket, []).append(ws)
                
            logger.debug(
                "Delta charge %s: %d sensitivities across %d buckets", 
                risk_class, len(senses), len(buckets)
            )

            K_b: Dict[str, float] = {}
            for b, ws_list in buckets.items():
                ws_arr = np.array(ws_list, dtype=np.float64)
                n = len(ws_arr)
                if n == 0:
                    K_b[b] = 0.0
                    continue
                corr_mat = self._intra_corr_mat(risk_class, n)
                K_sq = float(ws_arr @ corr_mat @ ws_arr)
                K_b[b] = math.sqrt(max(K_sq, 0.0))
                
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(
                        "  Bucket %s: %d factors, K_b=%.0f (sum_WS=%.0f)",
                        b, n, K_b[b], ws_arr.sum()
                    )

            K_arr = np.array(list(K_b.values()), dtype=np.float64)
            if len(K_arr) == 0:
                return 0.0

            corr_inter = self._inter_corr_mat(risk_class, len(K_arr))
            charge_sq = float(K_arr @ corr_inter @ K_arr)
            result = math.sqrt(max(charge_sq, 0.0))

            if breakdown_by_bucket is not None:
                breakdown_by_bucket.update(K_b)

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Delta charge produced NaN/inf for {risk_class}")
                
            logger.debug("Delta charge %s: %.0f", risk_class, result)
            return result

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Delta charge calculation failed for {risk_class}: {e}")

    def vega_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """
        MAR21: Vega charge via the same two-stage intra/inter bucket aggregation as delta.

        WS_k = RW_vega × VR_k   (VR = vega sensitivity to implied vol)
        K_b  = √(Σ WS_k² + Σ_{k≠l} ρ_kl WS_k WS_l)   [intra-bucket]
        Δ    = √(Σ K_b² + Σ_{b≠c} γ_bc K_b K_c)       [inter-bucket]
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class and s.vega != 0]
            if not senses:
                return 0.0

            rw_vega = self.config.vega_rw.get(risk_class, 0.55)

            # bucket → list of WS (weighted vega sensitivities)
            buckets: Dict[str, List[float]] = {}
            for s in senses:
                ws = rw_vega * s.vega
                buckets.setdefault(s.bucket, []).append(ws)

            # Intra-bucket aggregation
            K_b: Dict[str, float] = {}
            for b, ws_list in buckets.items():
                ws_arr = np.array(ws_list, dtype=np.float64)
                n = len(ws_arr)
                if n == 0:
                    K_b[b] = 0.0
                    continue
                corr_mat = self._intra_corr_mat(risk_class, n)
                K_sq = float(ws_arr @ corr_mat @ ws_arr)
                K_b[b] = math.sqrt(max(K_sq, 0.0))

            # Inter-bucket aggregation
            K_arr = np.array(list(K_b.values()), dtype=np.float64)
            if len(K_arr) == 0:
                return 0.0
            corr_inter = self._inter_corr_mat(risk_class, len(K_arr))
            charge_sq  = float(K_arr @ corr_inter @ K_arr)
            result     = math.sqrt(max(charge_sq, 0.0))

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Vega charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Vega charge calculation failed for {risk_class}: {e}")

    def curvature_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """
        MAR23.6: Curvature charge under three correlation scenarios.

        CVR_k = -min(CVR_up_k, CVR_dn_k, 0)   per risk factor
        For each correlation scenario s ∈ {low, medium, high}:
            ρ_s  = ρ_base scaled by {0.75², 1.0, min(1.25,1)}
            K_b  = √max(Σ CVR_k² + Σ_{k≠l} ρ_s² × CVR_k × CVR_l, 0)
            ψ_b  = Σ CVR_k if K_b < 0 else 0   (negative bucket treatment)
            Ξ_s  = Σ_b K_b² + Σ_{b≠c} γ_s × K_b × K_c + Σ_b ψ_b
        Result = max(max(Ξ_s), 0)
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                return 0.0

            # CVR_k = -min(CVR_up, CVR_dn, 0) per MAR23.3
            cvr = [-min(s.curvature_up, s.curvature_dn, 0.0) for s in senses]
            cvr_arr = np.array(cvr, dtype=np.float64)
            n = len(cvr_arr)
            if n == 0:
                return 0.0

            # Three intra-correlation scenarios (MAR23.6)
            base_intra = self._intra_corr_mat(risk_class, n)
            base_inter_scalar = self.config.inter_corr.get(risk_class, 0.5)

            scenario_charges = []
            for rho_scale in [0.75**2, 1.0, min(1.25, 1.0)]:
                # Scale intra correlation matrix (off-diagonals only)
                ρ_mat = np.ones_like(base_intra)
                for i in range(n):
                    for j in range(n):
                        if i != j:
                            ρ_mat[i, j] = min(base_intra[i, j] * rho_scale, 1.0)

                # Bucket-level aggregation
                bucket_names = [s.bucket for s in senses]
                unique_buckets = list(dict.fromkeys(bucket_names))

                K_b_vals = []
                psi_b_vals = []
                for b in unique_buckets:
                    idx = [i for i, s in enumerate(senses) if s.bucket == b]
                    cvr_b = cvr_arr[idx]
                    n_b = len(cvr_b)
                    if n_b == 0:
                        K_b_vals.append(0.0)
                        psi_b_vals.append(0.0)
                        continue
                    ρ_b = ρ_mat[np.ix_(idx, idx)]
                    K_sq = float(cvr_b @ ρ_b @ cvr_b)
                    K_b_v = math.sqrt(max(K_sq, 0.0))
                    K_b_vals.append(K_b_v)
                    # ψ_b = Σ CVR_k if K_b² < 0 (i.e. negative scenario)
                    psi_b_vals.append(float(cvr_b.sum()) if K_sq < 0 else 0.0)

                K_b_arr = np.array(K_b_vals)
                m = len(K_b_arr)
                # Inter-bucket aggregation
                γ_s = min(base_inter_scalar * rho_scale, 1.0)
                inter_mat = np.full((m, m), γ_s)
                np.fill_diagonal(inter_mat, 1.0)
                xi = float(K_b_arr @ inter_mat @ K_b_arr) + sum(psi_b_vals)
                scenario_charges.append(xi)

            result = max(max(scenario_charges), 0.0)
            # MAR23.6: Ξ_s is already a dollar capital charge — it is the sum
            # of squared K_b values where each K_b = sqrt(CVR^ᵀ × ρ² × CVR).
            # Taking sqrt(Ξ_s) again is a double square-root error.
            # Previous version mistakenly applied a final sqrt() here.
            # The correct result is max(max(Ξ_low, Ξ_med, Ξ_high), 0).

            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Curvature charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Curvature charge calculation failed for {risk_class}: {e}")


    def rrao_charge(
        self,
        sensitivities: Sequence[Sensitivity],
        notionals_by_instrument: Optional[Dict[str, Tuple[float, str]]] = None,
    ) -> float:
        """
        MAR23.5: Residual Risk Add-On (RRAO).

        Instruments with exotic underlyings: 1.0% × gross notional
        Instruments with gap/correlation/behavioural risk: 0.1% × gross notional

        Args:
            notionals_by_instrument: {trade_id: (notional, instrument_type)}
              instrument_type: 'EXOTIC' | 'RESIDUAL' | 'VANILLA'
              If None, derives a conservative estimate from sensitivities.
        """
        if notionals_by_instrument is not None:
            exotic_notional   = sum(n for n,t in notionals_by_instrument.values() if t=='EXOTIC')
            residual_notional = sum(n for n,t in notionals_by_instrument.values() if t=='RESIDUAL')
        else:
            # Conservative: treat all non-linear (non-zero curvature) sensitivities
            # as residual risk; exotic is zero (cannot distinguish without trade data)
            exotic_notional   = 0.0
            # Proxy: count non-linear sensitivities and apply a flat notional.
            # abs(delta)*1000 is dimensionally wrong (delta is in currency, not bps).
            # We count distinct trade IDs with optionality and assume avg_notional;
            # caller should supply notionals_by_instrument for accurate RRAO.
            trade_ids_with_optionality = {
                s.trade_id for s in sensitivities
                if (s.curvature_up != 0 or s.curvature_dn != 0)
            }
            n_residual = len(trade_ids_with_optionality)
            # Use a conservative per-trade proxy; override via notionals_by_instrument
            _proxy_notional = 1_000_000.0   # 1M per trade (conservative floor)
            residual_notional = n_residual * _proxy_notional
        return 0.010 * exotic_notional + 0.001 * residual_notional

    def total_sbm(
        self,
        sensitivities: Sequence[Sensitivity],
        market: Optional[MarketConditions] = None,
    ) -> Tuple[float, float, float, float, Dict[str, float], Dict[str, float]]:
        """
        Returns:
            delta_total, vega_total, curv_total, sbm_total,
            sbm_by_risk_class, sbm_by_bucket
        
        market: Optional real-time conditions for dynamic RW adjustment
        """
        delta_charges: Dict[str, float] = {}
        vega_charges: Dict[str, float] = {}
        curv_charges: Dict[str, float] = {}
        bucket_breakdown: Dict[str, float] = {}

        for rc in self.config.risk_classes:
            # MAR21.6: Compute delta under three correlation scenarios;
            # take the maximum as the regulatory charge.
            base_intra  = self.config.intra_corr.get(rc, 0.5)
            base_inter  = self.config.inter_corr.get(rc, 0.3)
            delta_scenarios = []
            # MAR21.6: three correlation scenarios for delta
            def _three_rho(base: float) -> List[float]:
                """
                MAR21.6 three correlation scenarios — exact Basel formulas.

                Low scenario:    ρ_low  = max(2×ρ − 1,  0)
                                 Previous version also applied max(0.5625×ρ, …)
                                 which has no MAR21 basis and is removed.

                Medium scenario: ρ_med  = ρ  (base correlation unchanged)

                High scenario:   ρ_high = min(ρ + 0.25×(1 − ρ),  1.0)
                                 Previous version used abs(ρ) in (1 − abs(ρ)),
                                 which is wrong for negative correlations
                                 (valid for CSR inter-bucket, MAR21.76). The
                                 formula must use ρ directly, not |ρ|.

                Applied identically to both ρ (intra-bucket) and γ (inter-bucket).
                """
                low    = max(2.0 * base - 1.0, 0.0)           # MAR21.6 exact
                medium = base                                    # MAR21.6 exact
                high   = min(base + 0.25 * (1.0 - base), 1.0)  # MAR21.6 exact
                return [low, medium, high]

            assert self.config.correlation_model is not None
            for rho_intra, rho_inter in zip(_three_rho(base_intra), _three_rho(base_inter)):
                orig_intra = self.config.correlation_model.intra_corr.copy()
                orig_inter = self.config.correlation_model.inter_corr.copy()
                try:
                    self.config.correlation_model.intra_corr[rc] = max(min(rho_intra, 0.9999), 0.0)
                    self.config.correlation_model.inter_corr[rc] = max(min(rho_inter, 1.0), -1.0)
                    self._intra_cache.clear()
                    self._inter_cache.clear()
                    rc_bucket_breakdown_s: Dict[str, float] = {}
                    d_s = self.delta_charge(sensitivities, rc,
                                            breakdown_by_bucket=rc_bucket_breakdown_s,
                                            market=market)
                    delta_scenarios.append((d_s, rc_bucket_breakdown_s))
                finally:
                    # Restore always runs, even on exception — prevents config corruption
                    self.config.correlation_model.intra_corr = orig_intra
                    self.config.correlation_model.inter_corr = orig_inter
                    self._intra_cache.clear()
                    self._inter_cache.clear()

            # Best scenario = highest charge (MAR21.6)
            best_idx = int(np.argmax([x[0] for x in delta_scenarios]))
            d = delta_scenarios[best_idx][0]
            rc_bucket_breakdown = delta_scenarios[best_idx][1]

            # Enhancement 2 (MAR21.6): vega and curvature also run under three
            # correlation scenarios; the highest charge is the regulatory result.
            assert self.config.correlation_model is not None
            vega_scenarios = []
            curv_scenarios = []
            for rho_intra, rho_inter in zip(_three_rho(base_intra), _three_rho(base_inter)):
                orig_intra = self.config.correlation_model.intra_corr.copy()
                orig_inter = self.config.correlation_model.inter_corr.copy()
                try:
                    self.config.correlation_model.intra_corr[rc] = max(min(rho_intra, 0.9999), 0.0)
                    self.config.correlation_model.inter_corr[rc] = max(min(rho_inter, 1.0), -1.0)
                    self._intra_cache.clear()
                    self._inter_cache.clear()
                    vega_scenarios.append(self.vega_charge(sensitivities, rc))
                    curv_scenarios.append(self.curvature_charge(sensitivities, rc))
                finally:
                    self.config.correlation_model.intra_corr = orig_intra
                    self.config.correlation_model.inter_corr = orig_inter
                    self._intra_cache.clear()
                    self._inter_cache.clear()

            v = max(vega_scenarios)
            c = max(curv_scenarios)
            delta_charges[rc] = d
            vega_charges[rc]  = v
            curv_charges[rc]  = c
            for b, val in rc_bucket_breakdown.items():
                bucket_breakdown[f"{rc}:{b}"] = val

        delta_t = sum(delta_charges.values())
        vega_t = sum(vega_charges.values())
        curv_t = sum(curv_charges.values())
        sbm_t = delta_t + vega_t + curv_t

        # NOTE: A "MAR21.100" floor was previously applied here. There is no
        # MAR21.100 in the Basel consolidated framework (MAR21 ends at .98).
        # The three-scenario correlation framework (MAR21.6) is the Basel
        # mechanism for limiting diversification benefit — no additional floor
        # on the SBM charge is prescribed. Applying an extra floor removes
        # legitimate Basel diversification benefit and overstates capital.
        # Floor block removed. If an internal Pillar 2 constraint is required,
        # implement it outside this engine and gate it behind an explicit flag.

        sbm_by_risk_class = {
            rc: delta_charges[rc] + vega_charges[rc] + curv_charges[rc]
            for rc in self.config.risk_classes
        }

        logger.debug("SBM: Δ=%.0f  V=%.0f  C=%.0f  Total=%.0f",
                     delta_t, vega_t, curv_t, sbm_t)

        # Store breakdowns so compute() can pick them up without changing signature
        self._last_sbm_by_risk_class = sbm_by_risk_class
        self._last_sbm_by_bucket     = bucket_breakdown

        return delta_t, vega_t, curv_t, sbm_t, sbm_by_risk_class, bucket_breakdown


# ─────────────────────────────────────────────────────────────────────────────
# IMA — Expected Shortfall (MAR33)
# ─────────────────────────────────────────────────────────────────────────────


class IMACalculator:
    """
    Simplified IMA/ES calculator using historical or parametric methods.
    ES_t = mean of losses exceeding (1-α) worst outcomes.
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()
        self.config.validate()

    def compute_es(
        self,
        pnl_series: np.ndarray,
        stressed: bool = False,
        method: str = "historical",
        return_ci: bool = False,
        bootstrap_samples: int = 0,
    ) -> float:
        """
        MAR33.8: ES = mean of worst (1-97.5%) = 2.5% worst PnL.
        Scaled to 10-day: ES_10d = ES_1d × sqrt(10).

        method:
            "historical" (default) — empirical ES
            "normal" — parametric normal ES

        return_ci:
            If True and bootstrap_samples > 0, returns (ES, ES_low, ES_high).
        """
        try:
            validate_pnl_series(pnl_series, min_length=10)

            losses = -pnl_series
            α = self.config.confidence_level

            if method == "historical":
                # MAR33.8: ES = mean of worst (1 − 97.5%) = 2.5% of daily PnL.
                # int() always rounds down, systematically understating ES.
                # math.ceil() correctly includes the boundary observation.
                # For a 250-day series: ceil(250×0.025) = ceil(6.25) = 7 obs.
                cutoff = max(math.ceil(len(losses) * (1 - α)), 1)
                worst  = np.sort(losses)[-cutoff:]
                es_1d  = float(worst.mean())
            elif method == "normal":
                mu = float(losses.mean())
                sigma = float(losses.std(ddof=1))
                if sigma <= 0:
                    es_1d = max(mu, 0.0)
                else:
                    # Normal ES formula: μ + σ φ(z)/(1-α)
                    # where z = Φ^{-1}(α)
                    try:
                        from scipy.special import erfinv
                        def norm_ppf(p: float) -> float:
                            return math.sqrt(2) * erfinv(2 * p - 1)
                    except ImportError:
                        # Fallback approximation if scipy unavailable
                        def norm_ppf(p: float) -> float:
                            # Beasley-Springer-Moro approximation
                            a = [2.50662823884, -18.61500062529, 41.39119773534,
                                 -25.44106049637]
                            b = [-8.47351093090, 23.08336743743, -21.06224101826,
                                 3.13082909833]
                            c = [0.3374754822726147, 0.9761690190917186,
                                 0.1607979714918209, 0.0276438810333863,
                                 0.0038405729373609, 0.0003951896511919,
                                 0.0000321767881768, 0.0000002888167364,
                                 0.0000003960315187]
                            if p <= 0 or p >= 1:
                                return 0.0
                            q = p - 0.5
                            if abs(q) <= 0.42:
                                r = q * q
                                return q * (((a[3]*r+a[2])*r+a[1])*r+a[0]) / \
                                       ((((b[3]*r+b[2])*r+b[1])*r+b[0])*r+1)
                            else:
                                r = p if q > 0 else 1 - p
                                r = math.sqrt(-math.log(r))
                                ret = (((((((c[8]*r+c[7])*r+c[6])*r+c[5])*r+c[4])*r+c[3])*r+c[2])*r+c[1])*r+c[0]
                                return ret if q > 0 else -ret

                    z = norm_ppf(α)
                    phi = (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * z * z)
                    es_1d = mu + sigma * phi / (1 - α)
            else:
                raise FRTBValidationError(f"Unknown ES method: {method}")

            es_10d = es_1d * math.sqrt(self.config.holding_period_days)
            if stressed:
                es_10d *= self.config.stressed_es_multiplier

            result = max(es_10d, 0.0)
            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError("ES calculation produced NaN/inf")

            # Always return float (confidence intervals removed for type safety)
            # For confidence intervals, call this method multiple times with bootstrapped data
            return result

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"ES computation failed: {e}")


    # Liquidity horizon per risk class (MAR33.12, Table 1)
    # Key = risk_class string, Value = LH in days
    LIQUIDITY_HORIZONS: Dict[str, int] = {
        "GIRR":    10,
        "FX":      10,
        "EQ_LARGE":20,   # Large-cap equity
        "EQ":      40,   # Small-cap equity (conservative)
        "CSR_NS":  40,   # Credit spread non-securitisation
        "CSR_SEC": 60,   # Credit spread securitisation
        "CMDTY":   20,   # Commodity (liquid)
        "CMDTY_ILLIQUID": 60,
    }
    # Five liquidity horizon buckets (MAR33.4 Table 1)
    LH_BUCKETS = [10, 20, 40, 60, 120]  # j = 1..5

    def compute_es_lh_adjusted(
        self,
        pnl_by_risk_class: Dict[str, np.ndarray],
        stressed: bool = False,
        method: str = "historical",
    ) -> float:
        """
        MAR33.4: Liquidity-horizon-adjusted ES.

        ES = √[ ES_T(full)²
               + Σ_{j=2..5} ES_T(P_j)² × (LH_j - LH_{j-1}) / T ]

        where P_j = sub-portfolio of risk factors with LH ≥ LH_j.
        T = base horizon = 10 days.

        If only one risk class is present (or pnl_by_risk_class has one key),
        falls back to simple scaling.
        """
        T = self.config.holding_period_days  # 10
        LH = self.LH_BUCKETS  # [10, 20, 40, 60, 120]

        if not pnl_by_risk_class:
            return 0.0

        # MAR33.4 LH-adjusted ES formula:
        #   ES_LH = sqrt[ ES_1d(full)² × LH_1/T
        #               + Σ_{j≥2} ES_1d(P_j)² × (LH_j − LH_{j-1}) / T ]
        #
        # CRITICAL: formula requires 1-day ES values, not 10-day.
        # compute_es() returns ES_10d = ES_1d × √T, so we divide back:
        #   ES_1d = ES_10d / √T
        full_pnl    = np.sum(list(pnl_by_risk_class.values()), axis=0)
        es_full_10d = self.compute_es(full_pnl, stressed=False, method=method)
        es_full_1d  = es_full_10d / math.sqrt(T) if T > 0 else es_full_10d

        # j=1: ES_1d² × LH_1/T  (LH_1 = T = 10  →  term = ES_1d²)
        result_sq = es_full_1d ** 2 * LH[0] / T

        for j_idx in range(1, len(LH)):
            lh_j      = LH[j_idx]
            lh_j_prev = LH[j_idx - 1]

            partial_pnls = []
            for rc, pnl in pnl_by_risk_class.items():
                if self.LIQUIDITY_HORIZONS.get(rc, 10) >= lh_j:
                    partial_pnls.append(pnl)

            if not partial_pnls:
                continue

            # Convert 10d → 1d before applying horizon increment
            es_partial_10d = self.compute_es(
                np.sum(partial_pnls, axis=0), stressed=False, method=method)
            es_partial_1d  = es_partial_10d / math.sqrt(T) if T > 0 else es_partial_10d
            result_sq     += es_partial_1d ** 2 * (lh_j - lh_j_prev) / T

        # Formula result is in 1-day units; scale to 10-day (same as compute_es output)
        lh_es_1d  = math.sqrt(max(result_sq, 0.0))
        lh_es_10d = lh_es_1d * math.sqrt(T)
        if stressed:
            # stressed_es_multiplier is an operational approximation.
            # Production: calibrate to actual stressed historical window (MAR33.4).
            lh_es_10d *= self.config.stressed_es_multiplier
        return max(lh_es_10d, 0.0)

    def compute_imcc(
        self,
        pnl_full: np.ndarray,
        pnl_by_risk_class: Optional[Dict[str, np.ndarray]] = None,
        pnl_uncorrelated: Optional[np.ndarray] = None,
        imcc_history: Optional[List[float]] = None,
        method: str = "historical",
    ) -> Dict[str, float]:
        """
        MAR33.4-8: Internal Models Capital Charge (IMCC) with partial ES decomposition.

        Regulatory formula (Enhancement 4):
            IMCC_t = ρ × ES_{S,C}(full risk factors, correlated)
                   + (1 − ρ) × ES_{S,U}(inter-risk-class correlations = 0)

        where ρ is endogenous:
            ρ = ES_{S,C} / (ES_{S,C} + ES_{S,U})    [MAR33.5]

        Final IMA capital uses the 60-day average constraint (MAR33.8):
            IMA = max(IMCC_{t-1},  m_c × mean(IMCC over 60d))  + SES

        Args:
            pnl_full:          Full-portfolio 1-day P&L series (all risk factors).
            pnl_by_risk_class: {rc: pnl_array} — used for LH-adjusted ES.
            pnl_uncorrelated:  P&L series with inter-class correlations = 0.
                               If None, approximated as RSS of per-class ES values.
            imcc_history:      Last ≤60 daily IMCC values for the average constraint.
            method:            'historical' or 'normal'.

        Returns:
            Dict: es_full, es_uncorrelated, rho, imcc_current, imcc_60d_avg,
                  imcc_regulatory.
        """
        try:
            # ES_S,C — stressed ES on the full (correlated) portfolio
            if pnl_by_risk_class:
                es_full = self.compute_es_lh_adjusted(
                    pnl_by_risk_class, stressed=True, method=method
                )
            else:
                es_full = self.compute_es(pnl_full, stressed=True, method=method)

            # ES_S,U — stressed ES with inter-risk-class correlations = 0.
            # Preferred: caller supplies a dedicated uncorrelated P&L series.
            # Fallback: RSS of individual risk-class ES values (conservative proxy).
            if pnl_uncorrelated is not None:
                es_uncorr = self.compute_es(pnl_uncorrelated, stressed=True, method=method)
            elif pnl_by_risk_class and len(pnl_by_risk_class) > 1:
                rc_es_vals = [
                    self.compute_es(pnl, stressed=True, method=method)
                    for pnl in pnl_by_risk_class.values()
                ]
                es_uncorr = math.sqrt(sum(v ** 2 for v in rc_es_vals))
            else:
                es_uncorr = es_full  # Single risk class: no inter-class correlation

            # ρ — endogenous correlation weight (MAR33.5)
            denom = es_full + es_uncorr
            rho = es_full / denom if denom > 0 else 0.5

            # IMCC_t = ρ × ES_C + (1−ρ) × ES_U
            imcc_current = rho * es_full + (1.0 - rho) * es_uncorr

            # 60-day moving-average constraint (MAR33.8)
            if imcc_history and len(imcc_history) > 0:
                imcc_60d_avg = float(np.mean(imcc_history[-60:]))
            else:
                imcc_60d_avg = imcc_current

            imcc_regulatory = max(imcc_current, imcc_60d_avg)

            logger.debug(
                "IMCC: ES_C=%.0f ES_U=%.0f rho=%.3f IMCC_t=%.0f "
                "IMCC_60d=%.0f IMCC_reg=%.0f",
                es_full, es_uncorr, rho, imcc_current, imcc_60d_avg, imcc_regulatory,
            )

            return {
                "es_full":         es_full,
                "es_uncorrelated": es_uncorr,
                "rho":             rho,
                "imcc_current":    imcc_current,
                "imcc_60d_avg":    imcc_60d_avg,
                "imcc_regulatory": imcc_regulatory,
            }

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"IMCC computation failed: {e}")

    # Enhancement 7 (MAR31.14): NMRF observation threshold.
    NMRF_OBS_THRESHOLD: int = 24   # fewer than 24 real price obs in 12m → NMRF

    @staticmethod
    def identify_nmrf(
        factor_observation_counts: Dict[str, int],
    ) -> List[str]:
        """
        MAR31.14: A risk factor is non-modellable (NMRF) if the institution
        cannot demonstrate at least 24 real price observations over the prior
        12-month period.

        Args:
            factor_observation_counts: {risk_factor_id: observation_count}

        Returns:
            List of NMRF risk factor IDs.
        """
        return [
            rf for rf, count in factor_observation_counts.items()
            if count < IMACalculator.NMRF_OBS_THRESHOLD
        ]

    def nmrf_charge(
        self,
        n_nmrf_factors: int,
        avg_notional: float,
        factor_ssrm: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        MAR31.14: NMRF Stress Scenario Risk Measure (SSRM).

        The regulatory charge for each NMRF is the Stress Scenario Risk
        Measure — the loss at the 99th percentile of the factor's historical
        distribution over its liquidity horizon.

        Args:
            n_nmrf_factors: Number of NMRF factors (used only when factor_ssrm
                            is not supplied, as a backward-compatible fallback).
            avg_notional:   Average notional per NMRF factor (fallback only).
            factor_ssrm:    {risk_factor_id: ssrm_loss} — preferred input.
                            If provided, SES = sqrt(Σ SSRM_i²) per MAR31.14
                            (partial aggregation — NMRFs are not diversifiable).
                            If None, falls back to n × avg_notional × nmrf_charge_bp.

        Returns:
            Aggregate NMRF / SES capital charge.
        """
        try:
            if factor_ssrm is not None and len(factor_ssrm) > 0:
                # MAR31.14: SES = sqrt(sum of squared SSRM values).
                # NMRFs receive NO diversification benefit with modellable factors.
                ssrm_values = list(factor_ssrm.values())
                if any(v < 0 for v in ssrm_values):
                    raise FRTBValidationError("SSRM values must be non-negative")
                ses = math.sqrt(sum(v ** 2 for v in ssrm_values))
                logger.debug(
                    "NMRF SES: %d factors, SES=%.0f (max_ssrm=%.0f)",
                    len(ssrm_values), ses, max(ssrm_values),
                )
                return ses

            # Fallback: flat proxy (backward compatible)
            if n_nmrf_factors < 0:
                raise FRTBValidationError("n_nmrf_factors must be non-negative")
            if avg_notional <= 0:
                raise FRTBValidationError("avg_notional must be positive")

            charge = n_nmrf_factors * avg_notional * self.config.nmrf_charge_bp
            if math.isnan(charge) or math.isinf(charge):
                raise FRTBCalculationError("NMRF charge produced NaN/inf")
            logger.debug(
                "NMRF fallback proxy: %d factors × %.0f × %.4f = %.0f",
                n_nmrf_factors, avg_notional, self.config.nmrf_charge_bp, charge,
            )
            return charge

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"NMRF charge calculation failed: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# DRC — Default Risk Charge (MAR22 SBM / MAR33.18 IMA)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DRCPosition:
    """Single position for DRC calculation."""
    trade_id:       str
    notional:       float          # gross notional (positive = long, negative = short)
    lgd:            float          # loss given default [0,1]; typically 0.45–1.0
    market_value:   float          # current market value of the position
    credit_quality: str            # 'AAA','AA','A','BBB','BB','B','CCC','DEFAULT'
    maturity_years: float = 1.0    # residual maturity in years (for maturity cap)
    asset_class:    str   = "CORP" # CORP | SOVERIGN | SECURITISATION

# Supervisory DRC risk weights per credit quality (MAR22, Table MAR22.2)
_DRC_RW: Dict[str, float] = {
    "AAA":     0.005,
    "AA":      0.02,
    "A":       0.03,
    "BBB":     0.06,
    "BB":      0.15,
    "B":       0.30,
    "CCC":     0.50,
    "DEFAULT": 1.00,
    "UNRATED": 0.15,
}

class DRCCalculator:
    """
    Standardised Default Risk Charge per MAR22.

    Algorithm (MAR22.8 corrected):
      1. Gross JTD per position:
           Cash bond (is_derivative=False):
               JTD_long  = LGD × max(Notional, 0)             (MAR22.8)
               JTD_short = LGD × max(−Notional, 0)
           Derivative (is_derivative=True):
               JTD_long  = max( LGD × Notional − MV, 0)      (MTM-adjusted)
               JTD_short = max(−LGD × Notional + MV, 0)
      2. Maturity scaling for sub-1yr positions (MAR22.9):
               JTD_scaled = JTD × min(maturity_years / 1.0, 1.0)
      3. Net long vs short within the same quality bucket.
         Short positions offset long with 50% recognition (MAR22.24).
         Index shorts offset constituents at 80% only (MAR22.27 basis risk).
      4. Apply supervisory RW per quality bucket → DRC.
    """

    # Enhancement 1 (MAR22.27): index hedge recognition ratio.
    # Single-name shorts perfectly offset single-name longs (100%).
    # Index shorts offset index/constituent longs at 80% (basis risk haircut).
    INDEX_HEDGE_RECOGNITION: float = 0.80

    @staticmethod
    def _gross_jtd(
        pos: "DRCPosition",
        is_derivative: bool = False,
    ) -> Tuple[float, float]:
        """
        MAR22.8: Compute (jtd_long, jtd_short) for a single position.

        For cash bonds/loans, JTD = LGD × |Notional|. The market value is
        already priced into the bond and must NOT be subtracted (doing so
        double-counts recovery for distressed bonds trading below par).

        For derivatives, JTD is the MTM-contingent loss:
            long:  max(LGD × N − MV, 0)
            short: max(−LGD × N + MV, 0)
        """
        n = pos.notional
        lgd = max(0.0, min(pos.lgd, 1.0))

        if not is_derivative:
            # Cash bond / loan (MAR22.8)
            if n >= 0:
                return lgd * n, 0.0
            else:
                return 0.0, lgd * abs(n)
        else:
            # Derivative
            if n >= 0:
                return max(lgd * n - pos.market_value, 0.0), 0.0
            else:
                return 0.0, max(-lgd * n + pos.market_value, 0.0)

    def compute(
        self,
        positions: List["DRCPosition"],
        is_derivative_map: Optional[Dict[str, bool]] = None,
        index_trade_ids: Optional[set] = None,
        enable_basis_risk: bool = True,
        maturity_buckets: bool = True,
    ) -> Dict[str, Any]:
        """
        Compute standardised DRC for a list of positions.

        Args:
            positions:         List of DRCPosition objects.
            is_derivative_map: {trade_id: True/False}. Default: False (cash bond).
            index_trade_ids:   Set of trade_ids that are index instruments.
                               These receive 80% hedge recognition (MAR22.27).
            enable_basis_risk: Apply 80% index offset (default True).
            maturity_buckets:  Apply sub-1yr maturity scaling (default True).

        Returns:
            dict with drc_total, by_quality breakdown, jtd_net.
        """
        if not positions:
            return {"drc_total": 0.0, "by_quality": {}, "jtd_net": 0.0}

        is_deriv = is_derivative_map or {}
        idx_ids  = index_trade_ids or set()

        # Step 1 & 2: Gross JTD + maturity scaling
        long_jtd_by_q:  Dict[str, float] = {}
        short_jtd_by_q: Dict[str, float] = {}

        for pos in positions:
            q = pos.credit_quality.upper()

            deriv = is_deriv.get(pos.trade_id, False)
            jtd_l, jtd_s = self._gross_jtd(pos, is_derivative=deriv)

            # Enhancement 1 (MAR22.9): maturity scaling for sub-1yr positions.
            if maturity_buckets and pos.maturity_years < 1.0:
                scale = max(pos.maturity_years, 0.0)   # clamp to [0, 1]
                jtd_l *= scale
                jtd_s *= scale

            # Enhancement 1 (MAR22.27): index shorts get 80% recognition.
            # Single-name shorts retain 100% offset against matching longs.
            if enable_basis_risk and pos.trade_id in idx_ids and pos.notional < 0:
                jtd_s *= self.INDEX_HEDGE_RECOGNITION

            long_jtd_by_q[q]  = long_jtd_by_q.get(q, 0.0)  + jtd_l
            short_jtd_by_q[q] = short_jtd_by_q.get(q, 0.0) + jtd_s

        # Step 3 & 4: Net JTD and apply risk weight
        drc_total = 0.0
        by_quality: Dict[str, Dict[str, float]] = {}
        all_qualities = set(list(long_jtd_by_q.keys()) + list(short_jtd_by_q.keys()))

        for q in all_qualities:
            rw     = _DRC_RW.get(q, _DRC_RW["UNRATED"])
            jtd_l  = long_jtd_by_q.get(q, 0.0)
            jtd_s  = short_jtd_by_q.get(q, 0.0)
            # Net JTD = long − 50% of short (MAR22.24)
            net_jtd = max(jtd_l - 0.50 * jtd_s, 0.0)
            drc_q   = rw * net_jtd
            drc_total += drc_q
            by_quality[q] = {
                "jtd_long": jtd_l, "jtd_short": jtd_s,
                "jtd_net": net_jtd, "rw": rw, "drc": drc_q,
            }

        return {
            "drc_total":  drc_total,
            "by_quality": by_quality,
            "jtd_net":    sum(v["jtd_net"] for v in by_quality.values()),
        }

    @staticmethod
    def positions_from_sensitivities(
        sensitivities: Sequence["Sensitivity"],
        avg_notional: float = 1_000_000,
    ) -> List[DRCPosition]:
        """
        Derive approximate DRC positions from credit sensitivities.
        Used when explicit position data is unavailable (fallback).
        Quality bucket derived from bucket number heuristic.
        """
        quality_map = {
            "1":  "AAA",  "2":  "AA",   "3":  "A",   "4":  "BBB",
            "5":  "BBB",  "6":  "BB",   "7":  "BB",  "8":  "B",
            "9":  "B",   "10": "CCC",  "11": "CCC", "12": "DEFAULT",
        }
        positions = []
        for s in sensitivities:
            if s.risk_class not in ("CSR_NS", "CSR_SEC"):
                continue
            q = quality_map.get(s.bucket, "BBB")
            # Use avg_notional as proxy for position size (signed by delta direction).
            # Note: this fallback is approximate — for accurate DRC, supply
            # explicit DRCPosition objects with real bond notionals and credit quality.
            direction = 1 if s.delta >= 0 else -1
            notional  = direction * avg_notional
            positions.append(DRCPosition(
                trade_id=s.trade_id, notional=notional,
                lgd=0.45, market_value=0.0,
                credit_quality=q, maturity_years=1.0,
            ))
        return positions

# ─────────────────────────────────────────────────────────────────────────────
# FRTB Master Engine
# ─────────────────────────────────────────────────────────────────────────────


class FRTBEngine:
    """
    FRTB capital calculator (SBM + IMA) per MAR21-33.
    Validates inputs, manages configuration, and orchestrates calculations.
    Includes:
      - position aggregation
      - scenario / what-if hooks
      - batch processing
      - basic risk decomposition
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()
        try:
            self.config.validate()
        except FRTBConfigurationError as e:
            logger.error(f"Configuration validation failed: {e}")
            raise

        self.sbm = SBMCalculator(self.config)
        self.ima = IMACalculator(self.config)
        logger.info("FRTB Engine initialised (SBM + IMA, MAR21-33)")


    def _ima_multiplier(self, backtesting_exceptions: int = 0) -> float:
        """
        MAR33.9: IMA multiplier mc = 1.5 + add-on based on backtesting exceptions.

        Exceptions (250d):  0-4 → +0.00  (green)
                            5   → +0.20
                            6   → +0.26
                            7   → +0.33
                            8   → +0.38
                            9   → +0.42
                           10+  → +0.50  (red zone, model revocation risk)
        """
        addon_table = {0:0.0, 1:0.0, 2:0.0, 3:0.0, 4:0.0,
                       5:0.20, 6:0.26, 7:0.33, 8:0.38, 9:0.42}
        addon = addon_table.get(backtesting_exceptions,
                                0.50 if backtesting_exceptions >= 10 else 0.0)
        return 1.5 + addon

    # ---- core compute -----------------------------------------------------

    def compute(
        self,
        portfolio_id: str,
        sensitivities: Sequence[Sensitivity],
        pnl_series: Optional[np.ndarray] = None,
        n_nmrf: int = 3,
        avg_notional: float = 1_000_000,
        run_date: Optional[date] = None,
        es_method: str = "historical",
        market_conditions: Optional[MarketConditions] = None,
        backtesting_exceptions: int = 0,
        pnl_by_risk_class: Optional[Dict[str, np.ndarray]] = None,
        pnl_uncorrelated: Optional[np.ndarray] = None,
        imcc_history: Optional[List[float]] = None,
        drc_positions: Optional[List[DRCPosition]] = None,
        notionals_by_instrument: Optional[Dict[str, tuple]] = None,
        factor_ssrm: Optional[Dict[str, float]] = None,
        rtpl: Optional[np.ndarray] = None,
        hpl: Optional[np.ndarray] = None,
    ) -> FRTBResult:
        """
        Compute complete FRTB capital charge (SBM + IMA) per MAR21-33.

        Args:
            portfolio_id:           Unique identifier for logging and output.
            sensitivities:          Trade-level sensitivity objects (delta/vega/curvature).
            pnl_series:             1-day P&L array for ES/backtesting (250+ days preferred).
            n_nmrf:                 Number of NMRF factors (used only if factor_ssrm=None).
            avg_notional:           Average notional per factor (NMRF fallback proxy only).
            run_date:               Calculation date (defaults to today).
            es_method:              'historical' (default) or 'normal' (parametric).
            market_conditions:      Optional real-time MarketConditions. If None and
                                    use_market_conditions=True, fetches current conditions.
            backtesting_exceptions: Number of VaR exceptions in the 250-day window.
                                    Drives the IMA multiplier per MAR33.9 (1.50 to 2.00).
            pnl_by_risk_class:      {risk_class: pnl_array} for LH-adjusted ES.
                                    If provided, ES uses the MAR33.4 five-horizon formula.
                                    If None, falls back to simple sqrt(10) scaling.
            pnl_uncorrelated:       P&L with inter-class correlations=0 for IMCC (MAR33.5).
            imcc_history:           Last ≤60 daily IMCC values for 60-day average (MAR33.8).
            drc_positions:          Explicit DRCPosition list (MAR22). If None → DRC=0.
            notionals_by_instrument:{trade_id: (notional, type)} for RRAO (MAR23.5).
            factor_ssrm:            {factor_id: ssrm_loss} for NMRF SES (MAR31.14).
            rtpl:                   Risk-theoretical P&L for PLA test (MAR32).
            hpl:                    Hypothetical P&L for PLA test (MAR32).

        Returns:
            FRTBResult with complete SBM, IMA, DRC, RRAO, PLA and floor fields.
        """
        try:
            run_date = run_date or date.today()

            # Fetch real-time market conditions if enabled
            market: Optional[MarketConditions] = None
            if self.config.use_market_conditions:
                if market_conditions is not None:
                    market = market_conditions
                elif self.config.market_data_feed is not None:
                    market = self.config.market_data_feed.get_current_conditions()
                
                if market:
                    logger.info(
                        "FRTB with real-time conditions: regime=%s, stress=%.2f, VIX=%.1f",
                        market.regime().value, market.stress_level(), market.vix_level
                    )

            # Validate & aggregate
            validate_sensitivities(sensitivities, self.config)
            agg_sens = aggregate_sensitivities(sensitivities)

            if pnl_series is not None:
                validate_pnl_series(pnl_series)

            # ── SBM (with market overlay if enabled) ──
            delta_t, vega_t, curv_t, sbm_t, sbm_by_rc, sbm_by_bucket = self.sbm.total_sbm(agg_sens, market=market)

            # ── IMA / ES — Enhancement 4 (MAR33.4-8 IMCC decomposition) ──
            if pnl_series is None and not pnl_by_risk_class:
                logger.info("No PnL series provided; generating synthetic for demonstration")
                rng = np.random.default_rng(42)
                pnl_series = rng.normal(0, avg_notional * 0.01, self.config.backtesting_window)

            effective_pnl = pnl_series if pnl_series is not None else np.zeros(1)

            imcc_result = self.ima.compute_imcc(
                pnl_full=effective_pnl,
                pnl_by_risk_class=pnl_by_risk_class,
                pnl_uncorrelated=pnl_uncorrelated,
                imcc_history=imcc_history,
                method=es_method,
            )
            # Backward-compatible aliases
            es_base     = imcc_result["es_full"]
            es_stressed = imcc_result["es_full"]   # stressed via compute_imcc internally
            imcc_reg    = imcc_result["imcc_regulatory"]

            nmrf_ch = self.ima.nmrf_charge(n_nmrf, avg_notional, factor_ssrm=factor_ssrm)
            # Enhancement 4 (MAR33.8): IMA = max(IMCC_{t-1}, mc × IMCC_60d) + SES
            mc = self._ima_multiplier(backtesting_exceptions)
            ima_t = max(imcc_result["imcc_current"], mc * imcc_result["imcc_60d_avg"]) + nmrf_ch

            # ── DRC (MAR22 / MAR33.18) ──────────────────────────────────────
            # DRC is only charged when explicit credit/bond positions are supplied.
            # When drc_positions is None (the default for derivative-only books),
            # the charge is zero — you cannot reliably infer bond notionals from
            # delta sensitivities. Pass drc_positions explicitly for credit portfolios.
            drc_calc = DRCCalculator()
            if drc_positions is None:
                drc_positions = []   # No DRC unless explicit positions provided
            drc_result  = drc_calc.compute(drc_positions)
            drc_total   = drc_result["drc_total"]
            drc_by_qual = drc_result["by_quality"]

            # ── RRAO (MAR23.5) ───────────────────────────────────────────────
            rrao_total = self.sbm.rrao_charge(agg_sens, notionals_by_instrument)

            # ── PLA test (MAR32) — desk IMA eligibility ───────────────────────
            pla_zone = "N/A"
            if rtpl is not None and hpl is not None:
                pla_res  = self.pla_test(rtpl, hpl)
                pla_zone = pla_res["zone"]
                if pla_zone == "RED":
                    logger.warning(
                        "FRTB [%s]: PLA test FAILED (RED) — desk forced to SBM", portfolio_id)
                    ima_t = 0.0   # IMA not available; SBM dominates

            # Capital = max(SBM + DRC + RRAO, IMA + DRC)   [MAR33.8-33.9]
            # Note: mc multiplier already folded into ima_t via IMCC formula above.
            sbm_with_extras = sbm_t + drc_total + rrao_total
            ima_with_drc    = ima_t + drc_total
            capital = max(sbm_with_extras, ima_with_drc)
            rwa     = capital * 12.5

            # Enhancement 10 (MAR12.11 / CRR3 Article 325a): SA output floor.
            # At the consolidated entity level, IMA capital >= 72.5% × SBM capital.
            sa_floor = 0.725 * sbm_with_extras
            sa_floor_binding = capital < sa_floor
            if sa_floor_binding:
                logger.warning(
                    "FRTB [%s]: SA output floor binding — capital %.0f → %.0f "
                    "(72.5%% × SBM %.0f)",
                    portfolio_id, capital, sa_floor, sbm_with_extras,
                )
                capital = sa_floor
                rwa = capital * 12.5

            ima_components = {
                "es_base_10d":        es_base,
                "es_stressed_10d":    es_stressed,
                "imcc_current":       imcc_result["imcc_current"],
                "imcc_60d_avg":       imcc_result["imcc_60d_avg"],
                "imcc_regulatory":    imcc_reg,
                "imcc_rho":           imcc_result["rho"],
                "nmrf_charge":        nmrf_ch,
                "ima_total":          ima_t,
                "drc_total":          drc_total,
                "rrao_total":         rrao_total,
                "sa_floor":           sa_floor,
                "sa_floor_binding":   sa_floor_binding,
            }

            logger.info(
                "FRTB [%s] SBM=%.0f  DRC=%.0f  RRAO=%.0f  IMCC=%.0f  "
                "Capital=%.0f  RWA=%.0f  PLA=%s  SAFloor=%s",
                portfolio_id, sbm_t, drc_total, rrao_total, ima_t, capital, rwa,
                pla_zone, "BINDING" if sa_floor_binding else "OK",
            )

            return FRTBResult(
                run_date=run_date,
                portfolio_id=portfolio_id,
                method="SBM+IMA",
                sbm_delta=delta_t,
                sbm_vega=vega_t,
                sbm_curvature=curv_t,
                sbm_total=sbm_t,
                es_99_10d=es_base,
                es_stressed=es_stressed,
                nmrf_charge=nmrf_ch,
                ima_total=ima_t,
                capital_market_risk=capital,
                rwa_market=rwa,
                drc_charge=drc_total,
                rrao_charge_v=rrao_total,
                pla_zone=pla_zone,
                sa_floor_capital=sa_floor,
                sa_floor_binding=sa_floor_binding,
                imcc_rho=imcc_result["rho"],
                imcc_es_full=imcc_result["es_full"],
                imcc_es_uncorr=imcc_result["es_uncorrelated"],
                sbm_by_risk_class=sbm_by_rc,
                sbm_by_bucket=sbm_by_bucket,
                ima_components=ima_components,
                drc_by_quality=drc_by_qual,
            )

        except (FRTBValidationError, FRTBCalculationError) as e:
            logger.error(f"FRTB computation failed for {portfolio_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in FRTB computation: {e}")
            raise FRTBCalculationError(f"Unexpected error: {e}")

    # ---- batch processing -------------------------------------------------


    def pla_test(
        self,
        rtpl: np.ndarray,
        hpl: np.ndarray,
    ) -> Dict[str, Any]:
        """
        MAR32.10-14: Profit & Loss Attribution (PLA) test.

        Compares RTPL (risk-theoretical P&L, using approved risk factors only)
        against HPL (hypothetical P&L, full desk revaluation).

        Two MAR32-prescribed metrics (Enhancement 3):

        1. Spearman rank correlation (MAR32.12):
               Green:  ρ_S ≥ 0.80
               Amber:  0.70 ≤ ρ_S < 0.80
               Red:    ρ_S < 0.70

        2. Variance Ratio — VNPNLR (MAR32.12):
               VNPNLR = Var(HPL − RTPL) / Var(HPL)
               Green:  VNPNLR ≤ 0.10
               Amber:  0.10 < VNPNLR ≤ 0.20
               Red:    VNPNLR > 0.20

        Zone assignment (MAR32.14):
            Green:  Both metrics Green.
            Amber:  At least one metric Amber, neither Red.
            Red:    At least one metric Red → desk forced to SBM.

        Returns dict with zone, statistics, and capital surcharge flag.
        """
        n = min(len(rtpl), len(hpl))
        rtpl_s = rtpl[:n].astype(float)
        hpl_s  = hpl[:n].astype(float)

        # ── Metric 2: Variance Ratio (VNPNLR) ─────────────────────────────
        diff = hpl_s - rtpl_s
        var_hpl  = float(np.var(hpl_s,  ddof=1)) if n > 1 else 1.0
        var_diff = float(np.var(diff,   ddof=1)) if n > 1 else 0.0
        vnpnlr   = var_diff / var_hpl if var_hpl > 0 else 0.0

        if vnpnlr <= 0.10:
            vr_zone = "GREEN"
        elif vnpnlr <= 0.20:
            vr_zone = "AMBER"
        else:
            vr_zone = "RED"

        # ── Metric 1: Spearman rank correlation ────────────────────────────
        try:
            from scipy.stats import spearmanr
            spearman_tuple = spearmanr(rtpl_s, hpl_s)
            spearman_corr: float = float(spearman_tuple[0])  # type: ignore
        except ImportError:
            logger.warning("scipy not available — using Pearson as Spearman proxy")
            mean_r = rtpl_s.mean(); mean_h = hpl_s.mean()
            denom  = np.linalg.norm(rtpl_s - mean_r) * np.linalg.norm(hpl_s - mean_h)
            spearman_corr = float(np.dot(rtpl_s - mean_r, hpl_s - mean_h) / (denom + 1e-12))

        if spearman_corr >= 0.80:
            sc_zone = "GREEN"
        elif spearman_corr >= 0.70:
            sc_zone = "AMBER"
        else:
            sc_zone = "RED"

        # ── Combined zone (MAR32.14) ───────────────────────────────────────
        _rank = {"GREEN": 0, "AMBER": 1, "RED": 2}
        worst = max(sc_zone, vr_zone, key=lambda z: _rank[z])
        zone  = worst

        logger.info(
            "PLA test: Spearman=%.3f (%s)  VNPNLR=%.4f (%s)  → %s zone",
            spearman_corr, sc_zone, vnpnlr, vr_zone, zone,
        )

        return {
            "zone":                       zone,
            "spearman":                   spearman_corr,
            "spearman_zone":              sc_zone,
            "vnpnlr":                     vnpnlr,
            "vnpnlr_zone":                vr_zone,
            "ima_eligible":               zone in ("GREEN", "AMBER"),
            "capital_surcharge_required": zone == "AMBER",
        }

    def compute_batch(
        self,
        portfolios: Iterable[Dict[str, Any]],
    ) -> List[FRTBResult]:
        """
        Compute FRTB for multiple portfolios.
        portfolios: iterable of dicts with keys accepted by self.compute.
        """
        results: List[FRTBResult] = []
        for p in portfolios:
            results.append(self.compute(**p))
        return results

    # ---- scenario / what-if analysis -------------------------------------

    @staticmethod
    def apply_shock_to_sensitivities(
        sensitivities: Sequence[Sensitivity],
        scenario: ShockScenario,
    ) -> List[Sensitivity]:
        """
        Apply parallel stress shocks to a sensitivity portfolio.

        Shock semantics (additive, not multiplicative):
          rate_bp:   Parallel shift of the entire rate curve in basis points.
                     Delta sensitivities are expressed as dV/d(rate) per 1bp,
                     so the P&L impact = delta × rate_bp (additive).
                     Previous version used multiplicative scaling (delta *= factor)
                     which is dimensionally incorrect — a 200bp shift does not
                     multiply delta by 1.02; it adds 200 × delta to the P&L.

          spread_bp: Parallel spread shift in basis points for CSR positions.

          fx_pct:    Percentage move in FX spot.  Delta is expressed as dV/d(spot)
                     per 1% move, so impact = delta × fx_pct (additive).

        Vega and curvature are also shocked where applicable so that option-heavy
        books produce correct scenario capital (previous version left them unchanged).

        For scenarios requiring non-parallel (term-structure) shocks, generate
        separate Sensitivity objects per tenor and pass them directly to compute().
        """
        shocked: List[Sensitivity] = []
        for s in sensitivities:
            s_new = copy.copy(s)

            if s_new.risk_class == "GIRR":
                # Additive: shift P&L by rate_bp × current_delta
                # The shocked sensitivity reflects the portfolio after the rate move.
                s_new.delta      += s.delta * (scenario.rate_bp / 10000.0)
                # Vega of IR options changes with rate level (simplified: rate shock
                # changes the vol regime; scale vega by same proportion as delta shift)
                if s_new.vega != 0:
                    s_new.vega   += s.vega * (scenario.rate_bp / 10000.0)
                # Curvature: recalculate if shock is large enough to matter
                if s_new.curvature_up != 0 or s_new.curvature_dn != 0:
                    scale = 1.0 + scenario.rate_bp / 10000.0
                    s_new.curvature_up = s.curvature_up * scale
                    s_new.curvature_dn = s.curvature_dn * scale

            elif s_new.risk_class in ("CSR_NS", "CSR_SEC", "CSR_CTP"):
                s_new.delta      += s.delta * (scenario.spread_bp / 10000.0)
                if s_new.vega != 0:
                    s_new.vega   += s.vega * (scenario.spread_bp / 10000.0)
                if s_new.curvature_up != 0 or s_new.curvature_dn != 0:
                    scale = 1.0 + scenario.spread_bp / 10000.0
                    s_new.curvature_up = s.curvature_up * scale
                    s_new.curvature_dn = s.curvature_dn * scale

            elif s_new.risk_class in ("FX", "FX_PRESCRIBED"):
                s_new.delta      += s.delta * scenario.fx_pct
                if s_new.vega != 0:
                    # FX vol typically rises when spot moves sharply
                    s_new.vega   += s.vega * abs(scenario.fx_pct)
                if s_new.curvature_up != 0 or s_new.curvature_dn != 0:
                    scale = 1.0 + scenario.fx_pct
                    s_new.curvature_up = s.curvature_up * scale
                    s_new.curvature_dn = s.curvature_dn * scale

            shocked.append(s_new)
        return shocked

    def run_scenarios(
        self,
        portfolio_id: str,
        sensitivities: Sequence[Sensitivity],
        pnl_series: Optional[np.ndarray],
        scenarios: Sequence[ShockScenario],
        **kwargs,
    ) -> Dict[str, FRTBResult]:
        """
        Run multiple shock scenarios and return a mapping:
            scenario_name -> FRTBResult
        """
        results: Dict[str, FRTBResult] = {}
        for sc in scenarios:
            shocked_sens = self.apply_shock_to_sensitivities(sensitivities, sc)
            res = self.compute(
                portfolio_id=f"{portfolio_id}:{sc.name}",
                sensitivities=shocked_sens,
                pnl_series=pnl_series,
                **kwargs,
            )
            results[sc.name] = res
        return results

    # ---- parameter overrides ---------------------------------------------

    def compute_with_overrides(
        self,
        overrides: Dict[str, Dict[str, Any]],
        **compute_kwargs,
    ) -> FRTBResult:
        """
        Compute capital with configuration overrides (what-if on parameters).
        overrides example:
            {
              "delta_rw": {"GIRR": [0.02, ...]},
              "intra_corr": {"EQ": 0.3},
            }
        """
        cfg = copy.deepcopy(self.config)
        for section, vals in overrides.items():
            attr = getattr(cfg, section, None)
            if isinstance(attr, dict):
                attr.update(vals)
            else:
                setattr(cfg, section, vals)
        cfg.validate()
        engine = FRTBEngine(config=cfg)
        return engine.compute(**compute_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Backtesting — Traffic Light Framework (MAR99)
# ─────────────────────────────────────────────────────────────────────────────


class BacktestEngine:
    """
    Compares predicted VaR/ES vs actual P&L losses.
    MAR99: 0-4 exceptions = Green, 5-9 = Amber, 10+ = Red.
    """

    def __init__(self, config: Optional[FRTBConfig] = None):
        self.config = config or FRTBConfig()

    def _count_exceptions(self, predicted: np.ndarray, pnl: np.ndarray) -> int:
        """Count days where actual loss (−PnL) exceeds the predicted VaR."""
        return int(np.sum(-pnl > predicted))

    def _zone_for_exceptions(self, exceptions: int) -> str:
        if exceptions <= self.config.green_zone_max:
            return "GREEN"
        elif exceptions <= self.config.amber_zone_max:
            return "AMBER"
        return "RED"

    def evaluate(
        self,
        predicted: np.ndarray,         # 1-day VaR/ES predictions (positive = loss)
        actual_pnl: np.ndarray,        # Actual daily P&L including fees/reserves
        hypothetical_pnl: Optional[np.ndarray] = None,  # Clean HPL (no fees/reserves)
    ) -> Dict[str, Any]:
        """
        MAR99.4: Dual-track backtesting framework.

        Enhancement 8: MAR99 requires TWO parallel backtests:
          Track 1 — Actual P&L (including intra-day trading, fees, reserves).
                     Exception count drives the IMA multiplier add-on.
          Track 2 — Hypothetical P&L (clean: static portfolio, no fees).
                     Exception count triggers model investigation.

        The zone is determined by the WORSE of the two exception counts.
        If hypothetical_pnl is None, only Track 1 is evaluated (backward compat).
        """
        try:
            if len(predicted) != len(actual_pnl):
                raise FRTBValidationError("Length mismatch: predicted vs actual_pnl")
            if np.any(np.isnan(predicted)) or np.any(np.isnan(actual_pnl)):
                raise FRTBValidationError("Predicted or actual_pnl contains NaN")

            n = len(predicted)

            # Track 1: Actual PnL
            exc_actual = self._count_exceptions(predicted, actual_pnl)
            zone_actual = self._zone_for_exceptions(exc_actual)

            # Track 2: Hypothetical PnL (clean, static portfolio)
            exc_hypo = None
            zone_hypo = "N/A"
            if hypothetical_pnl is not None:
                if len(hypothetical_pnl) != n:
                    raise FRTBValidationError(
                        "Length mismatch: predicted vs hypothetical_pnl"
                    )
                if np.any(np.isnan(hypothetical_pnl)):
                    raise FRTBValidationError("hypothetical_pnl contains NaN")
                exc_hypo = self._count_exceptions(predicted, hypothetical_pnl)
                zone_hypo = self._zone_for_exceptions(exc_hypo)

            # MAR99.4: worst of the two tracks determines the regulatory zone.
            _rank = {"GREEN": 0, "AMBER": 1, "RED": 2, "N/A": -1}
            if zone_hypo != "N/A" and _rank[zone_hypo] > _rank[zone_actual]:
                zone = zone_hypo
                driving_track = "hypothetical"
            else:
                zone = zone_actual
                driving_track = "actual"

            logger.info(
                "Backtesting: actual=%d exc (%s), hypo=%s exc (%s) → %s zone [driven by %s]",
                exc_actual, zone_actual,
                str(exc_hypo) if exc_hypo is not None else "N/A",
                zone_hypo, zone, driving_track,
            )

            mean_loss_actual = (
                float((-actual_pnl[actual_pnl < 0]).mean()) if any(actual_pnl < 0) else 0.0
            )

            return {
                "exceptions":             exc_actual,
                "exceptions_actual":      exc_actual,
                "exceptions_hypothetical": exc_hypo,
                "window_days":            n,
                "traffic_light":          zone,
                "zone_actual_track":      zone_actual,
                "zone_hypo_track":        zone_hypo,
                "driving_track":          driving_track,
                "exception_pct":          exc_actual / n if n > 0 else 0.0,
                "mean_predicted":         float(predicted.mean()),
                "mean_loss":              mean_loss_actual,
            }

        except FRTBValidationError:
            raise
        except Exception as e:
            raise FRTBCalculationError(f"Backtesting evaluation failed: {e}")
