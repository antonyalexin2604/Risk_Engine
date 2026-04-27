# Market Data Provider Architecture

## Overview

PROMETHEUS now supports **pluggable market data sources** for real-time CDS spreads, recovery rates, and risk-free rates. This architecture enables seamless integration with:

- **Bloomberg Terminal** (via `blpapi`)
- **Refinitiv/LSEG Eikon** (via `refinitiv.data`)
- **Internal REST APIs** (custom feeds)
- **Static test data** (development/testing)

The system uses intelligent fallback chains and caching to ensure reliability.

---

## Architecture Components

### 1. Abstract Interface
`MarketDataProvider` (abstract base class) defines the contract:

```python
from backend.data_sources import MarketDataProvider

class MarketDataProvider(ABC):
    def fetch_cds_spreads(obligor_id, tenor_years, as_of_date) -> Dict[float, float]
    def fetch_recovery_rate(obligor_id, as_of_date) -> float
    def fetch_risk_free_rate(currency, tenor_years, as_of_date) -> float
    def is_available() -> bool
```

### 2. Concrete Providers

#### Bloomberg Provider
```python
from backend.data_sources import BloombergProvider

provider = BloombergProvider(config)
# Connects via blpapi to Bloomberg Terminal
# Fetches CDS spreads: "MSFT US 5Y Corp Curve" → PX_LAST
```

**Requirements:**
- Bloomberg Terminal running locally
- `blpapi` Python library installed
- Valid Bloomberg subscription

#### Refinitiv Provider
```python
from backend.data_sources import RefinitivProvider

provider = RefinitivProvider(config)
# Connects via refinitiv.data to Eikon/Workspace
# Fetches CDS spreads using RIC codes
```

**Requirements:**
- Refinitiv Eikon Desktop or Workspace
- `refinitiv.data` library installed
- Valid application key and username

#### Internal Feed Provider
```python
from backend.data_sources import InternalFeedProvider

provider = InternalFeedProvider(config)
# Queries your bank's internal REST API
# Example endpoint: GET /api/cds/spreads/{obligor_id}
```

**Requirements:**
- Internal API endpoint URL
- API key for authentication

#### Static Test Provider
```python
from backend.data_sources import StaticTestProvider

provider = StaticTestProvider(config)
# Uses hardcoded test data from _MARKET_SPREADS_BPS
# Approximates term structure from 5Y spreads
```

**Use case:** Development, testing, demos without external dependencies

### 3. High-Level Service
`CDSSpreadService` wraps providers with:
- **Automatic fallback** (primary → fallback provider)
- **In-memory caching** (5-minute TTL by default)
- **Bulk fetching** for multiple obligors
- **Conversion** to `CreditSpreadsData` format for A-IRB

```python
from backend.data_sources import CDSSpreadService, MarketDataSource

service = CDSSpreadService.from_config(
    primary_source=MarketDataSource.BLOOMBERG,
    fallback_source=MarketDataSource.STATIC_TEST
)

spreads = service.get_spreads_for_obligor("CPTY-0001")
# Returns: CreditSpreadsData(tenor_1y=42.5, tenor_3y=65.0, tenor_5y=88.0, ...)
```

---

## Configuration

### Environment Variables
Set these to configure the active data source:

```bash
# Primary source (bloomberg/refinitiv/internal/static_test)
export MARKET_DATA_SOURCE=bloomberg

# Fallback source (optional)
export MARKET_DATA_FALLBACK=static_test

# Bloomberg settings
export BLOOMBERG_HOST=localhost
export BLOOMBERG_PORT=8194

# Refinitiv settings
export REFINITIV_APP_KEY=your_app_key
export REFINITIV_USERNAME=your_username

# Internal feed settings
export INTERNAL_API_URL=https://risk-api.yourbank.com
export INTERNAL_API_KEY=your_api_key

# Cache settings
export MARKET_DATA_CACHE_TTL=300  # seconds
export MARKET_DATA_USE_CACHE=true
```

### Programmatic Configuration
Or configure directly in code:

```python
from backend.data_sources import MarketDataSource, CDSSpreadService

service = CDSSpreadService.from_config(
    primary_source=MarketDataSource.REFINITIV,
    fallback_source=MarketDataSource.INTERNAL,
    refinitiv_app_key="YOUR_KEY",
    refinitiv_username="YOUR_USERNAME",
    internal_api_url="https://risk-api.yourbank.com",
    internal_api_key="YOUR_API_KEY"
)
```

### Global Config Object
Centralized configuration in `backend/config.py`:

```python
from backend.config import MARKET_DATA

# Access configured values
print(MARKET_DATA.primary_source)  # e.g., "bloomberg"
print(MARKET_DATA.bloomberg_host)  # e.g., "localhost"
print(MARKET_DATA.cache_ttl_seconds)  # e.g., 300
```

---

## Usage Examples

### Basic: Fetch Spreads
```python
from backend.data_sources import CDSSpreadService, MarketDataSource

service = CDSSpreadService.from_config(
    primary_source=MarketDataSource.STATIC_TEST
)

spreads = service.get_spreads_for_obligor("CPTY-0001")
print(f"5Y CDS spread: {spreads.tenor_5y} bps")
```

### Advanced: Fallback Chain
```python
# Try Bloomberg first, fall back to internal API if unavailable
service = CDSSpreadService.from_config(
    primary_source=MarketDataSource.BLOOMBERG,
    fallback_source=MarketDataSource.INTERNAL,
    bloomberg_host="localhost",
    bloomberg_port=8194,
    internal_api_url="https://risk-api.yourbank.com",
    internal_api_key="secret_key"
)

spreads = service.get_spreads_for_obligor("CPTY-0050")
# Tries Bloomberg → if unavailable, tries Internal → returns None if both fail
```

### Bulk Fetching
```python
from datetime import date

obligor_ids = ["CPTY-0001", "CPTY-0002", "CPTY-0003"]
results = service.get_spreads_bulk(obligor_ids, as_of_date=date(2024, 1, 15))

for obligor_id, spreads in results.items():
    if spreads:
        print(f"{obligor_id}: 5Y = {spreads.tenor_5y} bps")
```

### Integration with A-IRB
```python
from backend.engines.a_irb import AIRB
from backend.data_sources import CDSSpreadService, MarketDataSource

# Initialize service
service = CDSSpreadService.from_config(
    primary_source=MarketDataSource.BLOOMBERG,
    fallback_source=MarketDataSource.STATIC_TEST
)

# Fetch CDS spreads for counterparty
obligor_id = "CPTY-0025"
cds_spreads = service.get_spreads_for_obligor(obligor_id)

# Pass to A-IRB for market-implied PD calibration
airb = AIRB()
ead = airb.compute_with_macro_overlay(
    pd_base=0.02,
    lgd=0.45,
    exposure=1_000_000,
    maturity=3.0,
    cds_spreads=cds_spreads  # Market data drives PD term structure
)
```

---

## Testing

### Demo Script
Run the included demo to see all features:

```bash
cd /Users/aaron/Documents/Project/Prometheus
./demo_market_data.py
```

Output shows:
1. Static provider usage
2. Fallback chain (Bloomberg → StaticTest)
3. Bulk fetching
4. A-IRB integration pattern

### Unit Tests
Add tests for custom providers:

```python
from backend.data_sources import InternalFeedProvider, MarketDataConfig, MarketDataSource

def test_internal_provider():
    config = MarketDataConfig(
        source=MarketDataSource.INTERNAL,
        internal_api_url="https://test-api.example.com",
        internal_api_key="test_key"
    )
    provider = InternalFeedProvider(config)
    
    spreads = provider.fetch_cds_spreads("CPTY-0001", tenor_years=[1, 3, 5])
    assert 1.0 in spreads
    assert 3.0 in spreads
    assert 5.0 in spreads
```

---

## Implementation Status

### ✅ Complete
- Abstract `MarketDataProvider` interface
- `BloombergProvider` (skeleton — ready for blpapi integration)
- `RefinitivProvider` (skeleton — ready for refinitiv.data integration)
- `InternalFeedProvider` (skeleton — ready for REST API integration)
- `StaticTestProvider` (fully functional with test data)
- `CDSSpreadService` with caching and fallback logic
- Configuration management in `backend/config.py`
- Demo script: `demo_market_data.py`

### ⏳ Pending
- **Bloomberg blpapi integration:** Complete `_fetch_field()` method using `refdata` service
- **Refinitiv API integration:** Complete spread fetching using `get_data()` method
- **Internal API integration:** Implement actual HTTP requests to your bank's API
- **A-IRB engine integration:** Update `AIRB.compute_with_macro_overlay()` to accept `MarketDataProvider`
- **Ticker mapping:** Build `obligor_id → Bloomberg ticker` lookup table
- **RIC mapping:** Build `obligor_id → Refinitiv RIC` lookup table

---

## Production Checklist

Before deploying to production:

- [ ] Install optional dependencies:
  ```bash
  pip install blpapi  # Bloomberg
  pip install refinitiv-data  # Refinitiv
  ```

- [ ] Configure production data source:
  ```bash
  export MARKET_DATA_SOURCE=bloomberg
  export MARKET_DATA_FALLBACK=internal
  ```

- [ ] Set up ticker/RIC mappings in database or config file

- [ ] Implement authentication for Bloomberg/Refinitiv sessions

- [ ] Configure internal API endpoint and credentials

- [ ] Test fallback chain thoroughly:
  - Simulate Bloomberg connection failure → verify fallback to internal
  - Simulate network outage → verify graceful degradation

- [ ] Monitor cache hit rates:
  ```python
  stats = service.get_cache_stats()
  print(f"Cache hit rate: {stats['valid_entries'] / stats['total_entries']:.1%}")
  ```

- [ ] Set up logging for data source failures

- [ ] Implement retry logic for transient network errors

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    A-IRB Engine                             │
│  • Needs CDS spreads for market-implied PD calibration      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
           ┌───────────────────────┐
           │  CDSSpreadService     │
           │  • Caching            │
           │  • Fallback logic     │
           │  • Bulk fetching      │
           └───────────┬───────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
           ▼                       ▼
   ┌──────────────┐        ┌──────────────┐
   │   Primary    │        │   Fallback   │
   │   Provider   │        │   Provider   │
   └──────┬───────┘        └──────┬───────┘
          │                       │
    ┌─────┴─────┬─────┬──────────┼──────────┬──────────┐
    ▼           ▼     ▼          ▼          ▼          ▼
┌─────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Bloomberg│ │Refin.│ │Intern│ │Static│ │Custom│ │ ...  │
│Provider │ │Provid│ │alFeed│ │Test  │ │Provid│ │      │
└─────────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘
     │          │        │        │
     ▼          ▼        ▼        ▼
┌─────────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Bloomberg│ │Refini│ │Bank's│ │Test  │
│Terminal │ │tiv   │ │REST  │ │Data  │
│         │ │Eikon │ │API   │ │      │
└─────────┘ └──────┘ └──────┘ └──────┘
```

---

## Next Steps

1. **Complete Bloomberg integration:**
   - Implement `blpapi` reference data requests
   - Add subscription for real-time CDS updates
   - Build obligor → ticker mapping table

2. **Complete Refinitiv integration:**
   - Implement `refinitiv.data.get_data()` calls
   - Handle RIC code lookups
   - Add error handling for Eikon Desktop connectivity

3. **Wire to A-IRB engine:**
   - Update `AIRB.compute_with_macro_overlay()` signature
   - Add market-implied PD bootstrapping from CDS spreads
   - Document calibration methodology

4. **Production hardening:**
   - Add circuit breaker pattern for provider failures
   - Implement exponential backoff for retries
   - Set up monitoring/alerting for data staleness

---

## Support

For questions or issues:
- Review `demo_market_data.py` for working examples
- Check provider logs: `logger.info()` statements show connection status
- Test with `MARKET_DATA_SOURCE=static_test` first (no external dependencies)

