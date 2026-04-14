"""
PROMETHEUS — CVA Live Spreads Demo

Shows how to populate CVA inputs with live CDS spreads from
Bloomberg, Refinitiv, or test data sources.
"""

import logging
from datetime import date
from typing import Optional
from backend.engines.cva import CVAInput, CVAEngine, CVAMarketDataFeed
from backend.data_sources.cds_spread_service import CDSSpreadService
from backend.data_sources.market_data_provider import MarketDataSource

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def populate_cva_inputs_with_live_spreads(
    cva_inputs: list[CVAInput],
    spread_service: CDSSpreadService,
    as_of_date: Optional[date] = None,
) -> list[CVAInput]:
    """
    Fetch live CDS spreads and populate CVAInput.credit_spread_bps.
    
    Parameters
    ----------
    cva_inputs      : List of CVAInput objects (credit_spread_bps may be None)
    spread_service  : Configured CDSSpreadService instance
    as_of_date      : Date for historical spreads (None = live)
    
    Returns
    -------
    Updated list of CVAInput objects with credit_spread_bps populated.
    Counterparties with no available spread data retain credit_spread_bps=None
    and will fall back to the proxy cascade in CVAEngine.
    """
    as_of_date = as_of_date or date.today()
    
    # Collect all counterparty IDs that need spreads
    cpty_ids = [inp.counterparty_id for inp in cva_inputs]
    
    # Bulk fetch CDS spreads
    spreads_data = spread_service.get_spreads_bulk(cpty_ids, as_of_date)
    
    # Update CVAInput objects
    for inp in cva_inputs:
        spread_data = spreads_data.get(inp.counterparty_id)
        if spread_data is not None:
            # Use 5Y tenor by default (matches typical CVA duration)
            inp.credit_spread_bps = spread_data.tenor_5y
            inp.spread_source = "LIVE"
            logger.info(
                "Live spread: %s = %.0f bps (5Y tenor, source: primary/fallback provider)",
                inp.counterparty_id,
                inp.credit_spread_bps,
            )
        else:
            # Leave as None — CVAEngine will apply proxy cascade
            logger.warning(
                "No live spread for %s — will use proxy cascade (MAR50.32(3))",
                inp.counterparty_id,
            )
    
    return cva_inputs


def demo_cva_with_bloomberg():
    """
    Demo: CVA with live Bloomberg CDS spreads.
    
    Requirements:
      - Bloomberg Terminal running
      - blpapi installed: pip install blpapi
      - Bloomberg API service enabled
    """
    # Configure Bloomberg as primary source
    spread_service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.BLOOMBERG,
        fallback_source=MarketDataSource.STATIC_TEST,
        bloomberg_host="localhost",
        bloomberg_port=8194,
    )
    
    # Create CVA inputs (without spreads initially)
    cva_inputs = [
        CVAInput(
            counterparty_id="BAC",        # Bank of America
            netting_set_id="NS-001",
            ead=1_000_000,
            pd_1yr=0.0050,
            maturity_years=3.0,
            sector="Financials",
            credit_quality="IG",
            region="US",
        ),
        CVAInput(
            counterparty_id="JPM",        # JP Morgan
            netting_set_id="NS-002",
            ead=2_500_000,
            pd_1yr=0.0045,
            maturity_years=4.0,
            sector="Financials",
            credit_quality="IG",
            region="US",
        ),
        CVAInput(
            counterparty_id="T",          # AT&T
            netting_set_id="NS-003",
            ead=800_000,
            pd_1yr=0.0120,
            maturity_years=2.5,
            sector="Technology",
            credit_quality="BBB",
            region="US",
        ),
    ]
    
    # Populate with live spreads
    cva_inputs = populate_cva_inputs_with_live_spreads(cva_inputs, spread_service)
    
    # Configure CVA engine with SA-CVA approval and live market data
    market_feed = CVAMarketDataFeed(cache_ttl_seconds=900)
    engine = CVAEngine(
        sa_cva_approved=True,
        market_feed=market_feed,
        auto_refresh=True,
    )
    
    # Run CVA capital calculation
    result = engine.compute_portfolio_cva(
        inputs=cva_inputs,
        total_ccr_rwa=500_000,
        total_notional_eur=150_000_000_000,  # 150bn EUR
    )
    
    print("\n" + "="*80)
    print("CVA CAPITAL RESULT (Live Spreads)")
    print("="*80)
    print(f"Total RWA:         {result['total_rwa_cva']:>15,.0f}")
    print(f"Method:            {result['method']:>15}")
    print(f"Proxy spreads:     {result.get('spread_enriched_count', 0):>15} counterparties")
    print()
    
    print("Per-Counterparty Results:")
    print("-" * 80)
    for cpty_id, res in result['method_summary'].items():
        print(f"{cpty_id:<10} | Method: {res.method:<8} | RWA: {res.rwa_cva:>12,.0f} | "
              f"Spread: {res.spread_source}")
    print("="*80)


def demo_cva_with_test_data():
    """
    Demo: CVA with static test data (no external APIs required).
    
    Use this when Bloomberg/Refinitiv are not available.
    Test provider returns realistic synthetic spreads.
    """
    # Configure static test data as primary source
    spread_service = CDSSpreadService.from_config(
        primary_source=MarketDataSource.STATIC_TEST,
    )
    
    # Create CVA inputs
    cva_inputs = [
        CVAInput(
            counterparty_id="CPTY-0001",
            netting_set_id="NS-001",
            ead=1_000_000,
            pd_1yr=0.0080,
            maturity_years=3.0,
            sector="Financials",
            credit_quality="IG",
            region="US",
        ),
        CVAInput(
            counterparty_id="CPTY-0002",
            netting_set_id="NS-002",
            ead=1_500_000,
            pd_1yr=0.0200,
            maturity_years=2.0,
            sector="Energy",
            credit_quality="HY",
            region="US",
        ),
    ]
    
    # Populate with test spreads
    cva_inputs = populate_cva_inputs_with_live_spreads(cva_inputs, spread_service)
    
    # Configure CVA engine
    market_feed = CVAMarketDataFeed(cache_ttl_seconds=900)
    engine = CVAEngine(
        sa_cva_approved=True,
        market_feed=market_feed,
        auto_refresh=True,
    )
    
    # Run CVA capital calculation
    result = engine.compute_portfolio_cva(
        inputs=cva_inputs,
        total_ccr_rwa=300_000,
        total_notional_eur=120_000_000_000,  # 120bn EUR
    )
    
    print("\n" + "="*80)
    print("CVA CAPITAL RESULT (Test Data)")
    print("="*80)
    print(f"Total RWA:         {result['total_rwa_cva']:>15,.0f}")
    print(f"Method:            {result['method']:>15}")
    print(f"Proxy spreads:     {result.get('spread_enriched_count', 0):>15} counterparties")
    print()
    
    print("Per-Counterparty Results:")
    print("-" * 80)
    for cpty_id, res in result['method_summary'].items():
        print(f"{cpty_id:<12} | Method: {res.method:<8} | RWA: {res.rwa_cva:>12,.0f} | "
              f"Spread: {res.spread_source}")
    print("="*80)


def demo_manual_spread_injection():
    """
    Demo: Manually inject CDS spreads (e.g., from internal credit desk feed).
    """
    # Create CVA inputs
    cva_inputs = [
        CVAInput(
            counterparty_id="INTERNAL-001",
            netting_set_id="NS-001",
            ead=5_000_000,
            pd_1yr=0.0150,
            maturity_years=3.5,
            sector="Consumer",
            credit_quality="BBB",
            region="US",
            credit_spread_bps=250.0,      # ← Manually set spread
        ),
        CVAInput(
            counterparty_id="INTERNAL-002",
            netting_set_id="NS-002",
            ead=3_200_000,
            pd_1yr=0.0090,
            maturity_years=2.8,
            sector="Industrials",
            credit_quality="A",
            region="EUR",
            credit_spread_bps=140.0,      # ← Manually set spread
        ),
    ]
    
    # Mark as live spreads
    for inp in cva_inputs:
        inp.spread_source = "LIVE"
    
    # Configure CVA engine
    market_feed = CVAMarketDataFeed(cache_ttl_seconds=900)
    engine = CVAEngine(
        sa_cva_approved=True,
        market_feed=market_feed,
        auto_refresh=True,
    )
    
    # Run CVA capital calculation
    result = engine.compute_portfolio_cva(
        inputs=cva_inputs,
        total_ccr_rwa=400_000,
        total_notional_eur=180_000_000_000,  # 180bn EUR
    )
    
    print("\n" + "="*80)
    print("CVA CAPITAL RESULT (Manual Injection)")
    print("="*80)
    print(f"Total RWA:         {result['total_rwa_cva']:>15,.0f}")
    print(f"Method:            {result['method']:>15}")
    print(f"Proxy spreads:     {result.get('spread_enriched_count', 0):>15} counterparties")
    print()
    
    print("Per-Counterparty Results:")
    print("-" * 80)
    for cpty_id, res in result['method_summary'].items():
        print(f"{cpty_id:<15} | Method: {res.method:<8} | RWA: {res.rwa_cva:>12,.0f} | "
              f"Spread: {res.spread_source}")
    print("="*80)


if __name__ == "__main__":
    import sys
    
    print("PROMETHEUS CVA — Live Spreads Demo")
    print("Select demo:")
    print("  1. Bloomberg CDS spreads (requires Terminal)")
    print("  2. Static test data (no APIs required)")
    print("  3. Manual spread injection")
    
    choice = input("\nEnter choice [1-3]: ").strip()
    
    if choice == "1":
        demo_cva_with_bloomberg()
    elif choice == "2":
        demo_cva_with_test_data()
    elif choice == "3":
        demo_manual_spread_injection()
    else:
        print("Running test data demo (default)")
        demo_cva_with_test_data()
