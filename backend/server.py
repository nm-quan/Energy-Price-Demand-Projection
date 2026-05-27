"""
Energy Broker API — FastAPI backend (no auth, no demo, dynamic scenarios).
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# In-memory job store for async scenario generation
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()

import data_store
from models import (
    ClientCreate,
    Tariff,
    TariffAssign,
)
from interval_parser import (
    parse_interval_csv,
    build_typical_weekday,
    compute_interval_stats,
)
import anthropic as _anthropic
import os

from baseline_engine import compute_baseline, compute_shape_metrics
from scenario_claude import generate_scenarios, generate_single, _has_api_key, compute_retailer_comparison
from ai_engine import stream_analysis as _stream_analysis

logger = logging.getLogger("broker_api")
logging.basicConfig(level=logging.INFO)


# ── Realistic per-appliance profiles for cafe (48 half-hourly kW) ─────────────
# Each appliance has an independent curve based on real cafe operations.
# Bucket mapping: b=0 → 00:00, b=12 → 06:00, b=30 → 15:00 (TOU peak start),
#                 b=42 → 21:00 (TOU peak end), b=47 → 23:30

CAFE_APPLIANCE_PROFILES: Dict[str, List[float]] = {
    # HVAC: low overnight, ramps with morning heat, peaks hard during 3–9pm
    "HVAC": [
        # b0–11  midnight–6am: night setback
        0.20, 0.20, 0.18, 0.18, 0.16, 0.16, 0.16, 0.16, 0.18, 0.20, 0.30, 0.45,
        # b12–17  6am–9am: opening, morning warmup
        0.80, 1.00, 1.20, 1.40, 1.55, 1.65,
        # b18–23  9am–12pm: building heat load
        1.75, 1.85, 1.95, 2.05, 2.15, 2.30,
        # b24–29  12pm–3pm: midday heat rising
        2.45, 2.55, 2.65, 2.75, 2.80, 2.85,
        # b30–35  3pm–6pm  TOU PEAK: hottest part of day
        2.90, 3.00, 3.05, 3.00, 2.95, 2.85,
        # b36–41  6pm–9pm  TOU PEAK: cooling but still warm
        2.70, 2.50, 2.30, 2.10, 1.90, 1.70,
        # b42–47  9pm–midnight: wind-down
        1.30, 1.00, 0.70, 0.50, 0.35, 0.25,
    ],
    # Fridges: run 24/7, higher during service hours and warm afternoon
    "Fridges": [
        # b0–11  midnight–6am: steady overnight cycling
        0.82, 0.80, 0.78, 0.78, 0.76, 0.76, 0.78, 0.78, 0.80, 0.82, 0.88, 0.95,
        # b12–17  6am–9am: morning deliveries, door activity
        1.05, 1.10, 1.20, 1.25, 1.35, 1.45,
        # b18–23  9am–12pm: busy service, frequent openings
        1.55, 1.60, 1.65, 1.70, 1.72, 1.75,
        # b24–29  12pm–3pm: lunch rush, peak door activity
        1.82, 1.85, 1.80, 1.75, 1.68, 1.62,
        # b30–35  3pm–6pm  TOU PEAK: warm ambient, still operating
        1.68, 1.72, 1.72, 1.68, 1.62, 1.55,
        # b36–41  6pm–9pm  TOU PEAK: tapering
        1.48, 1.42, 1.35, 1.28, 1.18, 1.10,
        # b42–47  9pm–midnight: closing cleanup
        1.02, 0.95, 0.90, 0.86, 0.83, 0.82,
    ],
    # Ovens: pre-heat 5am, full operation breakfast + lunch, mostly done by 3pm
    "Ovens": [
        # b0–11  midnight–6am: off overnight
        0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.35, 0.70,
        # b12–17  6am–9am: pre-heat then full breakfast operation
        2.10, 2.50, 2.80, 2.95, 3.00, 2.95,
        # b18–23  9am–12pm: morning bakes, tapering toward lunch
        2.85, 2.75, 2.60, 2.45, 2.30, 2.10,
        # b24–29  12pm–3pm: lunch service, winding down
        1.85, 1.55, 1.20, 0.90, 0.65, 0.50,
        # b30–35  3pm–6pm  TOU PEAK: very low (small afternoon batch only)
        0.45, 0.40, 0.35, 0.35, 0.40, 0.35,
        # b36–41  6pm–9pm  TOU PEAK: essentially off
        0.20, 0.15, 0.12, 0.12, 0.10, 0.10,
        # b42–47  9pm–midnight: off
        0.10, 0.10, 0.10, 0.10, 0.10, 0.10,
    ],
    # Espresso: dominant morning rush, real afternoon coffee trade 3–5pm
    "Espresso": [
        # b0–11  midnight–6am: standby/off
        0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.15, 0.40,
        # b12–17  6am–9am: warm-up then morning rush building
        0.70, 0.90, 1.30, 1.60, 1.85, 1.90,
        # b18–23  9am–12pm: morning rush peak then easing
        1.85, 1.75, 1.60, 1.45, 1.20, 1.00,
        # b24–29  12pm–3pm: lunch crowd, slowing toward afternoon
        0.85, 0.75, 0.65, 0.58, 0.52, 0.50,
        # b30–35  3pm–6pm  TOU PEAK: afternoon coffee trade (real!)
        0.55, 0.65, 0.70, 0.68, 0.62, 0.55,
        # b36–41  6pm–9pm  TOU PEAK: evening wind-down
        0.42, 0.32, 0.22, 0.15, 0.10, 0.08,
        # b42–47  9pm–midnight: off
        0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
    ],
    # Hot Water: morning peak for coffee service and cleaning
    "Hot Water": [
        # b0–11  midnight–6am: minimal
        0.10, 0.10, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.10, 0.10, 0.25, 0.45,
        # b12–17  6am–9am: heating up, morning service
        0.65, 0.70, 0.88, 0.95, 1.05, 1.08,
        # b18–23  9am–12pm: full service
        0.95, 0.88, 0.78, 0.72, 0.65, 0.60,
        # b24–29  12pm–3pm: post-lunch cleanup
        0.58, 0.55, 0.52, 0.50, 0.48, 0.45,
        # b30–35  3pm–6pm  TOU PEAK: low
        0.42, 0.40, 0.38, 0.36, 0.32, 0.28,
        # b36–41  6pm–9pm  TOU PEAK: minimal
        0.22, 0.18, 0.15, 0.12, 0.12, 0.10,
        # b42–47  9pm–midnight: off
        0.10, 0.10, 0.10, 0.10, 0.10, 0.10,
    ],
    # Dishwasher: post-rush cycles — importantly runs through afternoon TOU window
    "Dishwasher": [
        # b0–15  midnight–8am: off
        0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
        0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
        # b16–21  8am–11am: post-breakfast wash cycles
        0.45, 0.70, 0.85, 0.75, 0.60, 0.40,
        # b22–29  11am–3pm: post-lunch heavy cycle
        0.25, 0.20, 0.65, 0.85, 1.00, 1.05, 0.95, 0.80,
        # b30–35  3pm–6pm  TOU PEAK: afternoon cleanup cycles
        0.65, 0.50, 0.40, 0.40, 0.50, 0.60,
        # b36–41  6pm–9pm  TOU PEAK: end-of-day wash
        0.65, 0.70, 0.55, 0.35, 0.20, 0.10,
        # b42–47  9pm–midnight: off
        0.05, 0.05, 0.05, 0.05, 0.05, 0.05,
    ],
    # Lighting: security overnight, full during trading hours
    "Lighting": [
        # b0–11  midnight–6am: security lights only
        0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.12, 0.18,
        # b12–17  6am–9am: opening lights on
        0.55, 0.60, 0.65, 0.65, 0.65, 0.65,
        # b18–23  9am–12pm: full trading
        0.65, 0.65, 0.65, 0.65, 0.65, 0.65,
        # b24–29  12pm–3pm: full trading
        0.65, 0.65, 0.65, 0.65, 0.65, 0.65,
        # b30–35  3pm–6pm  TOU PEAK: full trading
        0.65, 0.65, 0.65, 0.65, 0.65, 0.65,
        # b36–41  6pm–9pm  TOU PEAK: closing, lights dimming
        0.62, 0.58, 0.50, 0.40, 0.30, 0.20,
        # b42–47  9pm–midnight: security only
        0.12, 0.10, 0.08, 0.08, 0.08, 0.08,
    ],
    # Misc: POS, tablets, displays — flat during trading hours
    "Misc": [
        # b0–11  midnight–6am: minimal
        0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.06, 0.08,
        # b12–17  6am–9am: systems coming online
        0.20, 0.22, 0.28, 0.30, 0.30, 0.30,
        # b18–23  9am–12pm: full operation
        0.30, 0.30, 0.30, 0.30, 0.30, 0.30,
        # b24–29  12pm–3pm: full operation
        0.30, 0.30, 0.30, 0.30, 0.30, 0.28,
        # b30–35  3pm–6pm  TOU PEAK: still operating
        0.28, 0.28, 0.28, 0.28, 0.28, 0.28,
        # b36–41  6pm–9pm  TOU PEAK: closing down
        0.25, 0.22, 0.18, 0.15, 0.10, 0.08,
        # b42–47  9pm–midnight: standby
        0.05, 0.05, 0.04, 0.04, 0.04, 0.04,
    ],
}

# Validate all profiles are exactly 48 buckets
for _app, _curve in CAFE_APPLIANCE_PROFILES.items():
    assert len(_curve) == 48, f"CAFE_APPLIANCE_PROFILES[{_app!r}] has {len(_curve)} buckets, need 48"

# Site types that have realistic per-appliance profiles (others fall back to weights)
APPLIANCE_PROFILES_BY_SITE: Dict[str, Dict[str, List[float]]] = {
    "cafe": CAFE_APPLIANCE_PROFILES,
}

# ── Synthetic profiles by site_type (48 half-hourly kW values) ───────────────
# Cafe total is derived from the sum of its appliance profiles so they stay consistent.

def _sum_appliance_profiles(profiles: Dict[str, List[float]]) -> List[float]:
    total = [0.0] * 48
    for curve in profiles.values():
        for i, v in enumerate(curve):
            total[i] += v
    return [round(v, 4) for v in total]

SYNTHETIC_PROFILES: Dict[str, List[float]] = {
    "cafe": _sum_appliance_profiles(CAFE_APPLIANCE_PROFILES),
    "office": [
        1.2, 1.1, 1.0, 0.9, 0.9, 1.0, 1.2,
        2.5, 3.8,
        5.2, 6.1, 6.8, 7.2,
        6.5, 6.0,
        6.8, 7.5, 8.1, 8.4, 8.2, 7.9,
        6.5, 5.2,
        3.1, 2.4,
        1.8, 1.6, 1.5, 1.4,
        1.3, 1.2, 1.2, 1.2, 1.1, 1.1,
        1.1, 1.1, 1.2, 1.2, 1.2, 1.2,
        1.2, 1.2, 1.2, 1.2, 1.2, 1.2,
    ],
    "retail": [
        0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.6, 0.8,
        2.4, 3.2,
        4.5, 5.2, 6.1, 6.8, 7.2, 7.5, 7.8, 7.9, 7.5, 7.1,
        7.8, 8.2, 8.5, 8.1,
        6.5, 4.8, 3.2,
        2.1, 1.5, 1.0, 0.8, 0.7,
        0.6, 0.5, 0.5, 0.5, 0.5, 0.5,
        0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
        0.5, 0.5, 0.5, 0.5,
    ],
    "industrial": [
        8.5, 7.2, 6.8, 6.5, 6.8, 7.2,
        9.5, 12.4,
        15.8, 18.2, 19.5, 20.1, 20.4, 19.8,
        20.2, 20.6, 21.0, 21.3, 21.0, 20.5,
        20.8, 21.2, 21.5,
        18.5, 16.2,
        13.5, 12.1, 11.4, 10.8, 10.5,
        9.2, 8.8,
        8.6, 8.5, 8.5, 8.5, 8.5, 8.5,
        8.5, 8.5, 8.5, 8.5, 8.5, 8.5,
        8.5, 8.5, 8.5, 8.5, 8.5, 8.5,
    ],
    "hospitality": [
        3.2, 2.8, 2.5, 2.4, 2.4, 2.6,
        4.5, 6.8, 8.2,
        9.5, 10.8, 11.2, 11.5,
        12.1, 12.8,
        11.5, 10.8, 10.2,
        11.8, 13.2, 14.5, 15.2, 15.8, 15.5, 14.8, 13.5,
        10.2, 7.5, 5.8, 4.5,
        3.8, 3.5, 3.3, 3.2, 3.2, 3.2,
        3.2, 3.2, 3.2, 3.2, 3.2, 3.2,
        3.2, 3.2, 3.2, 3.2, 3.2, 3.2,
    ],
}

for _st, _prof in SYNTHETIC_PROFILES.items():
    if len(_prof) < 48:
        _prof.extend([_prof[-1]] * (48 - len(_prof)))
    SYNTHETIC_PROFILES[_st] = _prof[:48]


def _get_synthetic_profile(site_type: str) -> List[float]:
    profile = SYNTHETIC_PROFILES.get(site_type.lower(), SYNTHETIC_PROFILES["office"])
    return list(profile)


# ── Appliance split ───────────────────────────────────────────────────────────

APPLIANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "office":      {"Fridges": 0.06, "Espresso": 0.04, "Ovens": 0.02, "HVAC": 0.45, "Lighting": 0.20, "Dishwasher": 0.02, "Hot Water": 0.05, "Misc": 0.16},
    "retail":      {"Fridges": 0.20, "Espresso": 0.03, "Ovens": 0.05, "HVAC": 0.30, "Lighting": 0.25, "Dishwasher": 0.02, "Hot Water": 0.03, "Misc": 0.12},
    "industrial":  {"Fridges": 0.05, "Espresso": 0.01, "Ovens": 0.05, "HVAC": 0.15, "Lighting": 0.10, "Dishwasher": 0.02, "Hot Water": 0.05, "Misc": 0.57},
    "hospitality": {"Fridges": 0.18, "Espresso": 0.06, "Ovens": 0.22, "HVAC": 0.22, "Lighting": 0.10, "Dishwasher": 0.09, "Hot Water": 0.08, "Misc": 0.05},
}


def _split_appliance_curves(load_curve: List[float], site_type: str) -> Dict[str, List[float]]:
    stype = site_type.lower()
    # For site types with realistic per-appliance profiles, scale them to match
    # the input load curve's total energy (handles store-level scaling).
    if stype in APPLIANCE_PROFILES_BY_SITE:
        profiles = APPLIANCE_PROFILES_BY_SITE[stype]
        base_sum = sum(v for curve in profiles.values() for v in curve)
        input_sum = sum(load_curve)
        scale = (input_sum / base_sum) if base_sum > 0 else 1.0
        return {name: [round(v * scale, 4) for v in curve] for name, curve in profiles.items()}
    # Fallback: proportional weight split
    weights = APPLIANCE_WEIGHTS.get(stype, APPLIANCE_WEIGHTS["office"])
    return {name: [round(load_curve[b] * w, 4) for b in range(len(load_curve))] for name, w in weights.items()}


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Energy Broker API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    data_store.load_from_disk()
    if not data_store.clients:
        logger.info("No clients found — seeding synthetic demo client")
        data_store.seed_demo_client()
    # Seed demo stores if the demo client exists but has no stores yet
    demo_has_stores = any(v.get("client_id") == "client-demo-001" for v in data_store.stores.values())
    if "client-demo-001" in data_store.clients and not demo_has_stores:
        logger.info("Seeding demo stores for client-demo-001")
        data_store.seed_demo_stores()
    logger.info("Data store loaded — %d clients, %d stores, %d tariffs, %d scenarios, %d reports",
                len(data_store.clients), len(data_store.stores), len(data_store.tariffs),
                len(data_store.scenarios), len(data_store.reports))


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok", "claude": _has_api_key()}


# ── Clients ──────────────────────────────────────────────────────────────────

@app.get("/api/clients")
def list_clients():
    return list(data_store.clients.values())


@app.post("/api/clients", status_code=201)
def create_client(body: ClientCreate):
    client_id = f"client-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    client = {
        "id": client_id,
        "name": body.name,
        "address": body.address,
        "nmi": body.nmi,
        "site_type": body.site_type,
        "status": "active",
        "created_at": now,
        "has_interval_data": False,
        "has_tariff": False,
        "tariff_id": None,
        "annual_kwh": None,
        "annual_cost": None,
    }
    data_store.clients[client_id] = client
    data_store.save_to_disk()
    return client


@app.get("/api/clients/{client_id}")
def get_client(client_id: str):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.delete("/api/clients/{client_id}")
def delete_client(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    data_store.clients.pop(client_id, None)
    data_store.interval_data.pop(client_id, None)
    data_store.client_tariffs.pop(client_id, None)
    for sid in [k for k, v in data_store.stores.items() if v.get("client_id") == client_id]:
        data_store.stores.pop(sid, None)
    for sid in [k for k, v in data_store.scenarios.items() if v.get("client_id") == client_id]:
        data_store.scenarios.pop(sid, None)
    for rid in [k for k, v in data_store.reports.items() if v.get("client_id") == client_id]:
        data_store.reports.pop(rid, None)
    data_store.save_to_disk()
    return {"deleted": True}


# ── Stores ───────────────────────────────────────────────────────────────────

class StoreCreate(BaseModel):
    name: str
    address: Optional[str] = None
    site_type: str = "cafe"
    nmi: Optional[str] = None
    annual_kwh: Optional[float] = None


@app.get("/api/clients/{client_id}/stores")
def list_stores(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    items = [v for v in data_store.stores.values() if v.get("client_id") == client_id]
    items.sort(key=lambda s: s.get("name", ""))
    return items


@app.post("/api/clients/{client_id}/stores", status_code=201)
def create_store(client_id: str, body: StoreCreate):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    store_id = f"store-{uuid.uuid4().hex[:8]}"
    store = {
        "id": store_id,
        "client_id": client_id,
        "name": body.name,
        "address": body.address,
        "site_type": body.site_type,
        "nmi": body.nmi,
        "annual_kwh": body.annual_kwh,
        "annual_cost": None,
        "status": "active",
    }
    data_store.stores[store_id] = store
    data_store.save_to_disk()
    return store


@app.delete("/api/clients/{client_id}/stores/{store_id}")
def delete_store(client_id: str, store_id: str):
    store = data_store.stores.get(store_id)
    if store is None or store.get("client_id") != client_id:
        raise HTTPException(status_code=404, detail="Store not found")
    data_store.stores.pop(store_id)
    data_store.save_to_disk()
    return {"deleted": True}


def _get_store_load_curve(store: dict) -> tuple[List[float], float]:
    """Return (load_curve_48, annual_kwh) for a store using its synthetic profile scaled to annual_kwh."""
    profile = _get_synthetic_profile(store.get("site_type", "cafe"))
    annual_kwh = store.get("annual_kwh")
    if annual_kwh and annual_kwh > 0:
        raw_annual = sum(v * 0.5 for v in profile) * 365.0
        if raw_annual > 0:
            scale = annual_kwh / raw_annual
            profile = [round(v * scale, 4) for v in profile]
        return profile, float(annual_kwh)
    daily_kwh = sum(v * 0.5 for v in profile)
    return profile, daily_kwh * 365.0


@app.get("/api/clients/{client_id}/stores/{store_id}/baseline")
def get_store_baseline(client_id: str, store_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    store = data_store.stores.get(store_id)
    if store is None or store.get("client_id") != client_id:
        raise HTTPException(status_code=404, detail="Store not found")
    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_store_load_curve(store)
    result = compute_baseline(load_curve, tariff, annual_kwh)
    result["appliance_curves"] = _split_appliance_curves(load_curve, store.get("site_type", "cafe"))
    result["retailer_comparison"] = compute_retailer_comparison(load_curve, annual_kwh, tariff)
    store["annual_cost"] = result["cost_stack"]["total_annual"]
    data_store.stores[store_id] = store
    data_store.save_to_disk()
    return result


class AggregateBaselineRequest(BaseModel):
    store_ids: List[str]


@app.post("/api/clients/{client_id}/stores/aggregate-baseline")
def get_aggregate_baseline(client_id: str, body: AggregateBaselineRequest):
    """Sum load curves of selected stores and compute an aggregate baseline."""
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    if not body.store_ids:
        raise HTTPException(status_code=400, detail="store_ids must not be empty")

    load_curves: List[List[float]] = []
    total_annual_kwh = 0.0
    dominant_site_type = "cafe"

    for sid in body.store_ids:
        store = data_store.stores.get(sid)
        if store is None or store.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail=f"Store {sid} not found for this client")
        lc, akwh = _get_store_load_curve(store)
        load_curves.append(lc)
        total_annual_kwh += akwh
        dominant_site_type = store.get("site_type", dominant_site_type)

    agg_curve = [round(sum(lc[i] for lc in load_curves), 4) for i in range(48)]
    tariff = _resolve_tariff(client_id)
    result = compute_baseline(agg_curve, tariff, total_annual_kwh)
    result["appliance_curves"] = _split_appliance_curves(agg_curve, dominant_site_type)
    result["retailer_comparison"] = compute_retailer_comparison(agg_curve, total_annual_kwh, tariff)
    result["aggregate_store_ids"] = body.store_ids
    return result


# ── Interval data ─────────────────────────────────────────────────────────────

@app.post("/api/clients/{client_id}/upload")
async def upload_intervals(client_id: str, file: UploadFile = File(...)):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    content = await file.read()
    try:
        intervals = parse_interval_csv(content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {exc}")
    if not intervals:
        raise HTTPException(status_code=422, detail="No valid interval records found in CSV")
    stats = compute_interval_stats(intervals)
    data_store.interval_data[client_id] = intervals
    client["has_interval_data"] = True
    client["annual_kwh"] = stats["annual_kwh"]
    data_store.clients[client_id] = client
    data_store.save_to_disk()
    return {
        "success": True,
        "intervals_count": len(intervals),
        "date_range": stats["date_range"],
        "annual_kwh": stats["annual_kwh"],
        "peak_kw": stats["peak_kw"],
    }


@app.get("/api/clients/{client_id}/intervals/summary")
def intervals_summary(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    intervals = data_store.interval_data.get(client_id)
    if not intervals:
        raise HTTPException(status_code=404, detail="No interval data uploaded for this client")
    stats = compute_interval_stats(intervals)
    return {
        "date_range": stats["date_range"],
        "annual_kwh": stats["annual_kwh"],
        "peak_kw": stats["peak_kw"],
        "load_factor": stats["load_factor"],
        "typical_weekday": build_typical_weekday(intervals),
    }


# ── Tariffs ──────────────────────────────────────────────────────────────────

@app.get("/api/tariffs")
def list_tariffs():
    return list(data_store.tariffs.values())


@app.post("/api/tariffs", status_code=201)
def create_tariff(body: Tariff):
    if not body.id or body.id in data_store.tariffs:
        body = body.model_copy(update={"id": f"tariff-{uuid.uuid4().hex[:8]}"})
    data_store.tariffs[body.id] = body.model_dump()
    data_store.save_to_disk()
    return body.model_dump()


@app.put("/api/clients/{client_id}/tariff")
def assign_tariff(client_id: str, body: TariffAssign):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if body.tariff_id not in data_store.tariffs:
        raise HTTPException(status_code=404, detail="Tariff not found")
    data_store.client_tariffs[client_id] = body.tariff_id
    client["has_tariff"] = True
    client["tariff_id"] = body.tariff_id
    data_store.clients[client_id] = client
    data_store.save_to_disk()
    return {"success": True}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_client_load_curve(client_id: str, client: dict) -> tuple[List[float], float]:
    intervals = data_store.interval_data.get(client_id)
    if intervals:
        load_curve = build_typical_weekday(intervals)
        stats = compute_interval_stats(intervals)
        return load_curve, stats["annual_kwh"]
    load_curve = _get_synthetic_profile(client.get("site_type", "office"))
    daily_kwh = sum(v * 0.5 for v in load_curve)
    return load_curve, daily_kwh * 365.0


def _get_client_tariff(client_id: str) -> Optional[Tariff]:
    tariff_id = data_store.client_tariffs.get(client_id) or data_store.clients.get(client_id, {}).get("tariff_id")
    if tariff_id is None:
        return None
    tdata = data_store.tariffs.get(tariff_id)
    if tdata is None:
        return None
    return Tariff(**tdata)


def _resolve_tariff(client_id: str) -> Tariff:
    t = _get_client_tariff(client_id)
    if t is None:
        if data_store.tariffs:
            return Tariff(**next(iter(data_store.tariffs.values())))
        raise HTTPException(status_code=404, detail="No tariff configured for this client")
    return t


# ── Baseline ─────────────────────────────────────────────────────────────────

@app.get("/api/clients/{client_id}/baseline")
def get_baseline(client_id: str):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    result = compute_baseline(load_curve, tariff, annual_kwh)
    result["appliance_curves"] = _split_appliance_curves(load_curve, client.get("site_type", "office"))
    result["retailer_comparison"] = compute_retailer_comparison(load_curve, annual_kwh, tariff)
    client["annual_cost"] = result["cost_stack"]["total_annual"]
    if not client.get("annual_kwh"):
        client["annual_kwh"] = annual_kwh
    data_store.clients[client_id] = client
    data_store.save_to_disk()
    return result


class BaselineRecalcRequest(BaseModel):
    scales: Dict[str, float] = {}


@app.post("/api/clients/{client_id}/baseline/recalc")
def recalc_baseline(client_id: str, body: BaselineRecalcRequest):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    appliance_curves = _split_appliance_curves(load_curve, client.get("site_type", "office"))
    scales = body.scales or {}
    scaled_curves: Dict[str, List[float]] = {}
    for name, curve in appliance_curves.items():
        factor = float(scales.get(name, 1.0))
        scaled_curves[name] = [round(v * factor, 4) for v in curve]
    new_load = [0.0] * 48
    for curve in scaled_curves.values():
        for i, v in enumerate(curve):
            new_load[i] += v
    new_load = [round(v, 4) for v in new_load]
    base_sum = sum(load_curve)
    new_sum = sum(new_load)
    new_annual_kwh = annual_kwh * (new_sum / base_sum) if base_sum > 0 else annual_kwh
    result = compute_baseline(new_load, tariff, new_annual_kwh)
    result["appliance_curves"] = scaled_curves
    result["retailer_comparison"] = compute_retailer_comparison(new_load, new_annual_kwh, tariff)
    return result


# ── Scenarios ────────────────────────────────────────────────────────────────

class GenerateScenariosRequest(BaseModel):
    count: int = 3
    extra_instruction: Optional[str] = None
    aggregate_store_ids: Optional[List[str]] = None
    target_appliance: Optional[str] = None


def _run_generation_job(
    job_id: str,
    client_id: str,
    count: int,
    extra_instruction: Optional[str],
    aggregate_store_ids: Optional[List[str]] = None,
    target_appliance: Optional[str] = None,
) -> None:
    try:
        client = data_store.clients.get(client_id)
        if client is None:
            with JOBS_LOCK:
                JOBS[job_id] = {**JOBS.get(job_id, {}), "status": "error", "error": "Client deleted"}
            return

        tariff = _resolve_tariff(client_id)

        # Use aggregated store load curves if provided
        if aggregate_store_ids:
            load_curves = []
            total_kwh = 0.0
            dominant_type = client.get("site_type", "cafe")
            for sid in aggregate_store_ids:
                store = data_store.stores.get(sid)
                if store and store.get("client_id") == client_id:
                    lc, akwh = _get_store_load_curve(store)
                    load_curves.append(lc)
                    total_kwh += akwh
                    dominant_type = store.get("site_type", dominant_type)
            if load_curves:
                load_curve = [round(sum(lc[i] for lc in load_curves), 4) for i in range(48)]
                annual_kwh = total_kwh
            else:
                load_curve, annual_kwh = _get_client_load_curve(client_id, client)
                dominant_type = client.get("site_type", "cafe")
        else:
            load_curve, annual_kwh = _get_client_load_curve(client_id, client)
            dominant_type = client.get("site_type", "cafe")

        baseline = compute_baseline(load_curve, tariff, annual_kwh)
        appliance_curves = _split_appliance_curves(load_curve, dominant_type)
        baseline["load_curve"] = load_curve

        now = datetime.now(timezone.utc).isoformat()

        def _on_scenario_done(s: Dict[str, Any]) -> None:
            sid = f"scn-{uuid.uuid4().hex[:8]}"
            record = {
                "id": sid,
                "client_id": client_id,
                "created_at": now,
                "baseline_curve": [round(v, 4) for v in load_curve],
                "baseline_appliance_curves": appliance_curves,
                "aggregate_store_ids": aggregate_store_ids,
                "extra_instruction": extra_instruction,
                **s,
            }
            data_store.scenarios[sid] = record
            data_store.save_to_disk()
            with JOBS_LOCK:
                JOBS[job_id]["scenarios"].append(record)

        result = generate_scenarios(
            client=client,
            baseline=baseline,
            appliance_curves=appliance_curves,
            tariff=tariff,
            annual_kwh=annual_kwh,
            count=count,
            extra_instruction=extra_instruction,
            on_scenario_done=_on_scenario_done,
            forced_appliance=target_appliance,
        )

        if client_id not in data_store.clients:
            with JOBS_LOCK:
                JOBS[job_id] = {**JOBS.get(job_id, {}), "status": "error", "error": "Client deleted during generation"}
            return

        with JOBS_LOCK:
            JOBS[job_id] = {
                **JOBS.get(job_id, {}),
                "status": "done",
                "source": result.get("source", "claude"),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Scenario generation job %s failed", job_id)
        with JOBS_LOCK:
            JOBS[job_id] = {**JOBS.get(job_id, {}), "status": "error", "error": str(exc)[:300]}


@app.post("/api/clients/{client_id}/scenarios/generate", status_code=202)
def start_generate_job(client_id: str, body: GenerateScenariosRequest):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if not _has_api_key():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
    count = max(1, min(10, int(body.count or 3)))
    job_id = f"job-{uuid.uuid4().hex[:10]}"
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "client_id": client_id,
            "status": "running",
            "count": count,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "scenarios": [],
        }
    thread = threading.Thread(
        target=_run_generation_job,
        args=(job_id, client_id, count, body.extra_instruction, body.aggregate_store_ids, body.target_appliance),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id, "status": "running"}


@app.get("/api/scenarios/jobs/{job_id}")
def get_generation_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/clients/{client_id}/scenarios")
def list_client_scenarios(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    items = [v for v in data_store.scenarios.values() if v.get("client_id") == client_id]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return items


@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str):
    if scenario_id not in data_store.scenarios:
        raise HTTPException(status_code=404, detail="Scenario not found")
    data_store.scenarios.pop(scenario_id, None)
    data_store.save_to_disk()
    return {"deleted": True}


@app.delete("/api/clients/{client_id}/scenarios")
def clear_client_scenarios(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    ids = [k for k, v in data_store.scenarios.items() if v.get("client_id") == client_id]
    for sid in ids:
        data_store.scenarios.pop(sid, None)
    data_store.save_to_disk()
    return {"deleted": len(ids)}


# ── AI Analyse (SSE streaming) ────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    prompt: str
    history: List[Dict[str, Any]] = Field(default_factory=list)


@app.post("/api/clients/{client_id}/analyse")
async def analyse_client(client_id: str, body: AnalyseRequest):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if not _has_api_key():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    site_type = client.get("site_type", "cafe")
    appliance_curves = _split_appliance_curves(load_curve, site_type)
    shape = compute_shape_metrics(load_curve, annual_kwh)

    return StreamingResponse(
        _stream_analysis(
            client=client,
            appliance_curves=appliance_curves,
            baseline_curve=load_curve,
            tariff=tariff,
            annual_kwh=annual_kwh,
            shape=shape,
            prompt=body.prompt,
            history=body.history or [],
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatMsg(BaseModel):
    role: str
    content: str

class ClientChatRequest(BaseModel):
    messages: List[ChatMsg] = Field(default_factory=list)
    user_message: str

_CHAT_GEN_TOOL = {
    "name": "generate_scenario",
    "description": "Generate a load-shift energy saving scenario for this site. Call when the user asks for a plan, recommendation, or wants to see what savings are possible.",
    "input_schema": {
        "type": "object",
        "properties": {
            "instruction": {"type": "string", "description": "Brief focus, e.g. 'cheapest option', 'no upfront cost'"},
        },
    },
}

@app.post("/api/clients/{client_id}/chat")
def client_chat(client_id: str, body: ClientChatRequest):
    client = data_store.clients.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not _has_api_key():
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")

    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    baseline = compute_baseline(load_curve, tariff, annual_kwh)
    site_type = client.get("site_type", "cafe")
    appliance_curves = _split_appliance_curves(load_curve, site_type)

    total_kwh = sum(load_curve) * 0.5
    appliance_share = {
        name: (sum(curve) * 0.5) / total_kwh if total_kwh > 0 else 0.0
        for name, curve in appliance_curves.items()
    }
    top = sorted(appliance_share.items(), key=lambda kv: -kv[1])[:4]
    appliance_str = ", ".join(f"{k} {v*100:.0f}%" for k, v in top)
    rates = tariff.energy_rates

    system = (
        f"You are an energy advisor for {client.get('name')}, a {site_type}.\n\n"
        f"Site data:\n"
        f"- Annual usage: {annual_kwh:.0f} kWh, annual bill: ${baseline.get('annual_cost', 0):,.0f}\n"
        f"- Peak demand: {baseline.get('peak_kw', 0):.1f} kW\n"
        f"- Tariff: {tariff.retailer} {tariff.plan_name} — peak ${rates.peak:.3f}, off-peak ${rates.offpeak:.3f}/kWh\n"
        f"- Top energy users: {appliance_str}\n\n"
        f"Help the user understand their energy costs and how load shifting can unlock better contracts.\n"
        f"Load shifting = moving usage from peak hours (3–9pm) to off-peak (midnight–8am) to reduce peak charges and qualify for cheaper retailer plans.\n"
        f"When the user asks for a plan, scenario, or says 'do it' / 'show me', call generate_scenario.\n"
        f"Be concise — 2–3 sentences max. Be specific to this site."
    )

    sdk_messages = [
        {"role": m.role, "content": m.content}
        for m in body.messages
        if m.role in ("user", "assistant")
    ]
    sdk_messages.append({"role": "user", "content": body.user_message})

    ai = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    resp = ai.messages.create(
        model="claude-haiku-4-5-20251001",
        system=system,
        messages=sdk_messages,
        tools=[_CHAT_GEN_TOOL],
        max_tokens=512,
    )

    text_blocks = [b for b in resp.content if getattr(b, "type", None) == "text"]
    tu_blocks   = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
    reply = "\n".join(b.text for b in text_blocks if b.text).strip()

    generated_scenario = None
    if tu_blocks and tu_blocks[0].name == "generate_scenario":
        instruction = (tu_blocks[0].input or {}).get("instruction") or body.user_message
        try:
            baseline["load_curve"] = load_curve
            result = generate_single(
                client=client,
                baseline=baseline,
                appliance_curves=appliance_curves,
                tariff=tariff,
                annual_kwh=annual_kwh,
                extra_instruction=instruction,
            )
            if result and result.get("shifted_curve"):
                sid = f"scn-{uuid.uuid4().hex[:8]}"
                record = {
                    "id": sid,
                    "client_id": client_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "baseline_curve": [round(v, 4) for v in load_curve],
                    "baseline_appliance_curves": appliance_curves,
                    "from_chat": True,
                    **result,
                }
                data_store.scenarios[sid] = record
                data_store.save_to_disk()
                generated_scenario = record
                savings = result.get("savings_annual_low", 0)
                retailer = result.get("retailer_winner", "a cheaper retailer")
                reply = (
                    f"Here's a plan: {result.get('name', 'Load shift scenario')}. "
                    f"By shifting load off-peak you could save around ${savings:,.0f}/yr "
                    f"and qualify for better rates with {retailer}."
                )
        except Exception:
            logger.exception("Chat scenario generation failed for client %s", client_id)
            reply = "I tried to generate a plan but hit an error. Try the Generate button on the Scenarios tab."

    return {"reply": reply or "Got it.", "scenario": generated_scenario}


# ── Reports ──────────────────────────────────────────────────────────────────

class ReportCreate(BaseModel):
    title: Optional[str] = None
    scenario_ids: List[str]


@app.post("/api/clients/{client_id}/reports", status_code=201)
def create_report(client_id: str, body: ReportCreate):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    if not body.scenario_ids:
        raise HTTPException(status_code=400, detail="scenario_ids must contain at least one id")
    scenarios = []
    for sid in body.scenario_ids:
        scn = data_store.scenarios.get(sid)
        if scn is None or scn.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail=f"Scenario {sid} not found for this client")
        scenarios.append(scn)
    tariff = _resolve_tariff(client_id)
    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    baseline = compute_baseline(load_curve, tariff, annual_kwh)
    baseline["appliance_curves"] = _split_appliance_curves(load_curve, client.get("site_type", "office"))
    rid = f"rpt-{uuid.uuid4().hex[:8]}"
    title = body.title or f"{client.get('name')} — Energy Analysis"
    report = {
        "id": rid,
        "client_id": client_id,
        "title": title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "client": {
            "name": client.get("name"),
            "address": client.get("address"),
            "nmi": client.get("nmi"),
            "site_type": client.get("site_type"),
        },
        "tariff": tariff.model_dump(),
        "baseline": baseline,
        "scenarios": scenarios,
    }
    data_store.reports[rid] = report
    data_store.save_to_disk()
    return report


@app.get("/api/clients/{client_id}/reports")
def list_client_reports(client_id: str):
    if client_id not in data_store.clients:
        raise HTTPException(status_code=404, detail="Client not found")
    items = [v for v in data_store.reports.values() if v.get("client_id") == client_id]
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return items


@app.get("/api/reports/{report_id}")
def get_report(report_id: str):
    rep = data_store.reports.get(report_id)
    if rep is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return rep


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str):
    if report_id not in data_store.reports:
        raise HTTPException(status_code=404, detail="Report not found")
    data_store.reports.pop(report_id, None)
    data_store.save_to_disk()
    return {"deleted": True}


# ── Static frontend (production) ──────────────────────────────────────────────

import os as _os

_FRONTEND_BUILD = _os.path.abspath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "frontend", "build")
)

logger.info("Frontend build path: %s — exists: %s", _FRONTEND_BUILD, _os.path.isdir(_FRONTEND_BUILD))

if _os.path.isdir(_FRONTEND_BUILD):
    app.mount("/static", StaticFiles(directory=_os.path.join(_FRONTEND_BUILD, "static")), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        index = _os.path.join(_FRONTEND_BUILD, "index.html")
        return FileResponse(index)
else:
    @app.get("/")
    def no_frontend():
        return {"status": "api running", "frontend_build": _FRONTEND_BUILD, "found": False}
