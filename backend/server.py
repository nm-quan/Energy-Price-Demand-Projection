"""
Load Shape Lab — FastAPI backend.

Endpoints:
  GET  /api/                       — health
  GET  /api/meters                 — list pre-loaded sample meters
  GET  /api/meters/{id}            — meter detail (baseline shape, appliances, shift_assets)
  GET  /api/plans                  — list retailer plans
  GET  /api/zones                  — TOU zone metadata
  GET  /api/spot                   — NEM spot price overlay (48 buckets, $/MWh)
  POST /api/rank                   — given meter_ids + asset_positions + active_assets,
                                     return aggregated curves, per-meter shapes, and ranked plans.
  POST /api/refresh-cdr            — best-effort fetch from AER CDR
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

from seed_data import (
    ARCHETYPE_APPLIANCES,
    NEM_SPOT_AVG_VIC,
    SAMPLE_METERS,
    SAMPLE_PLANS,
    TOU_ZONES,
    meter_appliances,
    meter_baseline_shape,
    meter_shift_assets,
    shifted_shape,
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

app = FastAPI(title="Load Shape Lab API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────
class RankRequest(BaseModel):
    meter_ids: List[str] = Field(..., min_length=1)
    asset_positions: Dict[str, int] = Field(default_factory=dict)
    active_assets: List[str] = Field(default_factory=list)


def _meter(meter_id: str) -> dict:
    m = next((m for m in SAMPLE_METERS if m["id"] == meter_id), None)
    if not m:
        raise HTTPException(404, f"Meter {meter_id} not found")
    return m


def _sum_shapes(shapes: List[List[float]]) -> List[float]:
    if not shapes:
        return [0.0] * 48
    out = [0.0] * 48
    for s in shapes:
        for i, v in enumerate(s):
            out[i] += v
    return [round(v, 4) for v in out]


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.get("/api/")
async def root():
    return {"app": "Load Shape Lab", "status": "ok"}


@app.get("/api/meters")
async def list_meters():
    return [
        {
            "id": m["id"], "nmi": m["nmi"], "nickname": m["nickname"],
            "archetype": m["archetype"], "zone_code": m["zone_code"],
            "zone_name": m["zone_name"], "state": m["state"],
            "annual_kwh": m["annual_kwh"],
            "current_plan_label": m["current_plan_label"],
            "monthly_spend": m["monthly_spend"],
        }
        for m in SAMPLE_METERS
    ]


@app.get("/api/meters/{meter_id}")
async def get_meter(meter_id: str):
    m = _meter(meter_id)
    return {
        **m,
        "baseline_shape": meter_baseline_shape(m),
        "appliances": meter_appliances(m),
        "shift_assets": meter_shift_assets(m),
    }


@app.get("/api/plans")
async def list_plans(state: Optional[str] = None):
    if state:
        return [p for p in SAMPLE_PLANS if p["state"] == state]
    return SAMPLE_PLANS


@app.get("/api/zones")
async def list_zones():
    return [
        {
            "code": z["code"], "name": name, "state": z["state"],
            "peak_buckets": z["peak"], "shoulder_buckets": z["shoulder"],
        }
        for name, z in TOU_ZONES.items()
    ]


@app.get("/api/spot")
async def spot_prices():
    return {
        "region": "VIC1",
        "source": "OpenNEM-style average (existing repo data)",
        "buckets": 48,
        "rrp_mwh": NEM_SPOT_AVG_VIC,
        "rrp_kwh": [round(v / 1000.0, 4) for v in NEM_SPOT_AVG_VIC],
    }


@app.post("/api/rank")
async def rank_plans(req: RankRequest):
    meters = [_meter(mid) for mid in req.meter_ids]

    # Per-meter shapes
    per_meter = []
    for m in meters:
        baseline = meter_baseline_shape(m)
        shifted = shifted_shape(m, req.asset_positions, req.active_assets)
        per_meter.append({
            "meter_id": m["id"],
            "zone_code": m["zone_code"],
            "baseline_shape": baseline,
            "shifted_shape": shifted,
        })

    agg_baseline = _sum_shapes([pm["baseline_shape"] for pm in per_meter])
    agg_shifted = _sum_shapes([pm["shifted_shape"] for pm in per_meter])

    # Rank plans by SUM of per-meter cost
    ranked = []
    for plan in SAMPLE_PLANS:
        sum_base = 0.0
        sum_shift = 0.0
        for pm, m in zip(per_meter, meters):
            base_b = annual_cost(pm["baseline_shape"], plan, m["zone_code"])
            shift_b = annual_cost(pm["shifted_shape"], plan, m["zone_code"])
            sum_base += base_b["annual_total"]
            sum_shift += shift_b["annual_total"]
        ranked.append({
            "plan": plan,
            "baseline_cost": round(sum_base, 2),
            "shifted_cost": round(sum_shift, 2),
            "annual_delta": round(sum_shift - sum_base, 2),
            "pct_delta": round(
                (sum_shift - sum_base) / max(sum_base, 1e-9) * 100.0, 2
            ),
        })
    ranked.sort(key=lambda r: r["shifted_cost"])

    # Pick a representative "current" — first meter's current plan (most natural
    # in single-select; for multi we report the same plan id and use sum cost)
    current_plan_id = meters[0]["current_plan_id"]
    current = next((r for r in ranked if r["plan"]["id"] == current_plan_id), ranked[0])
    best = ranked[0]
    achievable_saving = round(current["shifted_cost"] - best["shifted_cost"], 2)

    # Aggregated stats — use the most common zone for TOU-band classification of the agg curve
    agg_zone = max(
        {m["zone_code"] for m in meters},
        key=lambda z: sum(1 for m in meters if m["zone_code"] == z),
    )

    return {
        "meter_ids": req.meter_ids,
        "n_sites": len(meters),
        "ranked": ranked,
        "current_plan_id": current_plan_id,
        "current": current,
        "best": best,
        "achievable_saving": achievable_saving,
        "shape": {
            "baseline": agg_baseline,
            "shifted": agg_shifted,
        },
        "stats": {
            "baseline": shape_stats(agg_baseline, agg_zone),
            "shifted": shape_stats(agg_shifted, agg_zone),
        },
        "per_meter": per_meter,
        "agg_zone": agg_zone,
    }


@app.post("/api/refresh-cdr")
async def refresh_cdr():
    """Best-effort live fetch from AER CDR — reports status only."""
    retailers = ["agl", "originenergy", "energyaustralia", "redenergy", "alintaenergy"]
    base = "https://cdr.energymadeeasy.gov.au"
    headers = {"x-v": "3", "Accept": "application/json"}
    results = {}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as cli:
        for r in retailers:
            try:
                resp = await cli.get(f"{base}/{r}/cds-au/v1/energy/plans?page-size=10")
                if resp.status_code == 200:
                    plans = resp.json().get("data", {}).get("plans", [])
                    results[r] = {"status": "ok", "count": len(plans)}
                else:
                    results[r] = {"status": "http_error", "code": resp.status_code}
            except Exception as exc:  # noqa: BLE001
                results[r] = {"status": "exception", "detail": str(exc)}
    return {"queried": retailers, "results": results}
