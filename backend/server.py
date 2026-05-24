"""
Energy Broker API — FastAPI backend.

Endpoints:
  GET  /api/health
  POST /api/auth/login
  GET  /api/auth/me

  GET  /api/clients
  POST /api/clients
  GET  /api/clients/{id}
  POST /api/clients/{id}/upload
  GET  /api/clients/{id}/intervals/summary
  PUT  /api/clients/{id}/tariff

  GET  /api/tariffs
  POST /api/tariffs

  GET  /api/clients/{id}/baseline
  GET  /api/scenarios/library
  POST /api/clients/{id}/scenarios/run
  GET  /api/clients/{id}/report
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv

# Load .env (e.g., ANTHROPIC_API_KEY) before importing modules that read env vars
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import data_store
from models import (
    Client,
    ClientCreate,
    IntervalRecord,
    UploadResponse,
    IntervalSummary,
    Tariff,
    TariffAssign,
    BaselineResponse,
    ScenarioRunRequest,
    ScenarioResult,
    ReportResponse,
)
from interval_parser import (
    parse_interval_csv,
    build_typical_weekday,
    compute_interval_stats,
)
from baseline_engine import compute_baseline
from scenario_engine import SCENARIO_LIBRARY, run_scenarios
from scenario_claude import generate_scenarios, fallback_scenarios, _has_api_key

logger = logging.getLogger("broker_api")
logging.basicConfig(level=logging.INFO)

# ── Synthetic profiles by site_type (48 half-hourly kW values) ───────────────

SYNTHETIC_PROFILES: Dict[str, List[float]] = {
    "cafe": [
        # midnight → 6am: very low
        0.8, 0.8, 0.6, 0.6, 0.6, 0.8,
        # 6am → 9am: morning rush ramp-up
        2.1, 3.2, 4.1, 4.8,
        # 9am → 2pm: busy daytime
        5.2, 5.6, 5.8, 5.6, 5.0, 4.6,
        # 2pm → 5pm: afternoon shoulder
        4.2, 4.4, 4.6, 4.8,
        # 5pm → 8pm: evening peak
        5.1, 5.4, 5.6, 5.4,
        # 8pm → 10pm: wind down
        4.9, 4.2, 3.6,
        # 10pm → midnight: closing
        2.8, 2.1, 1.5, 1.2,
        # pad to 48 buckets
        1.0, 0.9, 0.8, 0.8, 0.7, 0.7,
        0.7, 0.7, 0.8, 0.8, 0.8, 0.8,
        0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
    ],
    "office": [
        # midnight → 7am: base load only
        1.2, 1.1, 1.0, 0.9, 0.9, 1.0, 1.2,
        # 7am → 9am: startup
        2.5, 3.8,
        # 9am → 12pm: busy morning
        5.2, 6.1, 6.8, 7.2,
        # 12pm → 1pm: lunch dip
        6.5, 6.0,
        # 1pm → 5pm: afternoon peak
        6.8, 7.5, 8.1, 8.4, 8.2, 7.9,
        # 5pm → 7pm: wind down
        6.5, 5.2,
        # 7pm → 9pm: after-hours
        3.1, 2.4,
        # 9pm → midnight: base
        1.8, 1.6, 1.5, 1.4,
        # fill remaining
        1.3, 1.2, 1.2, 1.2, 1.1, 1.1,
        1.1, 1.1, 1.2, 1.2, 1.2, 1.2,
        1.2, 1.2, 1.2, 1.2, 1.2, 1.2,
    ],
    "retail": [
        # midnight → 8am: very low security/HVAC only
        0.5, 0.4, 0.4, 0.4, 0.4, 0.5, 0.6, 0.8,
        # 8am → 9am: store opening
        2.4, 3.2,
        # 9am → 5pm: full trading
        4.5, 5.2, 6.1, 6.8, 7.2, 7.5, 7.8, 7.9, 7.5, 7.1,
        # 5pm → 7pm: extended trading
        7.8, 8.2, 8.5, 8.1,
        # 7pm → 9pm: closing
        6.5, 4.8, 3.2,
        # 9pm → midnight: security
        2.1, 1.5, 1.0, 0.8, 0.7,
        # fill remaining
        0.6, 0.5, 0.5, 0.5, 0.5, 0.5,
        0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
    ],
    "industrial": [
        # midnight → 6am: night shift reduced
        8.5, 7.2, 6.8, 6.5, 6.8, 7.2,
        # 6am → 8am: shift change + ramp up
        9.5, 12.4,
        # 8am → 5pm: full production
        15.8, 18.2, 19.5, 20.1, 20.4, 19.8,
        20.2, 20.6, 21.0, 21.3, 21.0, 20.5,
        20.8, 21.2, 21.5,
        # 5pm → 6pm: handover
        18.5, 16.2,
        # 6pm → 10pm: reduced production
        13.5, 12.1, 11.4, 10.8, 10.5,
        # 10pm → midnight: night prep
        9.2, 8.8,
        # fill remaining
        8.6, 8.5, 8.5, 8.5, 8.5, 8.5,
        8.5, 8.5, 8.5, 8.5, 8.5, 8.5,
        8.5, 8.5, 8.5, 8.5, 8.5, 8.5,
    ],
    "hospitality": [
        # midnight → 5am: overnight base
        3.2, 2.8, 2.5, 2.4, 2.4, 2.6,
        # 5am → 8am: breakfast prep
        4.5, 6.8, 8.2,
        # 8am → 12pm: full service
        9.5, 10.8, 11.2, 11.5,
        # 12pm → 2pm: lunch service peak
        12.1, 12.8,
        # 2pm → 5pm: afternoon
        11.5, 10.8, 10.2,
        # 5pm → 10pm: dinner service peak
        11.8, 13.2, 14.5, 15.2, 15.8, 15.5, 14.8, 13.5,
        # 10pm → midnight: closing
        10.2, 7.5, 5.8, 4.5,
        # fill remaining
        3.8, 3.5, 3.3, 3.2, 3.2, 3.2,
        3.2, 3.2, 3.2, 3.2, 3.2, 3.2,
        3.2, 3.2, 3.2, 3.2, 3.2, 3.2,
    ],
}

# Ensure all profiles are exactly 48 buckets
for _st, _prof in SYNTHETIC_PROFILES.items():
    if len(_prof) < 48:
        _prof.extend([_prof[-1]] * (48 - len(_prof)))
    SYNTHETIC_PROFILES[_st] = _prof[:48]


def _get_synthetic_profile(site_type: str) -> List[float]:
    """Return 48-bucket kW profile for a site_type."""
    profile = SYNTHETIC_PROFILES.get(site_type.lower(), SYNTHETIC_PROFILES["office"])
    return list(profile)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Energy Broker API", version="1.0.0")

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
        logger.info("No clients found — seeding demo client")
        data_store.seed_demo_data()
    logger.info("Data store loaded on startup")
    # Pre-warm Claude scenarios for the demo client in a background thread
    # so the first user gets cached results without waiting 30s+.
    _prewarm_demo_scenarios()


def _prewarm_demo_scenarios() -> None:
    """If the demo client exists and has no cached Claude scenarios yet,
    kick off generation in a background thread."""
    import threading

    demo_id = "client-demo-001"
    cached_key = f"claude_default_{demo_id}"
    if demo_id not in data_store.clients or cached_key in data_store.client_scenarios:
        return
    if not _has_api_key():
        return

    def _bg() -> None:
        try:
            logger.info("Pre-warming Claude scenarios for %s", demo_id)
            client = data_store.clients[demo_id]
            tariff = _get_client_tariff(demo_id)
            if tariff is None and data_store.tariffs:
                tariff = Tariff(**next(iter(data_store.tariffs.values())))
            if tariff is None:
                return
            load_curve, annual_kwh = _get_client_load_curve(demo_id, client)
            baseline = compute_baseline(load_curve, tariff, annual_kwh)
            result = generate_scenarios(
                client=client,
                baseline=baseline,
                tariff=tariff,
                annual_kwh=annual_kwh,
                extra_instruction=None,
            )
            data_store.client_scenarios[cached_key] = {
                "scenarios": result.get("scenarios", []),
                "source": result.get("source", "claude"),
            }
            data_store.save_to_disk()
            logger.info("Pre-warmed %d Claude scenarios for %s", len(result.get("scenarios", [])), demo_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Demo scenario pre-warm failed: %s", exc)

    t = threading.Thread(target=_bg, daemon=True)
    t.start()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ── Clients ───────────────────────────────────────────────────────────────────

@app.get("/api/clients")
def list_clients():
    return list(data_store.clients.values())


@app.post("/api/clients", status_code=201)
def create_client(body: ClientCreate):
    client_id = f"client-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    client = {
        "id": client_id,
        "broker_id": "broker-1",
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


# ── Interval data ─────────────────────────────────────────────────────────────

@app.post("/api/clients/{client_id}/upload")
async def upload_intervals(
    client_id: str,
    file: UploadFile = File(...),
):
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
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    intervals = data_store.interval_data.get(client_id)
    if not intervals:
        raise HTTPException(status_code=404, detail="No interval data uploaded for this client")

    stats = compute_interval_stats(intervals)
    typical_weekday = build_typical_weekday(intervals)

    return {
        "date_range": stats["date_range"],
        "annual_kwh": stats["annual_kwh"],
        "peak_kw": stats["peak_kw"],
        "load_factor": stats["load_factor"],
        "typical_weekday": typical_weekday,
    }


# ── Tariff assignment ─────────────────────────────────────────────────────────

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


# ── Tariffs ───────────────────────────────────────────────────────────────────

@app.get("/api/tariffs")
def list_tariffs():
    return list(data_store.tariffs.values())


@app.post("/api/tariffs", status_code=201)
def create_tariff(body: Tariff):
    # Generate ID if not provided or if it conflicts
    if not body.id or body.id in data_store.tariffs:
        body = body.model_copy(update={"id": f"tariff-{uuid.uuid4().hex[:8]}"})
    data_store.tariffs[body.id] = body.model_dump()
    data_store.save_to_disk()
    return body.model_dump()


# ── Appliance split (for stacked-area chart) ──────────────────────────────────

# Site-type → appliance fraction weights (must sum to 1.0)
APPLIANCE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "cafe": {
        "Fridges": 0.22,
        "Espresso": 0.12,
        "Ovens": 0.18,
        "HVAC": 0.20,
        "Lighting": 0.08,
        "Dishwasher": 0.08,
        "Hot Water": 0.07,
        "Misc": 0.05,
    },
    "office": {
        "Fridges": 0.06,
        "Espresso": 0.04,
        "Ovens": 0.02,
        "HVAC": 0.45,
        "Lighting": 0.20,
        "Dishwasher": 0.02,
        "Hot Water": 0.05,
        "Misc": 0.16,
    },
    "retail": {
        "Fridges": 0.20,
        "Espresso": 0.03,
        "Ovens": 0.05,
        "HVAC": 0.30,
        "Lighting": 0.25,
        "Dishwasher": 0.02,
        "Hot Water": 0.03,
        "Misc": 0.12,
    },
    "industrial": {
        "Fridges": 0.05,
        "Espresso": 0.01,
        "Ovens": 0.05,
        "HVAC": 0.15,
        "Lighting": 0.10,
        "Dishwasher": 0.02,
        "Hot Water": 0.05,
        "Misc": 0.57,
    },
    "hospitality": {
        "Fridges": 0.18,
        "Espresso": 0.06,
        "Ovens": 0.22,
        "HVAC": 0.22,
        "Lighting": 0.10,
        "Dishwasher": 0.09,
        "Hot Water": 0.08,
        "Misc": 0.05,
    },
}


def _split_appliance_curves(load_curve: List[float], site_type: str) -> Dict[str, List[float]]:
    """Split a 48-bucket load curve into per-appliance contributions."""
    weights = APPLIANCE_WEIGHTS.get(site_type.lower(), APPLIANCE_WEIGHTS["cafe"])
    out: Dict[str, List[float]] = {}
    for name, w in weights.items():
        out[name] = [round(load_curve[b] * w, 4) for b in range(len(load_curve))]
    return out


# ── Baseline ──────────────────────────────────────────────────────────────────

def _get_client_load_curve(client_id: str, client: dict) -> tuple[List[float], float]:
    """
    Return (load_curve_kw, annual_kwh) for a client.
    Uses real interval data if available, else synthetic profile.
    """
    intervals = data_store.interval_data.get(client_id)
    if intervals:
        load_curve = build_typical_weekday(intervals)
        stats = compute_interval_stats(intervals)
        annual_kwh = stats["annual_kwh"]
    else:
        # Synthetic profile
        load_curve = _get_synthetic_profile(client.get("site_type", "office"))
        # Estimate annual consumption from synthetic profile
        daily_kwh = sum(v * 0.5 for v in load_curve)
        annual_kwh = daily_kwh * 365.0

    return load_curve, annual_kwh


def _get_client_tariff(client_id: str) -> Optional[Tariff]:
    """Return Tariff object for a client, or None."""
    tariff_id = data_store.client_tariffs.get(client_id)
    if tariff_id is None:
        tariff_id = data_store.clients.get(client_id, {}).get("tariff_id")
    if tariff_id is None:
        return None
    tariff_data = data_store.tariffs.get(tariff_id)
    if tariff_data is None:
        return None
    return Tariff(**tariff_data)


@app.get("/api/clients/{client_id}/baseline")
def get_baseline(client_id: str):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    tariff = _get_client_tariff(client_id)
    if tariff is None:
        # Use first available tariff as default for demo purposes
        if data_store.tariffs:
            first_tariff_data = next(iter(data_store.tariffs.values()))
            tariff = Tariff(**first_tariff_data)
        else:
            raise HTTPException(status_code=404, detail="No tariff assigned to this client")

    load_curve, annual_kwh = _get_client_load_curve(client_id, client)

    result = compute_baseline(load_curve, tariff, annual_kwh)

    # Appliance-split curves (frontend stacked-area chart)
    result["appliance_curves"] = _split_appliance_curves(load_curve, client.get("site_type", "office"))

    # Update client annual_cost
    client["annual_cost"] = result["cost_stack"]["total_annual"]
    if not client.get("annual_kwh"):
        client["annual_kwh"] = annual_kwh
    data_store.clients[client_id] = client
    data_store.save_to_disk()

    return result


# ── Scenarios ─────────────────────────────────────────────────────────────────

@app.get("/api/scenarios/library")
def get_scenario_library():
    return SCENARIO_LIBRARY


@app.post("/api/clients/{client_id}/scenarios/run")
def run_client_scenarios(client_id: str, body: ScenarioRunRequest):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    tariff = _get_client_tariff(client_id)
    if tariff is None:
        if data_store.tariffs:
            first_tariff_data = next(iter(data_store.tariffs.values()))
            tariff = Tariff(**first_tariff_data)
        else:
            raise HTTPException(status_code=404, detail="No tariff assigned to this client")

    load_curve, annual_kwh = _get_client_load_curve(client_id, client)

    scenarios_config = [
        {"type": s.type, "parameters": s.parameters}
        for s in body.scenarios
    ]

    result = run_scenarios(load_curve, scenarios_config, tariff, annual_kwh)

    # Store the result
    if client_id not in data_store.client_scenarios:
        data_store.client_scenarios[client_id] = []
    data_store.client_scenarios[client_id].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **result,
    })
    data_store.save_to_disk()

    return result


# ── Claude-generated dynamic scenarios ────────────────────────────────────────

class GenerateScenariosRequest(BaseModel):
    extra_instruction: Optional[str] = None


@app.post("/api/clients/{client_id}/scenarios/generate")
def generate_client_scenarios(client_id: str, body: GenerateScenariosRequest, response: Response):
    """
    Claude generates a ranked list of bespoke load-shift scenarios for this
    client. Falls back to the legacy 4-scenario engine if ANTHROPIC_API_KEY
    is missing.
    """
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    tariff = _get_client_tariff(client_id)
    if tariff is None:
        if data_store.tariffs:
            first_tariff_data = next(iter(data_store.tariffs.values()))
            tariff = Tariff(**first_tariff_data)
        else:
            raise HTTPException(status_code=404, detail="No tariff assigned to this client")

    load_curve, annual_kwh = _get_client_load_curve(client_id, client)
    baseline = compute_baseline(load_curve, tariff, annual_kwh)

    # For the demo client without an extra_instruction, serve cached scenarios
    # if available so the page is instant on repeat visits.
    cached_key = f"claude_default_{client_id}"
    if not body.extra_instruction:
        cached = data_store.client_scenarios.get(cached_key)
        if cached:
            response.headers["X-Scenario-Source"] = "claude-cached"
            result = dict(cached)
            result["baseline_curve"] = [round(v, 4) for v in load_curve]
            return result

    if not _has_api_key():
        response.headers["X-Scenario-Source"] = "fallback"
        logger.warning("ANTHROPIC_API_KEY missing — using fallback scenarios")
        result = fallback_scenarios(load_curve, tariff, annual_kwh)
        result["baseline_curve"] = [round(v, 4) for v in load_curve]
        return result

    try:
        result = generate_scenarios(
            client=client,
            baseline=baseline,
            tariff=tariff,
            annual_kwh=annual_kwh,
            extra_instruction=body.extra_instruction,
        )
        response.headers["X-Scenario-Source"] = result.get("source", "claude")
        result["baseline_curve"] = [round(v, 4) for v in load_curve]
        # Cache only successful Claude responses for the no-instruction default
        src = result.get("source", "")
        if not body.extra_instruction and src.startswith("claude") and result.get("scenarios"):
            data_store.client_scenarios[cached_key] = {
                "scenarios": result.get("scenarios", []),
                "source": src,
            }
            data_store.save_to_disk()
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Claude scenario generation failed — falling back: %s", exc)
        response.headers["X-Scenario-Source"] = "fallback"
        response.headers["X-Scenario-Error"] = str(exc)[:200]
        result = fallback_scenarios(load_curve, tariff, annual_kwh)
        result["baseline_curve"] = [round(v, 4) for v in load_curve]
        return result


# ── Report ────────────────────────────────────────────────────────────────────

@app.get("/api/clients/{client_id}/report")
def get_report(client_id: str):
    client = data_store.clients.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")

    tariff = _get_client_tariff(client_id)
    if tariff is None and data_store.tariffs:
        first_tariff_data = next(iter(data_store.tariffs.values()))
        tariff = Tariff(**first_tariff_data)

    baseline_data = None
    if tariff:
        load_curve, annual_kwh = _get_client_load_curve(client_id, client)
        baseline_data = compute_baseline(load_curve, tariff, annual_kwh)

    scenarios_list = data_store.client_scenarios.get(client_id, [])
    latest_scenario = scenarios_list[-1] if scenarios_list else None

    return {
        "client": {
            "name": client.get("name"),
            "address": client.get("address"),
            "nmi": client.get("nmi"),
        },
        "baseline": baseline_data,
        "scenarios": scenarios_list,
        "savings": latest_scenario.get("savings") if latest_scenario else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
