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

from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

from baseline_engine import compute_baseline
from scenario_claude import generate_scenarios, generate_single, _has_api_key, compute_retailer_comparison

logger = logging.getLogger("broker_api")
logging.basicConfig(level=logging.INFO)


# ── Synthetic profiles by site_type (48 half-hourly kW values) ───────────────

SYNTHETIC_PROFILES: Dict[str, List[float]] = {
    "cafe": [
        0.8, 0.8, 0.6, 0.6, 0.6, 0.8,
        2.1, 3.2, 4.1, 4.8,
        5.2, 5.6, 5.8, 5.6, 5.0, 4.6,
        4.2, 4.4, 4.6, 4.8,
        5.1, 5.4, 5.6, 5.4,
        4.9, 4.2, 3.6,
        2.8, 2.1, 1.5, 1.2,
        1.0, 0.9, 0.8, 0.8, 0.7, 0.7,
        0.7, 0.7, 0.8, 0.8, 0.8, 0.8,
        0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
    ],
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
    "cafe": {"Fridges": 0.22, "Espresso": 0.12, "Ovens": 0.18, "HVAC": 0.20, "Lighting": 0.08, "Dishwasher": 0.08, "Hot Water": 0.07, "Misc": 0.05},
    "office": {"Fridges": 0.06, "Espresso": 0.04, "Ovens": 0.02, "HVAC": 0.45, "Lighting": 0.20, "Dishwasher": 0.02, "Hot Water": 0.05, "Misc": 0.16},
    "retail": {"Fridges": 0.20, "Espresso": 0.03, "Ovens": 0.05, "HVAC": 0.30, "Lighting": 0.25, "Dishwasher": 0.02, "Hot Water": 0.03, "Misc": 0.12},
    "industrial": {"Fridges": 0.05, "Espresso": 0.01, "Ovens": 0.05, "HVAC": 0.15, "Lighting": 0.10, "Dishwasher": 0.02, "Hot Water": 0.05, "Misc": 0.57},
    "hospitality": {"Fridges": 0.18, "Espresso": 0.06, "Ovens": 0.22, "HVAC": 0.22, "Lighting": 0.10, "Dishwasher": 0.09, "Hot Water": 0.08, "Misc": 0.05},
}


def _split_appliance_curves(load_curve: List[float], site_type: str) -> Dict[str, List[float]]:
    weights = APPLIANCE_WEIGHTS.get(site_type.lower(), APPLIANCE_WEIGHTS["cafe"])
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


def _run_generation_job(
    job_id: str,
    client_id: str,
    count: int,
    extra_instruction: Optional[str],
    aggregate_store_ids: Optional[List[str]] = None,
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
        args=(job_id, client_id, count, body.extra_instruction, body.aggregate_store_ids),
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

_FRONTEND_BUILD = _os.path.join(_os.path.dirname(__file__), "..", "frontend", "build")

if _os.path.isdir(_FRONTEND_BUILD):
    app.mount("/static", StaticFiles(directory=_os.path.join(_FRONTEND_BUILD, "static")), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        index = _os.path.join(_FRONTEND_BUILD, "index.html")
        return FileResponse(index)
