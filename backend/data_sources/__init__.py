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
    # credit_calibration — RTM-based PD model
    "pd_from_rating",
    "pd_term_structure",
    "validate_rtm",
    "RTM_1Y",
    "RTM_CATEGORIES",
    "RTM_CAT_IDX",
    "NOTCH_TO_CATEGORY",
    "NOTCH_PD_MULT",
    "PD_FLOOR",
    "PD_CAP",
    # lgd_calibration — Frye-Jacobs LGD model
    "LGDModel",
    "LGDResult",
    "DEFAULT_LGD_MODEL",
    "downturn_lgd",
    "validate_lgd_table",
    "LGD_FLOORS_SECURED",
    "LGD_FLOOR_UNSECURED",
    "LGD_CAP",
]

# Credit calibration — RTM-based PD
from backend.data_sources.credit_calibration import (
    pd_from_rating,
    pd_term_structure,
    validate_rtm,
    RTM_1Y,
    RTM_CATEGORIES,
    RTM_CAT_IDX,
    NOTCH_TO_CATEGORY,
    NOTCH_PD_MULT,
    PD_FLOOR,
    PD_CAP,
)

# LGD calibration — Frye-Jacobs downturn model
from backend.data_sources.lgd_calibration import (
    LGDModel,
    LGDResult,
    DEFAULT_LGD_MODEL,
    downturn_lgd,
    validate_lgd_table,
    LGD_FLOORS_SECURED,
    LGD_FLOOR_UNSECURED,
    LGD_CAP,
)
