"""
In-memory data store with JSON file persistence for the energy broker API.

Keys:
  clients        : dict[str, dict]   — client objects keyed by client_id
  interval_data  : dict[str, list]   — client_id → [{timestamp, kwh}, ...]
  tariffs        : dict[str, dict]   — tariff objects keyed by tariff_id
  client_tariffs : dict[str, str]    — client_id → tariff_id
  client_scenarios: dict[str, list]  — client_id → list of scenario results
"""
from __future__ import annotations

import json
import os
import logging

logger = logging.getLogger("data_store")

DATA_FILE = "/home/user/Energy-Price-Demand-Projection/backend/data_store.json"

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


# ── Seed data ────────────────────────────────────────────────────────────────

def _seed_tariffs() -> None:
    """Pre-populate 10 demo Australian tariffs."""
    seed = [
        {
            "id": "tariff-001",
            "retailer": "AGL",
            "plan_name": "AGL Residential TOU",
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
        },
        {
            "id": "tariff-002",
            "retailer": "Origin Energy",
            "plan_name": "Origin Everyday Flat",
            "type": "Flat",
            "state": "VIC",
            "supply_charge": 0.9876,
            "energy_rates": {
                "peak": None,
                "shoulder": None,
                "offpeak": None,
                "flat": 0.2987,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0598,
                "transmission": 0.0179,
                "metering": 0.0158,
                "service": 0.0040,
            },
            "environmental_levy": 0.0198,
        },
        {
            "id": "tariff-003",
            "retailer": "EnergyAustralia",
            "plan_name": "EA Demand Advantage",
            "type": "Demand",
            "state": "VIC",
            "supply_charge": 1.1200,
            "energy_rates": {
                "peak": 0.3876,
                "shoulder": 0.2654,
                "offpeak": 0.1754,
                "flat": None,
            },
            "demand_charge": 18.50,
            "network_charges": {
                "distribution": 0.0623,
                "transmission": 0.0191,
                "metering": 0.0170,
                "service": 0.0045,
            },
            "environmental_levy": 0.0221,
        },
        {
            "id": "tariff-004",
            "retailer": "AGL",
            "plan_name": "AGL Business TOU",
            "type": "TOU",
            "state": "NSW",
            "supply_charge": 1.1532,
            "energy_rates": {
                "peak": 0.4512,
                "shoulder": 0.3021,
                "offpeak": 0.1876,
                "flat": None,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0734,
                "transmission": 0.0221,
                "metering": 0.0182,
                "service": 0.0052,
            },
            "environmental_levy": 0.0231,
        },
        {
            "id": "tariff-005",
            "retailer": "Origin Energy",
            "plan_name": "Origin Business Flat",
            "type": "Flat",
            "state": "NSW",
            "supply_charge": 1.0453,
            "energy_rates": {
                "peak": None,
                "shoulder": None,
                "offpeak": None,
                "flat": 0.3156,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0721,
                "transmission": 0.0213,
                "metering": 0.0175,
                "service": 0.0048,
            },
            "environmental_levy": 0.0219,
        },
        {
            "id": "tariff-006",
            "retailer": "EnergyAustralia",
            "plan_name": "EA Flex Demand NSW",
            "type": "Demand",
            "state": "NSW",
            "supply_charge": 1.2100,
            "energy_rates": {
                "peak": 0.4123,
                "shoulder": 0.2876,
                "offpeak": 0.1654,
                "flat": None,
            },
            "demand_charge": 21.30,
            "network_charges": {
                "distribution": 0.0745,
                "transmission": 0.0228,
                "metering": 0.0188,
                "service": 0.0055,
            },
            "environmental_levy": 0.0243,
        },
        {
            "id": "tariff-007",
            "retailer": "Energex",
            "plan_name": "Energex Residential TOU",
            "type": "TOU",
            "state": "QLD",
            "supply_charge": 1.0234,
            "energy_rates": {
                "peak": 0.4056,
                "shoulder": 0.2743,
                "offpeak": 0.1832,
                "flat": None,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0687,
                "transmission": 0.0198,
                "metering": 0.0161,
                "service": 0.0042,
            },
            "environmental_levy": 0.0205,
        },
        {
            "id": "tariff-008",
            "retailer": "Origin Energy",
            "plan_name": "Origin Solar Saver QLD",
            "type": "TOU",
            "state": "QLD",
            "supply_charge": 0.9543,
            "energy_rates": {
                "peak": 0.3876,
                "shoulder": 0.2543,
                "offpeak": 0.1654,
                "flat": None,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0671,
                "transmission": 0.0192,
                "metering": 0.0158,
                "service": 0.0041,
            },
            "environmental_levy": 0.0197,
        },
        {
            "id": "tariff-009",
            "retailer": "SA Power Networks",
            "plan_name": "SAPN Business Demand",
            "type": "Demand",
            "state": "SA",
            "supply_charge": 1.3210,
            "energy_rates": {
                "peak": 0.4987,
                "shoulder": 0.3123,
                "offpeak": 0.1987,
                "flat": None,
            },
            "demand_charge": 24.75,
            "network_charges": {
                "distribution": 0.0856,
                "transmission": 0.0265,
                "metering": 0.0201,
                "service": 0.0061,
            },
            "environmental_levy": 0.0267,
        },
        {
            "id": "tariff-010",
            "retailer": "AGL",
            "plan_name": "AGL SA Flat Business",
            "type": "Flat",
            "state": "SA",
            "supply_charge": 1.1876,
            "energy_rates": {
                "peak": None,
                "shoulder": None,
                "offpeak": None,
                "flat": 0.3654,
            },
            "demand_charge": None,
            "network_charges": {
                "distribution": 0.0834,
                "transmission": 0.0251,
                "metering": 0.0195,
                "service": 0.0058,
            },
            "environmental_levy": 0.0254,
        },
    ]
    for t in seed:
        tariffs[t["id"]] = t
    logger.info("Seeded %d demo tariffs", len(seed))
