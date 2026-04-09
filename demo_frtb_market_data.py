"""
FRTB Market Data Feed Demo
Demonstrates the new three-tier external data sourcing capability.

This demo shows:
1. How to use the enhanced MarketDataFeed to fetch real-time market data
2. Three-tier fallback: Bloomberg → FRED/yfinance → hardcoded defaults
3. Caching and manual injection capabilities
4. Integration with FRTB engine for dynamic parameter adjustment
"""

import logging
from datetime import date
from backend.engines.frtb import MarketDataFeed, MarketConditions, FRTBConfig, FRTBEngine

# Configure logging to see data source information
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def demo_basic_fetch():
    """Demonstrate basic market data fetching with three-tier fallback."""
    logger.info("\n" + "="*80)
    logger.info("DEMO 1: Basic Market Data Fetching")
    logger.info("="*80)
    
    # Initialize feed (no API keys - will use public FRED + yfinance)
    feed = MarketDataFeed(cache_ttl_seconds=3600)
    
    # Fetch current conditions (will try Bloomberg → FRED → yfinance → fallback)
    conditions = feed.get_current_conditions()
    
    logger.info("\nFetched Market Conditions:")
    logger.info(f"  Date:              {conditions.date}")
    logger.info(f"  VIX Level:         {conditions.vix_level:.2f}")
    logger.info(f"  Equity Vol Index:  {conditions.equity_vol_index:.2f}%")
    logger.info(f"  IG Spread:         {conditions.credit_spread_ig:.0f} bp")
    logger.info(f"  HY Spread:         {conditions.credit_spread_hy:.0f} bp")
    logger.info(f"  FX Vol Index:      {conditions.fx_vol_index:.2f}%")
    logger.info(f"  Commodity Vol:     {conditions.cmdty_vol_index:.2f}%")
    logger.info(f"  IR Vol (MOVE):     {conditions.ir_vol_swaption:.0f} bp")
    logger.info(f"\n  Stress Level:      {conditions.stress_level():.2%}")
    logger.info(f"  Market Regime:     {conditions.regime().value.upper()}")
    
    # Demonstrate caching
    logger.info("\nSecond fetch (should use cache):")
    conditions2 = feed.get_current_conditions()
    assert conditions == conditions2, "Cache should return same object"
    logger.info("  ✓ Cache working correctly")


def demo_with_api_keys():
    """Demonstrate initialization with API keys (optional)."""
    logger.info("\n" + "="*80)
    logger.info("DEMO 2: Configuration with API Keys")
    logger.info("="*80)
    
    # This example shows how to configure with API keys
    # In production, set environment variables or pass keys directly
    feed = MarketDataFeed(
        cache_ttl_seconds=1800,  # 30-minute cache
        fred_api_key=None,        # Will check FRED_API_KEY env var
        bloomberg_host=None,      # Will check BLOOMBERG_HOST env var
        refinitiv_key=None,       # Will check REFINITIV_APP_KEY env var
        cache_path="/tmp/frtb_market_cache.json"  # Optional disk cache
    )
    
    logger.info("\nMarketDataFeed Configuration:")
    logger.info("  Cache TTL:         1800 seconds (30 minutes)")
    logger.info("  Disk Cache:        /tmp/frtb_market_cache.json")
    logger.info("  FRED API:          Enabled if FRED_API_KEY env var set")
    logger.info("  Bloomberg:         Enabled if BLOOMBERG_HOST env var set")
    logger.info("  Refinitiv:         Enabled if REFINITIV_APP_KEY env var set")


def demo_manual_injection():
    """Demonstrate manual injection for testing/scenarios."""
    logger.info("\n" + "="*80)
    logger.info("DEMO 3: Manual Market Condition Injection")
    logger.info("="*80)
    
    feed = MarketDataFeed()
    
    # Inject crisis scenario
    logger.info("\nInjecting CRISIS scenario:")
    crisis_conditions = feed.inject(
        vix_level=75.0,           # Extreme fear
        credit_spread_hy=1200.0,  # 12% HY spread
        equity_vol_index=85.0,    # Very high equity vol
    )
    
    logger.info(f"  VIX:               {crisis_conditions.vix_level:.2f}")
    logger.info(f"  HY Spread:         {crisis_conditions.credit_spread_hy:.0f} bp")
    logger.info(f"  Equity Vol:        {crisis_conditions.equity_vol_index:.2f}%")
    logger.info(f"  Stress Level:      {crisis_conditions.stress_level():.2%}")
    logger.info(f"  Regime:            {crisis_conditions.regime().value.upper()}")
    
    # Inject normal scenario
    logger.info("\nInjecting NORMAL scenario:")
    normal_conditions = feed.inject(
        vix_level=12.0,
        credit_spread_hy=350.0,
        equity_vol_index=15.0,
    )
    
    logger.info(f"  VIX:               {normal_conditions.vix_level:.2f}")
    logger.info(f"  HY Spread:         {normal_conditions.credit_spread_hy:.0f} bp")
    logger.info(f"  Equity Vol:        {normal_conditions.equity_vol_index:.2f}%")
    logger.info(f"  Stress Level:      {normal_conditions.stress_level():.2%}")
    logger.info(f"  Regime:            {normal_conditions.regime().value.upper()}")


def demo_frtb_integration():
    """Demonstrate integration with FRTB engine for dynamic parameters."""
    logger.info("\n" + "="*80)
    logger.info("DEMO 4: FRTB Engine Integration")
    logger.info("="*80)
    
    # Create config with market conditions enabled
    config = FRTBConfig(use_market_conditions=True)
    
    # Initialize feed
    feed = MarketDataFeed()
    config.market_data_feed = feed
    
    # Inject a stressed scenario
    logger.info("\nInjecting STRESSED market scenario:")
    feed.inject(
        vix_level=35.0,
        credit_spread_hy=650.0,
        equity_vol_index=45.0,
        fx_vol_index=12.0,
    )
    
    # Show how risk weights adjust dynamically
    logger.info("\nDynamic Risk Weight Adjustment:")
    market = feed.cached
    adjuster = config.dynamic_adjuster
    
    if market and adjuster:
        logger.info(f"\n  Market Regime:     {market.regime().value.upper()}")
        logger.info(f"  Stress Level:      {market.stress_level():.2%}")
        
        # Show base vs. adjusted risk weights for different classes
        for risk_class in ["EQ_LARGE", "CSR_NS", "FX"]:
            base_rw = config.delta_rw.get(risk_class, [0.15])
            
            # Regulatory SBM (no adjustment)
            regulatory_rw = adjuster.adjust_risk_weights(
                market, risk_class, regulatory_sbm=True
            )
            
            # Internal stress (with adjustment)
            stress_rw = adjuster.adjust_risk_weights(
                market, risk_class, regulatory_sbm=False
            )
            
            logger.info(f"\n  {risk_class}:")
            logger.info(f"    Base RW (first):     {base_rw[0]:.4f}")
            logger.info(f"    Regulatory (MAR21):  {regulatory_rw[0]:.4f}")
            logger.info(f"    Stress-adjusted:     {stress_rw[0]:.4f}")
            logger.info(f"    Multiplier:          {stress_rw[0]/base_rw[0]:.2f}x")


def demo_data_sources():
    """Show which data sources are available and how fallback works."""
    logger.info("\n" + "="*80)
    logger.info("DEMO 5: Data Source Availability")
    logger.info("="*80)
    
    feed = MarketDataFeed()
    
    logger.info("\nData Source Map:")
    logger.info("\nTier 1 (Bloomberg/Refinitiv):")
    logger.info("  VIX:               VIX Index (PX_LAST)")
    logger.info("  Equity Vol:        VXO Index (PX_LAST)")
    logger.info("  IG Spread:         LUACOAS Index (US IG OAS)")
    logger.info("  HY Spread:         LF98OAS Index (US HY OAS)")
    logger.info("  FX Vol:            JPMVXYGL Index (JPM FX VIX)")
    logger.info("  Commodity Vol:     CRYTR Index (CRY TR Index)")
    logger.info("  IR Vol:            MOVE Index (Merrill Option Vol)")
    
    logger.info("\nTier 2 (FRED - Federal Reserve Economic Data):")
    logger.info("  VIX:               VIXCLS")
    logger.info("  Equity Vol:        VXEEMCLS (EM VIX)")
    logger.info("  IG Spread:         BAMLC0A0CMEY (BofA US Corp IG OAS)")
    logger.info("  HY Spread:         BAMLH0A0HYM2 (BofA US HY OAS)")
    logger.info("  FX Vol:            DEXJPUS (USD/JPY, calc realized vol)")
    logger.info("  IR Vol:            MOVE")
    
    logger.info("\nTier 3 (yfinance - 15-min delayed):")
    logger.info("  VIX:               ^VIX")
    logger.info("  Equity Vol:        ^VIX")
    logger.info("  Commodity Vol:     CL=F (WTI crude oil, calc realized)")
    
    logger.info("\nFallback (Conservative Defaults):")
    logger.info(f"  VIX:               {feed._FALLBACK['vix']}")
    logger.info(f"  Equity Vol:        {feed._FALLBACK['eq_vol']}%")
    logger.info(f"  IG Spread:         {feed._FALLBACK['ig_spread']*100:.0f} bp")
    logger.info(f"  HY Spread:         {feed._FALLBACK['hy_spread']*100:.0f} bp")
    logger.info(f"  FX Vol:            {feed._FALLBACK['fx_vol']}%")
    logger.info(f"  Commodity Vol:     {feed._FALLBACK['cmdty_vol']}%")
    logger.info(f"  IR Vol:            {feed._FALLBACK['ir_vol']} bp")


if __name__ == "__main__":
    logger.info("\n" + "="*80)
    logger.info("FRTB Market Data Feed - External Sourcing Demo")
    logger.info("="*80)
    logger.info("\nThis demo shows the new three-tier market data sourcing:")
    logger.info("  Tier 1: Bloomberg/Refinitiv (real-time, requires API)")
    logger.info("  Tier 2: FRED/yfinance (public, daily/15-min delayed)")
    logger.info("  Tier 3: Hardcoded fallback (never fails)")
    logger.info("\nAll demos use public data sources (FRED/yfinance) by default.")
    logger.info("To enable Bloomberg/Refinitiv, set environment variables:")
    logger.info("  - BLOOMBERG_HOST=localhost:8194")
    logger.info("  - REFINITIV_APP_KEY=your_key")
    logger.info("  - FRED_API_KEY=your_key (optional, increases rate limit)")
    
    try:
        demo_basic_fetch()
        demo_with_api_keys()
        demo_manual_injection()
        demo_frtb_integration()
        demo_data_sources()
        
        logger.info("\n" + "="*80)
        logger.info("All demos completed successfully! ✓")
        logger.info("="*80)
        
    except Exception as e:
        logger.error(f"\nDemo failed with error: {e}", exc_info=True)
        raise
