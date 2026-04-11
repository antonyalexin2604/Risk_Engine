"""
PROMETHEUS Risk Platform
Operational Risk Engine — Basel III SMA (OPE25)

FILE PATH: backend/engines/operational_risk.py

Implements the Standardised Measurement Approach for operational risk capital.

Regulatory Basis:
    - RBC20.10: Operational risk RWA calculation
    - OPE25: SMA methodology (Business Indicator Component + Internal Loss Multiplier)
"""

from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import List, Dict, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Basel Event Type Categories (Level 1)
# ─────────────────────────────────────────────────────────────────────────────

BASEL_EVENT_TYPES = {
    "INTERNAL_FRAUD": "Internal Fraud",
    "EXTERNAL_FRAUD": "External Fraud",
    "EPWS": "Employment Practices & Workplace Safety",
    "CPBP": "Clients, Products & Business Practices",
    "DPA": "Damage to Physical Assets",
    "BDSF": "Business Disruption & System Failures",
    "EDPM": "Execution, Delivery & Process Management",
}

# Basel Business Lines
BASEL_BUSINESS_LINES = {
    "CORPORATE_FINANCE": "Corporate Finance",
    "TRADING_SALES": "Trading & Sales",
    "RETAIL_BANKING": "Retail Banking",
    "COMMERCIAL_BANKING": "Commercial Banking",
    "PAYMENT_SETTLEMENT": "Payment & Settlement",
    "AGENCY_CUSTODY": "Agency Services & Custody",
    "ASSET_MANAGEMENT": "Asset Management",
    "RETAIL_BROKERAGE": "Retail Brokerage",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LossEvent:
    """
    Operational loss event record (OPE25 compliant).
    
    Each event must be categorized by Basel Event Type and Business Line.
    Loss amounts must be recorded in base currency (EUR millions).
    """
    event_id: str
    event_date: date
    discovery_date: date
    booking_date: date
    
    # Basel classification
    event_type: str  # Must be in BASEL_EVENT_TYPES
    business_line: str  # Must be in BASEL_BUSINESS_LINES
    
    # Loss amounts (EUR millions)
    gross_loss_amount: float
    recoveries: float = 0.0
    insurance_recovery: float = 0.0
    
    # Metadata
    description: str = ""
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    status: str = "CLOSED"
    
    @property
    def net_loss_amount(self) -> float:
        """Net loss after recoveries and insurance."""
        return self.gross_loss_amount - self.recoveries - self.insurance_recovery
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_date": self.event_date.isoformat(),
            "discovery_date": self.discovery_date.isoformat(),
            "booking_date": self.booking_date.isoformat(),
            "event_type": self.event_type,
            "business_line": self.business_line,
            "gross_loss_amount": self.gross_loss_amount,
            "recoveries": self.recoveries,
            "insurance_recovery": self.insurance_recovery,
            "net_loss_amount": self.net_loss_amount,
            "description": self.description,
            "root_cause": self.root_cause,
            "corrective_action": self.corrective_action,
            "status": self.status,
        }


@dataclass
class BusinessIndicatorInput:
    """
    Financial statement data for Business Indicator calculation (OPE25).
    
    All amounts should be annual averages in EUR millions.
    Banks must provide 3 consecutive years of data for BI calculation.
    """
    year: int
    
    # Interest Component
    interest_income: float = 0.0
    interest_expense: float = 0.0
    dividend_income: float = 0.0
    
    # Services Component
    services_income: float = 0.0   # Fee and commission income
    services_expense: float = 0.0  # Fee and commission expense
    
    # Financial Component
    financial_income: float = 0.0   # Net P&L from financial instruments
    financial_expense: float = 0.0
    
    # Other
    other_operating_income: float = 0.0
    
    # P&L Components
    trading_book_pnl: float = 0.0
    banking_book_pnl: float = 0.0
    
    def compute_bi_services(self) -> float:
        """OPE25: Services Component of Business Indicator."""
        return (abs(self.interest_income) + abs(self.interest_expense) + 
                abs(self.dividend_income) + 
                abs(self.services_income) + abs(self.services_expense) + 
                abs(self.financial_income) + abs(self.financial_expense) + 
                abs(self.other_operating_income))
    
    def compute_bi_banking(self) -> float:
        """OPE25: Banking Book P&L Component."""
        return abs(self.banking_book_pnl)
    
    def compute_bi_financial(self) -> float:
        """OPE25: Trading Book P&L Component."""
        return abs(self.trading_book_pnl)
    
    def compute_bi(self) -> float:
        """Total Business Indicator for this year."""
        return (self.compute_bi_services() + 
                self.compute_bi_banking() + 
                self.compute_bi_financial())


@dataclass
class SMAResult:
    """Operational Risk capital result using SMA."""
    business_indicator: float  # 3-year average BI
    bic: float  # Business Indicator Component
    loss_component: float  # LC = 15 × Average Annual Losses
    ilm: float  # Internal Loss Multiplier
    operational_risk_capital: float  # BIC × ILM
    rwa_operational: float  # Capital × 12.5
    
    # Diagnostic info
    years_of_loss_data: int
    total_loss_events: int
    average_annual_loss: float
    
    def to_dict(self) -> dict:
        return {
            "business_indicator_eur_m": self.business_indicator,
            "bic_eur_m": self.bic,
            "loss_component_eur_m": self.loss_component,
            "ilm": self.ilm,
            "operational_risk_capital_eur_m": self.operational_risk_capital,
            "rwa_operational_eur_m": self.rwa_operational,
            "years_of_loss_data": self.years_of_loss_data,
            "total_loss_events": self.total_loss_events,
            "average_annual_loss_eur_m": self.average_annual_loss,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SMA Calculation Functions
# ─────────────────────────────────────────────────────────────────────────────

def compute_business_indicator(bi_inputs: List[BusinessIndicatorInput]) -> float:
    """
    Compute 3-year average Business Indicator (OPE25).
    
    Parameters
    ----------
    bi_inputs : List of BusinessIndicatorInput for 3 consecutive years
    
    Returns
    -------
    Average BI over 3 years (EUR millions)
    """
    if not bi_inputs:
        raise ValueError("At least 1 year of BI data required")
    
    if len(bi_inputs) > 3:
        logger.warning(
            "More than 3 years of BI data provided (%d years). Using most recent 3 years per OPE25.",
            len(bi_inputs),
        )
        bi_inputs = sorted(bi_inputs, key=lambda x: x.year, reverse=True)[:3]
    
    annual_bis = [bi.compute_bi() for bi in bi_inputs]
    avg_bi = sum(annual_bis) / len(annual_bis)
    
    logger.info(
        "Business Indicator: Average over %d years = EUR %.1f million",
        len(bi_inputs), avg_bi,
    )
    
    return avg_bi


def compute_bic(bi_avg: float) -> float:
    """
    Compute Business Indicator Component using tiered marginal coefficients (OPE25).
    
    Tiers (EUR billions):
        BI ≤ 1:       α = 12%
        1 < BI ≤ 3:   α = 15%
        3 < BI ≤ 10:  α = 18%
        10 < BI ≤ 30: α = 21%
        BI > 30:      α = 23%
    
    Parameters
    ----------
    bi_avg : Business Indicator in EUR millions
    
    Returns
    -------
    BIC in EUR millions
    """
    # Convert to billions for tier calculation
    bi_bn = bi_avg / 1000.0
    
    # Tier boundaries and coefficients
    tiers = [
        (1, 0.12),
        (3, 0.15),
        (10, 0.18),
        (30, 0.21),
        (float('inf'), 0.23),
    ]
    
    bic = 0.0
    prev_threshold = 0.0
    
    for threshold, alpha in tiers:
        if bi_bn <= threshold:
            # Final tier
            marginal_bi = (bi_bn - prev_threshold) * 1000  # Back to millions
            bic += alpha * marginal_bi
            break
        else:
            # Intermediate tier
            marginal_bi = (threshold - prev_threshold) * 1000
            bic += alpha * marginal_bi
            prev_threshold = threshold
    
    logger.info(
        "BIC Calculation: BI=EUR %.1f bn → BIC=EUR %.1f million",
        bi_bn, bic,
    )
    
    return bic


def compute_loss_component(
    loss_events: List[LossEvent],
    years_required: int = 10,
) -> Tuple[float, int, float]:
    """
    Compute Loss Component from historical loss data (OPE25).
    
    LC = 15 × Average Annual Aggregate Losses (over 10 years)
    
    Parameters
    ----------
    loss_events : List of all historical loss events
    years_required : Number of years of loss history (default 10 per OPE25)
    
    Returns
    -------
    (loss_component, years_of_data, average_annual_loss)
    
    Notes
    -----
    If fewer than 10 years of data available: LC = 0, ILM defaults to 1.0
    Only include events with booking_date
    """
    if not loss_events:
        logger.warning("No historical loss events available — LC=0, ILM will default to 1.0")
        return 0.0, 0, 0.0
    
    # Group losses by year (using booking_date)
    losses_by_year: Dict[int, float] = {}
    
    for event in loss_events:
        year = event.booking_date.year
        net_loss = event.net_loss_amount
        
        if year not in losses_by_year:
            losses_by_year[year] = 0.0
        losses_by_year[year] += net_loss
    
    years_available = len(losses_by_year)
    
    if years_available < years_required:
        logger.warning(
            "Insufficient loss history: %d years available (need %d). LC=0, ILM will default to 1.0 per OPE25.",
            years_available, years_required,
        )
        # Still compute average for reporting purposes
        annual_losses = list(losses_by_year.values())
        avg_annual_loss = sum(annual_losses) / len(annual_losses) if annual_losses else 0.0
        return 0.0, years_available, avg_annual_loss
    
    # Use most recent 10 years
    recent_years = sorted(losses_by_year.keys(), reverse=True)[:years_required]
    annual_losses = [losses_by_year[year] for year in recent_years]
    
    avg_annual_loss = sum(annual_losses) / years_required
    lc = 15.0 * avg_annual_loss
    
    logger.info(
        "Loss Component: Average Annual Loss over %d years = EUR %.2f million → LC=EUR %.1f million",
        years_required, avg_annual_loss, lc,
    )
    
    return lc, years_available, avg_annual_loss


def compute_ilm(lc: float, bic: float) -> float:
    """
    Compute Internal Loss Multiplier (OPE25).
    
    ILM = ln( exp(1) - 1 + (LC / BIC)^0.8 )
    
    Capped at 1.0 (100%).
    If LC = 0 (insufficient loss data), ILM = 1.0 by default.
    
    Parameters
    ----------
    lc : Loss Component (EUR millions)
    bic : Business Indicator Component (EUR millions)
    
    Returns
    -------
    ILM (decimal, max 1.0)
    """
    if lc == 0.0:
        logger.info("ILM = 1.0 (default, insufficient loss history)")
        return 1.0
    
    if bic == 0.0:
        raise ValueError("BIC cannot be zero when computing ILM")
    
    # ILM formula
    ratio = lc / bic
    exp_term = math.exp(1) - 1 + math.pow(ratio, 0.8)
    ilm_raw = math.log(exp_term)
    
    # Cap at 1.0
    ilm = min(ilm_raw, 1.0)
    
    logger.info(
        "ILM Calculation: LC/BIC = %.3f → ILM (uncapped) = %.3f → ILM (capped) = %.3f",
        ratio, ilm_raw, ilm,
    )
    
    return ilm


def compute_sma_capital(
    bi_inputs: List[BusinessIndicatorInput],
    loss_events: List[LossEvent],
) -> SMAResult:
    """
    Compute operational risk capital using Standardised Measurement Approach (OPE25).
    
    Formula:
        Operational Risk Capital = BIC × ILM
    
    Where:
        BIC = Business Indicator Component (tiered function of 3-year average BI)
        ILM = Internal Loss Multiplier (function of historical losses)
    
    Parameters
    ----------
    bi_inputs : List of BusinessIndicatorInput for 3 consecutive years
    loss_events : Historical loss event database (ideally 10+ years)
    
    Returns
    -------
    SMAResult with capital, RWA, and diagnostic information
    """
    # Step 1: Compute 3-year average Business Indicator
    bi_avg = compute_business_indicator(bi_inputs)
    
    # Step 2: Compute BIC (tiered function)
    bic = compute_bic(bi_avg)
    
    # Step 3: Compute Loss Component from historical data
    lc, years_of_data, avg_annual_loss = compute_loss_component(loss_events)
    
    # Step 4: Compute ILM
    ilm = compute_ilm(lc, bic)
    
    # Step 5: Operational Risk Capital = BIC × ILM
    op_risk_capital = bic * ilm
    
    # Step 6: RWA = Capital × 12.5 (standard conversion)
    rwa_op = op_risk_capital * 12.5
    
    result = SMAResult(
        business_indicator=bi_avg,
        bic=bic,
        loss_component=lc,
        ilm=ilm,
        operational_risk_capital=op_risk_capital,
        rwa_operational=rwa_op,
        years_of_loss_data=years_of_data,
        total_loss_events=len(loss_events),
        average_annual_loss=avg_annual_loss,
    )
    
    logger.info(
        "SMA Operational Risk: BIC=EUR %.1f M × ILM=%.3f = Capital=EUR %.1f M → RWA=EUR %.1f M",
        bic, ilm, op_risk_capital, rwa_op,
    )
    
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Loss Event Analysis Functions
# ─────────────────────────────────────────────────────────────────────────────

def analyze_losses_by_event_type(loss_events: List[LossEvent]) -> pd.DataFrame:
    """Analyze loss distribution by Basel Event Type."""
    if not loss_events:
        return pd.DataFrame()
    
    data = []
    total_net = sum(e.net_loss_amount for e in loss_events)
    
    for event_type_code in BASEL_EVENT_TYPES.keys():
        events_in_type = [e for e in loss_events if e.event_type == event_type_code]
        
        if not events_in_type:
            continue
        
        total_gross = sum(e.gross_loss_amount for e in events_in_type)
        total_net_type = sum(e.net_loss_amount for e in events_in_type)
        
        data.append({
            "event_type": BASEL_EVENT_TYPES[event_type_code],
            "count": len(events_in_type),
            "total_gross_loss": total_gross,
            "total_net_loss": total_net_type,
            "avg_loss": total_net_type / len(events_in_type),
            "pct_of_total": (total_net_type / total_net * 100) if total_net > 0 else 0,
        })
    
    df = pd.DataFrame(data)
    df = df.sort_values("total_net_loss", ascending=False)
    
    return df


def analyze_losses_by_business_line(loss_events: List[LossEvent]) -> pd.DataFrame:
    """Analyze loss distribution by Business Line."""
    if not loss_events:
        return pd.DataFrame()
    
    data = []
    total_net = sum(e.net_loss_amount for e in loss_events)
    
    for bl_code in BASEL_BUSINESS_LINES.keys():
        events_in_bl = [e for e in loss_events if e.business_line == bl_code]
        
        if not events_in_bl:
            continue
        
        total_net_bl = sum(e.net_loss_amount for e in events_in_bl)
        
        data.append({
            "business_line": BASEL_BUSINESS_LINES[bl_code],
            "count": len(events_in_bl),
            "total_net_loss": total_net_bl,
            "avg_loss": total_net_bl / len(events_in_bl),
            "pct_of_total": (total_net_bl / total_net * 100) if total_net > 0 else 0,
        })
    
    df = pd.DataFrame(data)
    df = df.sort_values("total_net_loss", ascending=False)
    
    return df


def get_loss_timeline(loss_events: List[LossEvent]) -> pd.DataFrame:
    """Create timeline DataFrame for visualization."""
    if not loss_events:
        return pd.DataFrame()
    
    data = [{
        "date": e.booking_date,
        "event_id": e.event_id,
        "event_type": BASEL_EVENT_TYPES.get(e.event_type, e.event_type),
        "business_line": BASEL_BUSINESS_LINES.get(e.business_line, e.business_line),
        "net_loss": e.net_loss_amount,
        "gross_loss": e.gross_loss_amount,
    } for e in loss_events]
    
    df = pd.DataFrame(data)
    df = df.sort_values("date")
    
    return df
