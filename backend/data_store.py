"""
In-memory data store with JSON file persistence for the energy broker API.

Keys:
  clients         : dict[str, dict]   — client objects keyed by client_id
  interval_data   : dict[str, list]   — client_id → [{timestamp, kwh}, ...]
  tariffs         : dict[str, dict]   — tariff objects keyed by tariff_id
  client_tariffs  : dict[str, str]    — client_id → tariff_id
  scenarios       : dict[str, dict]   — scenario_id → scenario object
  reports         : dict[str, dict]   — report_id → saved report object
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("data_store")

DATA_FILE = os.path.join(os.path.dirname(__file__), "data_store.json")

# ── In-memory stores ─────────────────────────────────────────────────────────

clients: dict = {}
interval_data: dict = {}
tariffs: dict = {}
client_tariffs: dict = {}
scenarios: dict = {}   # scenario_id → full scenario payload
reports: dict = {}     # report_id → saved report


# ── Persistence ──────────────────────────────────────────────────────────────

def load_from_disk() -> None:
    global clients, interval_data, tariffs, client_tariffs, scenarios, reports
    if not os.path.exists(DATA_FILE):
        logger.info("data_store.json not found — starting fresh, seeding retailer tariffs")
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
        scenarios = data.get("scenarios", {})
        reports = data.get("reports", {})
        if not tariffs:
            _seed_tariffs()
            save_to_disk()
        logger.info(
            "Loaded: %d clients, %d tariffs, %d scenarios, %d reports",
            len(clients), len(tariffs), len(scenarios), len(reports),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load data_store.json: %s — resetting", exc)
        clients = {}
        interval_data = {}
        tariffs = {}
        client_tariffs = {}
        scenarios = {}
        reports = {}
        _seed_tariffs()
        save_to_disk()


def save_to_disk() -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump({
                "clients": clients,
                "interval_data": interval_data,
                "tariffs": tariffs,
                "client_tariffs": client_tariffs,
                "scenarios": scenarios,
                "reports": reports,
            }, fh, indent=2)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to save data_store.json: %s", exc)


# ── Retailer tariff library (negotiation reference + selectable) ─────────────

# These are the canonical 5 AU retailers used for negotiation comparison
# (also exposed via GET /api/tariffs so brokers can assign them).
RETAILER_TARIFFS = [
    {
        "id": "tariff-agl-tou-vic",
        "retailer": "AGL",
        "plan_name": "AGL Business TOU VIC",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0945,
        "energy_rates": {"peak": 0.4287, "shoulder": 0.2854, "offpeak": 0.1925, "flat": None},
        "demand_charge": None,
        "network_charges": {"distribution": 0.0612, "transmission": 0.0187, "metering": 0.0165, "service": 0.0043},
        "environmental_levy": 0.0213,
    },
    {
        "id": "tariff-origin-tou-vic",
        "retailer": "Origin Energy",
        "plan_name": "Origin Business TOU",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0312,
        "energy_rates": {"peak": 0.4156, "shoulder": 0.2731, "offpeak": 0.1812, "flat": None},
        "demand_charge": None,
        "network_charges": {"distribution": 0.0612, "transmission": 0.0187, "metering": 0.0165, "service": 0.0043},
        "environmental_levy": 0.0213,
    },
    {
        "id": "tariff-energyaustralia-tou-vic",
        "retailer": "EnergyAustralia",
        "plan_name": "EA Flexi Business",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 1.1230,
        "energy_rates": {"peak": 0.4198, "shoulder": 0.2812, "offpeak": 0.1854, "flat": None},
        "demand_charge": None,
        "network_charges": {"distribution": 0.0612, "transmission": 0.0187, "metering": 0.0165, "service": 0.0043},
        "environmental_levy": 0.0213,
    },
    {
        "id": "tariff-alinta-tou-vic",
        "retailer": "Alinta Energy",
        "plan_name": "Alinta HomeDeal Business",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 0.9876,
        "energy_rates": {"peak": 0.4045, "shoulder": 0.2698, "offpeak": 0.1789, "flat": None},
        "demand_charge": None,
        "network_charges": {"distribution": 0.0612, "transmission": 0.0187, "metering": 0.0165, "service": 0.0043},
        "environmental_levy": 0.0213,
    },
    {
        "id": "tariff-redenergy-tou-vic",
        "retailer": "Red Energy",
        "plan_name": "Red Living Energy Saver Business",
        "type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0512,
        "energy_rates": {"peak": 0.4321, "shoulder": 0.2876, "offpeak": 0.1898, "flat": None},
        "demand_charge": None,
        "network_charges": {"distribution": 0.0612, "transmission": 0.0187, "metering": 0.0165, "service": 0.0043},
        "environmental_levy": 0.0213,
    },
]


def _seed_tariffs() -> None:
    """Pre-populate the retailer comparison set."""
    for t in RETAILER_TARIFFS:
        tariffs[t["id"]] = t
    logger.info("Seeded %d retailer tariffs", len(tariffs))


# ── Demo client (synthetic cafe with 17,520 half-hourly intervals) ──────────

import math
import random
from datetime import datetime, timedelta, timezone

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
_CAFE_PROFILE = (_CAFE_PROFILE + [_CAFE_PROFILE[-1]] * 48)[:48]


def _generate_synthetic_intervals(start_year: int = 2024) -> list:
    rng = random.Random(42)
    profile = _CAFE_PROFILE
    records: list = []
    start = datetime(start_year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for day in range(365):
        day_date = start + timedelta(days=day)
        season_phase = math.cos(2 * math.pi * day / 365.0)
        seasonal_mult = 1.0 + 0.20 * season_phase
        daily_mult = 1.0 + rng.uniform(-0.15, 0.15)
        wd_mult = 1.05 if day_date.weekday() >= 5 else 1.0
        day_mult = seasonal_mult * daily_mult * wd_mult
        for bucket in range(48):
            kw = profile[bucket] * day_mult
            kwh = kw * 0.5
            ts = day_date + timedelta(minutes=30 * bucket)
            records.append({"timestamp": ts.isoformat(), "kwh": round(max(kwh, 0.0), 4)})
    return records


def seed_demo_client() -> None:
    """Seed a fully built-out demo client with interval data and tariff.
    Does NOT seed any scenarios or reports — those start empty.
    Idempotent: skips if demo client already exists.
    """
    demo_id = "client-demo-001"
    if demo_id in clients:
        return

    intervals = _generate_synthetic_intervals(start_year=2024)
    interval_data[demo_id] = intervals

    clients[demo_id] = {
        "id": demo_id,
        "name": "Brunswick East Cafe",
        "address": "142 Lygon St, Brunswick East VIC 3057",
        "nmi": "6305987412",
        "site_type": "cafe",
        "status": "active",
        "created_at": "2026-01-15T09:00:00+00:00",
        "has_interval_data": True,
        "has_tariff": True,
        "tariff_id": "tariff-agl-tou-vic",
        "annual_kwh": 24800.0,
        "annual_cost": None,
    }
    client_tariffs[demo_id] = "tariff-agl-tou-vic"
    save_to_disk()
    logger.info("Seeded demo client %s with %d intervals", demo_id, len(intervals))
