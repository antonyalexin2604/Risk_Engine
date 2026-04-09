# FRTB Market Data Enhancement

## Overview

The FRTB engine has been enhanced with external market data sourcing capabilities, similar to the A-IRB implementation. The `MarketDataFeed` class now supports a three-tier fallback strategy for fetching real-time market parameters.

## Key Changes

### 1. Enhanced MarketDataFeed Class

The `MarketDataFeed` class in [frtb.py](backend/engines/frtb.py) has been completely rewritten to support:

- **Three-tier fallback architecture**:
  - **Tier 1**: Bloomberg BSAPI / Refinitiv (real-time, intraday)
  - **Tier 2**: FRED public API / yfinance (daily close, T+0 or 15-min delayed)
  - **Tier 3**: Hardcoded conservative defaults (never fails)

- **Thread-safe caching**: RLock-protected in-memory cache with configurable TTL
- **Disk cache**: Optional JSON persistence for sharing across processes
- **Manual injection**: Testing and scenario analysis support

### 2. Market Parameters Sourced Externally

All seven `MarketConditions` fields are now sourced from external APIs:

| Parameter | Bloomberg | FRED | yfinance | Fallback |
|-----------|-----------|------|----------|----------|
| **VIX Level** | VIX Index | VIXCLS | ^VIX | 20.0 |
| **Equity Vol** | VXO Index | VXEEMCLS | ^VIX | 22.0% |
| **IG Spread** | LUACOAS Index | BAMLC0A0CMEY | - | 120 bp |
| **HY Spread** | LF98OAS Index | BAMLH0A0HYM2 | - | 450 bp |
| **FX Vol** | JPMVXYGL Index | DEXJPUS (calc) | - | 9.0% |
| **Commodity Vol** | CRYTR Index | - | CL=F (calc) | 28.0% |
| **IR Vol (MOVE)** | MOVE Index | MOVE | - | 60 bp |

### 3. Data Sources

#### Federal Reserve Economic Data (FRED)
- **Free, public API**: No authentication required for CSV endpoint
- **Optional API key**: Set `FRED_API_KEY` env var for JSON API (higher rate limit)
- **Series used**:
  - `VIXCLS` - CBOE VIX close
  - `VXEEMCLS` - CBOE EM VIX
  - `BAMLC0A0CMEY` - ICE BofA US Corporate IG OAS
  - `BAMLH0A0HYM2` - ICE BofA US HY OAS
  - `DEXJPUS` - USD/JPY (for realized vol calculation)
  - `MOVE` - Merrill Lynch Option Volatility Estimate

#### yfinance (Third-party Python library)
- **Free, delayed data**: 15-minute delay
- **No API key required**: `pip install yfinance`
- **Tickers used**:
  - `^VIX` - CBOE VIX Index
  - `CL=F` - WTI Crude Oil (for realized vol)

#### Bloomberg (Tier 1, optional)
- **Real-time intraday data**
- **Requires**: `pip install blpapi`, Bloomberg terminal/SAPI license
- **Configuration**: Set `BLOOMBERG_HOST=localhost:8194` env var

#### Refinitiv (Tier 1, optional)
- **Real-time intraday data**
- **Requires**: `pip install refinitiv-data`, API key
- **Configuration**: Set `REFINITIV_APP_KEY=your_key` env var

## Usage

### Basic Usage (Public Data Sources)

```python
from backend.engines.frtb import MarketDataFeed

# Initialize feed (uses FRED + yfinance by default)
feed = MarketDataFeed()

# Fetch current market conditions
conditions = feed.get_current_conditions()

print(f"VIX: {conditions.vix_level:.2f}")
print(f"HY Spread: {conditions.credit_spread_hy:.0f} bp")
print(f"Market Regime: {conditions.regime().value}")
```

### With API Keys

```python
# Option 1: Environment variables
# export FRED_API_KEY="your_fred_key"
# export BLOOMBERG_HOST="localhost:8194"
# export REFINITIV_APP_KEY="your_refinitiv_key"

feed = MarketDataFeed()

# Option 2: Direct configuration
feed = MarketDataFeed(
    fred_api_key="your_fred_key",
    bloomberg_host="localhost:8194",
    refinitiv_key="your_refinitiv_key",
    cache_path="/tmp/frtb_market_cache.json"
)
```

### Manual Injection (Testing/Scenarios)

```python
# Inject crisis scenario
crisis = feed.inject(
    vix_level=75.0,
    credit_spread_hy=1200.0,
    equity_vol_index=85.0
)

# Inject normal scenario
normal = feed.inject(
    vix_level=12.0,
    credit_spread_hy=350.0
)
```

### Integration with FRTB Engine

```python
from backend.engines.frtb import FRTBConfig, FRTBEngine, MarketDataFeed

# Enable real-time market conditions
config = FRTBConfig(use_market_conditions=True)
feed = MarketDataFeed()
config.market_data_feed = feed

# Engine will auto-fetch market data during compute()
engine = FRTBEngine(config)
result = engine.compute(
    portfolio_id="TRADING_BOOK_1",
    sensitivities=my_sensitivities,
    market_conditions=None,  # Auto-fetches if None
)
```

## Environment Variables

All environment variables are **optional**:

| Variable | Purpose | Default |
|----------|---------|---------|
| `FRED_API_KEY` | FRED JSON API (higher rate limit) | Public CSV endpoint |
| `BLOOMBERG_HOST` | Bloomberg BSAPI host:port | Disabled |
| `REFINITIV_APP_KEY` | Refinitiv Data API key | Disabled |

## Caching

### In-Memory Cache
- Default TTL: 3600 seconds (1 hour)
- Thread-safe via `RLock`
- Configurable via `cache_ttl_seconds` parameter

### Disk Cache
- Optional JSON persistence
- Share snapshots across processes
- Enable via `cache_path` parameter
- Example: `cache_path="/var/cache/frtb_market.json"`

## Fallback Behavior

The feed **never fails** — it always returns valid `MarketConditions`:

1. Try **Bloomberg/Refinitiv** (if configured)
2. Fall back to **FRED** (public, free)
3. Fall back to **yfinance** (delayed, free)
4. Use **hardcoded conservative values** (slightly above historical medians)

All fallbacks are logged with source information for audit trail.

## Comparison with A-IRB Implementation

The FRTB implementation follows the same architecture as [a_irb.py](backend/engines/a_irb.py#L169-L759):

| Feature | A-IRB (`USMacroDataFeed`) | FRTB (`MarketDataFeed`) |
|---------|---------------------------|-------------------------|
| **Three-tier fallback** | ✓ | ✓ |
| **Thread-safe caching** | ✓ | ✓ |
| **Disk cache** | ✓ | ✓ |
| **Bloomberg integration** | ✓ | ✓ |
| **FRED integration** | ✓ | ✓ |
| **yfinance integration** | ✓ | ✓ |
| **Manual injection** | ✓ | ✓ |
| **Conservative fallbacks** | ✓ | ✓ |

**Key Differences**:
- A-IRB focuses on **macroeconomic indicators** (GDP, unemployment, credit defaults)
- FRTB focuses on **market volatility indicators** (VIX, spreads, implied vol)
- Both support the same three-tier fetch architecture

## Demo Script

Run the demo to see all features in action:

```bash
python demo_frtb_market_data.py
```

The demo shows:
1. Basic market data fetching with fallback
2. Configuration with API keys
3. Manual injection for scenarios
4. Integration with FRTB engine and dynamic risk weights
5. Complete data source map and availability

## Regulatory Compliance

- **Regulatory SBM capital** always uses prescribed MAR21 risk weights (no dynamic adjustment)
- **Dynamic parameter adjustment** is for internal stress testing and ICAAP only
- Market regime classification follows stress index thresholds:
  - Normal: stress < 30%
  - Stressed: 30% ≤ stress < 65%
  - Crisis: stress ≥ 65%

## Installation

### Minimal (public data only)
```bash
# No additional dependencies required
# Uses standard library urllib for FRED
```

### Optional Bloomberg
```bash
pip install blpapi
export BLOOMBERG_HOST="localhost:8194"
```

### Optional Refinitiv
```bash
pip install refinitiv-data
export REFINITIV_APP_KEY="your_key"
```

### Optional yfinance
```bash
pip install yfinance
```

## Logging

The module logs data source information at appropriate levels:

- **INFO**: Successful fetches, regime classification, cache loads
- **DEBUG**: Individual source attempts, series values, cache hits
- **WARNING**: All tiers failed (using fallback), cache failures

Example log output:
```
INFO - MarketDataFeed initialized: FRED=public-only, Bloomberg=disabled, Refinitiv=disabled
INFO - Fetching fresh market conditions from external sources
DEBUG - VIX: 18.52 (source: FRED)
DEBUG - HY Spread: 412.00 (source: FRED)
WARNING - FX Vol: all sources failed, using fallback 9.00
INFO - Market conditions: VIX=18.5, HY=412bp, stress=0.23 (normal)
```

## Testing

The implementation includes comprehensive fallback handling:

1. **Network failures**: Graceful degradation to next tier
2. **Invalid data**: NaN/negative checks before acceptance
3. **Cache expiration**: Automatic refresh when TTL exceeded
4. **Thread safety**: Concurrent access to shared cache

## Future Enhancements

Potential improvements:
- [ ] Support for additional regional VIX indices (VSTOXX, VNKY)
- [ ] Multi-currency credit spread sources (EUR IG/HY, GBP)
- [ ] Realized volatility calculation for all asset classes
- [ ] Historical time series caching for backtesting
- [ ] WebSocket support for real-time streaming (Bloomberg)

## References

- A-IRB implementation: [backend/engines/a_irb.py](backend/engines/a_irb.py#L169-L759)
- FRED API documentation: https://fred.stlouisfed.org/docs/api/fred/
- Bloomberg BSAPI: https://www.bloomberg.com/professional/support/api-library/
- Refinitiv Data API: https://developers.refinitiv.com/en/api-catalog/refinitiv-data-platform/refinitiv-data-library-for-python
