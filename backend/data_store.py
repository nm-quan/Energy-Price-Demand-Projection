"""
In-memory data store with JSON file persistence for the energy broker API.

Keys:
  clients         : dict[str, dict]   — client objects keyed by client_id
  interval_data   : dict[str, list]   — client_id → [{timestamp, kwh}, ...]
  tariffs         : dict[str, dict]   — tariff objects keyed by tariff_id
  client_tariffs  : dict[str, str]    — client_id → tariff_id
  client_scenarios: dict[str, list]   — client_id → list of scenario results
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("data_store")

DATA_FILE = "/app/backend/data_store.json"

# ── In-memory stores ─────────────────────────────────────────────────────────

clients: dict = {}
interval_data: dict = {}
tariffs: dict = {}
client_tariffs: dict = {}
client_scenarios: dict = {}


# ── Persistence ──────────────────────────────────────────────────────────────

def load_from_disk() -> None:
    """Load state from DATA_FILE if it exists."""
    global clients, interval_data, tariffs, client_tariffs, client_scenarios
    if not os.path.exists(DATA_FILE):
        logger.info("data_store.json not found — starting fresh and seeding tariffs")
        _seed_tariffs()
        save_to_disk()
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        clients = data.get("clients", {})
        interval_data = data.get("interval_data", {})
        tariffs = data.get("tariffs", {})
        client_tariffs = data.get("client_tariffs", {})
        client_scenarios = data.get("client_scenarios", {})
        # Ensure seed tariffs are always present (idempotent)
        if not tariffs:
            _seed_tariffs()
            save_to_disk()
        # Idempotently ensure the AGL TOU VIC demo tariff exists
        if "tariff-agl-tou-vic" not in tariffs:
            _seed_demo_tariff()
            save_to_disk()
        logger.info(
            "Loaded from disk: %d clients, %d tariffs", len(clients), len(tariffs)
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load data_store.json: %s — resetting", exc)
        clients = {}
        interval_data = {}
        tariffs = {}
        client_tariffs = {}
        client_scenarios = {}
        _seed_tariffs()
        save_to_disk()


def save_to_disk() -> None:
    """Persist current in-memory state to DATA_FILE."""
    try:
        data = {
            "clients": clients,
            "interval_data": interval_data,
            "tariffs": tariffs,
            "client_tariffs": client_tariffs,
            "client_scenarios": client_scenarios,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save data_store.json: %s", exc)


# ── Demo tariff (AGL TOU VIC) ────────────────────────────────────────────────

def _seed_demo_tariff() -> None:
    """Seed the AGL TOU VIC tariff required by the demo client."""
    tariffs["tariff-agl-tou-vic"] = {
        "id": "tariff-agl-tou-vic",
        "retailer": "AGL",
        "plan_name": "AGL Business TOU VIC",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0945,
        "energy_rates": {
            "peak": 0.4287,
            "shoulder": 0.2854,
            "offpeak": 0.1925,
            "flat": None,
        },
        "demand_charge": None,
        "network_charges": {
            "distribution": 0.0612,
            "transmission": 0.0187,
            "metering": 0.0165,
            "service": 0.0043,
        },
        "environmental_levy": 0.0213,
    }


# ── Seed tariffs ─────────────────────────────────────────────────────────────

def _seed_tariffs() -> None:
    """Pre-populate Australian demo tariffs."""
    _seed_demo_tariff()  # AGL TOU VIC required by demo client

    seed = [
        {
            "id": "tariff-origin-flat-vic",
            "retailer": "Origin Energy",
            "plan_name": "Origin Everyday Flat",
            "type": "Flat",
            "state": "VIC",
            "supply_charge": 0.9876,
            "energy_rates": {"peak": None, "shoulder": None, "offpeak": None, "flat": 0.2987},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0598, "transmission": 0.0179, "metering": 0.0158, "service": 0.0040},
            "environmental_levy": 0.0198,
        },
        {
            "id": "tariff-ea-demand-vic",
            "retailer": "EnergyAustralia",
            "plan_name": "EA Demand Advantage",
            "type": "Demand",
            "state": "VIC",
            "supply_charge": 1.1200,
            "energy_rates": {"peak": 0.3876, "shoulder": 0.2654, "offpeak": 0.1754, "flat": None},
            "demand_charge": 18.50,
            "network_charges": {"distribution": 0.0623, "transmission": 0.0191, "metering": 0.0170, "service": 0.0045},
            "environmental_levy": 0.0221,
        },
        {
            "id": "tariff-agl-tou-nsw",
            "retailer": "AGL",
            "plan_name": "AGL Business TOU",
            "type": "TOU",
            "state": "NSW",
            "supply_charge": 1.1532,
            "energy_rates": {"peak": 0.4512, "shoulder": 0.3021, "offpeak": 0.1876, "flat": None},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0734, "transmission": 0.0221, "metering": 0.0182, "service": 0.0052},
            "environmental_levy": 0.0231,
        },
        {
            "id": "tariff-origin-flat-nsw",
            "retailer": "Origin Energy",
            "plan_name": "Origin Business Flat",
            "type": "Flat",
            "state": "NSW",
            "supply_charge": 1.0453,
            "energy_rates": {"peak": None, "shoulder": None, "offpeak": None, "flat": 0.3156},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0721, "transmission": 0.0213, "metering": 0.0175, "service": 0.0048},
            "environmental_levy": 0.0219,
        },
        {
            "id": "tariff-ea-demand-nsw",
            "retailer": "EnergyAustralia",
            "plan_name": "EA Flex Demand NSW",
            "type": "Demand",
            "state": "NSW",
            "supply_charge": 1.2100,
            "energy_rates": {"peak": 0.4123, "shoulder": 0.2876, "offpeak": 0.1654, "flat": None},
            "demand_charge": 21.30,
            "network_charges": {"distribution": 0.0745, "transmission": 0.0228, "metering": 0.0188, "service": 0.0055},
            "environmental_levy": 0.0243,
        },
        {
            "id": "tariff-energex-tou-qld",
            "retailer": "Energex",
            "plan_name": "Energex Residential TOU",
            "type": "TOU",
            "state": "QLD",
            "supply_charge": 1.0234,
            "energy_rates": {"peak": 0.4056, "shoulder": 0.2743, "offpeak": 0.1832, "flat": None},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0687, "transmission": 0.0198, "metering": 0.0161, "service": 0.0042},
            "environmental_levy": 0.0205,
        },
        {
            "id": "tariff-origin-solar-qld",
            "retailer": "Origin Energy",
            "plan_name": "Origin Solar Saver QLD",
            "type": "TOU",
            "state": "QLD",
            "supply_charge": 0.9543,
            "energy_rates": {"peak": 0.3876, "shoulder": 0.2543, "offpeak": 0.1654, "flat": None},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0671, "transmission": 0.0192, "metering": 0.0158, "service": 0.0041},
            "environmental_levy": 0.0197,
        },
        {
            "id": "tariff-sapn-demand-sa",
            "retailer": "SA Power Networks",
            "plan_name": "SAPN Business Demand",
            "type": "Demand",
            "state": "SA",
            "supply_charge": 1.3210,
            "energy_rates": {"peak": 0.4987, "shoulder": 0.3123, "offpeak": 0.1987, "flat": None},
            "demand_charge": 24.75,
            "network_charges": {"distribution": 0.0856, "transmission": 0.0265, "metering": 0.0201, "service": 0.0061},
            "environmental_levy": 0.0267,
        },
        {
            "id": "tariff-agl-flat-sa",
            "retailer": "AGL",
            "plan_name": "AGL SA Flat Business",
            "type": "Flat",
            "state": "SA",
            "supply_charge": 1.1876,
            "energy_rates": {"peak": None, "shoulder": None, "offpeak": None, "flat": 0.3654},
            "demand_charge": None,
            "network_charges": {"distribution": 0.0834, "transmission": 0.0251, "metering": 0.0195, "service": 0.0058},
            "environmental_levy": 0.0254,
        },
    ]
    for t in seed:
        tariffs[t["id"]] = t
    logger.info("Seeded %d demo tariffs", len(tariffs))


# ── Demo client + synthetic interval seeding ─────────────────────────────────

# Cafe load shape (48 half-hourly kW values) — same as server.py SYNTHETIC_PROFILES["cafe"]
_CAFE_PROFILE = [
    0.8, 0.8, 0.6, 0.6, 0.6, 0.8,
    2.1, 3.2, 4.1, 4.8,
    5.2, 5.6, 5.8, 5.6, 5.0, 4.6,
    4.2, 4.4, 4.6, 4.8,
    5.1, 5.4, 5.6, 5.4,
    4.9, 4.2, 3.6,
    2.8, 2.1, 1.5, 1.2,
    1.0, 0.9, 0.8, 0.8, 0.7, 0.7,
    0.7, 0.7, 0.8, 0.8, 0.8, 0.8,
    0.8, 0.8, 0.8, 0.8, 0.8,
]
# Ensure exactly 48 buckets
_CAFE_PROFILE = (_CAFE_PROFILE + [_CAFE_PROFILE[-1]] * 48)[:48]


def _generate_synthetic_intervals(start_year: int = 2024) -> list:
    """
    Generate 17,520 (365 × 48) half-hourly interval records using the cafe
    shape with ±15% daily variance and ±20% seasonal variance (sinusoidal).

    Each record: {"timestamp": ISO string, "kwh": float}
    """
    # Deterministic synthetic data so the demo is reproducible across restarts.
    rng = random.Random(42)
    profile = _CAFE_PROFILE
    records: list = []
    start = datetime(start_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for day in range(365):
        day_date = start + timedelta(days=day)
        # Seasonal: peaks in summer (Jan, day≈0) and winter (Jul, day≈180)
        # Australia: summer = Dec-Feb (cooling load) → use cosine
        season_phase = math.cos(2 * math.pi * day / 365.0)  # 1 at day 0
        seasonal_mult = 1.0 + 0.20 * season_phase
        # Daily variance ±15%
        daily_mult = 1.0 + rng.uniform(-0.15, 0.15)
        # Weekday vs weekend: cafés are busier on weekends in this scenario
        wd_mult = 1.05 if day_date.weekday() >= 5 else 1.0
        day_mult = seasonal_mult * daily_mult * wd_mult
        for bucket in range(48):
            kw = profile[bucket] * day_mult
            # Half-hour → kWh
            kwh = kw * 0.5
            ts = day_date + timedelta(minutes=30 * bucket)
            records.append({
                "timestamp": ts.isoformat(),
                "kwh": round(max(kwh, 0.0), 4),
            })
    return records


def seed_demo_data() -> None:
    """Seed a fully built-out demo client so the app is never blank."""
    demo_id = "client-demo-001"
    if demo_id in clients:
        logger.info("Demo client already present — skipping seed")
        return
    # Ensure AGL TOU VIC tariff exists
    if "tariff-agl-tou-vic" not in tariffs:
        _seed_demo_tariff()

    intervals = _generate_synthetic_intervals(start_year=2024)
    interval_data[demo_id] = intervals

    clients[demo_id] = {
        "id": demo_id,
        "broker_id": "broker-1",
        "name": "Brunswick East Café",
        "address": "142 Lygon St, Brunswick East VIC 3057",
        "nmi": "6305987412",
        "site_type": "cafe",
        "status": "active",
        "created_at": "2026-05-01T09:00:00+00:00",
        "has_interval_data": True,
        "has_tariff": True,
        "tariff_id": "tariff-agl-tou-vic",
        "annual_kwh": 24800.0,
        "annual_cost": 9200.0,
    }
    client_tariffs[demo_id] = "tariff-agl-tou-vic"
    save_to_disk()
    logger.info("Seeded demo client %s with %d intervals", demo_id, len(intervals))
