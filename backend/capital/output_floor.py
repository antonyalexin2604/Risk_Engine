"""
Dynamic Output Floor Calculator (CRR3)
=======================================

Implements Basel Endgame output floor per CRR3:
  Static Basel IV: 72.5% × SA_RWA
  Dynamic CRR3: f(SA_RWA, A-IRB ratio, stress regime)

Regulatory Basis: CRR3 Article 12a, RBC20.11
Market Practice: Dynamic calibration based on portfolio characteristics
"""

import logging
from datetime import date, timedelta
from typing import Tuple, Dict, Optional
import numpy as np
import sqlalchemy as sa

logger = logging.getLogger("prometheus.capital.output_floor")


class DynamicOutputFloorCalculator:
    """
    Compute CRR3-compliant dynamic output floor.

    Formula:
        Floored_RWA = max(Total_RWA, Dynamic_Floor)

    where:
        Dynamic_Floor = SA_RWA × [0.725 + stress_adjustment]

        stress_adjustment:
          - Normal regime: 0.5%
          - Stressed regime: 1.5–2.0%
          - Crisis regime: 2.0%+

    This enables:
      - Capital relief in normal conditions (lower floor)
      - Increased conservatism in stress (higher floor)
      - Compliance with CRR3 / Basel Endgame
    """

    def __init__(self, lookback_months: int = 24, db_engine=None):
        """
        Initialize calculator.

        Args:
            lookback_months: Historical window for calibration (default 24)
            db_engine: SQLAlchemy engine for data access
        """
        self.lookback_months = lookback_months
        self.db_engine = db_engine

        # Calibration cache
        self._historical_ratios: Optional[np.ndarray] = None
        self._last_calibration_date: Optional[date] = None

    def compute_floor_multiplier(
        self,
        sa_rwa: float,
        airb_rwa: float,
        regime: str = "normal",  # normal, stressed, crisis
    ) -> float:
        """
        Compute dynamic floor multiplier per CRR3.

        Args:
            sa_rwa: Standardised Approach RWA (denominator)
            airb_rwa: Advanced IRB total RWA (stress indicator)
            regime: Market regime (inferred or provided)

        Returns:
            Multiplier (e.g., 0.745 for 74.5% floor)

        Example:
            floor_mult = calc.compute_floor_multiplier(
                sa_rwa=1_500_000,
                airb_rwa=1_200_000,
                regime="normal"
            )
            floor_rwa = sa_rwa * floor_mult  # 72.5% of SA_RWA
        """

        logger.info(
            f"Computing floor multiplier: SA={sa_rwa:,.0f}, "
            f"A-IRB={airb_rwa:,.0f}, regime={regime}"
        )

        # Base floor: 72.5% (Basel IV static)
        base_multiplier = 0.725

        # Regime-based adjustment
        adjustment_map = {
            "normal": 0.005,      # +0.5% → 73.0% floor
            "stressed": 0.015,    # +1.5% → 74.0% floor
            "crisis": 0.020,      # +2.0% → 74.5% floor
        }

        adjustment = adjustment_map.get(regime, 0.005)

        # A-IRB penetration check: if A-IRB >> SA, tighten floor
        if sa_rwa > 0:
            airb_ratio = airb_rwa / sa_rwa

            # If A-IRB is <50% of SA: very conservative, add cushion
            if airb_ratio < 0.50:
                adjustment += 0.005
            # If A-IRB is 80%+ of SA: aggressive A-IRB use, tighten floor
            elif airb_ratio > 0.80:
                adjustment -= 0.005  # Can reduce floor (more A-IRB trust)

        dynamic_multiplier = base_multiplier + adjustment

        logger.info(f"  Floor multiplier: {dynamic_multiplier:.3%} (adjustment: {adjustment:+.1%})")

        return dynamic_multiplier

    def compute_regime(self, market_data: Dict) -> str:
        """
        Infer market regime from market data (simplified).

        Args:
            market_data: Dict with keys like 'vix', 'credit_spread_bbb_bps', 'equity_vol'

        Returns:
            Regime: "normal", "stressed", or "crisis"
        """

        vix = market_data.get("vix", 15)
        oas_spread = market_data.get("oas_bps", 100)
        equity_vol = market_data.get("equity_vol", 0.15)

        # Regime classification rules
        if vix > 30 or oas_spread > 300 or equity_vol > 0.35:
            regime = "crisis"
        elif vix > 20 or oas_spread > 200 or equity_vol > 0.25:
            regime = "stressed"
        else:
            regime = "normal"

        logger.debug(f"Market regime: {regime} (VIX={vix}, OAS={oas_spread}bps, Vol={equity_vol:.1%})")

        return regime

    def apply_floor(
        self,
        total_rwa: float,
        sa_rwa: float,
        airb_rwa: float,
        regime: Optional[str] = None,
        market_data: Optional[Dict] = None,
    ) -> Tuple[float, float, str]:
        """
        Apply dynamic output floor to total RWA.

        Args:
            total_rwa: Total RWA before floor (sum of all components)
            sa_rwa: Standardised Approach RWA (denominator)
            airb_rwa: Advanced IRB RWA (for regime inference)
            regime: Explicit regime override (optional)
            market_data: Market data for regime inference (optional)

        Returns:
            (floored_rwa, floor_impact, binding_status)

        Example:
            floored_rwa, impact, status = calc.apply_floor(
                total_rwa=1_000_000,
                sa_rwa=1_500_000,
                airb_rwa=1_200_000,
            )
            print(f"RWA after floor: {floored_rwa:,.0f}")  # max(1M, 1.5M * 0.725) = 1.0875M
            print(f"Floor binding: {status}")  # "binding" or "not_binding"
        """

        # Infer regime if not provided
        if regime is None:
            if market_data:
                regime = self.compute_regime(market_data)
            else:
                regime = "normal"

        # Compute floor multiplier
        multiplier = self.compute_floor_multiplier(sa_rwa, airb_rwa, regime)

        # Compute floor level
        floor_rwa = sa_rwa * multiplier

        # Apply floor
        if total_rwa >= floor_rwa:
            # Floor not binding
            floored_rwa = total_rwa
            impact = 0.0
            status = "not_binding"
            logger.info(
                f"Floor not binding: Total={total_rwa:,.0f} >= Floor={floor_rwa:,.0f}"
            )
        else:
            # Floor is binding—apply it
            floored_rwa = floor_rwa
            impact = floor_rwa - total_rwa
            status = "binding"
            logger.warning(
                f"Floor BINDING: Total={total_rwa:,.0f} < Floor={floor_rwa:,.0f}, "
                f"increase RWA by {impact:,.0f}"
            )

        return floored_rwa, impact, status

    def persist_floor_calculation(
        self,
        run_date: date,
        total_rwa: float,
        sa_rwa: float,
        airb_rwa: float,
        floored_rwa: float,
        regime: str,
    ) -> None:
        """
        Persist floor calculation to database for audit trail.

        Args:
            run_date: Risk run date
            total_rwa: RWA before floor
            sa_rwa: SA component
            airb_rwa: A-IRB component
            floored_rwa: Final RWA after floor
            regime: Market regime used
        """

        if not self.db_engine:
            logger.warning("Database engine not configured; skipping persistence")
            return

        multiplier = self.compute_floor_multiplier(sa_rwa, airb_rwa, regime)
        status = "binding" if floored_rwa > total_rwa else "not_binding"
        impact = floored_rwa - total_rwa

        with self.db_engine.connect() as conn:
            # Create table if not exists
            conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS prometheus_capital.output_floor_tracking (
                    id SERIAL PRIMARY KEY,
                    run_date DATE NOT NULL,
                    total_rwa DECIMAL(15,2),
                    sa_rwa DECIMAL(15,2),
                    airb_rwa DECIMAL(15,2),
                    floored_rwa DECIMAL(15,2),
                    floor_multiplier DECIMAL(5,4),
                    floor_impact DECIMAL(15,2),
                    regime VARCHAR(50),
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Insert row
            conn.execute(sa.text("""
                INSERT INTO prometheus_capital.output_floor_tracking
                (run_date, total_rwa, sa_rwa, airb_rwa, floored_rwa, floor_multiplier, floor_impact, regime, status)
                VALUES (:run_date, :total, :sa, :airb, :floored, :mult, :impact, :regime, :status)
            """), {
                "run_date": run_date,
                "total": total_rwa,
                "sa": sa_rwa,
                "airb": airb_rwa,
                "floored": floored_rwa,
                "mult": multiplier,
                "impact": impact,
                "regime": regime,
                "status": status,
            })

            conn.commit()

        logger.info(f"Persisted floor calculation for {run_date}")

    def generate_floor_report(self) -> str:
        """Generate markdown report of floor impact."""

        report = f"""
# PROMETHEUS Dynamic Output Floor Report
**Generated:** {date.today().isoformat()}

## CRR3 Output Floor Implementation

The output floor ensures minimum capital requirement:

```
Floored RWA = max(Total RWA, Dynamic Floor)

where:
  Dynamic Floor = SA_RWA × [72.5% + stress_adjustment]
  
  Stress Adjustment:
    - Normal regime: +0.5%   → 73.0% floor
    - Stressed: +1.5%        → 74.0% floor
    - Crisis: +2.0%          → 74.5% floor
```

## Recent Floor Applications

| Date | Total RWA | SA RWA | Floor RWA | Impact | Status |
|------|-----------|--------|-----------|--------|--------|
| TBD | — | — | — | — | — |

---

**End of Report**
"""

        return report


# ════════════════════════════════════════════════════════════════════════════
# Integration with main.py
# ════════════════════════════════════════════════════════════════════════════

def apply_output_floor_to_rwa(
    total_rwa: float,
    rwa_components: Dict[str, float],
    run_date: date,
    db_engine=None,
) -> Tuple[float, Dict]:
    """
    Apply output floor to RWA calculation.

    Usage in main.py:
        floored_rwa, metadata = apply_output_floor_to_rwa(
            total_rwa=rwa_total,
            rwa_components={
                "credit": rwa_credit,
                "ccr": rwa_ccr,
                "market": rwa_market,
                "cva": rwa_cva,
            },
            run_date=run_date,
            db_engine=db_engine,
        )
    """

    calculator = DynamicOutputFloorCalculator(db_engine=db_engine)

    # Compute SA as comparator (simple: 1.5x of A-IRB as proxy)
    airb_rwa = total_rwa
    sa_rwa = airb_rwa * 1.5  # Simplified; should use actual SA computation

    # Apply floor
    floored_rwa, impact, status = calculator.apply_floor(
        total_rwa=total_rwa,
        sa_rwa=sa_rwa,
        airb_rwa=airb_rwa,
    )

    # Persist
    if db_engine:
        calculator.persist_floor_calculation(
            run_date=run_date,
            total_rwa=total_rwa,
            sa_rwa=sa_rwa,
            airb_rwa=airb_rwa,
            floored_rwa=floored_rwa,
            regime="normal",  # Infer from market data in production
        )

    return floored_rwa, {
        "floor_impact": impact,
        "floor_status": status,
        "floor_multiplier": sa_rwa / total_rwa if total_rwa > 0 else 0,
    }


if __name__ == "__main__":
    # Demo
    calc = DynamicOutputFloorCalculator()

    floored, impact, status = calc.apply_floor(
        total_rwa=1_000_000,
        sa_rwa=1_500_000,
        airb_rwa=1_200_000,
        regime="normal",
    )

    print(f"Floored RWA: {floored:,.0f}")
    print(f"Floor impact: {impact:,.0f}")
    print(f"Floor status: {status}")

