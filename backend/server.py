"""
Load Shape Lab — FastAPI backend.

Endpoints:
  GET  /api/                       — health
  GET  /api/meters                 — list pre-loaded sample meters
  GET  /api/meters/{id}            — meter detail + baseline 48-bucket curve
  GET  /api/plans                  — list retailer plans
  GET  /api/zones                  — TOU zone metadata
  GET  /api/spot                   — NEM spot price overlay (48 buckets, $/MWh)
  POST /api/rank                   — given a shape + meter, rank plans by annual cost
  POST /api/refresh-cdr            — best-effort merge of AER CDR public dataset
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from seed_data import (
    ARCHETYPE_CURVES,
    NEM_SPOT_AVG_VIC,
    SAMPLE_METERS,
    SAMPLE_PLANS,
    SHIFT_ASSETS,
    TOU_ZONES,
)
from cost_engine import annual_cost, shape_stats

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("loadshapelab")
logging.basicConfig(level=logging.INFO)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="Load Shape Lab API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────
class RankRequest(BaseModel):
    meter_id: str = Field(..., description="Sample meter id (e.g. MTR-001)")
    shape: List[float] = Field(..., min_length=48, max_length=48)


class RankedPlan(BaseModel):
    plan: dict
    baseline_cost: float
    shifted_cost: float
    annual_delta: float
    pct_delta: float


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _baseline_shape(archetype: str, target_annual_kwh: Optional[float] = None) -> List[float]:
    curve = ARCHETYPE_CURVES.get(archetype) or ARCHETYPE_CURVES["office"]
    curve = list(curve)
    if target_annual_kwh:
        daily_kwh = sum(c * 0.5 for c in curve)
        target_daily = target_annual_kwh / 365.0
        if daily_kwh > 0:
            k = target_daily / daily_kwh
            curve = [round(c * k, 3) for c in curve]
    return curve


def _meter(meter_id: str) -> dict:
    m = next((m for m in SAMPLE_METERS if m["id"] == meter_id), None)
    if not m:
        raise HTTPException(404, f"Meter {meter_id} not found")
    return m


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/api/")
async def root():
    return {"app": "Load Shape Lab", "status": "ok"}


@app.get("/api/meters")
async def list_meters():
    return [
        {
            "id": m["id"],
            "nmi": m["nmi"],
            "nickname": m["nickname"],
            "archetype": m["archetype"],
            "zone_code": m["zone_code"],
            "zone_name": m["zone_name"],
            "state": m["state"],
            "annual_kwh": m["annual_kwh"],
            "current_plan_label": m["current_plan_label"],
            "monthly_spend": m["monthly_spend"],
        }
        for m in SAMPLE_METERS
    ]


@app.get("/api/meters/{meter_id}")
async def get_meter(meter_id: str):
    m = _meter(meter_id)
    baseline = _baseline_shape(m["archetype"], m["annual_kwh"])
    assets = SHIFT_ASSETS.get(m["archetype"], [])
    return {
        **m,
        "baseline_shape": baseline,
        "shift_assets": assets,
    }


@app.get("/api/plans")
async def list_plans(state: Optional[str] = None):
    if state:
        return [p for p in SAMPLE_PLANS if p["state"] == state or p["state"] == "*"]
    return SAMPLE_PLANS


@app.get("/api/zones")
async def list_zones():
    return [
        {
            "code": z["code"],
            "name": name,
            "state": z["state"],
            "peak_buckets": z["peak"],
            "shoulder_buckets": z["shoulder"],
        }
        for name, z in TOU_ZONES.items()
    ]


@app.get("/api/spot")
async def spot_prices():
    # Stored as $/MWh; expose as $/kWh too for charting convenience
    return {
        "region": "VIC1",
        "source": "OpenNEM-style average (existing repo data)",
        "buckets": 48,
        "rrp_mwh": NEM_SPOT_AVG_VIC,
        "rrp_kwh": [round(v / 1000.0, 4) for v in NEM_SPOT_AVG_VIC],
    }


@app.post("/api/rank")
async def rank_plans(req: RankRequest):
    m = _meter(req.meter_id)
    baseline = _baseline_shape(m["archetype"], m["annual_kwh"])

    # Scale incoming shape to preserve total annual energy (so cost diffs reflect
    # SHAPE optimisation, not magnitude changes from dragging blocks around)
    # Actually we do NOT scale — let the user see the real impact of moving load.
    shape = list(req.shape)

    ranked = []
    for plan in SAMPLE_PLANS:
        zone = m["zone_code"]
        base_breakdown = annual_cost(baseline, plan, zone)
        shift_breakdown = annual_cost(shape, plan, zone)
        ranked.append({
            "plan": plan,
            "baseline_cost": base_breakdown["annual_total"],
            "shifted_cost": shift_breakdown["annual_total"],
            "annual_delta": round(shift_breakdown["annual_total"] - base_breakdown["annual_total"], 2),
            "pct_delta": round(
                (shift_breakdown["annual_total"] - base_breakdown["annual_total"])
                / max(base_breakdown["annual_total"], 1e-9) * 100.0, 2
            ),
            "breakdown": shift_breakdown,
        })

    ranked.sort(key=lambda r: r["shifted_cost"])

    stats_baseline = shape_stats(baseline, m["zone_code"])
    stats_shifted = shape_stats(shape, m["zone_code"])

    current = next((r for r in ranked if r["plan"]["id"] == m["current_plan_id"]), ranked[0])
    best = ranked[0]
    achievable_saving = round(current["shifted_cost"] - best["shifted_cost"], 2)

    return {
        "meter_id": req.meter_id,
        "ranked": ranked,
        "current_plan_id": m["current_plan_id"],
        "current": current,
        "best": best,
        "achievable_saving": achievable_saving,
        "stats": {
            "baseline": stats_baseline,
            "shifted": stats_shifted,
        },
    }


@app.post("/api/refresh-cdr")
async def refresh_cdr():
    """
    Best-effort fetch from the AER CDR public Energy Product Reference Data API.
    Records counts only; does not mutate the in-process seed plans for stability.
    """
    retailers = ["agl", "originenergy", "energyaustralia", "redenergy", "alintaenergy"]
    base = "https://cdr.energymadeeasy.gov.au"
    headers = {"x-v": "3", "Accept": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as cli:
        for r in retailers:
            try:
                resp = await cli.get(f"{base}/{r}/cds-au/v1/energy/plans?page-size=10")
                if resp.status_code == 200:
                    data = resp.json()
                    plans = data.get("data", {}).get("plans", [])
                    results[r] = {"status": "ok", "count": len(plans), "first": plans[:2]}
                else:
                    results[r] = {"status": "http_error", "code": resp.status_code}
            except Exception as exc:  # noqa: BLE001
                results[r] = {"status": "exception", "detail": str(exc)}
    return {"queried": retailers, "results": results, "note": "Live AER CDR. Plans are not auto-merged in MVP."}
