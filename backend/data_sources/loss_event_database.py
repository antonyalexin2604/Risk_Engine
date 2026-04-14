"""
PROMETHEUS Risk Platform
Loss Event Database — Historical Operational Loss Storage

FILE PATH: backend/data_sources/loss_event_database.py

Manages operational loss events with Basel Event Type classification.
Production: Migrate to PostgreSQL table `operational_risk.loss_events`.
"""

from __future__ import annotations
import logging
import json
import os
from datetime import date
from typing import List, Optional
import sys

# Handle imports for both standalone and package usage
try:
    from backend.engines.operational_risk import LossEvent, BASEL_EVENT_TYPES, BASEL_BUSINESS_LINES
except ImportError:
    # If running standalone or in development
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engines.operational_risk import LossEvent, BASEL_EVENT_TYPES, BASEL_BUSINESS_LINES

logger = logging.getLogger(__name__)


class LossEventDatabase:
    """
    Central database for operational loss events.
    
    Development: Uses JSON file
    Production: PostgreSQL table `operational_risk.loss_events`
    """
    
    def __init__(self, db_file: Optional[str] = None):
        """
        Parameters
        ----------
        db_file : Path to JSON file storing loss events.
                 Default: backend/data_sources/loss_events.json
        """
        if db_file is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_file = os.path.join(base_dir, "loss_events.json")
        
        self.db_file = db_file
        self.events: List[LossEvent] = []
        self._load()
    
    def _load(self) -> None:
        """Load loss events from JSON file."""
        if not os.path.exists(self.db_file):
            logger.warning(
                "Loss event database file not found: %s — using empty database",
                self.db_file,
            )
            return
        
        try:
            with open(self.db_file, "r") as f:
                data = json.load(f)
            
            for event_dict in data.get("loss_events", []):
                event = LossEvent(
                    event_id=event_dict["event_id"],
                    event_date=date.fromisoformat(event_dict["event_date"]),
                    discovery_date=date.fromisoformat(event_dict["discovery_date"]),
                    booking_date=date.fromisoformat(event_dict["booking_date"]),
                    event_type=event_dict["event_type"],
                    business_line=event_dict["business_line"],
                    gross_loss_amount=event_dict["gross_loss_amount"],
                    recoveries=event_dict.get("recoveries", 0.0),
                    insurance_recovery=event_dict.get("insurance_recovery", 0.0),
                    description=event_dict.get("description", ""),
                    root_cause=event_dict.get("root_cause"),
                    corrective_action=event_dict.get("corrective_action"),
                    status=event_dict.get("status", "CLOSED"),
                )
                self.events.append(event)
            
            logger.info("Loaded %d loss events from %s", len(self.events), self.db_file)
        
        except Exception as exc:
            logger.error("Failed to load loss events from %s: %s", self.db_file, exc)
    
    def save(self) -> None:
        """Persist loss events to JSON file."""
        try:
            data = {
                "last_updated": date.today().isoformat(),
                "loss_events": [event.to_dict() for event in self.events],
            }
            with open(self.db_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Saved %d loss events to %s", len(self.events), self.db_file)
        except Exception as exc:
            logger.error("Failed to save loss events: %s", exc)
    
    def add_event(self, event: LossEvent) -> None:
        """Add new loss event to database."""
        self.events.append(event)
        self.save()
        logger.info(
            "Added loss event: %s (Net Loss: EUR %.2f M)", 
            event.event_id, event.net_loss_amount
        )
    
    def get_events_by_year(self, year: int) -> List[LossEvent]:
        """Retrieve all events booked in a specific year."""
        return [e for e in self.events if e.booking_date.year == year]
    
    def get_events_by_type(self, event_type: str) -> List[LossEvent]:
        """Retrieve all events of a specific Basel Event Type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_by_business_line(self, business_line: str) -> List[LossEvent]:
        """Retrieve all events from a specific business line."""
        return [e for e in self.events if e.business_line == business_line]
    
    def get_events_date_range(self, start_date: date, end_date: date) -> List[LossEvent]:
        """Retrieve all events within a date range (by booking_date)."""
        return [
            e for e in self.events 
            if start_date <= e.booking_date <= end_date
        ]
    
    def get_all_events(self) -> List[LossEvent]:
        """Retrieve all loss events."""
        return self.events
    
    def get_event_by_id(self, event_id: str) -> Optional[LossEvent]:
        """Retrieve a specific event by ID."""
        for event in self.events:
            if event.event_id == event_id:
                return event
        return None
    
    def delete_event(self, event_id: str) -> bool:
        """Delete an event by ID. Returns True if deleted, False if not found."""
        for i, event in enumerate(self.events):
            if event.event_id == event_id:
                del self.events[i]
                self.save()
                logger.info("Deleted loss event: %s", event_id)
                return True
        logger.warning("Loss event not found: %s", event_id)
        return False
    
    def get_summary_statistics(self) -> dict:
        """Get summary statistics for all loss events."""
        if not self.events:
            return {
                "total_events": 0,
                "total_gross_loss": 0.0,
                "total_net_loss": 0.0,
                "avg_net_loss": 0.0,
                "max_loss": 0.0,
                "years_covered": 0,
            }
        
        total_gross = sum(e.gross_loss_amount for e in self.events)
        total_net = sum(e.net_loss_amount for e in self.events)
        max_loss = max(e.net_loss_amount for e in self.events)
        
        years = set(e.booking_date.year for e in self.events)
        
        return {
            "total_events": len(self.events),
            "total_gross_loss": total_gross,
            "total_net_loss": total_net,
            "avg_net_loss": total_net / len(self.events),
            "max_loss": max_loss,
            "years_covered": len(years),
            "year_range": f"{min(years)}-{max(years)}" if years else "N/A",
        }


# Singleton instance
_GLOBAL_LOSS_DB: Optional[LossEventDatabase] = None


def get_loss_event_database(db_file: Optional[str] = None) -> LossEventDatabase:
    """
    Get the global loss event database (lazy initialization).
    
    Parameters
    ----------
    db_file : Optional custom database file path
    
    Returns
    -------
    LossEventDatabase instance
    """
    global _GLOBAL_LOSS_DB
    if _GLOBAL_LOSS_DB is None or db_file is not None:
        _GLOBAL_LOSS_DB = LossEventDatabase(db_file)
    return _GLOBAL_LOSS_DB
