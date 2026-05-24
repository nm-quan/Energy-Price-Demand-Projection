"""
Load-shift scenario engine for the energy broker API.

Supports 4 scenario types:
  - pre_cool_hvac   : Shift HVAC load to pre-peak cooling window
  - battery_dispatch: Charge off-peak, discharge peak
  - demand_cap      : Hard-cap peak demand at target kW
  - time_shift      : Shift a block of load from one window to another
"""
from __future__ import annotations

import copy
import logging
from typing import List, Dict, Any

from models import Tariff
from baseline_engine import compute_annual_cost_components, compute_shape_metrics

logger = logging.getLogger("scenario_engine")

# ── Scenario library (metadata for API) ──────────────────────────────────────

SCENARIO_LIBRARY = [
    {
        "id": "pre_cool_hvac",
        "name": "Pre-cool HVAC",
        "type": "pre_cool_hvac",
        "description": (
            "Shift HVAC load from peak hours to pre-peak cooling window. "
            "Reduces peak demand and peak-rate energy."
        ),
        "parameters_schema": {
            "hvac_fraction": {
                "type": "float",
                "label": "HVAC % of load",
                "default": 0.35,
                "min": 0.1,
                "max": 0.8,
            },
            "pre_cool_start": {
                "type": "int",
                "label": "Pre-cool start (bucket 0-47)",
                "default": 24,
                "min": 0,
                "max": 47,
            },
            "pre_cool_end": {
                "type": "int",
                "label": "Pre-cool end (bucket)",
                "default": 30,
                "min": 0,
                "max": 47,
            },
            "peak_start": {
                "type": "int",
                "label": "Peak reduction start (bucket)",
                "default": 30,
                "min": 0,
                "max": 47,
            },
            "peak_end": {
                "type": "int",
                "label": "Peak reduction end (bucket)",
                "default": 42,
                "min": 0,
                "max": 47,
            },
            "efficiency_gain": {
                "type": "float",
                "label": "Pre-cool efficiency ratio",
                "default": 0.85,
                "min": 0.5,
                "max": 1.0,
            },
        },
    },
    {
        "id": "battery_dispatch",
        "name": "Battery Dispatch",
        "type": "battery_dispatch",
        "description": (
            "Charge battery during off-peak, discharge during peak. "
            "Flattens demand profile."
        ),
        "parameters_schema": {
            "capacity_kwh": {
                "type": "float",
                "label": "Battery capacity (kWh)",
                "default": 50.0,
                "min": 10,
                "max": 500,
            },
            "power_kw": {
                "type": "float",
                "label": "Power rating (kW)",
                "default": 25.0,
                "min": 5,
                "max": 250,
            },
            "charge_start": {
                "type": "int",
                "label": "Charge window start (bucket)",
                "default": 2,
                "min": 0,
                "max": 47,
            },
            "charge_end": {
                "type": "int",
                "label": "Charge window end (bucket)",
                "default": 14,
                "min": 0,
                "max": 47,
            },
            "discharge_start": {
                "type": "int",
                "label": "Discharge window start (bucket)",
                "default": 30,
                "min": 0,
                "max": 47,
            },
            "discharge_end": {
                "type": "int",
                "label": "Discharge window end (bucket)",
                "default": 42,
                "min": 0,
                "max": 47,
            },
            "round_trip_efficiency": {
                "type": "float",
                "label": "Round-trip efficiency",
                "default": 0.90,
                "min": 0.7,
                "max": 1.0,
            },
        },
    },
    {
        "id": "demand_cap",
        "name": "Demand Cap",
        "type": "demand_cap",
        "description": (
            "Hard-cap peak demand at a target kW by shedding or deferring excess load."
        ),
        "parameters_schema": {
            "target_kw": {
                "type": "float",
                "label": "Target peak demand (kW)",
                "default": 0.0,
                "min": 0,
                "max": 10000,
            },
            "shed_fraction": {
                "type": "float",
                "label": "Fraction shed (vs deferred)",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
            },
        },
    },
    {
        "id": "time_shift",
        "name": "Time Shift",
        "type": "time_shift",
        "description": (
            "Shift a portion of peak load to off-peak hours "
            "(e.g. production, EV charging)."
        ),
        "parameters_schema": {
            "shift_kw": {
                "type": "float",
                "label": "kW to shift",
                "default": 10.0,
                "min": 0,
                "max": 10000,
            },
            "from_start": {
                "type": "int",
                "label": "Shift-from start (bucket)",
                "default": 30,
                "min": 0,
                "max": 47,
            },
            "from_end": {
                "type": "int",
                "label": "Shift-from end (bucket)",
                "default": 42,
                "min": 0,
                "max": 47,
            },
            "to_start": {
                "type": "int",
                "label": "Shift-to start (bucket)",
                "default": 2,
                "min": 0,
                "max": 47,
            },
            "to_end": {
                "type": "int",
                "label": "Shift-to end (bucket)",
                "default": 12,
                "min": 0,
                "max": 47,
            },
        },
    },
]


# ── Individual scenario functions ─────────────────────────────────────────────

def apply_pre_cool_hvac(profile: List[float], params: dict) -> List[float]:
    """
    Pre-cool HVAC: shift some HVAC load from peak hours to pre-peak window.
    The efficiency_gain < 1.0 means pre-cooling uses LESS energy than
    running during peak (thermal benefit), so total kWh may decrease slightly.
    """
    result = list(profile)
    hvac_fraction = float(params.get("hvac_fraction", 0.35))
    pre_cool_start = int(params.get("pre_cool_start", 24))
    pre_cool_end = int(params.get("pre_cool_end", 30))
    peak_start = int(params.get("peak_start", 30))
    peak_end = int(params.get("peak_end", 42))
    efficiency_gain = float(params.get("efficiency_gain", 0.85))

    pre_cool_buckets = max(pre_cool_end - pre_cool_start, 1)
    peak_buckets = max(peak_end - peak_start, 1)

    # Total HVAC load in the peak window
    peak_hvac_kw = sum(result[b] * hvac_fraction for b in range(peak_start, peak_end))

    # Redistribute: reduce peak, add pre-cool load (with efficiency gain)
    for b in range(peak_start, peak_end):
        result[b] = result[b] * (1.0 - hvac_fraction)

    # Pre-cool energy = peak HVAC energy × efficiency_gain
    pre_cool_add = (peak_hvac_kw * efficiency_gain) / pre_cool_buckets
    for b in range(pre_cool_start, pre_cool_end):
        result[b] = result[b] + pre_cool_add

    return [max(0.0, v) for v in result]


def apply_battery_dispatch(profile: List[float], params: dict) -> List[float]:
    """
    Battery: add charging load during charge window, subtract during discharge.
    Respects power and capacity limits with round-trip efficiency.
    """
    result = list(profile)
    capacity_kwh = float(params.get("capacity_kwh", 50.0))
    power_kw = float(params.get("power_kw", 25.0))
    charge_start = int(params.get("charge_start", 2))
    charge_end = int(params.get("charge_end", 14))
    discharge_start = int(params.get("discharge_start", 30))
    discharge_end = int(params.get("discharge_end", 42))
    rte = float(params.get("round_trip_efficiency", 0.90))

    # Charging phase: increase load during charge window
    charge_buckets = max(charge_end - charge_start, 1)
    # How much energy can we store? Capped by capacity and power
    max_charge_kwh = min(capacity_kwh, power_kw * charge_buckets * 0.5)
    charge_per_bucket = min(power_kw, max_charge_kwh / (charge_buckets * 0.5))
    for b in range(charge_start, charge_end):
        result[b] = result[b] + charge_per_bucket

    # Discharge phase: reduce load during discharge window
    discharge_buckets = max(discharge_end - discharge_start, 1)
    # Usable energy after round-trip efficiency
    usable_kwh = max_charge_kwh * rte
    discharge_per_bucket = min(power_kw, usable_kwh / (discharge_buckets * 0.5))
    for b in range(discharge_start, discharge_end):
        result[b] = max(0.0, result[b] - discharge_per_bucket)

    return result


def apply_demand_cap(profile: List[float], params: dict) -> List[float]:
    """
    Demand cap: hard-clip any bucket exceeding target_kw.
    The excess load is either shed (lost) or deferred to off-peak buckets.
    """
    result = list(profile)
    target_kw = float(params.get("target_kw", 0.0))
    shed_fraction = float(params.get("shed_fraction", 0.5))

    if target_kw <= 0:
        # Default target: 90% of current peak
        target_kw = max(result) * 0.90

    deferred_kwh = 0.0
    for b in range(48):
        if result[b] > target_kw:
            excess_kw = result[b] - target_kw
            deferred_kwh += excess_kw * 0.5 * (1.0 - shed_fraction)
            result[b] = target_kw

    # Spread deferred load across off-peak buckets (midnight to 7am: buckets 0-14)
    offpeak_buckets = list(range(0, 14))
    if deferred_kwh > 0 and offpeak_buckets:
        add_per_bucket = deferred_kwh / (len(offpeak_buckets) * 0.5)
        for b in offpeak_buckets:
            result[b] = result[b] + add_per_bucket

    return result


def apply_time_shift(profile: List[float], params: dict) -> List[float]:
    """
    Time shift: move a fixed kW block from one window to another.
    """
    result = list(profile)
    shift_kw = float(params.get("shift_kw", 10.0))
    from_start = int(params.get("from_start", 30))
    from_end = int(params.get("from_end", 42))
    to_start = int(params.get("to_start", 2))
    to_end = int(params.get("to_end", 12))

    from_buckets = max(from_end - from_start, 1)
    to_buckets = max(to_end - to_start, 1)

    # Remove from source window
    remove_per_bucket = shift_kw
    for b in range(from_start, from_end):
        result[b] = max(0.0, result[b] - remove_per_bucket)

    # Add to destination window — same total kWh
    from_kwh = shift_kw * from_buckets * 0.5
    add_per_bucket = from_kwh / (to_buckets * 0.5)
    for b in range(to_start, to_end):
        result[b] = result[b] + add_per_bucket

    return result


def apply_scenario(profile: List[float], scenario_config: dict) -> List[float]:
    """Dispatch to the right scenario function."""
    stype = scenario_config.get("type", "")
    params = scenario_config.get("parameters", {})

    if stype == "pre_cool_hvac":
        return apply_pre_cool_hvac(profile, params)
    elif stype == "battery_dispatch":
        return apply_battery_dispatch(profile, params)
    elif stype == "demand_cap":
        return apply_demand_cap(profile, params)
    elif stype == "time_shift":
        return apply_time_shift(profile, params)
    else:
        logger.warning("Unknown scenario type: %s — skipping", stype)
        return profile


# ── Main run_scenarios ────────────────────────────────────────────────────────

def run_scenarios(
    baseline_curve: List[float],
    scenarios_config: List[dict],
    tariff: Tariff,
    annual_kwh: float,
) -> dict:
    """
    Apply all scenarios in sequence to the baseline curve, then compute savings.

    Parameters
    ----------
    baseline_curve  : 48 half-hourly kW values
    scenarios_config: list of {type, parameters} dicts
    tariff          : Tariff object
    annual_kwh      : actual annual consumption

    Returns
    -------
    dict with keys: baseline_curve, shifted_curve, scenarios_applied,
                    savings, new_shape_metrics
    """
    shifted = list(baseline_curve)

    scenarios_applied = []
    for s in scenarios_config:
        before_peak = max(shifted)
        shifted = apply_scenario(shifted, s)
        after_peak = max(shifted)
        scenarios_applied.append({
            "type": s.get("type"),
            "parameters": s.get("parameters", {}),
            "peak_reduction_kw": round(before_peak - after_peak, 3),
        })

    # Scale annual_kwh for shifted profile based on kWh ratio
    baseline_sum = sum(baseline_curve)
    shifted_sum = sum(shifted)
    if baseline_sum > 0:
        shifted_kwh = annual_kwh * (shifted_sum / baseline_sum)
    else:
        shifted_kwh = annual_kwh

    # Compute costs
    baseline_costs = compute_annual_cost_components(baseline_curve, tariff, annual_kwh)
    shifted_costs = compute_annual_cost_components(shifted, tariff, shifted_kwh)

    energy_saving = baseline_costs["energy_total"] - shifted_costs["energy_total"]
    demand_saving = baseline_costs["demand_charge"] - shifted_costs["demand_charge"]

    # Indicative contract saving: 2-6% uplift from improved load factor
    baseline_lf = (
        (sum(baseline_curve) / len(baseline_curve)) / max(baseline_curve)
        if max(baseline_curve) > 0 else 0
    )
    shifted_lf = (
        (sum(shifted) / len(shifted)) / max(shifted)
        if max(shifted) > 0 else 0
    )
    load_factor_improvement = max(0.0, shifted_lf - baseline_lf)

    contract_low = max(0.0, shifted_costs["energy_total"] * 0.02)
    contract_high = max(
        0.0,
        shifted_costs["energy_total"] * 0.06
        + load_factor_improvement * shifted_costs["energy_total"] * 0.5,
    )

    savings = {
        "billing_defensible": {
            "energy": round(energy_saving, 2),
            "demand": round(demand_saving, 2),
            "total": round(energy_saving + demand_saving, 2),
        },
        "indicative": {
            "contract_low": round(contract_low, 2),
            "contract_high": round(contract_high, 2),
        },
        "total_low": round(energy_saving + demand_saving + contract_low, 2),
        "total_high": round(energy_saving + demand_saving + contract_high, 2),
    }

    new_shape_metrics = compute_shape_metrics(shifted, shifted_kwh)

    return {
        "baseline_curve": [round(v, 4) for v in baseline_curve],
        "shifted_curve": [round(v, 4) for v in shifted],
        "scenarios_applied": scenarios_applied,
        "savings": savings,
        "new_shape_metrics": new_shape_metrics,
    }
