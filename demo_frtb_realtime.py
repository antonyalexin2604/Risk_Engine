#!/usr/bin/env python3
"""
Demo: FRTB with Real-Time Market Conditions
Shows how risk weights and correlations adjust dynamically based on market volatility.
"""

from datetime import date
from backend.engines.frtb import (
    FRTBEngine, FRTBConfig, Sensitivity,
    MarketConditions, MarketDataFeed
)

print("=" * 80)
print("FRTB REAL-TIME MARKET CONDITIONS DEMO")
print("=" * 80)

# Create sample sensitivities (trading book portfolio)
sensitivities = [
    Sensitivity("T1", "GIRR", "USD", "2Y", delta=100_000, vega=5_000),
    Sensitivity("T2", "GIRR", "USD", "5Y", delta=-80_000, vega=3_000),
    Sensitivity("T3", "EQ", "Financials", "US_LARGE", delta=50_000, vega=8_000),
    Sensitivity("T4", "FX", "G10", "EURUSD", delta=30_000, vega=2_000),
    Sensitivity("T5", "CSR_NS", "IG", "Financials", delta=20_000, vega=1_500),
]

print("\n" + "-" * 80)
print("SCENARIO 1: Normal Market Conditions (Base RWs)")
print("-" * 80)

# Configure FRTB without real-time (static RWs)
config_static = FRTBConfig(use_market_conditions=False)
engine_static = FRTBEngine(config=config_static)

result_static = engine_static.compute(
    portfolio_id="TRADING_BOOK_001",
    sensitivities=sensitivities,
    n_nmrf=2,
    avg_notional=50_000_000,
)

print(f"SBM Delta:      ${result_static.sbm_delta:,.0f}")
print(f"SBM Total:      ${result_static.sbm_total:,.0f}")
print(f"Capital (MR):   ${result_static.capital_market_risk:,.0f}")
print(f"RWA:            ${result_static.rwa_market:,.0f}")

print("\n" + "-" * 80)
print("SCENARIO 2: Stressed Market (VIX=35, HY spreads=800bp)")
print("-" * 80)

# Configure FRTB with real-time conditions
config_realtime = FRTBConfig(use_market_conditions=True)
engine_realtime = FRTBEngine(config=config_realtime)

# Simulate stressed market conditions
stressed_market = MarketConditions(
    date=date.today(),
    vix_level=35.0,              # Elevated (normal ~15)
    equity_vol_index=35.0,       # High volatility
    credit_spread_ig=180.0,      # IG spreads widened
    credit_spread_hy=800.0,      # HY spreads stressed (normal ~400)
    fx_vol_index=12.0,           # FX vol elevated
    cmdty_vol_index=40.0,        # Commodity vol high
    ir_vol_swaption=75.0,        # IR vol elevated
)

print(f"Market Stress Level:  {stressed_market.stress_level():.2f}")
print(f"Market Regime:        {stressed_market.regime().value.upper()}")

result_stressed = engine_realtime.compute(
    portfolio_id="TRADING_BOOK_001",
    sensitivities=sensitivities,
    n_nmrf=2,
    avg_notional=50_000_000,
    market_conditions=stressed_market,
)

print(f"\nSBM Delta:      ${result_stressed.sbm_delta:,.0f}")
print(f"SBM Total:      ${result_stressed.sbm_total:,.0f}")
print(f"Capital (MR):   ${result_stressed.capital_market_risk:,.0f}")
print(f"RWA:            ${result_stressed.rwa_market:,.0f}")

# Show impact
delta_increase = (result_stressed.sbm_delta - result_static.sbm_delta) / result_static.sbm_delta * 100
capital_increase = (result_stressed.capital_market_risk - result_static.capital_market_risk) / result_static.capital_market_risk * 100

print(f"\n{'=' * 40}")
print(f"STRESSED vs NORMAL IMPACT:")
print(f"{'=' * 40}")
print(f"Delta Charge:   +{delta_increase:.1f}%")
print(f"Capital:        +{capital_increase:.1f}%")

print("\n" + "-" * 80)
print("SCENARIO 3: Crisis Market (VIX=60, HY spreads=1200bp)")
print("-" * 80)

# Simulate crisis conditions
crisis_market = MarketConditions(
    date=date.today(),
    vix_level=60.0,              # Crisis level
    equity_vol_index=55.0,       # Extreme volatility
    credit_spread_ig=300.0,      # IG spreads blown out
    credit_spread_hy=1200.0,     # HY spreads in crisis
    fx_vol_index=18.0,           # FX vol extreme
    cmdty_vol_index=65.0,        # Commodity vol crisis
    ir_vol_swaption=120.0,       # IR vol extreme
)

print(f"Market Stress Level:  {crisis_market.stress_level():.2f}")
print(f"Market Regime:        {crisis_market.regime().value.upper()}")

result_crisis = engine_realtime.compute(
    portfolio_id="TRADING_BOOK_001",
    sensitivities=sensitivities,
    n_nmrf=2,
    avg_notional=50_000_000,
    market_conditions=crisis_market,
)

print(f"\nSBM Delta:      ${result_crisis.sbm_delta:,.0f}")
print(f"SBM Total:      ${result_crisis.sbm_total:,.0f}")
print(f"Capital (MR):   ${result_crisis.capital_market_risk:,.0f}")
print(f"RWA:            ${result_crisis.rwa_market:,.0f}")

crisis_increase = (result_crisis.capital_market_risk - result_static.capital_market_risk) / result_static.capital_market_risk * 100

print(f"\n{'=' * 40}")
print(f"CRISIS vs NORMAL IMPACT:")
print(f"{'=' * 40}")
print(f"Capital:        +{crisis_increase:.1f}%")

print("\n" + "=" * 80)
print("INTEGRATION WITH LIVE DATA FEEDS")
print("=" * 80)
print("""
To connect to real-time data in production:

1. Bloomberg Terminal API:
   ```python
   from blpapi import Session, SessionOptions
   
   market_feed = MarketDataFeed()
   vix = bloomberg.get('VIX Index', 'LAST_PRICE')
   hy_spread = bloomberg.get('CDX HY', 'LAST_PRICE')
   
   market_feed.update_from_dict({
       'vix': vix,
       'hy_spread': hy_spread,
       ...
   })
   ```

2. Reuters/Refinitiv Eikon:
   ```python
   import eikon as ek
   
   vix_data = ek.get_data('.VIX', 'TR.CLOSEPRICE')
   market_feed.update_from_dict({'vix': float(vix_data[0][1])})
   ```

3. Internal Market Data System:
   ```python
   # Your bank's internal feed
   market_data = internal_api.get_market_snapshot()
   market_feed.update_from_dict(market_data)
   ```

4. Scheduled Updates (e.g., hourly recalc):
   ```python
   import schedule
   
   def update_frtb_capital():
       market = market_feed.get_current_conditions(force_refresh=True)
       result = engine_realtime.compute(..., market_conditions=market)
       save_to_database(result)
   
   schedule.every().hour.do(update_frtb_capital)
   ```
""")

print("\n✅ Demo complete! Risk weights now respond to real-time market volatility.")
