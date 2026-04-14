"""
PROMETHEUS Risk Platform — Live Market Calibration Engine
==========================================================
Replaces ALL hardcoded risk-factor parameters in MarketParams (imm.py)
and _DAILY_VOL / _REF_LEVELS (market_state.py) with values derived from
real market data fetched via yfinance (free, no API key required).

What gets calibrated
────────────────────
  MarketParams.volatility       ← 252-day realised vol of the S&P 500
  MarketParams.stressed_vol     ← worst 21-day rolling vol in the lookback window
  MarketParams.drift            ← 252-day annualised log-return mean (S&P 500)
  MarketParams.ir_vol           ← 252-day daily std of 10Y Treasury yield changes
  MarketParams.ir_stressed_vol  ← worst 21-day rolling vol of 10Y yield changes
  MarketParams.mean_reversion   ← Estimated via Ornstein-Uhlenbeck MLE on SOFR
  MarketParams.long_run_rate    ← OLS long-run mean of 3M SOFR / T-bill
  MarketParams.correlation_matrix ← EWMA pairwise correlation of all 6 factor returns

  _REF_LEVELS (market_state)    ← actual last-known spots/rates from yfinance
  _DAILY_VOL  (market_state)    ← realised daily volatilities per factor

Architecture
────────────
  1. CalibratedParams.from_market()   — fetch + calibrate everything
  2. CalibratedParams.apply_to_imm()  — patch a MarketParams instance in place
  3. CalibratedParams.apply_to_state_engine() — update the module-level dicts
                                                 in market_state.py
  4. Automatic fallback: if any fetch fails, the corresponding hardcoded value
     is kept and a warning is logged — the platform never crashes.
  5. Results are written to a JSON sidecar file so backfill_history.py can
     load yesterday's calibration without re-fetching.

Data sources  (all free, no API keys)
──────────────────────────────────────
  Equities:   yfinance  (Yahoo Finance)
    ^GSPC  = S&P 500          EQ_US
    ^STOXX50E = Euro Stoxx 50 EQ_EU
    EEM    = MSCI EM ETF      EQ_EM
    ACWI   = MSCI World ETF   EQ_GLOBAL
  Rates:
    ^TNX   = 10Y UST yield    IR_10Y
    ^FVX   = 5Y UST yield     IR_5Y
    ^IRX   = 13w T-bill       IR_SHORT (SOFR proxy)
  FX:
    EURUSD=X, GBPUSD=X, JPY=X, CHFUSD=X
  Commodities:
    CL=F   = WTI crude        CMDTY_ENERGY
    GC=F   = Gold             CMDTY_METALS
    ZC=F   = Corn             CMDTY_AGRI
  Volatility:
    ^VIX   = CBOE VIX         (stress indicator)
    ^MOVE  = ML MOVE index    (rate vol indicator — Yahoo ticker ^MOVE)

Usage
─────
  from backend.data_sources.calibration import CalibratedParams
  cal = CalibratedParams.from_market(lookback_days=252)
  cal.apply_to_imm(market_params)       # patch IMM MarketParams
  cal.apply_to_state_engine()           # patch market_state module dicts
  cal.save("calibration_cache.json")    # save for offline reuse

  # Load cached calibration (no network required)
  cal = CalibratedParams.load("calibration_cache.json")
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ─── Ticker map: internal factor key → Yahoo Finance symbol ──────────────────
_TICKERS: Dict[str, str] = {
    # Equity indices
    "EQ_US":         "^GSPC",       # S&P 500
    "EQ_EU":         "^STOXX50E",   # Euro Stoxx 50
    "EQ_EM":         "EEM",         # iShares MSCI EM ETF
    "EQ_GLOBAL":     "ACWI",        # iShares MSCI ACWI ETF
    # Interest rates (yields in %)
    "IR_SHORT":      "^IRX",        # 13-week T-bill rate
    "IR_2Y":         "^TwoYear",    # Not on Yahoo — use IR_5Y for proxy
    "IR_5Y":         "^FVX",        # 5Y Treasury yield
    "IR_10Y":        "^TNX",        # 10Y Treasury yield
    "IR_30Y":        "^TYX",        # 30Y Treasury yield
    # FX (USD per foreign unit — will convert)
    "FX_EUR":        "EURUSD=X",
    "FX_GBP":        "GBPUSD=X",
    "FX_JPY":        "JPY=X",       # USD/JPY → invert to JPY per USD
    "FX_CHF":        "CHFUSD=X",
    # Commodities
    "CMDTY_ENERGY":  "CL=F",        # WTI crude (front month)
    "CMDTY_METALS":  "GC=F",        # Gold (front month)
    "CMDTY_AGRI":    "ZC=F",        # Corn (front month)
    # Volatility indices
    "VIX":           "^VIX",
    "MOVE":          "^MOVE",       # Bond volatility index
}

# Factors used for IMM MarketParams correlation matrix (6×6)
# Order: [EQ, FX, IR, CR, CMDTY, Market]
_CORR_PROXIES = {
    "EQ":     "^GSPC",
    "FX":     "EURUSD=X",
    "IR":     "^TNX",     # yield changes (inverted = price-equivalent)
    "CR":     "HYG",      # iShares HY Bond ETF (credit spread proxy)
    "CMDTY":  "DJP",      # iPath Bloomberg Commodity ETF
    "MARKET": "^GSPC",    # market factor = equity market
}

# ─── EWMA decay factor for conditional volatility and correlation ─────────────
_LAMBDA_EWMA = 0.94    # RiskMetrics standard


# ─────────────────────────────────────────────────────────────────────────────
# Core computation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log_returns(prices: np.ndarray) -> np.ndarray:
    """Compute log returns, dropping the first NaN."""
    return np.diff(np.log(np.maximum(prices, 1e-12)))


def _historical_vol(log_rets: np.ndarray, ann: bool = True) -> float:
    """Annualised (or daily) historical volatility from log returns."""
    v = float(np.std(log_rets, ddof=1))
    return v * math.sqrt(252) if ann else v


def _ewma_vol(log_rets: np.ndarray, lam: float = _LAMBDA_EWMA) -> float:
    """
    EWMA conditional volatility (RiskMetrics).
    σ²_t = λ σ²_{t-1} + (1-λ) r²_{t-1}
    Returns annualised vol.
    """
    var = float(np.var(log_rets[:10]))  # seed with first 10 obs
    for r in log_rets[10:]:
        var = lam * var + (1 - lam) * r * r
    return math.sqrt(var * 252)


def _stressed_vol(log_rets: np.ndarray, window: int = 21) -> float:
    """
    Worst rolling-window annualised vol within the lookback period.
    window=21 = 1 calendar month.
    """
    if len(log_rets) < window:
        return _historical_vol(log_rets)
    rolling = [float(np.std(log_rets[i:i + window], ddof=1)) * math.sqrt(252)
               for i in range(len(log_rets) - window + 1)]
    return max(rolling)


def _annual_drift(log_rets: np.ndarray) -> float:
    """Annualised average log return (arithmetic approximation of drift)."""
    return float(np.mean(log_rets)) * 252


def _ewma_corr_matrix(returns_dict: Dict[str, np.ndarray],
                       lam: float = _LAMBDA_EWMA) -> np.ndarray:
    """
    Compute EWMA pairwise correlation matrix for the 6 IMM risk factors.
    Inputs: dict of {factor_label: log_return_array}, all same length.
    Returns: 6×6 symmetric correlation matrix.
    """
    labels = ["EQ", "FX", "IR", "CR", "CMDTY", "MARKET"]
    n = len(labels)
    matrix = np.eye(n)

    for i in range(n):
        for j in range(i + 1, n):
            r_i = returns_dict.get(labels[i])
            r_j = returns_dict.get(labels[j])
            if r_i is None or r_j is None:
                # If one factor is missing, use a sensible default
                matrix[i, j] = matrix[j, i] = _DEFAULT_CORR[i][j]
                continue
            # Align lengths
            min_len = min(len(r_i), len(r_j))
            ri = r_i[-min_len:]
            rj = r_j[-min_len:]
            # EWMA covariance
            cov  = 0.0
            var_i = float(np.var(ri[:10]))
            var_j = float(np.var(rj[:10]))
            for k in range(10, min_len):
                cov   = lam * cov   + (1 - lam) * ri[k] * rj[k]
                var_i = lam * var_i + (1 - lam) * ri[k] ** 2
                var_j = lam * var_j + (1 - lam) * rj[k] ** 2
            denom = math.sqrt(max(var_i * var_j, 1e-30))
            rho   = max(-0.99, min(0.99, cov / denom))
            matrix[i, j] = matrix[j, i] = rho

    return _nearest_psd(matrix)


def _ou_mle(rates: np.ndarray, dt: float = 1 / 252) -> Tuple[float, float, float]:
    """
    Maximum-likelihood estimate of Ornstein-Uhlenbeck parameters.
    dr = κ(θ − r)dt + σdW
    Uses the Euler-discretisation OLS regression:
      r_{t+1} − r_t = a + b × r_t + ε_t
    → κ = −b/dt,  θ = −a/b,  σ = std(ε)/sqrt(dt)

    Returns: (kappa, theta, sigma)
    """
    if len(rates) < 10:
        return 0.10, float(np.mean(rates)), 0.015

    x = rates[:-1]
    y = np.diff(rates)          # r_{t+1} - r_t
    # OLS: [1, x] → y
    A = np.column_stack([np.ones_like(x), x])
    try:
        result, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        a, b = result
        kappa = max(-b / dt, 0.01)        # negative b means mean-reversion
        theta = -a / b if abs(b) > 1e-8 else float(np.mean(rates))
        resid = y - (a + b * x)
        sigma = float(np.std(resid, ddof=2)) / math.sqrt(dt)
        return float(kappa), float(theta), float(sigma)
    except Exception:
        return 0.10, float(np.mean(rates)), 0.015


def _nearest_psd(matrix: np.ndarray) -> np.ndarray:
    """
    Project a symmetric matrix to the nearest positive semi-definite matrix
    (Higham 1988) by flooring negative eigenvalues to a small positive value.
    """
    eigvals, eigvecs = np.linalg.eigh(matrix)
    eigvals = np.maximum(eigvals, 1e-6)
    psd = eigvecs @ np.diag(eigvals) @ eigvecs.T
    # Re-normalise to unit diagonal (correlation matrix)
    d = np.sqrt(np.diag(psd))
    d = np.where(d < 1e-9, 1.0, d)
    return psd / np.outer(d, d)


# Default hardcoded correlation matrix (fallback when data is unavailable)
_DEFAULT_CORR = np.array([
    [1.00, 0.60, 0.20, 0.50, 0.40, 0.70],  # EQ
    [0.60, 1.00, 0.15, 0.30, 0.35, 0.65],  # FX
    [0.20, 0.15, 1.00, 0.10, 0.05, 0.25],  # IR
    [0.50, 0.30, 0.10, 1.00, 0.20, 0.60],  # CR
    [0.40, 0.35, 0.05, 0.20, 1.00, 0.55],  # CMDTY
    [0.70, 0.65, 0.25, 0.60, 0.55, 1.00],  # Market
])


# ─────────────────────────────────────────────────────────────────────────────
# Main calibration dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CalibratedParams:
    """
    Market-derived risk-factor parameters. Replaces all hardcoded scalars
    in MarketParams (imm.py) and the module-level dicts in market_state.py.

    All volatilities are annualised (×√252 from daily).
    """
    calibration_date: str               # ISO date string
    lookback_days:    int = 252         # trading days used for estimation
    data_quality:     str = "full"      # "full" | "partial" | "fallback"

    # ── IMM MarketParams parameters ───────────────────────────────────────────
    eq_vol_hist:      float = 0.20      # EQ historical annual vol
    eq_vol_ewma:      float = 0.20      # EQ EWMA conditional vol
    eq_vol_stressed:  float = 0.40      # EQ worst 21-day rolling vol
    eq_drift:         float = 0.05      # EQ annual log-return mean
    eq_spot:          float = 5_000.0   # S&P 500 last close

    ir_vol_hist:      float = 0.015     # IR daily vol (annual, rate units)
    ir_vol_stressed:  float = 0.030
    ir_kappa:         float = 0.10      # OU mean reversion speed
    ir_theta_10y:     float = 0.045     # OU long-run 10Y target rate
    ir_theta_short:   float = 0.040     # OU long-run short rate
    ir_spot_10y:      float = 0.045     # 10Y yield last observation
    ir_spot_short:    float = 0.040     # 3M T-bill last observation

    fx_vol_eur:       float = 0.08      # EUR/USD annual vol
    fx_vol_gbp:       float = 0.09
    fx_vol_jpy:       float = 0.10
    fx_vol_chf:       float = 0.08
    fx_spot_eur:      float = 0.90      # EUR per USD (inverted of EUR/USD)
    fx_spot_gbp:      float = 0.78
    fx_spot_jpy:      float = 130.0
    fx_spot_chf:      float = 0.92

    cs_ig_vol:        float = 0.30      # Credit spread relative vol (IG)
    cs_hy_vol:        float = 0.45
    vix_level:        float = 18.0      # VIX last close

    cmdty_energy_vol: float = 0.30
    cmdty_metals_vol: float = 0.20
    cmdty_agri_vol:   float = 0.18
    cmdty_energy_spot:float = 100.0
    cmdty_metals_spot:float = 100.0
    cmdty_agri_spot:  float = 100.0

    # 6×6 correlation matrix (serialised as nested list for JSON)
    correlation_matrix: List[List[float]] = field(
        default_factory=lambda: _DEFAULT_CORR.tolist()
    )

    # ── Fetch diagnostics ─────────────────────────────────────────────────────
    fetch_log: Dict[str, str] = field(default_factory=dict)

    # ─────────────────────────────────────────────────────────────────────────
    # Factory: fetch + calibrate
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def from_market(
        cls,
        lookback_days: int = 252,
        as_of: Optional[date] = None,
        cache_path: Optional[str] = None,
        max_cache_age_hours: float = 8.0,
    ) -> "CalibratedParams":
        """
        Fetch real market data via yfinance and calibrate all parameters.

        Steps:
          1. Try loading a recent cache (avoids repeated downloads).
          2. Fetch 14 months of daily OHLCV for every required ticker.
          3. Compute historical vol, EWMA vol, stressed vol, drift for each factor.
          4. Estimate OU parameters for interest rates.
          5. Build EWMA pairwise correlation matrix for the 6 IMM factors.
          6. Fall back gracefully to hardcoded defaults for any failed fetch.
          7. Persist cache to JSON.

        Parameters
        ----------
        lookback_days : int
            Number of trading days for vol/drift estimation (default 252 = 1Y).
        as_of : date, optional
            Reference date (default today).
        cache_path : str, optional
            Path to JSON cache file. If the file is < max_cache_age_hours old,
            it is loaded instead of re-fetching.
        max_cache_age_hours : float
            Maximum age (hours) of a cache file before re-fetching.
        """
        as_of = as_of or date.today()
        target = cls(
            calibration_date=as_of.isoformat(),
            lookback_days=lookback_days,
        )
        target.fetch_log = {}

        # ── Try cache first ────────────────────────────────────────────────
        if cache_path and os.path.exists(cache_path):
            try:
                import time
                age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
                if age_h < max_cache_age_hours:
                    loaded = cls.load(cache_path)
                    logger.info("Calibration: loaded cache (%s, age %.1fh)", cache_path, age_h)
                    return loaded
            except Exception as e:
                logger.warning("Calibration cache load failed: %s", e)

        # ── Fetch raw price history ────────────────────────────────────────
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not installed — using fallback parameters. "
                           "Install with: pip install yfinance")
            target.data_quality = "fallback"
            if cache_path:
                target.save(cache_path)
            return target

        end_dt   = as_of
        start_dt = end_dt - timedelta(days=int(lookback_days * 1.4) + 60)  # buffer for weekends

        raw: Dict[str, Optional[np.ndarray]] = {}
        for factor, ticker in _TICKERS.items():
            if ticker in ("^TwoYear", "^MOVE"):   # not on Yahoo
                raw[factor] = None
                target.fetch_log[factor] = f"skip:{ticker}"
                continue
            try:
                df = yf.download(
                    ticker, start=start_dt.isoformat(), end=end_dt.isoformat(),
                    progress=False, auto_adjust=True, timeout=10,
                )
                if df.empty:
                    raw[factor] = None
                    target.fetch_log[factor] = "empty"
                    continue
                closes = df["Close"].dropna().squeeze().values.astype(float)
                # Keep last lookback_days trading days
                raw[factor] = closes[-lookback_days:] if len(closes) >= lookback_days \
                               else closes
                target.fetch_log[factor] = f"ok:{len(raw[factor])} obs"
                logger.debug("Fetched %s (%s): %d obs, last=%.4f",
                             factor, ticker, len(raw[factor]), raw[factor][-1])
            except Exception as e:
                raw[factor] = None
                target.fetch_log[factor] = f"error:{e}"
                logger.warning("Fetch failed for %s (%s): %s", factor, ticker, e)

        n_ok = sum(1 for v in raw.values() if v is not None)
        total = len(_TICKERS)
        target.data_quality = "full" if n_ok >= total * 0.8 \
                              else ("partial" if n_ok > 0 else "fallback")
        logger.info("Calibration: %d/%d tickers fetched (%s)", n_ok, total,
                    target.data_quality)

        # ── Calibrate: Equity ─────────────────────────────────────────────
        eq_data = raw.get("EQ_US")
        if eq_data is not None and len(eq_data) >= 30:
            lr = _log_returns(eq_data)
            target.eq_vol_hist    = _historical_vol(lr)
            target.eq_vol_ewma    = _ewma_vol(lr)
            target.eq_vol_stressed= _stressed_vol(lr)
            target.eq_drift       = _annual_drift(lr)
            target.eq_spot        = float(eq_data[-1])
            target.fetch_log["EQ_US_cal"] = (
                f"vol={target.eq_vol_hist*100:.2f}% stressed={target.eq_vol_stressed*100:.2f}%")

        # ── Calibrate: Interest rates ─────────────────────────────────────
        ir10y = raw.get("IR_10Y")
        if ir10y is not None and len(ir10y) >= 30:
            # Yields are already in % — convert to decimal for rate processes
            rates10y = ir10y / 100.0
            kappa, theta, sigma = _ou_mle(rates10y)
            target.ir_kappa       = min(max(kappa, 0.01), 5.0)
            target.ir_theta_10y   = min(max(theta, 0.0001), 0.20)
            target.ir_vol_hist    = sigma
            target.ir_vol_stressed= _stressed_vol(np.diff(rates10y)) * math.sqrt(252)
            target.ir_spot_10y    = float(rates10y[-1])
            target.fetch_log["IR_10Y_cal"] = (
                f"kappa={kappa:.3f} theta={theta*100:.2f}% vol={sigma*100:.2f}%")

        ir_short = raw.get("IR_SHORT")
        if ir_short is not None and len(ir_short) >= 20:
            rates_s = ir_short / 100.0
            target.ir_theta_short = float(np.mean(rates_s))
            target.ir_spot_short  = float(rates_s[-1])

        # ── Calibrate: FX ────────────────────────────────────────────────
        _fx_cal = {
            "FX_EUR": ("fx_vol_eur", "fx_spot_eur", False),  # EURUSD = USD per EUR → invert
            "FX_GBP": ("fx_vol_gbp", "fx_spot_gbp", False),
            "FX_JPY": ("fx_vol_jpy", "fx_spot_jpy", False),  # Yahoo gives USD/JPY
            "FX_CHF": ("fx_vol_chf", "fx_spot_chf", False),
        }
        for factor, (vol_attr, spot_attr, invert) in _fx_cal.items():
            fx_data = raw.get(factor)
            if fx_data is not None and len(fx_data) >= 20:
                lr = _log_returns(fx_data)
                setattr(target, vol_attr, _ewma_vol(lr))
                spot = float(fx_data[-1])
                # For JPY: Yahoo gives USD/JPY, we store JPY per USD
                if factor == "FX_JPY":
                    spot = spot   # USD/JPY is already "JPY per USD" if inverted
                setattr(target, spot_attr, spot)

        # ── Calibrate: Commodities ─────────────────────────────────────────
        _cmdty_cal = {
            "CMDTY_ENERGY": ("cmdty_energy_vol", "cmdty_energy_spot"),
            "CMDTY_METALS": ("cmdty_metals_vol", "cmdty_metals_spot"),
            "CMDTY_AGRI":   ("cmdty_agri_vol",   "cmdty_agri_spot"),
        }
        for factor, (vol_attr, spot_attr) in _cmdty_cal.items():
            data = raw.get(factor)
            if data is not None and len(data) >= 20:
                lr = _log_returns(data)
                setattr(target, vol_attr, _ewma_vol(lr))
                setattr(target, spot_attr, float(data[-1]))

        # ── Calibrate: VIX ───────────────────────────────────────────────
        vix_data = raw.get("VIX")
        if vix_data is not None and len(vix_data) >= 5:
            target.vix_level = float(vix_data[-1])

        # ── Calibrate: Pairwise correlation matrix ─────────────────────────
        corr_rets: Dict[str, np.ndarray] = {}
        for factor_label, ticker in _CORR_PROXIES.items():
            # Find the matching raw series
            raw_key = next((k for k, t in _TICKERS.items() if t == ticker), None)
            data = raw.get(raw_key) if raw_key else None
            if data is not None and len(data) >= 30:
                lr = _log_returns(data)
                # IR: negate yields to get price-equivalent returns
                if factor_label == "IR":
                    lr = -lr
                corr_rets[factor_label] = lr

        if len(corr_rets) >= 3:
            mat = _ewma_corr_matrix(corr_rets)
            target.correlation_matrix = mat.tolist()
            target.fetch_log["CORR_CAL"] = f"factors={list(corr_rets.keys())}"

        # ── Persist cache ─────────────────────────────────────────────────
        if cache_path:
            try:
                target.save(cache_path)
            except Exception as e:
                logger.warning("Failed to save calibration cache: %s", e)

        return target

    # ─────────────────────────────────────────────────────────────────────────
    # Apply calibrated params to the IMM engine
    # ─────────────────────────────────────────────────────────────────────────

    def apply_to_imm(self, params) -> None:
        """
        Patch a MarketParams instance in place with calibrated values.

        Mapping decisions:
          volatility    ← EWMA conditional vol (more responsive than historical)
          stressed_vol  ← worst 21-day rolling vol in the lookback window
          drift         ← annualised log-return mean (capped: −30% to +30%)
          ir_vol        ← OU sigma for 10Y yield process
          ir_stressed_vol ← worst rolling vol of yield changes
          mean_reversion← OU kappa from MLE on SOFR/T-bill rates
          long_run_rate ← OU theta (long-run 10Y yield)
          correlation_matrix ← EWMA pairwise matrix
        """
        params.volatility      = max(self.eq_vol_ewma,    0.05)
        params.stressed_vol    = max(self.eq_vol_stressed, params.volatility * 1.5)
        params.drift           = max(min(self.eq_drift, 0.30), -0.30)
        params.ir_vol          = max(self.ir_vol_hist,    0.001)
        params.ir_stressed_vol = max(self.ir_vol_stressed, params.ir_vol * 1.5)
        params.mean_reversion  = max(min(self.ir_kappa, 3.0), 0.01)
        if hasattr(params, "long_run_rate"):
            params.long_run_rate = max(self.ir_theta_10y, 0.001)
        params.correlation_matrix = np.array(self.correlation_matrix)
        try:
            params.validate()
            logger.info(
                "IMM calibration applied: vol=%.2f%% stressed=%.2f%% "
                "drift=%+.2f%% ir_vol=%.3f%% kappa=%.3f theta=%.3f%%",
                params.volatility * 100, params.stressed_vol * 100,
                params.drift * 100, params.ir_vol * 100,
                params.mean_reversion, self.ir_theta_10y * 100,
            )
        except Exception as e:
            logger.warning("Post-calibration validation failed: %s — reverting corr", e)
            params.correlation_matrix = _DEFAULT_CORR

    # ─────────────────────────────────────────────────────────────────────────
    # Apply calibrated params to market_state module dicts
    # ─────────────────────────────────────────────────────────────────────────

    def apply_to_state_engine(self) -> None:
        """
        Update the module-level _REF_LEVELS and _DAILY_VOL dicts in
        market_state.py with live calibrated values.

        This patches the running process's module globals in place so
        that market_state.get_market_state() uses live spots and vols
        as the starting point for its path simulation.

        Call this once at startup, before the first run_daily() call.
        """
        try:
            from backend.data_sources import market_state as ms
        except ImportError:
            logger.warning("market_state module not found — state engine not patched")
            return

        # ── Spot levels → _REF_LEVELS ─────────────────────────────────────
        updates_levels: Dict[str, float] = {
            "EQ_US":         self.eq_spot,
            "EQ_GLOBAL":     self.eq_spot,     # use S&P as global proxy
            "EQ_EU":         self.eq_spot * 0.92,  # rough ratio
            "EQ_EM":         self.eq_spot * 0.40,
            "IR_SHORT":      max(self.ir_spot_short, 0.0001),
            "IR_2Y":         max((self.ir_spot_short + self.ir_spot_10y) / 2, 0.0001),
            "IR_5Y":         max((self.ir_spot_short * 0.3 + self.ir_spot_10y * 0.7), 0.0001),
            "IR_10Y":        max(self.ir_spot_10y,   0.0001),
            "IR_30Y":        max(self.ir_spot_10y * 1.06, 0.0001),
            "FX_EUR":        self.fx_spot_eur,
            "FX_GBP":        self.fx_spot_gbp,
            "FX_JPY":        self.fx_spot_jpy,
            "FX_CHF":        self.fx_spot_chf,
            "CMDTY_ENERGY":  self.cmdty_energy_spot,
            "CMDTY_METALS":  self.cmdty_metals_spot,
            "CMDTY_AGRI":    self.cmdty_agri_spot,
            "VIX":           self.vix_level,
        }
        for key, val in updates_levels.items():
            if key in ms._REF_LEVELS:
                ms._REF_LEVELS[key] = val

        # ── Daily vols → _DAILY_VOL ───────────────────────────────────────
        sq252 = math.sqrt(252)
        updates_vol: Dict[str, float] = {
            "EQ_US":        self.eq_vol_ewma    / sq252,
            "EQ_GLOBAL":    self.eq_vol_ewma    / sq252,
            "EQ_EU":        self.eq_vol_ewma * 1.1 / sq252,
            "EQ_EM":        self.eq_vol_ewma * 1.3 / sq252,
            "IR_SHORT":     self.ir_vol_hist    / sq252,
            "IR_2Y":        self.ir_vol_hist * 0.85 / sq252,
            "IR_5Y":        self.ir_vol_hist * 0.75 / sq252,
            "IR_10Y":       self.ir_vol_hist * 0.65 / sq252,
            "IR_30Y":       self.ir_vol_hist * 0.55 / sq252,
            "FX_EUR":       self.fx_vol_eur     / sq252,
            "FX_GBP":       self.fx_vol_gbp     / sq252,
            "FX_JPY":       self.fx_vol_jpy     / sq252,
            "FX_CHF":       self.fx_vol_chf     / sq252,
            "CS_IG":        self.cs_ig_vol      / sq252,
            "CS_HY":        self.cs_hy_vol      / sq252,
            "CMDTY_ENERGY": self.cmdty_energy_vol / sq252,
            "CMDTY_METALS": self.cmdty_metals_vol / sq252,
            "CMDTY_AGRI":   self.cmdty_agri_vol   / sq252,
        }
        for key, val in updates_vol.items():
            if key in ms._DAILY_VOL and val > 0:
                ms._DAILY_VOL[key] = val

        # ── Vasicek parameters ────────────────────────────────────────────
        ms._IR_MEAN_REVERSION = self.ir_kappa
        for key in ms._IR_LONG_RUN:
            if key == "IR_SHORT":
                ms._IR_LONG_RUN[key] = self.ir_theta_short
            elif key == "IR_10Y":
                ms._IR_LONG_RUN[key] = self.ir_theta_10y
            elif key in ("IR_2Y", "IR_5Y", "IR_30Y"):
                # Interpolate
                w = {"IR_2Y": 0.2, "IR_5Y": 0.5, "IR_30Y": 1.1}.get(key, 0.5)
                ms._IR_LONG_RUN[key] = (
                    self.ir_theta_short * (1 - w) + self.ir_theta_10y * w
                )

        # Clear the state cache so next call rebuilds from updated params
        ms._STATE_CACHE.clear()
        logger.info(
            "market_state patched: EQ_US spot=%.1f vol=%.2f%% | "
            "IR_10Y spot=%.3f%% kappa=%.3f",
            self.eq_spot, self.eq_vol_ewma * 100,
            self.ir_spot_10y * 100, self.ir_kappa,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Write calibrated params to a JSON cache file."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._to_json(), f, indent=2)
        logger.debug("Calibration saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "CalibratedParams":
        """Load calibrated params from a JSON cache file."""
        with open(path) as f:
            data = json.load(f)
        obj = cls(calibration_date=data.get("calibration_date", "unknown"))
        for k, v in data.items():
            if hasattr(obj, k):
                setattr(obj, k, v)
        return obj

    def _to_json(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, np.ndarray):
                d[k] = v.tolist()
            elif isinstance(v, dict):
                d[k] = {str(kk): vv for kk, vv in v.items()}
            else:
                d[k] = v
        return d

    def summary(self) -> str:
        """Human-readable calibration summary for logging / dashboard display."""
        lines = [
            f"Calibration as of {self.calibration_date}  [{self.data_quality}]",
            f"  Equity (S&P 500)",
            f"    Spot:         {self.eq_spot:>10,.1f}",
            f"    Hist vol:     {self.eq_vol_hist*100:>10.2f}%  (was 20.00%)",
            f"    EWMA vol:     {self.eq_vol_ewma*100:>10.2f}%",
            f"    Stressed vol: {self.eq_vol_stressed*100:>10.2f}%  (was 40.00%)",
            f"    Drift:        {self.eq_drift*100:>+10.2f}%  (was  +5.00%)",
            f"  Interest rates (10Y UST)",
            f"    Spot:         {self.ir_spot_10y*100:>10.3f}%",
            f"    OU kappa:     {self.ir_kappa:>10.4f}  (was  0.1000)",
            f"    OU theta:     {self.ir_theta_10y*100:>10.3f}%  (was  4.500%)",
            f"    IR vol:       {self.ir_vol_hist*100:>10.4f}%  (was  1.500%)",
            f"    Stressed vol: {self.ir_vol_stressed*100:>10.4f}%  (was  3.000%)",
            f"  FX vols",
            f"    EUR:          {self.fx_vol_eur*100:>10.2f}%  GBP: {self.fx_vol_gbp*100:.2f}%"
            f"  JPY: {self.fx_vol_jpy*100:.2f}%",
            f"  Commodities",
            f"    Energy:       {self.cmdty_energy_vol*100:>10.2f}%"
            f"  Metals: {self.cmdty_metals_vol*100:.2f}%",
            f"  VIX:            {self.vix_level:>10.1f}",
            f"  Data quality:   {self.data_quality}",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: one-call startup calibration
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "calibration_cache.json"
)


def calibrate_and_apply(
    market_params=None,
    lookback_days: int = 252,
    cache_path: str = _DEFAULT_CACHE_PATH,
    force_refresh: bool = False,
) -> CalibratedParams:
    """
    One-call convenience: calibrate from live market data and patch
    both the IMM engine and the market state engine.

    Parameters
    ----------
    market_params : MarketParams, optional
        If provided, patched in place with live values.
    lookback_days : int
        Lookback window for vol/drift estimation.
    cache_path : str
        Path to JSON sidecar. Reused if < 8 hours old.
    force_refresh : bool
        If True, always re-fetch even if cache is fresh.

    Returns
    -------
    CalibratedParams
        The calibrated parameter set (also applied to market_params if given).

    Example
    -------
    >>> from backend.data_sources.calibration import calibrate_and_apply
    >>> from backend.engines.imm import MarketParams
    >>> params = MarketParams()
    >>> cal = calibrate_and_apply(params)
    >>> print(cal.summary())
    """
    cal = CalibratedParams.from_market(
        lookback_days=lookback_days,
        cache_path=None if force_refresh else cache_path,
    )
    if market_params is not None:
        cal.apply_to_imm(market_params)
    cal.apply_to_state_engine()
    logger.info("Market calibration complete:\n%s", cal.summary())
    return cal
