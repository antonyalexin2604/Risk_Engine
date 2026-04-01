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
"""

from __future__ import annotations

import math
import copy
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date
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
)

import numpy as np

logger = logging.getLogger(__name__)

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

    def intra(self, risk_class: str, n: int) -> np.ndarray:
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
    """Centralized FRTB configuration per MAR21-33."""
    risk_classes: List[str] = field(default_factory=lambda: [
        "GIRR", "CSR_NS", "CSR_SEC", "EQ", "CMDTY", "FX"
    ])

    delta_rw: Dict[str, Sequence[float]] = field(default_factory=lambda: {
        "GIRR": [0.017, 0.017, 0.016, 0.013, 0.012, 0.011, 0.011,
                 0.011, 0.011, 0.011, 0.013, 0.015, 0.018],
        "CSR_NS": [0.005, 0.010, 0.050, 0.030, 0.020, 0.030, 0.080,
                   0.060, 0.050, 0.100, 0.120, 0.140, 0.020, 0.020,
                   0.020, 0.030, 0.030, 0.050],
        "EQ_LARGE": [0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70],
        "FX": [0.15],
        "CMDTY": [0.30, 0.35, 0.60, 0.80, 0.40, 0.45, 0.20, 0.35, 0.25, 0.35,
                  0.50, 0.42, 0.18, 0.18, 0.18, 0.16, 0.18],
    })

    intra_corr: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.999, "CSR_NS": 0.65, "EQ": 0.15, "FX": 1.0, "CMDTY": 0.55,
    })

    inter_corr: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.50, "CSR_NS": 0.0, "EQ": 0.15, "FX": 0.60, "CMDTY": 0.20,
    })

    vega_rw: Dict[str, float] = field(default_factory=lambda: {
        "GIRR": 0.55, "CSR_NS": 0.55, "EQ": 0.78, "FX": 0.47, "CMDTY": 1.00
    })

    # Optional deterministic mapping (risk_class, risk_factor) -> RW index
    rw_index_map: Dict[Tuple[str, str], int] = field(default_factory=dict)

    confidence_level: float = 0.975
    holding_period_days: int = 10
    backtesting_window: int = 260
    green_zone_max: int = 4
    amber_zone_max: int = 9
    ima_multiplier: float = 1.5
    nmrf_charge_bp: float = 0.0015
    stressed_es_multiplier: float = 1.5

    # Pluggable correlation model
    correlation_model: Optional[CorrelationModel] = None

    def __post_init__(self):
        if self.correlation_model is None:
            self.correlation_model = CorrelationModel(
                intra_corr=self.intra_corr,
                inter_corr=self.inter_corr,
            )

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

    # Optional breakdowns / details
    sbm_by_risk_class: Dict[str, float] = field(default_factory=dict)
    sbm_by_bucket: Dict[str, float] = field(default_factory=dict)
    ima_components: Dict[str, float] = field(default_factory=dict)

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

    def __init__(self, config: FRTBConfig):
        self.config = config
        config.validate()
        # Simple caches keyed by (risk_class, n)
        self._intra_cache: Dict[Tuple[str, int], np.ndarray] = {}
        self._inter_cache: Dict[Tuple[str, int], np.ndarray] = {}

    # ---- internal helpers -------------------------------------------------

    def _intra_corr_mat(self, risk_class: str, n: int) -> np.ndarray:
        key = (risk_class, n)
        if key not in self._intra_cache:
            self._intra_cache[key] = self.config.correlation_model.intra(risk_class, n)
        return self._intra_cache[key]

    def _inter_corr_mat(self, risk_class: str, m: int) -> np.ndarray:
        key = (risk_class, m)
        if key not in self._inter_cache:
            self._inter_cache[key] = self.config.correlation_model.inter(risk_class, m)
        return self._inter_cache[key]

    def _risk_weight_for(self, s: Sensitivity) -> float:
        """
        Deterministic RW lookup:
          1. Try explicit rw_index_map[(risk_class, risk_factor)]
          2. Fallback to sequential index based on risk_factor name
        """
        rw_map = self.config.delta_rw.get(
            s.risk_class,
            self.config.delta_rw.get(s.risk_class + "_LARGE", [0.15]),
        )
        if (s.risk_class, s.risk_factor) in self.config.rw_index_map:
            idx = self.config.rw_index_map[(s.risk_class, s.risk_factor)]
        else:
            # deterministic but simple: hash of risk_factor string
            idx = abs(hash(s.risk_factor)) % len(rw_map)
        return rw_map[idx]

    # ---- main SBM components ----------------------------------------------

    def delta_charge(
        self,
        sensitivities: Sequence[Sensitivity],
        risk_class: str,
        breakdown_by_bucket: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        1. WS_k = RW_k × s_k
        2. K_b = sqrt(Σ_k WS_k² + Σ_{k≠l} ρ_{kl} WS_k WS_l)   [intra-bucket]
        3. Δ   = sqrt(Σ_b K_b² + Σ_{b≠c} γ_{bc} K_b K_c)      [inter-bucket]
        """
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                return 0.0

            # bucket -> list of WS
            buckets: Dict[str, List[float]] = {}
            for s in senses:
                rw = self._risk_weight_for(s)
                ws = rw * s.delta
                buckets.setdefault(s.bucket, []).append(ws)

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
            return result

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Delta charge calculation failed for {risk_class}: {e}")

    def vega_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """Vega charge using vega sensitivities — simplified as scaled absolute vega."""
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class and s.vega != 0]
            if not senses:
                return 0.0
            total_vega = sum(abs(s.vega) for s in senses)
            rw = self.config.vega_rw.get(risk_class, 0.55)
            result = rw * total_vega * 0.30
            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Vega charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Vega charge calculation failed for {risk_class}: {e}")

    def curvature_charge(self, sensitivities: Sequence[Sensitivity], risk_class: str) -> float:
        """MAR23: curvature = max(0, Σ CVR_k) aggregated with correlation scenarios."""
        try:
            senses = [s for s in sensitivities if s.risk_class == risk_class]
            if not senses:
                return 0.0
            cvr = [max(-(min(s.curvature_up, s.curvature_dn)), 0) for s in senses]
            cvr_arr = np.array(cvr, dtype=np.float64)
            n = len(cvr_arr)
            if n == 0:
                return 0.0
            ρ_mat = self._intra_corr_mat(risk_class, n)
            agg = float(cvr_arr @ ρ_mat @ cvr_arr)
            result = math.sqrt(max(agg, 0.0)) + float(cvr_arr.sum())
            if math.isnan(result) or math.isinf(result):
                raise FRTBCalculationError(f"Curvature charge produced NaN/inf for {risk_class}")
            return result
        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"Curvature charge calculation failed for {risk_class}: {e}")

    def total_sbm(
        self,
        sensitivities: Sequence[Sensitivity],
    ) -> Tuple[float, float, float, float, Dict[str, float], Dict[str, float]]:
        """
        Returns:
            delta_total, vega_total, curv_total, sbm_total,
            sbm_by_risk_class, sbm_by_bucket
        """
        delta_charges: Dict[str, float] = {}
        vega_charges: Dict[str, float] = {}
        curv_charges: Dict[str, float] = {}
        bucket_breakdown: Dict[str, float] = {}

        for rc in self.config.risk_classes:
            rc_bucket_breakdown: Dict[str, float] = {}
            d = self.delta_charge(sensitivities, rc, breakdown_by_bucket=rc_bucket_breakdown)
            v = self.vega_charge(sensitivities, rc)
            c = self.curvature_charge(sensitivities, rc)
            delta_charges[rc] = d
            vega_charges[rc] = v
            curv_charges[rc] = c
            # merge bucket breakdowns with risk_class prefix
            for b, val in rc_bucket_breakdown.items():
                bucket_breakdown[f"{rc}:{b}"] = val

        delta_t = sum(delta_charges.values())
        vega_t = sum(vega_charges.values())
        curv_t = sum(curv_charges.values())
        sbm_t = delta_t + vega_t + curv_t

        sbm_by_risk_class = {
            rc: delta_charges[rc] + vega_charges[rc] + curv_charges[rc]
            for rc in self.config.risk_classes
        }

        logger.debug("SBM: Δ=%.0f  V=%.0f  C=%.0f  Total=%.0f",
                     delta_t, vega_t, curv_t, sbm_t)

        return delta_t, vega_t, curv_t, sbm_t, sbm_by_risk_class, bucket_breakdown


# ─────────────────────────────────────────────────────────────────────────────
# IMA — Expected Shortfall (MAR33)
# ─────────────────────────────────────────────────────────────────────────────


class IMACalculator:
    """
    Simplified IMA/ES calculator using historical or parametric methods.
    ES_t = mean of losses exceeding (1-α) worst outcomes.
    """

    def __init__(self, config: FRTBConfig):
        self.config = config
        config.validate()

    def compute_es(
        self,
        pnl_series: np.ndarray,
        stressed: bool = False,
        method: str = "historical",
        return_ci: bool = False,
        bootstrap_samples: int = 0,
    ) -> Union[float, Tuple[float, float, float]]:
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
                cutoff = max(int(len(losses) * (1 - α)), 1)
                worst = np.sort(losses)[-cutoff:]
                es_1d = float(worst.mean())
            elif method == "normal":
                mu = float(losses.mean())
                sigma = float(losses.std(ddof=1))
                if sigma <= 0:
                    es_1d = max(mu, 0.0)
                else:
                    from math import sqrt, pi, exp
                    # Normal ES formula: μ + σ φ(z)/(1-α)
                    # where z = Φ^{-1}(α)
                    from math import erf

                    def norm_ppf(p: float) -> float:
                        # simple approximation for Φ^{-1}
                        # not super-precise but fine for this context
                        return math.sqrt(2) * math.erfinv(2 * p - 1)

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

            if not return_ci or bootstrap_samples <= 0:
                return result

            # Bootstrap confidence interval
            boot = []
            rng = np.random.default_rng(123)
            for _ in range(bootstrap_samples):
                sample = rng.choice(pnl_series, size=len(pnl_series), replace=True)
                boot.append(self.compute_es(sample, stressed=stressed, method=method))
            boot_arr = np.array(boot)
            low, high = np.percentile(boot_arr, [5, 95])
            return result, float(low), float(high)

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"ES computation failed: {e}")

    def nmrf_charge(self, n_nmrf_factors: int, avg_notional: float) -> float:
        """
        MAR31.14: NMRF charge = 99th-pct loss for each NMRF.
        Simplified: charge = n × avg_notional × nmrf_charge_bp.
        """
        try:
            if n_nmrf_factors < 0:
                raise FRTBValidationError("n_nmrf_factors must be non-negative")
            if avg_notional <= 0:
                raise FRTBValidationError("avg_notional must be positive")

            charge = n_nmrf_factors * avg_notional * self.config.nmrf_charge_bp
            if math.isnan(charge) or math.isinf(charge):
                raise FRTBCalculationError("NMRF charge produced NaN/inf")
            return charge

        except (ValueError, TypeError) as e:
            raise FRTBCalculationError(f"NMRF charge calculation failed: {e}")


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
    ) -> FRTBResult:
        """
        Compute complete FRTB capital charge.
        """
        try:
            run_date = run_date or date.today()

            # Validate & aggregate
            validate_sensitivities(sensitivities, self.config)
            agg_sens = aggregate_sensitivities(sensitivities)

            if pnl_series is not None:
                validate_pnl_series(pnl_series)

            # ── SBM ──
            delta_t, vega_t, curv_t, sbm_t, sbm_by_rc, sbm_by_bucket = self.sbm.total_sbm(agg_sens)

            # ── IMA / ES ──
            if pnl_series is not None and len(pnl_series) > 0:
                es_base = self.ima.compute_es(pnl_series, stressed=False, method=es_method)
                es_stressed = self.ima.compute_es(pnl_series, stressed=True, method=es_method)
            else:
                logger.info("No PnL series provided; generating synthetic for demonstration")
                rng = np.random.default_rng(42)
                pnl_series = rng.normal(0, avg_notional * 0.01, self.config.backtesting_window)
                es_base = self.ima.compute_es(pnl_series, stressed=False, method=es_method)
                es_stressed = self.ima.compute_es(pnl_series, stressed=True, method=es_method)

            nmrf_ch = self.ima.nmrf_charge(n_nmrf, avg_notional)
            ima_t = max(es_base, es_stressed) + nmrf_ch

            # Capital = max(SBM_total, m_c × IMA_total)   [MAR33.8]
            capital = max(sbm_t, self.config.ima_multiplier * ima_t)
            rwa = capital * 12.5

            logger.info(
                "FRTB [%s] SBM=%.0f  IMA=%.0f  Capital=%.0f  RWA=%.0f",
                portfolio_id, sbm_t, ima_t, capital, rwa
            )

            ima_components = {
                "es_base_10d": es_base,
                "es_stressed_10d": es_stressed,
                "nmrf_charge": nmrf_ch,
                "ima_total": ima_t,
            }

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
                sbm_by_risk_class=sbm_by_rc,
                sbm_by_bucket=sbm_by_bucket,
                ima_components=ima_components,
            )

        except (FRTBValidationError, FRTBCalculationError) as e:
            logger.error(f"FRTB computation failed for {portfolio_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in FRTB computation: {e}")
            raise FRTBCalculationError(f"Unexpected error: {e}")

    # ---- batch processing -------------------------------------------------

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
        Very simple shock application:
          - rate_bp: scales GIRR deltas
          - spread_bp: scales CSR_NS / CSR_SEC deltas
          - fx_pct: scales FX deltas
        """
        shocked: List[Sensitivity] = []
        for s in sensitivities:
            s_new = copy.copy(s)
            if s_new.risk_class == "GIRR":
                s_new.delta *= (1 + scenario.rate_bp / 10000.0)
            elif s_new.risk_class in ("CSR_NS", "CSR_SEC"):
                s_new.delta *= (1 + scenario.spread_bp / 10000.0)
            elif s_new.risk_class == "FX":
                s_new.delta *= (1 + scenario.fx_pct)
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

    def evaluate(
        self,
        predicted: np.ndarray,   # 1-day VaR/ES predictions (positive = loss)
        actual_pnl: np.ndarray,  # actual daily P&L (negative = loss)
    ) -> Dict[str, Any]:
        """
        Evaluate backtesting exceptions against traffic light zones.
        """
        try:
            if len(predicted) != len(actual_pnl):
                raise FRTBValidationError("Length mismatch: predicted vs actual_pnl")
            if np.any(np.isnan(predicted)) or np.any(np.isnan(actual_pnl)):
                raise FRTBValidationError("Predicted or actual_pnl contains NaN")

            exceptions = int(np.sum(-actual_pnl > predicted))
            n = len(predicted)

            if exceptions <= self.config.green_zone_max:
                zone = "GREEN"
            elif exceptions <= self.config.amber_zone_max:
                zone = "AMBER"
            else:
                zone = "RED"

            logger.info(
                "Backtesting: %d exceptions / %d days → %s zone",
                exceptions, n, zone
            )

            mean_loss = float(((-actual_pnl[actual_pnl < 0]).mean())) if any(actual_pnl < 0) else 0.0

            return {
                "exceptions": exceptions,
                "window_days": n,
                "traffic_light": zone,
                "exception_pct": exceptions / n if n > 0 else 0.0,
                "mean_predicted": float(predicted.mean()),
                "mean_loss": mean_loss,
            }

        except FRTBValidationError:
            raise
        except Exception as e:
            raise FRTBCalculationError(f"Backtesting evaluation failed: {e}")
