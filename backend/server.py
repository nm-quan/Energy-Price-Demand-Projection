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
    meter_active_shape,
    meter_appliances,
    meter_baseline_shape,
)
from cost_engine import annual_cost, shape_stats
from scenario_chat import ChatRequest, ChatResponse, run_chat
from historical import synthesize_for_range
import supabase_client as sb

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
    appliance_scales: Dict[str, float] = Field(default_factory=dict)


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
    return _rank_for(req.meter_ids, req.appliance_scales)


def _rank_for(meter_ids: List[str], appliance_scales: Dict[str, float]) -> Dict[str, Any]:
    """Pure helper — same logic as POST /api/rank but invokable from Python (used by Claude tool-use)."""
    meters = [_meter(mid) for mid in meter_ids]
    appliance_template = ARCHETYPE_APPLIANCES.get(meters[0]["archetype"], [])
    appliance_order = [a["id"] for a in appliance_template]
    appliance_meta = {a["id"]: a for a in appliance_template}

    per_appliance_profiles: Dict[str, List[float]] = {aid: [0.0] * 48 for aid in appliance_order}
    for m in meters:
        for a in meter_appliances(m):
            for i, v in enumerate(a["profile"]):
                per_appliance_profiles[a["id"]][i] += v

    scales = {aid: float(appliance_scales.get(aid, 1.0)) for aid in appliance_order}

    per_meter, full_shapes, active_shapes = [], [], []
    for m in meters:
        full = meter_baseline_shape(m)
        active_s = meter_active_shape(m, scales)
        full_shapes.append(full)
        active_shapes.append(active_s)
        per_meter.append({"meter_id": m["id"], "zone_code": m["zone_code"],
                          "full_shape": full, "active_shape": active_s})

    agg_full = _sum_shapes(full_shapes)
    agg_active = _sum_shapes(active_shapes)

    appliance_breakdown = []
    for aid in appliance_order:
        meta = appliance_meta[aid]
        scale = scales[aid]
        prof = [round(v * scale, 4) for v in per_appliance_profiles[aid]]
        appliance_breakdown.append({
            "id": aid, "name": meta["name"], "color": meta["color"],
            "always_on": meta.get("always_on", False), "note": meta.get("note", ""),
            "profile": prof, "daily_kwh": round(sum(prof) * 0.5, 2),
            "scale": scale, "active": scale > 0,
        })

    ranked = []
    for plan in SAMPLE_PLANS:
        sum_full = sum_active = 0.0
        for pm, m in zip(per_meter, meters):
            sum_full += annual_cost(pm["full_shape"], plan, m["zone_code"])["annual_total"]
            sum_active += annual_cost(pm["active_shape"], plan, m["zone_code"])["annual_total"]
        ranked.append({
            "plan": plan,
            "baseline_cost": round(sum_full, 2),
            "shifted_cost": round(sum_active, 2),
            "annual_delta": round(sum_active - sum_full, 2),
            "pct_delta": round((sum_active - sum_full) / max(sum_full, 1e-9) * 100.0, 2),
        })
    ranked.sort(key=lambda r: r["shifted_cost"])

    current_plan_id = meters[0]["current_plan_id"]
    current = next((r for r in ranked if r["plan"]["id"] == current_plan_id), ranked[0])
    best = ranked[0]
    achievable_saving = round(current["shifted_cost"] - best["shifted_cost"], 2)
    agg_zone = max(
        {m["zone_code"] for m in meters},
        key=lambda z: sum(1 for m in meters if m["zone_code"] == z),
    )

    return {
        "meter_ids": meter_ids,
        "n_sites": len(meters),
        "appliance_scales": scales,
        "appliance_breakdown": appliance_breakdown,
        "shape": {"full": agg_full, "active": agg_active},
        "stats": {
            "full": shape_stats(agg_full, agg_zone),
            "active": shape_stats(agg_active, agg_zone),
        },
        "ranked": ranked,
        "current_plan_id": current_plan_id,
        "current": current,
        "best": best,
        "achievable_saving": achievable_saving,
        "agg_zone": agg_zone,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    m = _meter(req.meter_id)
    site_context = {
        "nickname": m["nickname"],
        "nmi": m["nmi"],
        "state": m["state"],
        "zone_name": m["zone_name"],
        "annual_kwh": m["annual_kwh"],
        "current_plan_label": m["current_plan_label"],
    }
    try:
        return run_chat(req, site_context, _rank_for, [mm["id"] for mm in SAMPLE_METERS])
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat failed")
        raise HTTPException(500, f"Claude call failed: {exc}")


@app.get("/api/readings/{meter_id}")
async def get_readings(meter_id: str, range: str = "24h"):
    m = _meter(meter_id)
    if range not in {"24h", "month", "year"}:
        raise HTTPException(400, "range must be 24h, month or year")
    return {"meter_id": meter_id, **synthesize_for_range(m, range)}


@app.get("/api/readings-agg")
async def get_readings_aggregate(ids: str, range: str = "24h"):
    """Aggregate readings across multiple meter ids."""
    meter_ids = [x.strip() for x in ids.split(",") if x.strip()]
    if not meter_ids:
        raise HTTPException(400, "ids required")
    if range not in {"24h", "month", "year"}:
        raise HTTPException(400, "range must be 24h, month or year")
    per_site = [synthesize_for_range(_meter(mid), range) for mid in meter_ids]
    if not per_site:
        return {"meter_ids": meter_ids, "range": range, "points": []}
    grain = per_site[0]["grain"]
    # Sum kw_avg / kw_peak / kwh by ts (assumes identical ts series across meters)
    by_ts: Dict[str, Dict[str, float]] = {}
    for site in per_site:
        for p in site["points"]:
            row = by_ts.setdefault(p["ts"], {"kw_avg": 0.0, "kw_peak": 0.0, "kwh": 0.0})
            row["kw_avg"] += p["kw_avg"]
            row["kw_peak"] += p["kw_peak"]
            row["kwh"] += p["kwh"]
    points = [{"ts": ts, **{k: round(v, 3) for k, v in row.items()}} for ts, row in sorted(by_ts.items())]
    return {"meter_ids": meter_ids, "range": range, "grain": grain, "points": points}


@app.get("/api/health/supabase")
async def supabase_health():
    return {"available": sb.check_available(force=True)}


@app.post("/api/scenarios/save")
async def save_scenario(payload: Dict[str, Any]):
    saved = sb.save_scenario(payload)
    return {"ok": bool(saved), "scenario": saved}


@app.get("/api/scenarios/{meter_id}")
async def list_scenarios(meter_id: str):
    return {"scenarios": sb.list_scenarios(meter_id)}


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
