"""
PROMETHEUS Risk Platform
Operational Loss Generator — Synthetic Loss Event Creation

FILE PATH: backend/portfolio_generator/operational_loss_generator.py

Generates realistic synthetic operational loss events for testing and development.
Loss severity follows lognormal distribution (typical for operational risk).
"""

from __future__ import annotations
import random
from datetime import date, timedelta
from typing import List
import sys
import os

# Handle imports for both standalone and package usage
try:
    from backend.engines.operational_risk import LossEvent, BASEL_EVENT_TYPES, BASEL_BUSINESS_LINES
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engines.operational_risk import LossEvent, BASEL_EVENT_TYPES, BASEL_BUSINESS_LINES


def generate_random_loss_events(
    n_events: int = 100,
    start_year: int = 2015,
    end_year: int = 2025,
    mean_loss_eur_m: float = 0.5,
    loss_volatility: float = 1.5,
) -> List[LossEvent]:
    """
    Generate synthetic operational loss events for testing.
    
    Loss severity distribution follows a lognormal distribution
    (most losses small, few large tail losses — realistic for op risk).
    
    Parameters
    ----------
    n_events : Number of loss events to generate
    start_year : Start year for loss events
    end_year : End year for loss events
    mean_loss_eur_m : Mean loss amount in EUR millions
    loss_volatility : Volatility parameter for lognormal distribution
    
    Returns
    -------
    List of LossEvent objects
    
    Examples
    --------
    >>> # Generate 200 events for 10 years
    >>> events = generate_random_loss_events(n_events=200, start_year=2015, end_year=2025)
    >>> print(f"Generated {len(events)} loss events")
    >>> 
    >>> # Save to database
    >>> from backend.data_sources.loss_event_database import get_loss_event_database
    >>> db = get_loss_event_database()
    >>> for event in events:
    ...     db.add_event(event)
    """
    events = []
    event_types = list(BASEL_EVENT_TYPES.keys())
    business_lines = list(BASEL_BUSINESS_LINES.keys())
    
    # Lognormal parameters
    # mean_loss_eur_m = 0.5 → mu ≈ 13.1, sigma = 1.5 gives realistic tail
    mu = 13.1  # Adjust based on mean_loss_eur_m
    sigma = loss_volatility
    
    for i in range(n_events):
        # Random dates
        days_range = (date(end_year, 12, 31) - date(start_year, 1, 1)).days
        event_date = date(start_year, 1, 1) + timedelta(days=random.randint(0, days_range))
        discovery_date = event_date + timedelta(days=random.randint(1, 60))
        booking_date = discovery_date + timedelta(days=random.randint(1, 30))
        
        # Lognormal loss distribution (realistic)
        # Mean loss: ~EUR 0.5M, with occasional large losses up to EUR 50M
        gross_loss = random.lognormvariate(mu=mu, sigma=sigma) / 1_000_000  # EUR millions
        
        # Recoveries (0-30% of gross loss)
        recoveries = gross_loss * random.uniform(0, 0.3) if random.random() > 0.5 else 0.0
        
        # Insurance (0-20% of gross loss, only for larger losses)
        insurance = gross_loss * random.uniform(0, 0.2) if gross_loss > 1.0 and random.random() > 0.7 else 0.0
        
        # Generate realistic descriptions
        event_type = random.choice(event_types)
        business_line = random.choice(business_lines)
        
        descriptions = {
            "INTERNAL_FRAUD": [
                "Unauthorized trading activity",
                "Theft of proprietary information",
                "Employee embezzlement",
            ],
            "EXTERNAL_FRAUD": [
                "Cyberattack and data breach",
                "Third-party fraud",
                "Theft by external party",
            ],
            "EPWS": [
                "Discrimination lawsuit settlement",
                "Workplace safety incident",
                "Employee compensation claim",
            ],
            "CPBP": [
                "Mis-selling of financial products",
                "Breach of fiduciary duty",
                "Market manipulation fine",
            ],
            "DPA": [
                "Natural disaster damage",
                "Equipment failure",
                "Fire damage to facilities",
            ],
            "BDSF": [
                "IT system outage",
                "Cybersecurity breach",
                "Telecommunications failure",
            ],
            "EDPM": [
                "Failed transaction processing",
                "Data entry error",
                "Vendor dispute",
            ],
        }
        
        description = random.choice(descriptions.get(event_type, ["Operational loss event"]))
        
        root_causes = [
            "Inadequate controls",
            "System failure",
            "Human error",
            "External event",
            "Process deficiency",
        ]
        
        corrective_actions = [
            "Enhanced monitoring controls",
            "Process redesign",
            "Staff training program",
            "System upgrade",
            "Third-party review",
        ]
        
        event = LossEvent(
            event_id=f"LOSS_{start_year}_{i+1:04d}",
            event_date=event_date,
            discovery_date=discovery_date,
            booking_date=booking_date,
            event_type=event_type,
            business_line=business_line,
            gross_loss_amount=gross_loss,
            recoveries=recoveries,
            insurance_recovery=insurance,
            description=f"{description} - Synthetic event {i+1}",
            root_cause=random.choice(root_causes),
            corrective_action=random.choice(corrective_actions),
            status="CLOSED",
        )
        
        events.append(event)
    
    return events


def generate_scenario_loss_event(
    scenario_name: str,
    loss_amount_eur_m: float,
    event_year: int = 2025,
) -> LossEvent:
    """
    Generate a specific scenario loss event (for stress testing).
    
    Parameters
    ----------
    scenario_name : Name of the scenario
    loss_amount_eur_m : Loss amount in EUR millions
    event_year : Year when event occurs
    
    Returns
    -------
    LossEvent object
    
    Examples
    --------
    >>> # Generate major cyber attack scenario
    >>> cyber_event = generate_scenario_loss_event(
    ...     scenario_name="Major Cyberattack",
    ...     loss_amount_eur_m=25.0,
    ...     event_year=2025
    ... )
    """
    event_date = date(event_year, 6, 15)  # Mid-year
    discovery_date = event_date + timedelta(days=7)
    booking_date = discovery_date + timedelta(days=14)
    
    # Map scenario to Basel Event Type
    scenario_mapping = {
        "Major Cyberattack": ("BDSF", "TRADING_SALES"),
        "Employee Fraud": ("INTERNAL_FRAUD", "CORPORATE_FINANCE"),
        "External Fraud": ("EXTERNAL_FRAUD", "RETAIL_BANKING"),
        "Regulatory Fine": ("CPBP", "COMMERCIAL_BANKING"),
        "IT System Failure": ("BDSF", "PAYMENT_SETTLEMENT"),
        "Natural Disaster": ("DPA", "RETAIL_BANKING"),
    }
    
    event_type, business_line = scenario_mapping.get(
        scenario_name,
        ("EDPM", "COMMERCIAL_BANKING")  # Default
    )
    
    event = LossEvent(
        event_id=f"SCENARIO_{scenario_name.upper().replace(' ', '_')}_{event_year}",
        event_date=event_date,
        discovery_date=discovery_date,
        booking_date=booking_date,
        event_type=event_type,
        business_line=business_line,
        gross_loss_amount=loss_amount_eur_m,
        recoveries=loss_amount_eur_m * 0.1,  # 10% recovery
        insurance_recovery=loss_amount_eur_m * 0.15 if loss_amount_eur_m > 5.0 else 0.0,
        description=f"Scenario: {scenario_name}",
        root_cause=f"Stress test scenario: {scenario_name}",
        corrective_action="Scenario analysis - N/A",
        status="CLOSED",
    )
    
    return event


def generate_loss_events_by_year(
    events_per_year: int = 20,
    start_year: int = 2015,
    end_year: int = 2025,
) -> List[LossEvent]:
    """
    Generate loss events with consistent count per year.
    
    Useful for creating balanced historical datasets for ILM calculation.
    
    Parameters
    ----------
    events_per_year : Number of events per year
    start_year : Start year
    end_year : End year
    
    Returns
    -------
    List of LossEvent objects
    """
    all_events = []
    
    for year in range(start_year, end_year + 1):
        year_events = generate_random_loss_events(
            n_events=events_per_year,
            start_year=year,
            end_year=year,
        )
        all_events.extend(year_events)
    
    return all_events


if __name__ == "__main__":
    """
    Standalone script to generate and save loss events.
    
    Usage:
        python operational_loss_generator.py
    """
    print("=" * 60)
    print("PROMETHEUS Operational Loss Generator")
    print("=" * 60)
    
    # Generate 200 loss events over 10 years
    print("\nGenerating 200 synthetic loss events (2015-2025)...")
    events = generate_random_loss_events(
        n_events=200,
        start_year=2015,
        end_year=2025,
    )
    
    # Calculate statistics
    total_gross = sum(e.gross_loss_amount for e in events)
    total_net = sum(e.net_loss_amount for e in events)
    max_loss = max(e.net_loss_amount for e in events)
    
    print(f"\nGenerated {len(events)} loss events:")
    print(f"  Total Gross Loss: EUR {total_gross:.2f} million")
    print(f"  Total Net Loss: EUR {total_net:.2f} million")
    print(f"  Max Single Loss: EUR {max_loss:.2f} million")
    print(f"  Average Loss: EUR {total_net/len(events):.3f} million")
    
    # Event type distribution
    type_counts = {}
    for event in events:
        type_name = BASEL_EVENT_TYPES[event.event_type]
        type_counts[type_name] = type_counts.get(type_name, 0) + 1
    
    print("\nEvent Type Distribution:")
    for event_type, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {event_type}: {count} events ({count/len(events)*100:.1f}%)")
    
    # Save to JSON (optional)
    save_to_file = input("\nSave to loss_events.json? (y/n): ").lower().strip()
    
    if save_to_file == 'y':
        import json
        output_file = "loss_events.json"
        
        data = {
            "last_updated": date.today().isoformat(),
            "loss_events": [event.to_dict() for event in events],
        }
        
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✅ Saved {len(events)} events to {output_file}")
        print(f"   File path: {os.path.abspath(output_file)}")
        print(f"\n   Move this file to: backend/data_sources/loss_events.json")
    else:
        print("\nEvents not saved. Re-run when ready.")
    
    print("\n" + "=" * 60)
    print("Generation complete!")
    print("=" * 60)
