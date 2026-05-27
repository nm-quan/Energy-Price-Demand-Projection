"""
Scenario generator — deterministic simulation + 1 AI call per scenario.

Flow:
  Server  pick target appliance by rotating index
  Server  apply APPLIANCE_STRATEGIES (realistic shift params, no AI guesswork)
  Server  compute_retailer_comparison() — pure math
  AI      single forced commit_scenario call — writes name, rationale, levers
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

import anthropic

from models import Tariff
from baseline_engine import compute_annual_cost_components, compute_shape_metrics

logger = logging.getLogger("scenario_claude")

MODEL_NAME = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1500


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Appliance strategies (server-side, deterministic) ────────────────────────
# Each appliance gets a realistic shift strategy based on how it actually operates.
# from_window / to_window are half-hourly bucket indices (0=midnight, 30=3pm, 42=9pm).

APPLIANCE_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "HVAC": {
        "action": "shift_window",
        "from_window": [30, 42],   # 3pm–9pm TOU peak
        "to_window":   [0, 14],    # midnight–7am off-peak
        "from_scale":  0.55,
        "scenario_name": "HVAC Pre-Cool — Shift Peak Load to Off-Peak",
        "narrative_hint": (
            "Pre-cooling strategy: run HVAC harder during cheap overnight hours to build thermal "
            "mass, then coast through the expensive 3–9pm window with reduced compressor load."
        ),
    },
    "Fridges": {
        "action": "shift_window",
        "from_window": [30, 42],
        "to_window":   [0, 12],    # midnight–6am
        "from_scale":  0.35,
        "scenario_name": "Refrigeration Pre-Cool Overnight Cycling",
        "narrative_hint": (
            "Refrigeration pre-cooling: lower thermostat setpoints overnight so the thermal mass "
            "absorbs cold, reducing compressor cycling during peak pricing window."
        ),
    },
    "Dishwasher": {
        "action": "shift_window",
        "from_window": [30, 42],
        "to_window":   [2, 16],    # 1am–8am
        "from_scale":  0.85,
        "scenario_name": "Dishwasher Cycles Moved to Overnight",
        "narrative_hint": (
            "Overnight scheduling: defer all dishwasher cycles to 1–8am off-peak window. "
            "No operational change needed — just reprogram the start timer."
        ),
    },
    "Hot Water": {
        "action": "shift_window",
        "from_window": [30, 42],
        "to_window":   [0, 14],    # midnight–7am
        "from_scale":  0.75,
        "scenario_name": "Hot Water Pre-Heat During Off-Peak Hours",
        "narrative_hint": (
            "Hot water pre-heating: use the storage tank as a thermal battery — heat water "
            "overnight at cheap rates and maintain temperature through the peak window."
        ),
    },
    "Espresso": {
        "action": "shift_window",
        "from_window": [30, 42],
        "to_window":   [16, 30],   # 8am–3pm morning rush
        "from_scale":  0.50,
        "scenario_name": "Espresso Machine Load Concentrated in Morning",
        "narrative_hint": (
            "Machine scheduling: concentrate espresso machine operation in the morning rush "
            "(8am–3pm) and reduce afternoon idle heating during the 3–9pm peak window."
        ),
    },
    "Lighting": {
        "action": "set_off",
        "from_window": [30, 42],
        "from_scale":  0.25,
        "scenario_name": "Smart Lighting Dim 25% During Peak Window",
        "narrative_hint": (
            "Smart dimming: automate a 25% lighting reduction during 3–9pm via smart controls "
            "or occupancy sensors. Minimal customer impact, instant zero-capital saving."
        ),
    },
    "Ovens": {
        "action": "shift_window",
        "from_window": [24, 42],   # noon–9pm
        "to_window":   [6, 18],    # 3am–9am early morning
        "from_scale":  0.50,
        "scenario_name": "Oven Baking Shifted to Early Morning Prep",
        "narrative_hint": (
            "Morning batch baking: shift prep cooking and baking to early morning hours before "
            "the peak window opens, reducing oven load during expensive afternoon pricing."
        ),
    },
    "Misc": {
        "action": "set_off",
        "from_window": [30, 42],
        "from_scale":  0.20,
        "scenario_name": "Misc Load Standby Reduction During Peak",
        "narrative_hint": (
            "Standby reduction: automated 20% cut to miscellaneous loads (charging stations, "
            "office equipment, displays) during peak via smart power strips or a building controller."
        ),
    },
}

_DEFAULT_STRATEGY: Dict[str, Any] = {
    "action": "shift_window",
    "from_window": [30, 42],
    "to_window":   [0, 16],
    "from_scale":  0.50,
    "narrative_hint": "Shift load from 3–9pm TOU peak to overnight off-peak window.",
}


# ── Commit tool schema ────────────────────────────────────────────────────────

COMMIT_TOOL: Dict[str, Any] = {
    "name": "commit_scenario",
    "description": "Write the final scenario summary based on the simulation results.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name":        {"type": "string", "description": "5–8 words, specific appliance + strategy (e.g. 'HVAC Pre-Cool Shift to Off-Peak')"},
            "rationale":   {"type": "string", "description": "2 sentences: what was shifted and why it saves money"},
            "appliance_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "appliance": {"type": "string"},
                        "action":    {"type": "string"},
                        "summary":   {"type": "string", "description": "One sentence describing the change"},
                    },
                    "required": ["appliance", "action", "summary"],
                },
            },
            "retailer_winner":      {"type": "string"},
            "negotiation_levers":   {"type": "array", "items": {"type": "string"}, "description": "3 specific, numbered broker talking points with actual kWh/$ figures"},
            "memory_bullets":       {"type": "array", "items": {"type": "string"}, "description": "3 key facts about this specific site"},
            "savings_annual_low":   {"type": "number"},
            "savings_annual_high":  {"type": "number"},
        },
        "required": [
            "rationale", "appliance_changes", "retailer_winner",
            "negotiation_levers", "memory_bullets", "savings_annual_low", "savings_annual_high",
        ],
    },
}

COMMIT_SYSTEM = """You are a senior energy broker writing a client-facing recommendation.

Your job: write rationale, appliance_changes summary, negotiation levers, memory bullets, and savings figures.
The scenario name is already set — do not invent a different one.

Rules:
- rationale: 2 sentences. First: what was done (appliance, window, fraction). Second: why this saves money.
- appliance_changes: one entry. appliance = exact name given. summary = one actionable sentence for the site manager.
- negotiation_levers: 3 specific talking points with real numbers (kWh shifted, % reduction, retailer names, $ figures).
- memory_bullets: 3 facts about THIS site (annual kWh, load factor, peak demand kW, % in TOU peak).
- savings_annual_low  = annual_saving_on_current_tariff (must be > 0)
- savings_annual_high = savings_annual_low + max_saving_vs_current (must be > savings_annual_low)"""


# ── Core simulation (server-side, no AI) ─────────────────────────────────────

def _aggregate_appliance_curves(appliance_curves: Dict[str, List[float]]) -> List[float]:
    if not appliance_curves:
        return [0.0] * 48
    total = [0.0] * 48
    for curve in appliance_curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


def compute_retailer_comparison(load_curve: List[float], annual_kwh: float, current_tariff: Tariff) -> Dict[str, Any]:
    """Pure math — no AI."""
    from data_store import RETAILER_TARIFFS

    if not load_curve or len(load_curve) != 48:
        return {"error": "load_curve must be 48 numbers"}

    current_cost = compute_annual_cost_components(load_curve, current_tariff, annual_kwh)["grand_total"]
    rows = []
    for tdict in RETAILER_TARIFFS:
        t = Tariff(**tdict)
        cost = compute_annual_cost_components(load_curve, t, annual_kwh)["grand_total"]
        rows.append({
            "retailer": t.retailer,
            "plan": t.plan_name,
            "peak_rate": t.energy_rates.peak,
            "shoulder_rate": t.energy_rates.shoulder,
            "offpeak_rate": t.energy_rates.offpeak,
            "supply_charge_daily": t.supply_charge,
            "annual_cost": round(cost, 2),
            "delta_vs_current": round(cost - current_cost, 2),
            "delta_pct": round((cost - current_cost) / current_cost * 100, 2) if current_cost > 0 else 0,
            "is_current": t.retailer == current_tariff.retailer and t.plan_name == current_tariff.plan_name,
        })
    rows.sort(key=lambda r: r["annual_cost"])
    return {
        "current_retailer": current_tariff.retailer,
        "current_annual_cost": round(current_cost, 2),
        "comparison": rows,
        "best": rows[0]["retailer"] if rows else None,
        "max_saving_vs_current": round(current_cost - rows[0]["annual_cost"], 2) if rows else 0,
    }


def _run_simulation(
    appliance_curves: Dict[str, List[float]],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
    target: str,
    strategy: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Apply a strategy to one appliance. Returns sim result dict or None on error."""
    working = {k: list(v) for k, v in appliance_curves.items()}

    if target not in working:
        logger.warning("appliance '%s' not in curves (%s)", target, list(working.keys()))
        return None

    before = list(working[target])
    after  = list(before)
    action = strategy["action"]
    fs     = min(1.0, max(0.0, float(strategy.get("from_scale", 0.5))))

    if action == "shift_window":
        fw = strategy.get("from_window", [30, 42])
        tw = strategy.get("to_window",   [0, 16])
        f_s, f_e = int(fw[0]), int(fw[1])
        t_s, t_e = int(tw[0]), int(tw[1])
        moved_kwh = 0.0
        for b in range(max(0, f_s), min(48, f_e)):
            delta = before[b] * fs
            after[b] = before[b] - delta
            moved_kwh += delta * 0.5
        to_buckets = max(1, t_e - t_s)
        add_per    = (moved_kwh / 0.5) / to_buckets
        for b in range(max(0, t_s), min(48, t_e)):
            after[b] = after[b] + add_per

    elif action == "set_off":
        fw = strategy.get("from_window", [0, 48])
        f_s, f_e = int(fw[0]), int(fw[1])
        for b in range(max(0, f_s), min(48, f_e)):
            after[b] = before[b] * (1.0 - fs)

    elif action == "scale":
        sf = float(strategy.get("scale_factor", 1.0))
        after = [v * sf for v in before]

    working[target] = after
    new_total = _aggregate_appliance_curves(working)

    baseline_sum = sum(baseline_curve)
    new_sum      = sum(new_total)
    new_annual   = annual_kwh * (new_sum / baseline_sum) if baseline_sum > 0 else annual_kwh

    base_cost = compute_annual_cost_components(baseline_curve, tariff, annual_kwh)["grand_total"]
    new_cost  = compute_annual_cost_components(new_total,      tariff, new_annual)["grand_total"]

    peak_before = sum((before[b] if b < len(before) else 0.0) * 0.5 for b in range(30, 42))
    peak_after  = sum((after[b]  if b < len(after)  else 0.0) * 0.5 for b in range(30, 42))

    return {
        "appliance":      target,
        "action":         action,
        "before_curve":   [round(v, 3) for v in before],
        "after_curve":    [round(v, 3) for v in after],
        "total_curve_after": [round(v, 3) for v in new_total],
        "working_curves": working,
        "annual_cost_before":            round(base_cost, 2),
        "annual_cost_after":             round(new_cost,  2),
        "annual_saving_on_current_tariff": round(base_cost - new_cost, 2),
        "peak_kw_after":   round(max(new_total), 3) if new_total else 0,
        "peak_kwh_before": round(peak_before, 2),
        "peak_kwh_after":  round(peak_after,  2),
        "peak_kwh_shifted": round(peak_before - peak_after, 2),
        "new_annual_kwh":  round(new_annual, 1),
    }


# ── Commit message builder ────────────────────────────────────────────────────

def _build_commit_message(
    client: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    sim: Dict[str, Any],
    retailer: Dict[str, Any],
    strategy: Dict[str, Any],
) -> str:
    rates = tariff.energy_rates
    saving_low  = sim["annual_saving_on_current_tariff"]
    saving_high = saving_low + retailer.get("max_saving_vs_current", 0)
    best        = retailer.get("best", "unknown")
    peak_pct    = shape.get("peak_coincidence", 0) * 100
    load_factor = shape.get("load_factor", 0) * 100

    return (
        f"Site: {client.get('name')} ({client.get('site_type', 'commercial')})\n"
        f"Annual consumption: {annual_kwh:.0f} kWh/yr · Peak demand: {shape.get('peak_kw', 0):.1f} kW\n"
        f"Load factor: {load_factor:.0f}% · {peak_pct:.0f}% of load falls in TOU peak (3–9pm)\n"
        f"Current tariff: {tariff.retailer} {tariff.plan_name} — "
        f"peak ${rates.peak or 0:.3f}/kWh · off-peak ${rates.offpeak or 0:.3f}/kWh\n"
        f"\nSimulation performed:\n"
        f"  Appliance: {sim['appliance']}\n"
        f"  Action: {strategy.get('narrative_hint', '')}\n"
        f"  Peak window kWh before: {sim['peak_kwh_before']:.1f} kWh/day · after: {sim['peak_kwh_after']:.1f} kWh/day\n"
        f"  Shifted out of peak: {sim['peak_kwh_shifted']:.1f} kWh/day "
        f"({sim['peak_kwh_shifted'] * 365:.0f} kWh/year)\n"
        f"  Annual saving on current tariff: ${saving_low:.0f}\n"
        f"\nRetailer comparison after shift:\n"
        f"  Current retailer: {tariff.retailer} — ${retailer.get('current_annual_cost', 0):.0f}/yr\n"
        f"  Cheapest retailer: {best} — saves additional ${retailer.get('max_saving_vs_current', 0):.0f}/yr\n"
        f"  Combined saving potential: ${saving_high:.0f}/yr\n"
        f"\nNow call commit_scenario. Name must reference '{sim['appliance']}' specifically."
    )


# ── Core generation ───────────────────────────────────────────────────────────

def _finalize(
    committed: Dict[str, Any],
    sim: Dict[str, Any],
    retailer_table: Optional[Dict[str, Any]],
    scenario_name: str,
) -> Dict[str, Any]:
    # Always use the Python-generated name — AI cannot override this
    committed["name"] = scenario_name

    for ch in committed.get("appliance_changes", []) or []:
        if ch.get("appliance", "").lower() == sim["appliance"].lower():
            ch["before_curve"] = sim["before_curve"]
            ch["after_curve"]  = sim["after_curve"]

    # If AI returned no appliance_changes, build one from the sim result
    if not committed.get("appliance_changes"):
        committed["appliance_changes"] = [{
            "appliance": sim["appliance"],
            "action": sim["action"],
            "summary": f"Shifted {sim['peak_kwh_shifted']:.1f} kWh/day out of 3–9pm peak window",
            "before_curve": sim["before_curve"],
            "after_curve":  sim["after_curve"],
        }]

    committed["shifted_curve"] = sim["total_curve_after"]
    if retailer_table:
        committed["retailer_comparison"] = retailer_table
    return committed


def _generate_one(
    cli: anthropic.Anthropic,
    client: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    scenario_idx: int,
    total_count: int,
    extra_instruction: Optional[str],
) -> Optional[Dict[str, Any]]:

    # ── Pick target appliance by scenario index ──────────────────────────────
    def tou_peak_kwh(name: str) -> float:
        c = appliance_curves.get(name, [])
        return sum((c[b] if b < len(c) else 0.0) * 0.5 for b in range(30, 42))

    all_appliances  = list(appliance_curves.keys())
    sorted_by_peak  = sorted(all_appliances, key=tou_peak_kwh, reverse=True)
    # Filter to appliances that actually have load (avoid targeting zero-load appliances)
    active = [a for a in sorted_by_peak if tou_peak_kwh(a) > 0.01]
    if not active:
        active = sorted_by_peak  # fallback: use all

    target   = active[(scenario_idx - 1) % len(active)]
    strategy = APPLIANCE_STRATEGIES.get(target, _DEFAULT_STRATEGY)

    # ── Server-side simulation ───────────────────────────────────────────────
    sim = _run_simulation(appliance_curves, baseline_curve, tariff, annual_kwh, target, strategy)
    if sim is None:
        logger.warning("scenario %d: simulation failed for %s", scenario_idx, target)
        return None

    # ── Server-side retailer comparison ─────────────────────────────────────
    shifted_curve = sim["total_curve_after"]
    retailer_result = compute_retailer_comparison(shifted_curve, sim["new_annual_kwh"], tariff)

    # ── Single AI call: write the scenario ──────────────────────────────────
    commit_msg = _build_commit_message(client, tariff, annual_kwh, shape, sim, retailer_result, strategy)
    if extra_instruction:
        commit_msg += f"\nAdditional focus: {extra_instruction}"

    resp = cli.messages.create(
        model=MODEL_NAME,
        system=COMMIT_SYSTEM,
        messages=[{"role": "user", "content": commit_msg}],
        tools=[COMMIT_TOOL],
        tool_choice={"type": "tool", "name": "commit_scenario"},
        max_tokens=MAX_TOKENS,
    )
    tu = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
    if not tu:
        logger.warning("scenario %d: no commit tool call", scenario_idx)
        return None

    scenario_name = strategy.get("scenario_name", f"{target} Load Shift Plan")
    result = _finalize(dict(tu.input or {}), sim, retailer_result, scenario_name)
    result["baseline_curve"] = [round(v, 3) for v in baseline_curve]
    return result


# ── Public API ───────────────────────────────────────────────────────────────

def generate_single(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    extra_instruction: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate one scenario synchronously — used by the chat endpoint."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)
    return _generate_one(cli, client, appliance_curves, baseline_curve, tariff, annual_kwh, shape, 1, 1, extra_instruction)


def generate_scenarios(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    count: int = 3,
    extra_instruction: Optional[str] = None,
    on_scenario_done: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Generate N scenarios in parallel — each targets a different appliance."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)

    scenarios: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(count, 4)) as pool:
        futures = {
            pool.submit(
                _generate_one,
                cli, client, appliance_curves, baseline_curve, tariff, annual_kwh,
                shape, i + 1, count, extra_instruction,
            ): i + 1
            for i in range(count)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                result = fut.result()
                if result and result.get("shifted_curve"):
                    scenarios.append(result)
                    if on_scenario_done:
                        try:
                            on_scenario_done(result)
                        except Exception:
                            logger.exception("on_scenario_done callback failed for scenario %d", idx)
                else:
                    logger.warning("scenario %d: empty result", idx)
            except Exception as exc:
                logger.exception("scenario %d failed: %s", idx, exc)

    if not scenarios:
        raise RuntimeError("All scenario generations failed")

    scenarios.sort(key=lambda s: s.get("savings_annual_low", 0), reverse=True)
    for i, s in enumerate(scenarios, start=1):
        s["rank"] = i

    return {"scenarios": scenarios, "source": "claude"}
