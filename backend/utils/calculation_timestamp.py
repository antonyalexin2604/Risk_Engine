"""
PROMETHEUS Risk Platform
Calculation Timestamp Module

FILE PATH: backend/utils/calculation_timestamp.py

Captures and formats timestamps for every risk calculation run.
Enables Day-on-Day, Month-on-Month, Quarter-on-Quarter trend analysis.
"""

from datetime import datetime, date
from typing import Dict, Optional
import pytz


class CalculationTimestamp:
    """
    Captures timestamp information for each calculation run.
    
    Attributes
    ----------
    calculation_date : date
        The business date for which calculations are performed
    run_timestamp : datetime
        The exact datetime when the calculation was initiated
    formatted_date : str
        Date in format "Apr-14-2026"
    year : int
        Year component
    month : int
        Month component (1-12)
    day : int
        Day component
    quarter : int
        Quarter component (1-4)
    """
    
    def __init__(
        self,
        calculation_date: Optional[date] = None,
        timezone: str = "America/New_York"
    ):
        """
        Initialize calculation timestamp.
        
        Parameters
        ----------
        calculation_date : date, optional
            The business date for calculations. Defaults to today.
        timezone : str
            Timezone for timestamp (default: US Eastern)
        """
        self.tz = pytz.timezone(timezone)
        self.run_timestamp = datetime.now(self.tz)
        
        # Use provided date or today's date
        if calculation_date is None:
            calculation_date = self.run_timestamp.date()
        
        self.calculation_date = calculation_date
        
        # Extract date components
        self.year = calculation_date.year
        self.month = calculation_date.month
        self.day = calculation_date.day
        
        # Calculate quarter (Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec)
        self.quarter = (self.month - 1) // 3 + 1
        
        # Formatted date: "Apr-14-2026"
        self.formatted_date = calculation_date.strftime("%b-%d-%Y")
        
        # Additional useful formats
        self.iso_date = calculation_date.isoformat()  # "2026-04-14"
        self.quarter_label = f"Q{self.quarter} {self.year}"  # "Q2 2026"
        self.month_label = calculation_date.strftime("%b %Y")  # "Apr 2026"
    
    def to_dict(self) -> Dict:
        """
        Convert timestamp to dictionary for database storage.
        
        Returns
        -------
        Dictionary with all timestamp fields
        """
        return {
            "calculation_date": self.calculation_date,
            "calculation_date_formatted": self.formatted_date,
            "run_timestamp": self.run_timestamp,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "quarter": self.quarter,
            "quarter_label": self.quarter_label,
            "month_label": self.month_label,
            "iso_date": self.iso_date,
        }
    
    def to_db_dict(self) -> Dict:
        """
        Convert to dictionary suitable for PostgreSQL insertion.
        
        Returns
        -------
        Dictionary with database-compatible types
        """
        return {
            "calculation_date": self.calculation_date,
            "calculation_date_formatted": self.formatted_date,
            "run_timestamp": self.run_timestamp,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "quarter": self.quarter,
        }
    
    def __str__(self) -> str:
        """String representation."""
        return f"Calculation Date: {self.formatted_date} | Run Timestamp: {self.run_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    
    def __repr__(self) -> str:
        """Developer representation."""
        return f"CalculationTimestamp(date={self.formatted_date}, timestamp={self.run_timestamp})"


def get_current_calculation_timestamp() -> CalculationTimestamp:
    """
    Get timestamp for current calculation run.
    
    Returns
    -------
    CalculationTimestamp instance
    """
    return CalculationTimestamp()


def get_calculation_timestamp_for_date(calculation_date: date) -> CalculationTimestamp:
    """
    Get timestamp for a specific calculation date.
    
    Parameters
    ----------
    calculation_date : date
        The business date for calculations
    
    Returns
    -------
    CalculationTimestamp instance
    """
    return CalculationTimestamp(calculation_date=calculation_date)


def format_date_for_db(dt: date) -> str:
    """
    Format date for display in database/reports.
    
    Parameters
    ----------
    dt : date
        Date to format
    
    Returns
    -------
    Formatted string like "Apr-14-2026"
    """
    return dt.strftime("%b-%d-%Y")


def get_quarter(dt: date) -> int:
    """
    Get quarter number for a date.
    
    Parameters
    ----------
    dt : date
        Date to check
    
    Returns
    -------
    Quarter number (1-4)
    """
    return (dt.month - 1) // 3 + 1


def get_quarter_label(dt: date) -> str:
    """
    Get quarter label for a date.
    
    Parameters
    ----------
    dt : date
        Date to check
    
    Returns
    -------
    Quarter label like "Q2 2026"
    """
    quarter = get_quarter(dt)
    return f"Q{quarter} {dt.year}"


def get_month_label(dt: date) -> str:
    """
    Get month label for a date.
    
    Parameters
    ----------
    dt : date
        Date to check
    
    Returns
    -------
    Month label like "Apr 2026"
    """
    return dt.strftime("%b %Y")


# Example usage
if __name__ == "__main__":
    # Get current timestamp
    ts = get_current_calculation_timestamp()
    
    print("=== Calculation Timestamp ===")
    print(ts)
    print("\n=== Dictionary Format ===")
    for key, value in ts.to_dict().items():
        print(f"{key}: {value}")
    
    print("\n=== Database Format ===")
    for key, value in ts.to_db_dict().items():
        print(f"{key}: {value}")
    
    # Example for specific date
    specific_date = date(2026, 4, 14)
    ts2 = get_calculation_timestamp_for_date(specific_date)
    print(f"\n=== Specific Date Example ===")
    print(f"Formatted: {ts2.formatted_date}")
    print(f"Quarter: {ts2.quarter_label}")
    print(f"Month: {ts2.month_label}")
