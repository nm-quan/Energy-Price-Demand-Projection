"""
Baseline cost engine for the energy broker API.

Given a typical weekday load curve (48 half-hourly kW values) and a Tariff,
computes the full annual cost stack and shape metrics.
"""
from __future__ import annotations

from typing import List, Dict, Any

from models import Tariff

# ── TOU zone definitions ──────────────────────────────────────────────────────
# Each range is (start_bucket_inclusive, end_bucket_exclusive)
# Bucket 0 = midnight, bucket 30 = 15:00 (3pm)

TOU_ZONES: Dict[str, Dict[str, List[tuple]]] = {
    "VIC": {
        "peak":     [(30, 42)],               # 3pm – 9pm
        "shoulder": [(14, 30), (42, 44)],      # 7am – 3pm, 9pm – 10pm
    },
    "NSW": {
        "peak":     [(28, 42)],               # 2pm – 9pm
        "shoulder": [(14, 28), (42, 44)],
    },
    "QLD": {
        "peak":     [(28, 42)],
        "shoulder": [(14, 28), (42, 44)],
    },
    "SA": {
        "peak":     [(30, 44)],               # 3pm – 10pm
        "shoulder": [(12, 30), (44, 46)],
    },
}

# Default fallback zone for unknown states
_DEFAULT_ZONE = TOU_ZONES["VIC"]


def _get_bucket_zone(bucket: int, state: str) -> str:
    """Return 'peak', 'shoulder', or 'offpeak' for a given bucket and state."""
    zones = TOU_ZONES.get(state.upper(), _DEFAULT_ZONE)
    for start, end in zones.get("peak", []):
        if start <= bucket < end:
            return "peak"
    for start, end in zones.get("shoulder", []):
        if start <= bucket < end:
            return "shoulder"
    return "offpeak"


def compute_shape_metrics(load_curve_kw: List[float], annual_kwh: float) -> dict:
    """Compute shape metrics from a 48-bucket kW load curve."""
    n = len(load_curve_kw)
    if n == 0 or all(v == 0 for v in load_curve_kw):
        return {
            "load_factor": 0.0,
            "peak_kw": 0.0,
            "peak_coincidence": 0.0,
            "annual_kwh": annual_kwh,
            "avg_daily_kwh": round(annual_kwh / 365, 2),
            "max_demand_month": "January",
        }

    peak_kw = max(load_curve_kw)
    avg_kw = sum(load_curve_kw) / n
    load_factor = round(avg_kw / peak_kw, 4) if peak_kw > 0 else 0.0

    # Peak coincidence: fraction of total energy that falls in TOU peak window (VIC as reference)
    # Use VIC peak buckets (30-42) as default
    peak_buckets_energy = sum(load_curve_kw[b] for b in range(30, 42))
    total_energy = sum(load_curve_kw)
    peak_coincidence = round(peak_buckets_energy / total_energy, 4) if total_energy > 0 else 0.0

    return {
        "load_factor": load_factor,
        "peak_kw": round(peak_kw, 3),
        "peak_coincidence": peak_coincidence,
        "annual_kwh": round(annual_kwh, 2),
        "avg_daily_kwh": round(annual_kwh / 365, 2),
        "max_demand_month": "January",
    }


def compute_baseline(
    load_curve_kw: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> dict:
    """
    Compute full baseline cost stack and shape metrics.

    Parameters
    ----------
    load_curve_kw : 48 half-hourly kW values (typical weekday average)
    tariff        : Tariff object with rates
    annual_kwh    : actual annual consumption in kWh (used to scale energy costs)

    Returns
    -------
    dict with keys: load_curve, cost_stack, shape_metrics
    """
    n = len(load_curve_kw)
    if n != 48:
        raise ValueError(f"load_curve_kw must have 48 elements, got {n}")

    # Scale factor: map typical-day profile to annual consumption
    typical_day_kwh = sum(load_curve_kw) * 0.5  # kW × 0.5h = kWh per bucket
    if typical_day_kwh <= 0:
        scale = 0.0
    else:
        scale = annual_kwh / (typical_day_kwh * 365.0)

    state = getattr(tariff, "state", "VIC")

    # ── Classify each bucket into TOU zone and compute annual kWh ────────────
    zone_kwh: Dict[str, float] = {"peak": 0.0, "shoulder": 0.0, "offpeak": 0.0}
    for bucket in range(48):
        kw = load_curve_kw[bucket]
        kwh_per_interval = kw * 0.5  # half-hour → kWh
        annual_interval_kwh = kwh_per_interval * 365.0 * scale
        zone = _get_bucket_zone(bucket, state)
        zone_kwh[zone] += annual_interval_kwh

    # ── Energy costs ─────────────────────────────────────────────────────────
    rates = tariff.energy_rates

    if tariff.type == "Flat":
        # Use flat rate for all consumption
        flat_rate = rates.flat or 0.0
        energy_peak = 0.0
        energy_shoulder = 0.0
        energy_offpeak = annual_kwh * flat_rate
    else:
        # TOU or Demand — use zone rates
        peak_rate = rates.peak or 0.0
        shoulder_rate = rates.shoulder or 0.0
        offpeak_rate = rates.offpeak or 0.0

        energy_peak = zone_kwh["peak"] * peak_rate
        energy_shoulder = zone_kwh["shoulder"] * shoulder_rate
        energy_offpeak = zone_kwh["offpeak"] * offpeak_rate

    # ── Demand charge ─────────────────────────────────────────────────────────
    peak_kw = max(load_curve_kw) * scale if scale > 0 else max(load_curve_kw)
    # For demand tariffs: $/kW/month × peak_kW × 12 months
    if tariff.demand_charge and tariff.demand_charge > 0:
        demand_charge_annual = tariff.demand_charge * peak_kw * 12.0
    else:
        demand_charge_annual = 0.0

    # ── Network charges ───────────────────────────────────────────────────────
    nc = tariff.network_charges
    network_distribution = nc.distribution * annual_kwh
    network_transmission = nc.transmission * annual_kwh
    network_metering = nc.metering * annual_kwh
    # network service/fixed: treat as per-day fixed
    network_service_annual = nc.service * 365.0

    # ── Fixed supply charge ───────────────────────────────────────────────────
    fixed_supply = tariff.supply_charge * 365.0

    # ── Environmental levy ────────────────────────────────────────────────────
    environmental = tariff.environmental_levy * annual_kwh

    # ── Total ─────────────────────────────────────────────────────────────────
    total_annual = (
        energy_peak
        + energy_shoulder
        + energy_offpeak
        + demand_charge_annual
        + network_distribution
        + network_transmission
        + network_metering
        + network_service_annual
        + fixed_supply
        + environmental
    )

    cost_stack = {
        "energy_peak": round(energy_peak, 2),
        "energy_shoulder": round(energy_shoulder, 2),
        "energy_offpeak": round(energy_offpeak, 2),
        "demand_charge": round(demand_charge_annual, 2),
        "network_distribution": round(network_distribution, 2),
        "network_transmission": round(network_transmission, 2),
        "network_metering": round(network_metering, 2),
        "fixed_supply": round(fixed_supply, 2),
        "environmental": round(environmental, 2),
        "total_annual": round(total_annual, 2),
    }

    shape_metrics = compute_shape_metrics(load_curve_kw, annual_kwh)

    return {
        "load_curve": [round(v, 4) for v in load_curve_kw],
        "cost_stack": cost_stack,
        "shape_metrics": shape_metrics,
    }


def compute_annual_cost_components(
    load_curve_kw: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> Dict[str, float]:
    """
    Returns a flat dict of cost components suitable for savings calculations.
    Keys: energy_total, demand_charge, network_total, fixed_total, environmental, grand_total
    """
    result = compute_baseline(load_curve_kw, tariff, annual_kwh)
    cs = result["cost_stack"]
    energy_total = cs["energy_peak"] + cs["energy_shoulder"] + cs["energy_offpeak"]
    network_total = (
        cs["network_distribution"]
        + cs["network_transmission"]
        + cs["network_metering"]
    )
    return {
        "energy_total": energy_total,
        "demand_charge": cs["demand_charge"],
        "network_total": network_total,
        "fixed_total": cs["fixed_supply"],
        "environmental": cs["environmental"],
        "grand_total": cs["total_annual"],
    }
