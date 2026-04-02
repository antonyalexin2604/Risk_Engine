"""
PROMETHEUS Risk Platform — Configuration
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# ─── Database ────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME",     "prometheus_risk"),
    "user":     os.getenv("DB_USER",     "risk_admin"),
    "password": os.getenv("DB_PASSWORD", "P@ssw0rd_Risk2024"),
}

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
)

# ─── Regulatory Parameters ────────────────────────────────────────────────────

@dataclass
class SACarCRConfig:
    """SA-CCR parameters per CRE52."""
    alpha: float = 1.4              # CRE52.7 — multiplier
    floor_multiplier: float = 0.05  # CRE52.23 — PFE multiplier floor
    mpor_secured: int = 10          # Margin Period of Risk (days)
    mpor_unsecured: int = 20        # MPOR for non-margin trades
    threshold_pct: float = 0.95     # confidence for multiplier

@dataclass
class IMMConfig:
    """IMM / Monte Carlo configuration — sized for M1 8GB RAM."""
    num_scenarios: int = 2_000      # conservative for M1
    time_horizon_years: float = 1.0
    time_steps: int = 52            # weekly steps
    random_seed: int = 42
    alpha: float = 1.4              # regulatory alpha (EAD = alpha * EEPE)
    confidence_level: float = 0.95
    stress_period_start: str = "2007-06-01"
    stress_period_end:   str = "2009-06-30"

@dataclass
class AIRBConfig:
    """A-IRB parameters per CRE31."""
    pd_floor: float = 0.0003        # CRE31.4 — 3bp floor
    lgd_floor_unsecured: float = 0.25   # CRE32 — 25% floor (financial)
    lgd_floor_secured: float = 0.00     # varies by collateral type
    maturity_default: float = 2.5   # CRE31.7
    maturity_floor: float = 1.0
    maturity_cap: float = 5.0
    size_sme_threshold: float = 50_000_000  # EUR equiv.

@dataclass
class FRTBConfig:
    """FRTB parameters per MAR21-33."""
    confidence_var: float = 0.99    # VaR confidence
    confidence_es:  float = 0.975   # ES confidence (MAR33.8)
    holding_period_days: int = 10
    liquidity_horizon: int = 10     # minimum LH (days)
    backtesting_window: int = 250   # trading days
    green_zone_exceptions: int = 4  # 0-4 = green
    amber_zone_max: int = 9         # 5-9 = amber → red >9

@dataclass
class MarketDataConfig:
    """Market data provider configuration."""
    # Primary data source (bloomberg/refinitiv/internal/static_test)
    primary_source: str = os.getenv("MARKET_DATA_SOURCE", "static_test")
    # Fallback source if primary unavailable
    fallback_source: Optional[str] = os.getenv("MARKET_DATA_FALLBACK", None)
    
    # Bloomberg settings
    bloomberg_host: str = os.getenv("BLOOMBERG_HOST", "localhost")
    bloomberg_port: int = int(os.getenv("BLOOMBERG_PORT", "8194"))
    
    # Refinitiv settings
    refinitiv_app_key: Optional[str] = os.getenv("REFINITIV_APP_KEY", None)
    refinitiv_username: Optional[str] = os.getenv("REFINITIV_USERNAME", None)
    
    # Internal feed settings
    internal_api_url: Optional[str] = os.getenv("INTERNAL_API_URL", None)
    internal_api_key: Optional[str] = os.getenv("INTERNAL_API_KEY", None)
    
    # Cache settings
    cache_ttl_seconds: int = int(os.getenv("MARKET_DATA_CACHE_TTL", "300"))
    use_cache: bool = os.getenv("MARKET_DATA_USE_CACHE", "true").lower() == "true"

# Global instances
SACCR = SACarCRConfig()
IMM   = IMMConfig()
AIRB  = AIRBConfig()
FRTB  = FRTBConfig()
MARKET_DATA = MarketDataConfig()

# ─── Misc ─────────────────────────────────────────────────────────────────────

REPORT_OUTPUT_DIR = os.getenv("REPORT_DIR", "/tmp/prometheus_reports")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Risk-weight matrix for SA credit (CRE20 — used in capital summary)
CORP_RISK_WEIGHTS = {
    "AAA": 0.20, "AA+": 0.20, "AA": 0.20, "AA-": 0.20,
    "A+":  0.50, "A":  0.50, "A-": 0.50,
    "BBB+": 1.00, "BBB": 1.00, "BBB-": 1.00,
    "BB+": 1.00, "BB": 1.00,
    "B+":  1.50, "B":  1.50,
    "CCC": 1.50,
    "NR":  1.00,
}
