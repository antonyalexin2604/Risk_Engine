"""
PROMETHEUS Risk Platform
Market Data Sources — Pluggable provider architecture
"""

from backend.data_sources.market_data_provider import (
    MarketDataProvider,
    MarketDataConfig,
    MarketDataSource,
    BloombergProvider,
    RefinitivProvider,
    InternalFeedProvider,
    StaticTestProvider,
    create_provider
)
from backend.data_sources.cds_spread_service import CDSSpreadService

__all__ = [
    "MarketDataProvider",
    "MarketDataConfig",
    "MarketDataSource",
    "BloombergProvider",
    "RefinitivProvider",
    "InternalFeedProvider",
    "StaticTestProvider",
    "create_provider",
    "CDSSpreadService",
]
