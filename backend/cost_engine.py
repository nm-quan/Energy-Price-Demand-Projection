"""
Cost engine — computes annual energy spend for a given 48-bucket half-hourly
load shape (kW per bucket) under a retailer plan's tariff structure.

Each bucket represents a 30-min slice → energy_kwh = power_kw * 0.5.
Annual cost = sum_over_buckets(energy_kwh * tariff_for_bucket) * 365 + supply_charge * 365
For demand plans we also add a kW-month peak charge.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from seed_data import classify_bucket, TOU_ZONES


def annual_cost(shape: List[float], plan: Dict, zone_code: str) -> Dict:
    """
    shape: 48 entries, kW per 30-min bucket (typical weekday).
    plan: a retailer plan dict.
    zone_code: distribution zone code for TOU bands.
    Returns: dict with breakdown.
    """
    if len(shape) != 48:
        raise ValueError("shape must have 48 buckets")

    energy_by_band = {"peak": 0.0, "shoulder": 0.0, "offpeak": 0.0}
    for i, kw in enumerate(shape):
        kwh = max(kw, 0.0) * 0.5
        band = classify_bucket(zone_code, i)
        energy_by_band[band] += kwh

    daily_supply = float(plan.get("supply_charge") or 0.0)

    plan_type = plan.get("plan_type", "TOU")
    if plan_type == "Flat":
        rate = float(plan.get("flat_rate") or 0.0)
        total_kwh = sum(energy_by_band.values())
        daily_usage_cost = total_kwh * rate
    elif plan_type == "Demand":
        peak = float(plan.get("peak_rate") or 0.0)
        shoulder = float(plan.get("shoulder_rate") or 0.0)
        offpeak = float(plan.get("offpeak_rate") or 0.0)
        daily_usage_cost = (
            energy_by_band["peak"] * peak
            + energy_by_band["shoulder"] * shoulder
            + energy_by_band["offpeak"] * offpeak
        )
    else:  # TOU
        peak = float(plan.get("peak_rate") or 0.0)
        shoulder = float(plan.get("shoulder_rate") or 0.0)
        offpeak = float(plan.get("offpeak_rate") or 0.0)
        daily_usage_cost = (
            energy_by_band["peak"] * peak
            + energy_by_band["shoulder"] * shoulder
            + energy_by_band["offpeak"] * offpeak
        )

    annual_usage = daily_usage_cost * 365.0
    annual_supply = daily_supply * 365.0
    annual_demand = 0.0
    if plan_type == "Demand":
        peak_kw = 0.0
        for i, kw in enumerate(shape):
            if classify_bucket(zone_code, i) == "peak":
                peak_kw = max(peak_kw, max(kw, 0.0))
        annual_demand = float(plan.get("demand_charge_per_kw_month") or 0.0) * peak_kw * 12.0

    annual_total = annual_usage + annual_supply + annual_demand

    return {
        "annual_total": round(annual_total, 2),
        "annual_usage": round(annual_usage, 2),
        "annual_supply": round(annual_supply, 2),
        "annual_demand": round(annual_demand, 2),
        "energy_by_band_kwh_per_day": {k: round(v, 2) for k, v in energy_by_band.items()},
        "plan_type": plan_type,
    }


def shape_stats(shape: List[float], zone_code: str) -> Dict:
    """Live stats for the dashboard."""
    if not shape:
        return {}
    total_kwh = sum(max(v, 0.0) * 0.5 for v in shape)
    peak_kw = max(shape)
    avg_kw = sum(shape) / 48.0
    load_factor = (avg_kw / peak_kw) if peak_kw > 0 else 0.0

    peak_kwh = 0.0
    for i, kw in enumerate(shape):
        if classify_bucket(zone_code, i) == "peak":
            peak_kwh += max(kw, 0.0) * 0.5
    pct_in_peak = (peak_kwh / total_kwh) if total_kwh > 0 else 0.0

    return {
        "total_kwh_per_day": round(total_kwh, 2),
        "annual_kwh": round(total_kwh * 365.0, 2),
        "peak_kw": round(peak_kw, 2),
        "avg_kw": round(avg_kw, 2),
        "load_factor": round(load_factor, 3),
        "pct_in_peak": round(pct_in_peak, 3),
        "peak_kwh_per_day": round(peak_kwh, 2),
    }
