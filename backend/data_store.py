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

DATA_FILE = "/app/backend/data_store.json"

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
