"""
PROMETHEUS Risk Platform
Market Data Provider — Abstract interface for pluggable data sources

Supports:
- Bloomberg Terminal (blpapi)
- Refinitiv/LSEG Eikon (refinitiv.data)
- Internal feeds (REST API / database)
- Static test data (for development/testing)
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import date
from enum import Enum

logger = logging.getLogger(__name__)


class MarketDataSource(Enum):
    """Available market data providers."""
    BLOOMBERG = "bloomberg"
    REFINITIV = "refinitiv"
    INTERNAL = "internal"
    STATIC_TEST = "static_test"


@dataclass
class MarketDataConfig:
    """Configuration for market data provider."""
    source: MarketDataSource
    # Bloomberg settings
    bloomberg_host: str = "localhost"
    bloomberg_port: int = 8194
    # Refinitiv settings
    refinitiv_app_key: Optional[str] = None
    refinitiv_username: Optional[str] = None
    # Internal feed settings
    internal_api_url: Optional[str] = None
    internal_api_key: Optional[str] = None
    # Cache settings
    cache_ttl_seconds: int = 300  # 5 minutes
    use_cache: bool = True


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.
    Subclasses implement specific vendor APIs.
    """

    def __init__(self, config: MarketDataConfig):
        self.config = config
        self._cache: Dict[str, tuple] = {}  # {key: (value, timestamp)}
        logger.info("Initialized %s market data provider", self.__class__.__name__)

    @abstractmethod
    def fetch_cds_spreads(
        self,
        obligor_id: str,
        tenor_years: Optional[List[float]] = None,
        as_of_date: Optional[date] = None
    ) -> Dict[float, Optional[float]]:
        """
        Fetch CDS spreads for an obligor across multiple tenors.
        
        Args:
            obligor_id: Internal obligor identifier
            tenor_years: List of tenors in years (e.g., [1, 3, 5])
            as_of_date: Historical date for spreads (None = live)
        
        Returns:
            Dict mapping tenor to spread in basis points (None if unavailable)
            Example: {1.0: 42.5, 3.0: 65.0, 5.0: 88.0}
        """
        pass

    @abstractmethod
    def fetch_recovery_rate(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None
    ) -> float:
        """
        Fetch market-implied recovery rate for an obligor.
        
        Returns:
            Recovery rate as decimal (e.g., 0.40 = 40%)
        """
        pass

    @abstractmethod
    def fetch_risk_free_rate(
        self,
        currency: str = "USD",
        tenor_years: float = 5.0,
        as_of_date: Optional[date] = None
    ) -> float:
        """
        Fetch risk-free rate (OIS/SOFR) for discounting.
        
        Returns:
            Rate as decimal (e.g., 0.043 = 4.3%)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the data source is available (connected)."""
        pass

    def _get_ticker_mapping(self, obligor_id: str) -> Optional[str]:
        """
        Map internal obligor_id to vendor ticker/RIC.
        Override in production with database lookup.
        """
        # Static mapping for known counterparties
        ticker_map = {
            "CPTY-0001": "GS",      # Goldman Sachs
            "CPTY-0002": "DB",      # Deutsche Bank
            "CPTY-0003": "AAPL",    # Apple
            "CPTY-0004": "SHEL",    # Shell
            "CPTY-0006": "BNP",     # BNP Paribas
            "CPTY-0009": "HSBA",    # HSBC
            "CPTY-0010": "JPM",     # JPMorgan
            "CPTY-0011": "C",       # Citibank
        }
        return ticker_map.get(obligor_id)


class BloombergProvider(MarketDataProvider):
    """
    Bloomberg Terminal market data provider.
    Requires blpapi package and active Bloomberg Terminal connection.
    """

    def __init__(self, config: MarketDataConfig):
        super().__init__(config)
        self._session = None
        self._connect()

    def _connect(self):
        """Establish Bloomberg API session."""
        try:
            import blpapi
            sessionOptions = blpapi.SessionOptions()
            sessionOptions.setServerHost(self.config.bloomberg_host)
            sessionOptions.setServerPort(self.config.bloomberg_port)
            self._session = blpapi.Session(sessionOptions)
            
            if not self._session.start():
                logger.error("Failed to start Bloomberg session")
                self._session = None
            else:
                if not self._session.openService("//blp/refdata"):
                    logger.error("Failed to open Bloomberg refdata service")
                    self._session.stop()
                    self._session = None
                else:
                    logger.info("Bloomberg session connected successfully")
        except ImportError:
            logger.warning("blpapi not installed — Bloomberg provider unavailable")
            self._session = None
        except Exception as e:
            logger.error("Bloomberg connection failed: %s", e)
            self._session = None

    def fetch_cds_spreads(
        self,
        obligor_id: str,
        tenor_years: Optional[List[float]] = None,
        as_of_date: Optional[date] = None
    ) -> Dict[float, Optional[float]]:
        """Fetch CDS spreads from Bloomberg CDSW."""
        if self._session is None:
            raise RuntimeError("Bloomberg session not available")
        
        tenor_years = tenor_years or [1, 3, 5]
        ticker = self._get_ticker_mapping(obligor_id)
        if not ticker:
            logger.warning("No Bloomberg ticker mapping for %s", obligor_id)
            return {}
        
        spreads = {}
        for tenor in tenor_years:
            # Bloomberg CDS ticker format: <TICKER> US <TENOR>Y Corp Curve
            bbg_ticker = f"{ticker} US {int(tenor)}Y Corp Curve"
            try:
                # Simplified: actual implementation would use refdata request
                # spread_bp = self._fetch_field(bbg_ticker, "PX_LAST", as_of_date)
                logger.debug("Bloomberg fetch: %s", bbg_ticker)
                # Placeholder: return None to signal unavailable
                spreads[tenor] = None
            except Exception as e:
                logger.warning("Bloomberg CDS fetch failed for %s: %s", bbg_ticker, e)
        
        return spreads

    def fetch_recovery_rate(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch recovery rate from Bloomberg CDSW."""
        if self._session is None:
            raise RuntimeError("Bloomberg session not available")
        
        ticker = self._get_ticker_mapping(obligor_id)
        if not ticker:
            return 0.40  # Default
        
        # Bloomberg field: CDS_RECOVERY_RATE
        # Placeholder implementation
        return 0.40

    def fetch_risk_free_rate(
        self,
        currency: str = "USD",
        tenor_years: float = 5.0,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch OIS rate from Bloomberg."""
        if self._session is None:
            raise RuntimeError("Bloomberg session not available")
        
        # Bloomberg OIS curve: USSO5 Curncy (5Y USD OIS)
        bbg_ticker = f"USSO{int(tenor_years)} Curncy"
        # Placeholder
        return 0.043

    def is_available(self) -> bool:
        return self._session is not None


class RefinitivProvider(MarketDataProvider):
    """
    Refinitiv/LSEG Eikon market data provider.
    Requires refinitiv.data package and API credentials.
    """

    def __init__(self, config: MarketDataConfig):
        super().__init__(config)
        self._session = None
        self._connect()

    def _connect(self):
        """Establish Refinitiv session."""
        try:
            import refinitiv.data as rd
            rd.open_session(
                app_key=self.config.refinitiv_app_key,
                username=self.config.refinitiv_username
            )
            self._session = rd
            logger.info("Refinitiv session opened successfully")
        except ImportError:
            logger.warning("refinitiv.data not installed — Refinitiv provider unavailable")
            self._session = None
        except Exception as e:
            logger.error("Refinitiv connection failed: %s", e)
            self._session = None

    def fetch_cds_spreads(
        self,
        obligor_id: str,
        tenor_years: Optional[List[float]] = None,
        as_of_date: Optional[date] = None
    ) -> Dict[float, Optional[float]]:
        """Fetch CDS spreads from Refinitiv."""
        if self._session is None:
            raise RuntimeError("Refinitiv session not available")
        
        tenor_years = tenor_years or [1, 3, 5]
        ticker = self._get_ticker_mapping(obligor_id)
        if not ticker:
            logger.warning("No Refinitiv RIC mapping for %s", obligor_id)
            return {}
        
        spreads = {}
        for tenor in tenor_years:
            # Refinitiv RIC format: <TICKER>.CDS<TENOR>Y
            ric = f"{ticker}.CDS{int(tenor)}Y"
            try:
                # Actual implementation would use rd.get_data()
                logger.debug("Refinitiv fetch: %s", ric)
                spreads[tenor] = None  # Placeholder
            except Exception as e:
                logger.warning("Refinitiv CDS fetch failed for %s: %s", ric, e)
        
        return spreads

    def fetch_recovery_rate(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch recovery rate from Refinitiv."""
        if self._session is None:
            raise RuntimeError("Refinitiv session not available")
        
        # Refinitiv recovery rate field
        return 0.40  # Placeholder

    def fetch_risk_free_rate(
        self,
        currency: str = "USD",
        tenor_years: float = 5.0,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch OIS rate from Refinitiv."""
        if self._session is None:
            raise RuntimeError("Refinitiv session not available")
        
        # Refinitiv OIS RIC
        return 0.043  # Placeholder

    def is_available(self) -> bool:
        return self._session is not None


class InternalFeedProvider(MarketDataProvider):
    """
    Internal market data feed (REST API or database).
    For proprietary credit desk feeds or internal data warehouse.
    """

    def __init__(self, config: MarketDataConfig):
        super().__init__(config)
        self._api_url = config.internal_api_url
        self._api_key = config.internal_api_key

    def fetch_cds_spreads(
        self,
        obligor_id: str,
        tenor_years: Optional[List[float]] = None,
        as_of_date: Optional[date] = None
    ) -> Dict[float, Optional[float]]:
        """Fetch CDS spreads from internal API."""
        tenor_years = tenor_years or [1, 3, 5]
        
        if not self._api_url:
            logger.warning("Internal API URL not configured")
            return {}
        
        # Example REST API call
        # import requests
        # response = requests.get(
        #     f"{self._api_url}/cds/spreads/{obligor_id}",
        #     headers={"Authorization": f"Bearer {self._api_key}"},
        #     params={"tenors": ",".join(map(str, tenor_years))}
        # )
        # return response.json()
        
        logger.debug("Internal API fetch for %s (stub)", obligor_id)
        return {}  # Placeholder

    def fetch_recovery_rate(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch recovery rate from internal database."""
        # Query internal credit database
        return 0.40  # Placeholder

    def fetch_risk_free_rate(
        self,
        currency: str = "USD",
        tenor_years: float = 5.0,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch OIS rate from internal curve."""
        return 0.043  # Placeholder

    def is_available(self) -> bool:
        return self._api_url is not None


class StaticTestProvider(MarketDataProvider):
    """
    Static test data provider for development/testing.
    Uses hardcoded spreads from cva_generator.py.
    """

    def __init__(self, config: MarketDataConfig):
        super().__init__(config)
        # Import static test data
        from backend.data_generators.cva_generator import (
            _MARKET_SPREADS_BPS,
            _COUNTERPARTY_PARAMS
        )
        self._spreads = _MARKET_SPREADS_BPS
        self._params = _COUNTERPARTY_PARAMS

    def fetch_cds_spreads(
        self,
        obligor_id: str,
        tenor_years: Optional[List[float]] = None,
        as_of_date: Optional[date] = None
    ) -> Dict[float, Optional[float]]:
        """Fetch static CDS spreads."""
        tenor_years = tenor_years or [1, 3, 5]
        
        # Static data only has 5Y spreads; approximate others
        spread_5y = self._spreads.get(obligor_id)
        if spread_5y is None:
            return {}
        
        spreads = {}
        for tenor in tenor_years:
            # Simple approximation: shorter tenors have slightly lower spreads
            if tenor <= 1:
                spreads[tenor] = spread_5y * 0.85
            elif tenor <= 3:
                spreads[tenor] = spread_5y * 0.92
            else:
                spreads[tenor] = spread_5y
        
        return spreads

    def fetch_recovery_rate(
        self,
        obligor_id: str,
        as_of_date: Optional[date] = None
    ) -> float:
        """Fetch static recovery rate."""
        params = self._params.get(obligor_id, {})
        return params.get("lgd_mkt", 0.40)

    def fetch_risk_free_rate(
        self,
        currency: str = "USD",
        tenor_years: float = 5.0,
        as_of_date: Optional[date] = None
    ) -> float:
        """Return static risk-free rate."""
        return 0.043

    def is_available(self) -> bool:
        return True


def create_provider(config: MarketDataConfig) -> MarketDataProvider:
    """
    Factory function to create appropriate market data provider.
    
    Usage:
        config = MarketDataConfig(source=MarketDataSource.BLOOMBERG)
        provider = create_provider(config)
        spreads = provider.fetch_cds_spreads("CPTY-0001")
    """
    if config.source == MarketDataSource.BLOOMBERG:
        return BloombergProvider(config)
    elif config.source == MarketDataSource.REFINITIV:
        return RefinitivProvider(config)
    elif config.source == MarketDataSource.INTERNAL:
        return InternalFeedProvider(config)
    elif config.source == MarketDataSource.STATIC_TEST:
        return StaticTestProvider(config)
    else:
        raise ValueError(f"Unknown market data source: {config.source}")
