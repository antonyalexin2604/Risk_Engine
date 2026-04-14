#!/usr/bin/env python3
"""
PROMETHEUS Risk Platform
Demo: Market Data Provider Architecture

Shows how to configure and use pluggable market data sources
for CDS spreads in A-IRB calculations.
"""

import logging
from datetime import date
from backend.data_sources import (
    MarketDataSource,
    CDSSpreadService
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)

logger = logging.getLogger(__name__)


def demo_static_provider():
    """Demo static test provider (default for development)."""
    logger.info("=" * 70)
    logger.info("DEMO 1: Static Test Provider")
    logger.info("=" * 70)
    
    service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.STATIC_TEST
    )
    
    # Fetch spreads for a few counterparties
    test_obligors = ["CPTY-0001", "CPTY-0050", "CPTY-0099"]
    
    for obligor_id in test_obligors:
        spreads = service.get_spreads_for_obligor(obligor_id)
        if spreads:
            logger.info(
                "%-12s | 1Y: %6.1f bps | 3Y: %6.1f bps | 5Y: %6.1f bps | RR: %.1f%%",
                obligor_id,
                spreads.tenor_1y,
                spreads.tenor_3y,
                spreads.tenor_5y,
                spreads.recovery_assumption * 100
            )
        else:
            logger.warning("%-12s | No spread data available", obligor_id)
    
    # Show cache stats
    stats = service.get_cache_stats()
    logger.info("Cache stats: %s", stats)


def demo_fallback_chain():
    """Demo fallback from Bloomberg to static test provider."""
    logger.info("=" * 70)
    logger.info("DEMO 2: Fallback Chain (Bloomberg → StaticTest)")
    logger.info("=" * 70)
    
    # Bloomberg will fail (not installed), fall back to static
    service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.BLOOMBERG,
        fallback_source=MarketDataSource.STATIC_TEST,
        bloomberg_host="localhost",
        bloomberg_port=8194
    )
    
    obligor_id = "CPTY-0025"
    logger.info("Attempting to fetch spreads for %s...", obligor_id)
    
    spreads = service.get_spreads_for_obligor(obligor_id)
    if spreads:
        logger.info(
            "SUCCESS via fallback: 1Y=%6.1f bps, 3Y=%6.1f bps, 5Y=%6.1f bps",
            spreads.tenor_1y,
            spreads.tenor_3y,
            spreads.tenor_5y
        )
    else:
        logger.error("FAILED: Both primary and fallback providers unavailable")


def demo_bulk_fetch():
    """Demo bulk fetching for multiple obligors."""
    logger.info("=" * 70)
    logger.info("DEMO 3: Bulk Fetch")
    logger.info("=" * 70)
    
    service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.STATIC_TEST
    )
    
    obligor_ids = [f"CPTY-{i:04d}" for i in range(1, 11)]
    results = service.get_spreads_bulk(obligor_ids, as_of_date=date.today())
    
    success_count = sum(1 for v in results.values() if v is not None)
    logger.info("Fetched spreads for %d/%d obligors", success_count, len(obligor_ids))
    
    for obligor_id, spreads in results.items():
        if spreads:
            logger.info(
                "  %s: 5Y spread = %6.1f bps",
                obligor_id,
                spreads.tenor_5y
            )


def demo_integration_with_airb():
    """Show how to integrate with A-IRB engine."""
    logger.info("=" * 70)
    logger.info("DEMO 4: Integration with A-IRB Engine")
    logger.info("=" * 70)
    
    # Create service
    service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.STATIC_TEST
    )
    
    # Simulate A-IRB workflow
    obligor_id = "CPTY-0033"
    logger.info("A-IRB calculation for %s...", obligor_id)
    
    # 1. Fetch market-implied CDS spreads
    cds_spreads = service.get_spreads_for_obligor(obligor_id)
    
    if cds_spreads:
        logger.info("  Market CDS spreads fetched:")
        logger.info("    1Y: %.1f bps", cds_spreads.tenor_1y)
        logger.info("    3Y: %.1f bps", cds_spreads.tenor_3y)
        logger.info("    5Y: %.1f bps", cds_spreads.tenor_5y)
        
        # 2. Pass to A-IRB engine (simplified — actual integration needed)
        logger.info("  → Would pass cds_spreads to AIRB.compute_with_macro_overlay()")
        logger.info("  → Engine would calibrate market-implied PD term structure")
        logger.info("  → Then apply capital curve K(PD, LGD, M)")
    else:
        logger.warning("  No CDS spreads available — falling back to internal PD model")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PROMETHEUS — Market Data Provider Architecture Demo")
    print("=" * 70 + "\n")
    
    demo_static_provider()
    print()
    demo_fallback_chain()
    print()
    demo_bulk_fetch()
    print()
    demo_integration_with_airb()
    
    print("\n" + "=" * 70)
    print("CONFIGURATION GUIDE")
    print("=" * 70)
    print("""
To switch data sources, set environment variables:

  # Use Bloomberg Terminal (requires blpapi)
  export MARKET_DATA_SOURCE=bloomberg
  export BLOOMBERG_HOST=localhost
  export BLOOMBERG_PORT=8194
  
  # Use Refinitiv Eikon (requires refinitiv.data)
  export MARKET_DATA_SOURCE=refinitiv
  export REFINITIV_APP_KEY=your_app_key
  export REFINITIV_USERNAME=your_username
  
  # Use internal REST API
  export MARKET_DATA_SOURCE=internal
  export INTERNAL_API_URL=https://risk-api.yourbank.com
  export INTERNAL_API_KEY=your_api_key
  
  # Add fallback source
  export MARKET_DATA_FALLBACK=static_test

Or configure programmatically:
  
  from backend.data_sources import MarketDataSource, CDSSpreadService
  
  service = CDSSpreadService.from_config(
      primary_source=MarketDataSource.BLOOMBERG,
      fallback_source=MarketDataSource.STATIC_TEST,
      bloomberg_host="localhost",
      bloomberg_port=8194
  )
""")
