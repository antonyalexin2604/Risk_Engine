"""
PROMETHEUS Risk Platform
CDS Spread Service — High-level service for fetching CDS spread data

Wraps market data providers with caching, fallback logic, and
conversion to CreditSpreadsData format for A-IRB engine.
"""

from __future__ import annotations
import logging
from typing import Optional, List
from datetime import date, datetime, timedelta

from backend.data_sources.market_data_provider import (
    MarketDataProvider,
    MarketDataConfig,
    MarketDataSource,
    create_provider
)
from backend.engines.a_irb import CreditSpreadsData

logger = logging.getLogger(__name__)


class CDSSpreadService:
    """
    Service for fetching CDS spreads with intelligent fallback.
    
    Tries primary provider first, falls back to secondary if unavailable.
    Caches results to minimize API calls.
    
    Usage:
        service = CDSSpreadService.from_config(
            primary_source=MarketDataSource.BLOOMBERG,
            fallback_source=MarketDataSource.STATIC_TEST
        )
        spreads = service.get_spreads_for_obligor("CPTY-0001")
    """

    def __init__(
        self,
        primary_provider: MarketDataProvider,
        fallback_provider: Optional[MarketDataProvider] = None
    ):
        self.primary = primary_provider
        self.fallback = fallback_provider
        self._cache: dict = {}
        self._cache_ttl = timedelta(minutes=5)
        logger.info(
            "CDS Spread Service initialized (primary=%s, fallback=%s)",
            primary_provider.__class__.__name__,
            fallback_provider.__class__.__name__ if fallback_provider else "None"
        )

    @classmethod
    def from_config(
        cls,
        primary_source: MarketDataSource,
        fallback_source: Optional[MarketDataSource] = None,
        **config_kwargs
    ) -> "CDSSpreadService":
        """
        Create service from source enums.
        
        Example:
            service = CDSSpreadService.from_config(
                primary_source=MarketDataSource.BLOOMBERG,
                fallback_source=MarketDataSource.STATIC_TEST,
                bloomberg_host="localhost",
                bloomberg_port=8194
            )
        """
        primary_config = MarketDataConfig(source=primary_source, **config_kwargs)
        primary = create_provider(primary_config)
        
        fallback = None
        if fallback_source is not None:
            fallback_config = MarketDataConfig(source=fallback_source, **config_kwargs)
            fallback = create_provider(fallback_config)
        
        return cls(primary, fallback)

    def get_spreads_for_obligor(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None,
        use_cache: bool = True
    ) -> Optional[CreditSpreadsData]:
        """
        Fetch CDS spreads for an obligor and return as CreditSpreadsData.
        
        Args:
            obligor_id: Internal obligor identifier
            as_of_date: Historical date (None = live)
            use_cache: Whether to use cached data
        
        Returns:
            CreditSpreadsData or None if unavailable
        """
        as_of_date = as_of_date or date.today()
        cache_key = f"{obligor_id}_{as_of_date.isoformat()}"
        
        # Check cache
        if use_cache and cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            if datetime.now() - cached_time < self._cache_ttl:
                logger.debug("Cache hit for %s", obligor_id)
                return cached_data
        
        # Try primary provider
        try:
            if self.primary.is_available():
                spreads = self.primary.fetch_cds_spreads(
                    obligor_id, tenor_years=[1, 3, 5], as_of_date=as_of_date
                )
                recovery = self.primary.fetch_recovery_rate(obligor_id, as_of_date)
                
                if spreads and any(v is not None for v in spreads.values()):
                    result = CreditSpreadsData(
                        date=as_of_date,
                        obligor_id=obligor_id,
                        tenor_1y=spreads.get(1.0, 0.0) or 0.0,
                        tenor_3y=spreads.get(3.0, 0.0) or 0.0,
                        tenor_5y=spreads.get(5.0, 0.0) or 0.0,
                        recovery_assumption=recovery,
                        bid_ask_spread=10.0  # Default
                    )
                    self._cache[cache_key] = (result, datetime.now())
                    logger.info("Primary provider: fetched spreads for %s", obligor_id)
                    return result
        except Exception as e:
            logger.warning("Primary provider failed for %s: %s", obligor_id, e)
        
        # Try fallback provider
        if self.fallback is not None:
            try:
                if self.fallback.is_available():
                    spreads = self.fallback.fetch_cds_spreads(
                        obligor_id, tenor_years=[1, 3, 5], as_of_date=as_of_date
                    )
                    recovery = self.fallback.fetch_recovery_rate(obligor_id, as_of_date)
                    
                    if spreads and any(v is not None for v in spreads.values()):
                        result = CreditSpreadsData(
                            date=as_of_date,
                            obligor_id=obligor_id,
                            tenor_1y=spreads.get(1.0, 0.0) or 0.0,
                            tenor_3y=spreads.get(3.0, 0.0) or 0.0,
                            tenor_5y=spreads.get(5.0, 0.0) or 0.0,
                            recovery_assumption=recovery,
                            bid_ask_spread=15.0  # Wider for fallback
                        )
                        self._cache[cache_key] = (result, datetime.now())
                        logger.info("Fallback provider: fetched spreads for %s", obligor_id)
                        return result
            except Exception as e:
                logger.warning("Fallback provider failed for %s: %s", obligor_id, e)
        
        logger.warning("No CDS spread data available for %s", obligor_id)
        return None

    def get_spreads_bulk(
        self,
        obligor_ids: List[str],
        as_of_date: Optional[date] = None
    ) -> dict[str, Optional[CreditSpreadsData]]:
        """
        Fetch CDS spreads for multiple obligors.
        
        Returns:
            Dict mapping obligor_id to CreditSpreadsData (or None if unavailable)
        """
        results = {}
        for obligor_id in obligor_ids:
            results[obligor_id] = self.get_spreads_for_obligor(obligor_id, as_of_date)
        return results

    def clear_cache(self):
        """Clear cached spread data."""
        self._cache.clear()
        logger.info("CDS spread cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        valid_entries = sum(
            1 for (data, ts) in self._cache.values()
            if datetime.now() - ts < self._cache_ttl
        )
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
        }
