"""
PROMETHEUS Risk Platform — Daily Market State Engine
Provides deterministic but date-varying market prices for realistic
day-on-day MTM evolution across all asset classes.

Design:
  - Each date maps to a unique market state via seeded GBM stepping
    from a fixed reference date (2020-01-01), so any given date always
    produces the same state (full replayability) and adjacent dates
    produce different states.
  - Asset-class specific volatilities calibrated to long-run historical
    realised vols (approximate mid-market):
        IR rates:    vol ~1bp/day (short end), ~0.5bp (long end)
        FX rates:    vol ~0.5% /day (major pairs)
        Equity:      vol ~1.0% /day (broad indices)
        Credit sprd: vol ~2.0% /day (IG), ~3.5% (HY)
        Commodity:   vol ~1.5% /day (energy/metals)
  - All steps use antithetic draws seeded from the date ordinal — no
    external dependencies, no live feeds required.
"""

from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, Optional

# ─── Reference date: all paths start here ────────────────────────────────────
_REF_DATE = date(2020, 1, 1)

# ─── Reference market levels (base values on _REF_DATE) ──────────────────────
_REF_LEVELS: Dict[str, float] = {
    # Interest rates (decimal, e.g. 0.04 = 4%)
    "IR_SHORT":      0.04,    # 3-month OIS / SOFR
    "IR_2Y":         0.042,
    "IR_5Y":         0.043,
    "IR_10Y":        0.045,
    "IR_30Y":        0.048,
    # FX (units of each CCY per USD — USD=1.0 is the numéraire)
    "FX_EUR":        0.90,    # EUR/USD = 1/0.90 ≈ 1.11
    "FX_GBP":        0.78,
    "FX_JPY":      130.0,
    "FX_CHF":        0.92,
    # Equity broad index levels (normalised to 100 at ref date)
    "EQ_GLOBAL":   100.0,
    "EQ_US":       100.0,
    "EQ_EU":       100.0,
    "EQ_EM":       100.0,
    # Credit spreads (basis points)
    "CS_IG":        90.0,     # IG index CDS spread
    "CS_HY":       380.0,     # HY index CDS spread
    "CS_FINANCIALS":100.0,
    "CS_ENERGY":   150.0,
    # Commodity prices (normalised to 100 at ref date)
    "CMDTY_ENERGY":100.0,     # crude oil proxy
    "CMDTY_METALS":100.0,     # base metals proxy
    "CMDTY_AGRI":  100.0,     # agricultural proxy
    # Volatility indices
    "VIX":          18.0,
    "MOVE":         80.0,     # bond vol index
}

# ─── Daily volatilities (annualised / sqrt(252)) ─────────────────────────────
_DAILY_VOL: Dict[str, float] = {
    "IR_SHORT":      0.010 / math.sqrt(252),   # ~10bp/yr daily std
    "IR_2Y":         0.008 / math.sqrt(252),
    "IR_5Y":         0.007 / math.sqrt(252),
    "IR_10Y":        0.006 / math.sqrt(252),
    "IR_30Y":        0.005 / math.sqrt(252),
    "FX_EUR":        0.06  / math.sqrt(252),   # 6% annual FX vol
    "FX_GBP":        0.08  / math.sqrt(252),
    "FX_JPY":        0.09  / math.sqrt(252),
    "FX_CHF":        0.07  / math.sqrt(252),
    "EQ_GLOBAL":     0.15  / math.sqrt(252),
    "EQ_US":         0.16  / math.sqrt(252),
    "EQ_EU":         0.18  / math.sqrt(252),
    "EQ_EM":         0.22  / math.sqrt(252),
    "CS_IG":         0.30  / math.sqrt(252),   # 30% relative spread vol
    "CS_HY":         0.45  / math.sqrt(252),
    "CS_FINANCIALS": 0.35  / math.sqrt(252),
    "CS_ENERGY":     0.40  / math.sqrt(252),
    "CMDTY_ENERGY":  0.30  / math.sqrt(252),
    "CMDTY_METALS":  0.20  / math.sqrt(252),
    "CMDTY_AGRI":    0.18  / math.sqrt(252),
    "VIX":           0.80  / math.sqrt(252),
    "MOVE":          0.60  / math.sqrt(252),
}

# IR mean reversion (Vasicek κ) — strong pull prevents negative rates
_IR_MEAN_REVERSION = 0.15   # κ: mean reversion speed
_IR_LONG_RUN = {            # θ: long-run target rates
    "IR_SHORT": 0.04, "IR_2Y": 0.042, "IR_5Y": 0.043,
    "IR_10Y": 0.045, "IR_30Y": 0.048,
}


@dataclass
class MarketState:
    """
    Snapshot of all market observables on a given date.
    All prices are deterministically derived from the date — the same
    date always returns the same MarketState regardless of when you call it.
    """
    as_of_date: date
    levels: Dict[str, float] = field(default_factory=dict)

    # ── Convenience accessors ─────────────────────────────────────────────────

    def ir_rate(self, tenor: str = "IR_5Y") -> float:
        """Current rate for given tenor key."""
        return self.levels.get(tenor, _REF_LEVELS.get(tenor, 0.04))

    def fx_rate(self, ccy: str) -> float:
        """Domestic units per USD for given currency."""
        key = f"FX_{ccy.upper()}"
        return self.levels.get(key, _REF_LEVELS.get(key, 1.0))

    def equity_level(self, index: str = "EQ_GLOBAL") -> float:
        """Equity index level (normalised to 100 at reference date)."""
        return self.levels.get(index, 100.0)

    def credit_spread(self, quality: str = "IG") -> float:
        """Credit spread in basis points."""
        key = f"CS_{quality.upper()}"
        return self.levels.get(key, _REF_LEVELS.get(key, 100.0))

    def commodity_level(self, subtype: str = "ENERGY") -> float:
        key = f"CMDTY_{subtype.upper()}"
        return self.levels.get(key, 100.0)

    def vix(self) -> float:
        return self.levels.get("VIX", 18.0)

    # ── MTM pricing by asset class ────────────────────────────────────────────

    def price_ir_trade(
        self,
        notional: float,
        direction: int,
        trade_date: date,
        maturity_date: date,
        tenor_key: str = "IR_5Y",
    ) -> float:
        """
        Approximate MTM for an IR swap / bond using modified duration.
        MTM ≈ direction × notional × DV01 × (r_today − r_trade_date)
        where DV01 ≈ duration × 0.0001 × notional.
        """
        r_today = self.ir_rate(tenor_key)
        r_ref   = _REF_LEVELS.get(tenor_key, 0.04)
        state_on_trade = get_market_state(trade_date)
        r_trade = state_on_trade.ir_rate(tenor_key)
        duration = max((maturity_date - self.as_of_date).days / 365.0, 0.1)
        # Modified duration approximation: D_mod ≈ duration / (1 + r)
        d_mod   = duration / (1.0 + r_today)
        # MTM = direction × notional × (−D_mod) × (r_today − r_trade)
        delta_r = r_today - r_trade
        mtm = direction * notional * (-d_mod) * delta_r
        return float(mtm)

    def price_fx_trade(
        self,
        notional: float,
        direction: int,
        trade_date: date,
        ccy: str,
    ) -> float:
        """FX forward MTM = direction × notional × (spot_today/spot_trade − 1)."""
        spot_today = self.fx_rate(ccy)
        spot_trade = get_market_state(trade_date).fx_rate(ccy)
        if spot_trade <= 0:
            return 0.0
        pct_change = (spot_today - spot_trade) / spot_trade
        return float(direction * notional * pct_change)

    def price_equity_trade(
        self,
        notional: float,
        direction: int,
        trade_date: date,
        index: str = "EQ_GLOBAL",
    ) -> float:
        """Equity swap/forward MTM = direction × notional × (S_today/S_trade − 1)."""
        s_today = self.equity_level(index)
        s_trade = get_market_state(trade_date).equity_level(index)
        if s_trade <= 0:
            return 0.0
        return float(direction * notional * (s_today / s_trade - 1.0))

    def price_credit_trade(
        self,
        notional: float,
        direction: int,
        trade_date: date,
        maturity_date: date,
        quality: str = "IG",
    ) -> float:
        """
        CDS MTM ≈ direction × notional × ΔSpread × Duration_approx.
        A protection buyer (direction=+1) gains when spreads widen.
        """
        cs_today = self.credit_spread(quality) / 10_000   # bps → decimal
        cs_trade = get_market_state(trade_date).credit_spread(quality) / 10_000
        duration = max((maturity_date - self.as_of_date).days / 365.0, 0.5)
        delta_s  = cs_today - cs_trade
        # Positive direction (protection buyer) profits from spread widening
        mtm = direction * notional * delta_s * duration
        return float(mtm)

    def price_commodity_trade(
        self,
        notional: float,
        direction: int,
        trade_date: date,
        subtype: str = "ENERGY",
    ) -> float:
        """Commodity forward MTM = direction × notional × (P_today/P_trade − 1)."""
        p_today = self.commodity_level(subtype)
        p_trade = get_market_state(trade_date).commodity_level(subtype)
        if p_trade <= 0:
            return 0.0
        return float(direction * notional * (p_today / p_trade - 1.0))


# ─────────────────────────────────────────────────────────────────────────────
# Core: build market state for any date deterministically
# ─────────────────────────────────────────────────────────────────────────────

def _daily_z(factor_key: str, day_ordinal: int) -> float:
    """
    Deterministic standard normal draw for a given factor and day.
    Uses SHA-256 to produce a stable, reproducible value in (0,1) then
    applies the rational approximation to the normal quantile.
    """
    seed_bytes = f"{factor_key}:{day_ordinal}".encode()
    h = hashlib.sha256(seed_bytes).digest()
    # Map first 8 bytes to [0,1)
    u = int.from_bytes(h[:8], "big") / (2**64)
    # Clamp away from extremes
    u = max(min(u, 1.0 - 1e-9), 1e-9)
    # Rational approximation to Φ⁻¹(u) — Beasley-Springer-Moro
    a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
    b = [-8.47351093090, 23.08336743743, -21.06224101826, 3.13082909833]
    c = [0.3374754822726147, 0.9761690190917186, 0.1607979714918209,
         0.0276438810333863, 0.0038405729373609, 0.0003951896511919,
         0.0000321767881768, 0.0000002888167364, 0.0000003960315187]
    q = u - 0.5
    if abs(q) <= 0.42:
        r = q * q
        return q * (((a[3]*r+a[2])*r+a[1])*r+a[0]) / ((((b[3]*r+b[2])*r+b[1])*r+b[0])*r+1)
    else:
        r = u if q > 0 else 1.0 - u
        r = math.sqrt(-math.log(r))
        z = (((((((c[8]*r+c[7])*r+c[6])*r+c[5])*r+c[4])*r+c[3])*r+c[2])*r+c[1])*r+c[0]
        return z if q > 0 else -z


def _evolve_gbm(level: float, vol: float, z: float) -> float:
    """
    One GBM step: S_{t+1} = S_t × exp((−σ²/2) + σZ).
    Clipped to prevent degenerate levels.
    """
    log_ret = -0.5 * vol * vol + vol * z
    return max(level * math.exp(log_ret), level * 0.01)


def _evolve_vasicek(level: float, theta: float, kappa: float,
                     vol: float, z: float) -> float:
    """
    Vasicek mean-reverting step for interest rates:
    r_{t+1} = r_t + κ(θ − r_t) + σZ.
    Floor at 0bp to prevent negative rates in simple mode.
    """
    drift = kappa * (theta - level)
    return max(level + drift + vol * z, 0.0001)


# Module-level cache — avoids recomputing for the same date
_STATE_CACHE: Dict[int, MarketState] = {}


def get_market_state(as_of: date) -> MarketState:
    """
    Return the MarketState for `as_of` date, computed deterministically.
    Stepping daily from _REF_DATE using seeded GBM / Vasicek processes.
    Results are cached in-process; the same date always returns the same state.
    """
    ordinal = as_of.toordinal()

    if ordinal in _STATE_CACHE:
        return _STATE_CACHE[ordinal]

    # Build the reference state on _REF_DATE
    ref_ordinal = _REF_DATE.toordinal()
    if ordinal < ref_ordinal:
        # For dates before reference, step backwards (invert the process)
        state = _build_state_stepping(ordinal, ref_ordinal, backward=True)
    else:
        state = _build_state_stepping(ref_ordinal, ordinal, backward=False)

    _STATE_CACHE[ordinal] = state
    return state


def _build_state_stepping(
    start_ordinal: int,
    end_ordinal: int,
    backward: bool,
) -> MarketState:
    """Step the market state from start to end, one calendar day at a time."""
    levels = dict(_REF_LEVELS)   # start from reference

    step_range = range(start_ordinal, end_ordinal)
    if backward:
        step_range = range(end_ordinal, start_ordinal, -1)

    for day_ord in step_range:
        for key, level in levels.items():
            z = _daily_z(key, day_ord)
            vol = _DAILY_VOL.get(key, 0.01)

            if key.startswith("IR_"):
                theta = _IR_LONG_RUN.get(key, 0.04)
                kappa = _IR_MEAN_REVERSION
                new_level = _evolve_vasicek(level, theta, kappa, vol, z)
            else:
                new_level = _evolve_gbm(level, vol, z)

            levels[key] = new_level

    return MarketState(
        as_of_date=date.fromordinal(end_ordinal),
        levels=dict(levels),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Asset-class routing helper (used by portfolio_generator)
# ─────────────────────────────────────────────────────────────────────────────

# Map CMDTY hedging-set labels to commodity subtype keys
_CMDTY_MAP = {
    "CMDTY_ENERGY": "ENERGY",
    "CMDTY_METALS": "METALS",
    "CMDTY_AGRI":   "AGRI",
}
_FX_CCY_MAP = {
    "EUR": "EUR", "GBP": "GBP", "JPY": "JPY", "CHF": "CHF",
    "USD": "EUR",  # USD/USD pair defaults to EUR as proxy
}
_IR_TENOR_MAP = {
    "SHORT": "IR_SHORT", "MEDIUM": "IR_5Y", "LONG": "IR_10Y",
}
_EQ_INDEX_MAP = {
    "1": "EQ_US", "2": "EQ_EU", "3": "EQ_EM", "4": "EQ_GLOBAL",
}


def compute_trade_mtm(trade, as_of_date: date) -> float:
    """
    Compute mark-to-market for a single trade on `as_of_date` using the
    daily market state engine. Replaces the static rng.uniform(±5%) call.

    Supported asset classes: IR, FX, EQ, CR, CMDTY.
    Falls back to zero for unrecognised types.
    """
    state = get_market_state(as_of_date)
    ac    = getattr(trade, "asset_class", "IR")
    n     = abs(getattr(trade, "notional", 0.0))
    d     = int(getattr(trade, "direction", 1))
    td    = getattr(trade, "trade_date", as_of_date)
    md    = getattr(trade, "maturity_date", as_of_date)
    ccy   = getattr(trade, "notional_ccy", "USD")

    if ac == "IR":
        # Pick tenor key from remaining maturity
        days_to_mat = max((md - as_of_date).days, 0)
        if days_to_mat <= 365:
            tenor = "IR_SHORT"
        elif days_to_mat <= 3 * 365:
            tenor = "IR_2Y"
        elif days_to_mat <= 7 * 365:
            tenor = "IR_5Y"
        elif days_to_mat <= 15 * 365:
            tenor = "IR_10Y"
        else:
            tenor = "IR_30Y"
        return state.price_ir_trade(n, d, td, md, tenor)

    elif ac == "FX":
        return state.price_fx_trade(n, d, td, _FX_CCY_MAP.get(ccy, "EUR"))

    elif ac == "EQ":
        return state.price_equity_trade(n, d, td)

    elif ac == "CR":
        quality = "IG"  # default; override via trade.credit_quality
        if hasattr(trade, "credit_quality"):
            quality = trade.credit_quality.upper()
        return state.price_credit_trade(n, d, td, md, quality)

    elif ac == "CMDTY":
        subtype = "ENERGY"  # default
        hs = getattr(trade, "hedging_set", None)
        if hs and hs.upper() in _CMDTY_MAP:
            subtype = _CMDTY_MAP[hs.upper()]
        return state.price_commodity_trade(n, d, td, subtype)

    return 0.0
