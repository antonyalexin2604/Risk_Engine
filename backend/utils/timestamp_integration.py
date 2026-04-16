"""
PROMETHEUS Risk Platform
Timestamp Integration for Calculations

FILE PATH: backend/utils/timestamp_integration.py

Functions to inject timestamp data into calculation results before database storage.
"""

from typing import Dict, List, Any
from datetime import date
from backend.utils.calculation_timestamp import (
    get_current_calculation_timestamp,
    get_calculation_timestamp_for_date,
    CalculationTimestamp
)


def add_timestamp_to_exposure(
    exposure: Dict[str, Any],
    timestamp: CalculationTimestamp
) -> Dict[str, Any]:
    """
    Add timestamp fields to a single exposure record.
    
    Parameters
    ----------
    exposure : dict
        Exposure dictionary (e.g., banking book exposure, derivative position)
    timestamp : CalculationTimestamp
        Timestamp object for current calculation run
    
    Returns
    -------
    exposure : dict
        Updated exposure with timestamp fields
    
    Example
    -------
    >>> from backend.utils.calculation_timestamp import get_current_calculation_timestamp
    >>> ts = get_current_calculation_timestamp()
    >>> exposure = {'counterparty': 'ABC Bank', 'ead': 1000000, 'rwa': 500000}
    >>> exposure = add_timestamp_to_exposure(exposure, ts)
    >>> print(exposure['calculation_date_formatted'])
    'Apr-14-2026'
    """
    timestamp_fields = timestamp.to_db_dict()
    
    # Add all timestamp fields to exposure
    exposure.update(timestamp_fields)
    
    return exposure


def add_timestamp_to_exposures(
    exposures: List[Dict[str, Any]],
    timestamp: CalculationTimestamp
) -> List[Dict[str, Any]]:
    """
    Add timestamp fields to a list of exposure records.
    
    Parameters
    ----------
    exposures : list of dict
        List of exposure dictionaries
    timestamp : CalculationTimestamp
        Timestamp object for current calculation run
    
    Returns
    -------
    exposures : list of dict
        Updated exposures with timestamp fields
    
    Example
    -------
    >>> ts = get_current_calculation_timestamp()
    >>> exposures = [
    ...     {'counterparty': 'ABC', 'ead': 1000000},
    ...     {'counterparty': 'XYZ', 'ead': 2000000},
    ... ]
    >>> exposures = add_timestamp_to_exposures(exposures, ts)
    >>> all(e.get('calculation_date_formatted') for e in exposures)
    True
    """
    timestamp_fields = timestamp.to_db_dict()
    
    for exposure in exposures:
        exposure.update(timestamp_fields)
    
    return exposures


def create_timestamped_result(
    calculation_results: Dict[str, Any],
    calculation_date: date = None
) -> Dict[str, Any]:
    """
    Wrap calculation results with timestamp information.
    
    Parameters
    ----------
    calculation_results : dict
        Dictionary of calculation results (RWA, EAD, etc.)
    calculation_date : date, optional
        Specific calculation date. If None, uses current date.
    
    Returns
    -------
    results : dict
        Calculation results with embedded timestamp info
    
    Example
    -------
    >>> results = {'total_rwa': 50000000, 'cet1_ratio': 12.5}
    >>> timestamped = create_timestamped_result(results)
    >>> 'timestamp_info' in timestamped
    True
    >>> timestamped['timestamp_info']['formatted_date']
    'Apr-14-2026'
    """
    if calculation_date is None:
        ts = get_current_calculation_timestamp()
    else:
        ts = get_calculation_timestamp_for_date(calculation_date)
    
    # Create result with timestamp section
    result = {
        **calculation_results,
        'timestamp_info': ts.to_dict(),
    }
    
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Example Integration with Main Calculation Workflow
# ═════════════════════════════════════════════════════════════════════════════

def example_banking_book_calculation():
    """
    Example showing how to integrate timestamps into banking book calculations.
    """
    from backend.utils.calculation_timestamp import get_current_calculation_timestamp
    
    # 1. Get current timestamp at start of calculation
    ts = get_current_calculation_timestamp()
    
    print(f"Starting calculation for: {ts.formatted_date}")
    print(f"Run timestamp: {ts.run_timestamp}")
    
    # 2. Perform calculations (example)
    exposures = [
        {'counterparty': 'Goldman Sachs', 'ead': 1000000, 'lgd': 0.45, 'pd': 0.02},
        {'counterparty': 'JPMorgan', 'ead': 2000000, 'lgd': 0.40, 'pd': 0.015},
    ]
    
    # Calculate RWA (simplified example)
    for exp in exposures:
        exp['rwa'] = exp['ead'] * exp['lgd'] * exp['pd'] * 12.5
    
    # 3. Add timestamp to all exposures
    exposures = add_timestamp_to_exposures(exposures, ts)
    
    # 4. Now exposures are ready for database insertion
    print("\nExposures with timestamps:")
    for exp in exposures:
        print(f"  {exp['counterparty']}: RWA={exp['rwa']:,.0f}, Date={exp['calculation_date_formatted']}")
    
    return exposures


def example_aggregate_results():
    """
    Example showing how to add timestamps to aggregate RWA results.
    """
    from backend.utils.calculation_timestamp import get_current_calculation_timestamp
    
    # 1. Get timestamp
    ts = get_current_calculation_timestamp()
    
    # 2. Calculate aggregate results (example)
    agg_results = {
        'total_rwa': 50000000,
        'banking_book_rwa': 25000000,
        'ccr_rwa': 10000000,
        'market_risk_rwa': 8000000,
        'cva_rwa': 5000000,
        'operational_rwa': 2000000,
        'cet1_ratio': 12.5,
        'tier1_ratio': 14.0,
    }
    
    # 3. Add timestamp fields directly
    agg_results.update(ts.to_db_dict())
    
    # 4. Ready for database
    print("\nAggregate results with timestamp:")
    print(f"  Date: {agg_results['calculation_date_formatted']}")
    print(f"  Total RWA: EUR {agg_results['total_rwa']:,.0f}")
    print(f"  Year: {agg_results['year']}, Quarter: {agg_results['quarter']}")
    
    return agg_results


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("PROMETHEUS Timestamp Integration - Examples")
    print("=" * 70)
    
    print("\n1. Banking Book Exposures:")
    print("-" * 70)
    banking_exposures = example_banking_book_calculation()
    
    print("\n2. Aggregate RWA Results:")
    print("-" * 70)
    aggregate = example_aggregate_results()
    
    print("\n" + "=" * 70)
    print("Integration examples complete!")
    print("=" * 70)
