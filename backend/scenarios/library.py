"""
Regulatory Scenario Library
============================

Defines BCBS, ECB, FED, and custom stress scenarios.
Each scenario captures:
  - Market parameters (rates, spreads, volatility, FX)
  - Correlation regime (normal vs. stressed)
  - Liquidity conditions
  - Regulatory classification

Reference Standards:
  - MAR31 (IMA scenarios)
  - MAR99 (Backtesting examples)
  - ECB CRDP (Concurrent Risk Distress Period)
  - FED CCAR (Comprehensive Capital Analysis)
"""

import json
from dataclasses import dataclass, asdict, field
from datetime import date
from enum import Enum
from typing import Dict, Optional, List
import logging

logger = logging.getLogger("prometheus.scenarios.library")


class ScenarioType(Enum):
    """Scenario classification."""
    BASELINE = "baseline"              # Pre-stress baseline
    HISTORICAL_CRISIS = "hist_crisis"  # Realized historical crisis
    REGULATORY_ADVERSE = "reg_adverse" # Regulatory stress (FED/ECB)
    REGULATORY_SEVERE = "reg_severe"   # Severe regulatory stress
    CUSTOM = "custom"                  # Bank-specific scenario
    USER_DEFINED = "user_defined"      # Ad-hoc user input


class LiquidityRegime(Enum):
    """Market liquidity conditions."""
    NORMAL = "normal"              # Normal market conditions
    TIGHTENED = "tightened"        # Funding spreads elevated
    STRESSED = "stressed"          # Significant liquidity stress
    CRISIS = "crisis"              # Full market stress


@dataclass
class MarketParameters:
    """Market inputs for scenario."""

    # Interest Rates (basis points offset from current)
    rate_shock_usd_3m: float = 0.0     # 3M USD rates shift (bps)
    rate_shock_usd_10y: float = 0.0    # 10Y USD rates shift (bps)
    rate_shock_eur_3m: float = 0.0
    rate_shock_eur_10y: float = 0.0
    rate_shock_gbp_3m: float = 0.0
    rate_shock_gbp_10y: float = 0.0

    # Credit Spreads (basis points)
    credit_spread_aaa: float = 0.0     # AAA corporate spreads shift (bps)
    credit_spread_a: float = 0.0       # A spreads shift
    credit_spread_bbb: float = 0.0     # BBB spreads shift
    credit_spread_hy: float = 0.0      # High-yield spreads shift
    cds_spread_financial: float = 0.0  # CDS on financials (bps shift)
    cds_spread_energy: float = 0.0     # CDS on energy sector

    # Volatility (percentage points shift from baseline)
    equity_volatility: float = 0.15    # Equity Vol (absolute, not shift)
    ir_volatility: float = 0.0085      # Interest rate Vol
    fx_volatility: float = 0.12        # FX Vol
    credit_volatility: float = 0.0     # Credit Vol shift (bps)

    # FX Rates (percentage shift)
    eur_usd_shock: float = 0.0         # EUR/USD % shift
    gbp_usd_shock: float = 0.0         # GBP/USD % shift
    jpy_usd_shock: float = 0.0         # JPY/USD % shift

    # Equity Indices (percentage shift)
    sp500_shock: float = 0.0           # S&P 500 % change
    stoxx50_shock: float = 0.0         # STOXX 50 % change
    nikkei_shock: float = 0.0          # Nikkei 225 % change

    # Correlation regime (multiplier on baseline correlation)
    correlation_multiplier: float = 1.0  # 1.0 = baseline, 1.25 = stressed, 0.75 = relaxed


@dataclass
class Scenario:
    """Complete scenario specification."""

    # Identification
    scenario_id: str                    # Unique ID (e.g., "CRISIS_2008")
    scenario_name: str                  # Display name
    scenario_type: ScenarioType
    description: str

    # Temporal
    start_date: date
    end_date: date
    historical_basis: Optional[str] = None  # "2007-06-01 to 2009-06-30" for hist periods

    # Market parameters
    market_params: MarketParameters = field(default_factory=MarketParameters)

    # Regime characteristics
    liquidity_regime: LiquidityRegime = LiquidityRegime.NORMAL
    stress_level: str = "normal"        # normal, moderate, severe, crisis

    # Regulatory classification
    regulatory_basis: Optional[str] = None  # e.g., "MAR31", "ECB CRDP", "FED CCAR"
    is_regulatory: bool = False
    regulatory_guidance: Optional[str] = None

    # Risk metrics (precomputed for reference)
    expected_rwa_increase_pct: Optional[float] = None  # Expected RWA increase vs. baseline
    expected_credit_spread_increase_bps: Optional[float] = None
    expected_correlation_uplift: Optional[float] = None

    # Metadata
    created_date: Optional[date] = None
    last_updated_date: Optional[date] = None
    source: str = "PROMETHEUS"          # Data source
    comments: str = ""


# ════════════════════════════════════════════════════════════════════════════
# REGULATORY SCENARIO LIBRARY
# ════════════════════════════════════════════════════════════════════════════

def create_baseline_scenario() -> Scenario:
    """Create baseline (no-stress) scenario."""
    return Scenario(
        scenario_id="BASELINE_CURRENT",
        scenario_name="Baseline — Current Market",
        scenario_type=ScenarioType.BASELINE,
        description="No shocks; current market conditions (reference point)",
        start_date=date.today(),
        end_date=date.today(),
        market_params=MarketParameters(),
        liquidity_regime=LiquidityRegime.NORMAL,
        stress_level="normal",
        is_regulatory=True,
        expected_rwa_increase_pct=0.0,
    )


def create_2007_2009_crisis_scenario() -> Scenario:
    """
    Historical 2007-2009 Global Financial Crisis.

    Regulatory basis: IMM stressed period (CRE53)

    Characteristics:
    - Credit spreads widen 300-500 bps (AAA to HY)
    - Equity markets down 50-60%
    - Correlations spike to near 1.0
    - VIX equivalent: 80+
    - Funding stress: LIBOR-OIS spike 100+ bps
    """
    return Scenario(
        scenario_id="CRISIS_2008",
        scenario_name="Global Financial Crisis (2007–2009)",
        scenario_type=ScenarioType.HISTORICAL_CRISIS,
        description=(
            "Lehman Brothers collapse, credit market seizure. "
            "Rates spike, spreads widen dramatically, correlations near 1.0"
        ),
        start_date=date(2007, 6, 1),
        end_date=date(2009, 6, 30),
        historical_basis="Jun 2007 - Jun 2009",
        market_params=MarketParameters(
            # Interest rates
            rate_shock_usd_3m=-150,       # 3M rates fall (flight to quality)
            rate_shock_usd_10y=-50,       # 10Y rates fall but less
            rate_shock_eur_3m=-100,
            rate_shock_eur_10y=-30,

            # Credit spreads widen sharply
            credit_spread_aaa=150,        # AAA corporates widen 150 bps
            credit_spread_a=250,          # A spreads widen 250 bps
            credit_spread_bbb=400,        # BBB spreads widen 400 bps
            credit_spread_hy=700,         # HY spreads widen 700 bps
            cds_spread_financial=450,     # Financial CDS spikes
            cds_spread_energy=350,

            # Volatility skyrockets
            equity_volatility=0.65,       # VIX equivalent 65+
            ir_volatility=0.025,          # IR Vol up significantly
            fx_volatility=0.18,
            credit_volatility=150,

            # FX moves
            eur_usd_shock=-0.10,          # EUR weakens 10% vs USD
            gbp_usd_shock=-0.15,          # GBP weakens 15% vs USD

            # Equity collapse
            sp500_shock=-0.55,            # S&P down 55%
            stoxx50_shock=-0.60,          # STOXX down 60%

            # Correlation spike
            correlation_multiplier=1.35,  # Correlations jump by 35%
        ),
        liquidity_regime=LiquidityRegime.CRISIS,
        stress_level="crisis",
        regulatory_basis="CRE53 (IMM stressed period), MAR99",
        is_regulatory=True,
        expected_rwa_increase_pct=40,     # RWA typically up 30-50% in crisis
        expected_credit_spread_increase_bps=350,
        expected_correlation_uplift=0.35,
        comments="Basel III baseline stressed period for IMM calculations"
    )


def create_ecb_crdp_scenario() -> Scenario:
    """
    ECB Concurrent Risk Distress Period (CRDP).

    Regulatory basis: ECB SREP guidance (supervisory stress test)

    Characteristics:
    - Sovereign debt stress (Italy, Spain CDS +200 bps)
    - Banking sector stress (financial CDS +300 bps)
    - Equity sell-off (20-30%)
    - Funding market dysfunction
    - Credit spreads widen 100-200 bps
    """
    return Scenario(
        scenario_id="ECB_CRDP",
        scenario_name="ECB Concurrent Risk Distress Period",
        scenario_type=ScenarioType.REGULATORY_ADVERSE,
        description=(
            "Sovereign debt crisis with concurrent banking stress. "
            "European periphery stress, funding fragmentation."
        ),
        start_date=date(2011, 6, 1),
        end_date=date(2012, 9, 30),
        historical_basis="Jun 2011 - Sep 2012 (Eurozone crisis peak)",
        market_params=MarketParameters(
            # Interest rates
            rate_shock_eur_10y=100,       # Eurozone peripheral rates spike
            rate_shock_eur_3m=50,

            # Sovereign + financial spreads
            credit_spread_aaa=80,
            credit_spread_a=150,
            credit_spread_bbb=250,
            credit_spread_hy=400,
            cds_spread_financial=300,     # Financial CDS +300 bps (contagion risk)
            cds_spread_energy=120,

            # Volatility elevated but not crisis-level
            equity_volatility=0.42,       # VIX ~40-45
            ir_volatility=0.012,
            fx_volatility=0.14,

            # Moderate equity decline
            sp500_shock=-0.25,            # US equities down 25%
            stoxx50_shock=-0.32,          # European equities down 32%

            # Correlation stress but not maximum
            correlation_multiplier=1.22,  # +22% correlation stretch
        ),
        liquidity_regime=LiquidityRegime.STRESSED,
        stress_level="severe",
        regulatory_basis="ECB SREP stress test guidance",
        is_regulatory=True,
        expected_rwa_increase_pct=25,
        expected_credit_spread_increase_bps=220,
        expected_correlation_uplift=0.22,
        comments="ECB supervisory stress test scenario; reflects 2011-2012 crisis"
    )


def create_fed_adverse_scenario() -> Scenario:
    """
    FED CCAR Adverse Scenario.

    Regulatory basis: Comprehensive Capital Analysis and Review (CCAR)

    Characteristics:
    - Unemployment +3% (vs. baseline)
    - S&P down 35%
    - Treasury rates +100 bps (long end)
    - Credit spreads widen 100-200 bps
    - Moderate volatility spike (not crisis)
    """
    return Scenario(
        scenario_id="FED_ADVERSE",
        scenario_name="FED CCAR Adverse Scenario",
        scenario_type=ScenarioType.REGULATORY_ADVERSE,
        description=(
            "US economic downturn: unemployment rising, equity sell-off, "
            "credit spreads widening, rates rising."
        ),
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        market_params=MarketParameters(
            # Rates rise (reflation scenario)
            rate_shock_usd_3m=100,        # 3M rates up 100 bps
            rate_shock_usd_10y=100,       # 10Y rates up 100 bps

            # Credit spreads widen moderately
            credit_spread_aaa=100,
            credit_spread_a=150,
            credit_spread_bbb=200,
            credit_spread_hy=350,
            cds_spread_financial=180,

            # Volatility spike (not extreme)
            equity_volatility=0.38,       # VIX ~35-40
            ir_volatility=0.015,

            # Equity decline 35%
            sp500_shock=-0.35,            # S&P down 35% (CCAR spec)
            stoxx50_shock=-0.28,

            # Correlation moderate stress
            correlation_multiplier=1.15,
        ),
        liquidity_regime=LiquidityRegime.TIGHTENED,
        stress_level="severe",
        regulatory_basis="FED CCAR guidance",
        is_regulatory=True,
        expected_rwa_increase_pct=22,
        comments="FED Comprehensive Capital Analysis (CCAR) adverse scenario"
    )


def create_fed_severely_adverse_scenario() -> Scenario:
    """
    FED CCAR Severely Adverse Scenario (worst-case regulatory).

    Regulatory basis: CCAR Severely Adverse

    Characteristics:
    - Unemployment +4% (worse than adverse)
    - S&P down 50%
    - Treasury rates +200 bps long end
    - Credit spreads widen 200-400 bps
    - Significant volatility spike
    """
    return Scenario(
        scenario_id="FED_SEVERELY_ADVERSE",
        scenario_name="FED CCAR Severely Adverse Scenario",
        scenario_type=ScenarioType.REGULATORY_SEVERE,
        description=(
            "Severe US recession: unemployment up 4%, equity crash 50%, "
            "massive credit spread widening, rates elevated."
        ),
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        market_params=MarketParameters(
            # Rates rise sharply
            rate_shock_usd_3m=150,
            rate_shock_usd_10y=200,

            # Credit spreads widen severely
            credit_spread_aaa=200,
            credit_spread_a=300,
            credit_spread_bbb=400,
            credit_spread_hy=600,
            cds_spread_financial=350,

            # Volatility high
            equity_volatility=0.50,       # VIX ~50+
            ir_volatility=0.020,

            # Major equity decline
            sp500_shock=-0.50,            # S&P down 50% (CCAR severely adverse)
            stoxx50_shock=-0.45,

            # Correlation significantly stressed
            correlation_multiplier=1.28,
        ),
        liquidity_regime=LiquidityRegime.STRESSED,
        stress_level="crisis",
        regulatory_basis="FED CCAR severely adverse",
        is_regulatory=True,
        expected_rwa_increase_pct=35,
        comments="FED worst-case regulatory scenario for capital planning"
    )


def create_hfl_scenario() -> Scenario:
    """
    Higher-for-Longer (HFL) 2023-2024 Market Scenario.

    Characteristics:
    - Rates remain elevated (2.5-3.5% for extended period)
    - Mild credit spread widening (50-75 bps)
    - Modest equity weakness (5-10%)
    - Moderate volatility (18-22)
    - Used for medium-term horizon planning
    """
    return Scenario(
        scenario_id="HFL_2024",
        scenario_name="Higher-for-Longer Rate Environment",
        scenario_type=ScenarioType.CUSTOM,
        description=(
            "Persistent high interest rates, contained inflation, "
            "modest credit stress. Market practice scenario for 2024-2025."
        ),
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        market_params=MarketParameters(
            # Rates stay elevated but stable
            rate_shock_usd_3m=50,
            rate_shock_usd_10y=75,
            rate_shock_eur_10y=50,

            # Credit spreads moderately wide
            credit_spread_aaa=50,
            credit_spread_a=80,
            credit_spread_bbb=120,
            credit_spread_hy=200,

            # Volatility moderate
            equity_volatility=0.18,       # VIX ~15-20
            ir_volatility=0.010,

            # Mild equity weakness
            sp500_shock=-0.08,            # S&P down 8%
            stoxx50_shock=-0.10,

            # Baseline to modest correlation rise
            correlation_multiplier=1.08,
        ),
        liquidity_regime=LiquidityRegime.NORMAL,
        stress_level="moderate",
        is_regulatory=False,
        expected_rwa_increase_pct=8,
        comments="Market practice scenario: rates elevated but stable"
    )


# ════════════════════════════════════════════════════════════════════════════
# SCENARIO REGISTRY & LOOKUP
# ════════════════════════════════════════════════════════════════════════════

_SCENARIO_REGISTRY: Dict[str, Scenario] = {
    "BASELINE_CURRENT": create_baseline_scenario(),
    "CRISIS_2008": create_2007_2009_crisis_scenario(),
    "ECB_CRDP": create_ecb_crdp_scenario(),
    "FED_ADVERSE": create_fed_adverse_scenario(),
    "FED_SEVERELY_ADVERSE": create_fed_severely_adverse_scenario(),
    "HFL_2024": create_hfl_scenario(),
}


def get_regulatory_scenario(scenario_id: str) -> Optional[Scenario]:
    """
    Retrieve scenario by ID.

    Args:
        scenario_id: Scenario identifier (e.g., "CRISIS_2008", "FED_ADVERSE")

    Returns:
        Scenario object or None if not found

    Example:
        crisis = get_regulatory_scenario("CRISIS_2008")
        print(f"Equity shock: {crisis.market_params.sp500_shock:.1%}")
    """
    return _SCENARIO_REGISTRY.get(scenario_id)


def get_all_scenarios(scenario_type: Optional[ScenarioType] = None) -> List[Scenario]:
    """
    Retrieve all scenarios, optionally filtered by type.

    Args:
        scenario_type: Filter by scenario type (e.g., ScenarioType.REGULATORY_ADVERSE)

    Returns:
        List of Scenario objects

    Example:
        regulatory = get_all_scenarios(ScenarioType.HISTORICAL_CRISIS)
    """
    scenarios = list(_SCENARIO_REGISTRY.values())

    if scenario_type:
        scenarios = [s for s in scenarios if s.scenario_type == scenario_type]

    return scenarios


def register_custom_scenario(scenario: Scenario) -> None:
    """
    Register a custom user-defined scenario.

    Args:
        scenario: Scenario object

    Example:
        custom = Scenario(
            scenario_id="CUSTOM_GEOPOLITICAL",
            scenario_name="Geopolitical Shock",
            ...
        )
        register_custom_scenario(custom)
    """
    if scenario.scenario_id in _SCENARIO_REGISTRY:
        logger.warning(f"Overwriting existing scenario: {scenario.scenario_id}")

    _SCENARIO_REGISTRY[scenario.scenario_id] = scenario
    logger.info(f"Registered scenario: {scenario.scenario_id}")


def export_scenarios_to_json(filepath: str) -> None:
    """Export all scenarios to JSON file."""
    scenarios_dict = {
        sid: asdict(s) for sid, s in _SCENARIO_REGISTRY.items()
    }

    # Convert enums to strings for JSON serialization
    for scenario_dict in scenarios_dict.values():
        scenario_dict["scenario_type"] = scenario_dict["scenario_type"].value
        scenario_dict["liquidity_regime"] = scenario_dict["liquidity_regime"].value
        scenario_dict["market_params"]["correlation_multiplier"] = float(
            scenario_dict["market_params"]["correlation_multiplier"]
        )
        if scenario_dict.get("start_date"):
            scenario_dict["start_date"] = scenario_dict["start_date"].isoformat()
        if scenario_dict.get("end_date"):
            scenario_dict["end_date"] = scenario_dict["end_date"].isoformat()

    with open(filepath, "w") as f:
        json.dump(scenarios_dict, f, indent=2)

    logger.info(f"Exported {len(scenarios_dict)} scenarios to {filepath}")


def print_scenario_summary():
    """Print human-readable scenario summary."""
    print("\n" + "="*70)
    print("PROMETHEUS REGULATORY SCENARIO LIBRARY")
    print("="*70 + "\n")

    for scenario in get_all_scenarios():
        print(f"ID: {scenario.scenario_id}")
        print(f"  Name: {scenario.scenario_name}")
        print(f"  Type: {scenario.scenario_type.value}")
        print(f"  Equity Shock: {scenario.market_params.sp500_shock:+.1%}")
        print(f"  Spread Increase (BBB): {scenario.market_params.credit_spread_bbb:+d} bps")
        print(f"  Correlation ×: {scenario.market_params.correlation_multiplier:.2f}")
        print(f"  Regulatory: {scenario.is_regulatory}")
        if scenario.expected_rwa_increase_pct is not None:
            print(f"  Expected RWA Increase: {scenario.expected_rwa_increase_pct:+d}%")
        print()


if __name__ == "__main__":
    print_scenario_summary()

