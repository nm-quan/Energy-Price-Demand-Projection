"""
Scenario generator — AI understands the request, server runs all math.

Flow:
  AI      reads real appliance data + user prompt → outputs simulation params + narrative
  Server  runs simulation math deterministically from AI's params
  Server  compute_retailer_comparison() — pure math
  Result  structured scenario with curves, savings, retailer data
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

_DEFAULT_PARAMS: Dict[str, Dict[str, Any]] = {
    "Fridges":    {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 12],  "from_scale": 0.35},
    "HVAC":       {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 16],  "from_scale": 0.55},
    "Dishwasher": {"action": "shift_window", "from_window": [30, 42], "to_window": [2, 16],  "from_scale": 0.85},
    "Hot Water":  {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 14],  "from_scale": 0.75},
    "Ovens":      {"action": "shift_window", "from_window": [24, 42], "to_window": [6, 18],  "from_scale": 0.50},
    "Espresso":   {"action": "shift_window", "from_window": [30, 42], "to_window": [16, 30], "from_scale": 0.50},
    "Lighting":   {"action": "set_off",      "from_window": [30, 42], "from_scale": 0.25},
    "Misc":       {"action": "set_off",      "from_window": [30, 42], "from_scale": 0.20},
}


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Single tool: AI decides params, server runs the math ─────────────────────

SCENARIO_TOOL: Dict[str, Any] = {
    "name": "create_scenario",
    "description": (
        "Propose an energy-saving change for one appliance. "
        "The server will run all simulation math — just specify what to change and write the narrative."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "appliance":    {"type": "string",  "description": "Exact appliance name from the list provided"},
            "action":       {"type": "string",  "enum": ["shift_window", "set_off", "scale"],
                             "description": "shift_window=move load between time windows; set_off=reduce load in a window; scale=multiply all load"},
            "from_window":  {"type": "array",   "items": {"type": "integer"},
                             "description": "Half-hourly bucket range to reduce [start, end]. 0=midnight, 30=3pm, 42=9pm"},
            "to_window":    {"type": "array",   "items": {"type": "integer"},
                             "description": "Where to move the load (shift_window only)"},
            "from_scale":   {"type": "number",  "description": "Fraction to move or reduce (0.0–1.0)"},
            "scale_factor": {"type": "number",  "description": "Multiplier for scale action (e.g. 0.8 = 20% reduction)"},
            "name":         {"type": "string",  "description": "Scenario name, 5–8 words, specific to the appliance and strategy"},
            "rationale":    {"type": "string",  "description": "2 sentences: what changes and why it saves money"},
            "negotiation_levers": {"type": "array", "items": {"type": "string"},
                                   "description": "3 broker talking points with real numbers"},
            "memory_bullets":     {"type": "array", "items": {"type": "string"},
                                   "description": "3 key facts about this site"},
        },
        "required": ["appliance", "action", "name", "rationale", "negotiation_levers", "memory_bullets"],
    },
}

SYSTEM_PROMPT = """You are an experienced energy broker who analyses commercial sites and recommends load-shifting strategies.

You will receive:
- Real per-appliance load data showing actual kWh in each time window
- The user's request or a target appliance to focus on
- Tariff rates and site details

Your job: propose ONE realistic, specific change that reduces peak costs. Be intelligent — read the data, understand the request, choose the right action.

=== HOW TO INTERPRET REQUESTS ===
"cut the fridge" / "reduce fridges" → target Fridges, shift peak compressor load to overnight
"shift dishwasher" / "move dishwasher" → target Dishwasher, schedule cycles to 1–8am off-peak
"pre-cool HVAC" / "reduce HVAC" → target HVAC, shift cooling load to pre-peak early morning
"hot water" → target Hot Water, pre-heat tank overnight
"lighting" / "dim lights" → target Lighting, set_off 20–30% during peak
"espresso" / "coffee machine" → target Espresso, concentrate use in morning rush
"ovens" / "baking" → target Ovens, shift baking to early morning
If no specific appliance mentioned → pick the appliance with most kWh in the 3–9pm peak window

=== PARAMETER GUIDE ===
Bucket index: 0=midnight, 14=7am, 16=8am, 30=3pm, 42=9pm, 48=midnight (next day)

shift_window: move a fraction of load from one window to another
  - from_window: where load currently is (e.g. [30, 42] = 3pm–9pm peak)
  - to_window: where to move it (e.g. [0, 14] = midnight–7am off-peak)
  - from_scale: fraction to move, 0.0–1.0 (be realistic: fridges ~0.3, dishwasher ~0.85, HVAC ~0.55)

set_off: reduce load in a window without moving it elsewhere
  - from_window: window to reduce
  - from_scale: fraction to reduce (lighting: 0.25, misc: 0.20)

scale: multiply entire appliance load by a factor
  - scale_factor: e.g. 0.80 = 20% overall reduction

=== NAMING RULES ===
Name must mention the specific appliance AND the strategy. Examples:
  "HVAC Pre-Cool — Shift 55% to Off-Peak"
  "Fridges Overnight Cycling — 35% Peak Reduction"
  "Dishwasher Fully Rescheduled to 1–8am"
  "Hot Water Pre-Heat Using Off-Peak Tank Storage"
  "Lighting Dimmed 25% During 3–9pm Peak"
DO NOT write generic names like "Energy Optimisation Plan" or "Load Shifting Scenario"

=== RATIONALE ===
2 sentences. First: what appliance, what action, what fraction, what window.
Second: why this saves money (TOU rate difference, reduced peak demand, retailer opportunity).
Write like a professional talking to a business owner, not a tech spec."""


# ── Math engine (server-side, no AI) ─────────────────────────────────────────

def _aggregate(curves: Dict[str, List[float]]) -> List[float]:
    total = [0.0] * 48
    for curve in curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


def compute_retailer_comparison(load_curve: List[float], annual_kwh: float, current_tariff: Tariff) -> Dict[str, Any]:
    from data_store import RETAILER_TARIFFS
    if not load_curve or len(load_curve) != 48:
        return {"error": "load_curve must be 48 numbers"}
    current_cost = compute_annual_cost_components(load_curve, current_tariff, annual_kwh)["grand_total"]
    rows = []
    for tdict in RETAILER_TARIFFS:
        t = Tariff(**tdict)
        cost = compute_annual_cost_components(load_curve, t, annual_kwh)["grand_total"]
        rows.append({
            "retailer": t.retailer, "plan": t.plan_name,
            "peak_rate": t.energy_rates.peak, "shoulder_rate": t.energy_rates.shoulder,
            "offpeak_rate": t.energy_rates.offpeak, "supply_charge_daily": t.supply_charge,
            "annual_cost": round(cost, 2),
            "delta_vs_current": round(cost - current_cost, 2),
            "delta_pct": round((cost - current_cost) / current_cost * 100, 2) if current_cost else 0,
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
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Apply AI-chosen params to one appliance. Returns full sim result."""
    working = {k: list(v) for k, v in appliance_curves.items()}
    target = params.get("appliance", "")

    # Case-insensitive match
    if target not in working:
        match = next((k for k in working if k.lower() == target.lower()), None)
        if match:
            target = match
        else:
            logger.warning("appliance '%s' not found in %s", target, list(working.keys()))
            return None

    before = list(working[target])
    after  = list(before)
    action = params.get("action", "shift_window")
    fs     = min(1.0, max(0.0, float(params.get("from_scale", 0.5))))

    if action == "shift_window":
        fw = params.get("from_window") or [30, 42]
        tw = params.get("to_window")   or [0, 14]
        f_s, f_e = int(fw[0]), int(fw[1])
        t_s, t_e = int(tw[0]), int(tw[1])
        moved_kwh = 0.0
        for b in range(max(0, f_s), min(48, f_e)):
            delta = before[b] * fs
            after[b] -= delta
            moved_kwh += delta * 0.5
        to_buckets = max(1, t_e - t_s)
        add_per = (moved_kwh / 0.5) / to_buckets
        for b in range(max(0, t_s), min(48, t_e)):
            after[b] += add_per

    elif action == "set_off":
        fw = params.get("from_window") or [30, 42]
        f_s, f_e = int(fw[0]), int(fw[1])
        for b in range(max(0, f_s), min(48, f_e)):
            after[b] = before[b] * (1.0 - fs)

    elif action == "scale":
        sf = float(params.get("scale_factor", 1.0))
        after = [v * sf for v in before]

    working[target] = after
    new_total = _aggregate(working)

    baseline_sum = sum(baseline_curve)
    new_sum      = sum(new_total)
    new_annual   = annual_kwh * (new_sum / baseline_sum) if baseline_sum > 0 else annual_kwh

    base_cost = compute_annual_cost_components(baseline_curve, tariff, annual_kwh)["grand_total"]
    new_cost  = compute_annual_cost_components(new_total, tariff, new_annual)["grand_total"]

    peak_before = sum((before[b] if b < len(before) else 0.0) * 0.5 for b in range(30, 42))
    peak_after  = sum((after[b]  if b < len(after)  else 0.0) * 0.5 for b in range(30, 42))

    return {
        "appliance": target, "action": action,
        "before_curve": [round(v, 3) for v in before],
        "after_curve":  [round(v, 3) for v in after],
        "total_curve_after": [round(v, 3) for v in new_total],
        "new_annual_kwh": round(new_annual, 1),
        "annual_saving_on_current_tariff": round(base_cost - new_cost, 2),
        "peak_kwh_before": round(peak_before, 2),
        "peak_kwh_after":  round(peak_after,  2),
        "peak_kwh_shifted": round(peak_before - peak_after, 2),
        "peak_kw_after": round(max(new_total), 3) if new_total else 0,
    }


# ── User message builder ──────────────────────────────────────────────────────

def _appliance_summary(name: str, curve: List[float]) -> str:
    def kwh(r): return sum((curve[b] if b < len(curve) else 0.0) * 0.5 for b in r)
    offpk = kwh(range(0, 16))
    mid   = kwh(range(16, 30))
    peak  = kwh(range(30, 42))
    eve   = kwh(range(42, 48))
    total = offpk + mid + peak + eve
    pct   = peak / total * 100 if total > 0 else 0
    peak_b = max(range(len(curve)), key=lambda b: curve[b]) if curve else 0
    peak_h = f"{peak_b//2:02d}:{(peak_b%2)*30:02d}"
    return (
        f"  {name:<14} off-pk {offpk:.1f} | mid {mid:.1f} | "
        f"TOU-peak {peak:.1f} kWh ({pct:.0f}%) | eve {eve:.1f} | peaks at {peak_h}"
    )


def _build_user_message(
    client: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    scenario_idx: int,
    total_count: int,
    extra_instruction: Optional[str],
    forced_appliance: Optional[str] = None,
) -> str:
    rates = tariff.energy_rates

    def tou_kwh(n): return sum((appliance_curves.get(n, [])[b] if b < len(appliance_curves.get(n, [])) else 0.0) * 0.5 for b in range(30, 42))
    sorted_apps = sorted(appliance_curves.keys(), key=tou_kwh, reverse=True)

    lines = "\n".join(_appliance_summary(n, appliance_curves[n]) for n in sorted_apps)

    msg = (
        f"Site: {client.get('name')} ({client.get('site_type', 'commercial')})\n"
        f"Annual: {annual_kwh:.0f} kWh · Peak demand: {shape.get('peak_kw', 0):.1f} kW · "
        f"Load factor: {shape.get('load_factor', 0)*100:.0f}% · "
        f"{shape.get('peak_coincidence', 0)*100:.0f}% of load in TOU peak\n"
        f"Tariff: {tariff.retailer} {tariff.plan_name} — "
        f"peak ${rates.peak or 0:.3f} | shoulder ${rates.shoulder or 0:.3f} | off-peak ${rates.offpeak or 0:.3f}/kWh\n"
        f"\nAppliance load (sorted by TOU-peak exposure):\n"
        f"  {'Name':<14} off-pk    | mid      | TOU-peak       | eve   | max hour\n"
        f"{lines}\n"
        f"\nAppliances available: {', '.join(appliance_curves.keys())}\n"
    )

    if extra_instruction:
        msg += f"\nUser request: {extra_instruction}\n"
    else:
        # For auto-generation, tell AI which rank to target for variety
        active = [n for n in sorted_apps if tou_kwh(n) > 0.01]
        target_hint = active[(scenario_idx - 1) % len(active)] if active else sorted_apps[0]
        msg += (
            f"\nThis is scenario {scenario_idx} of {total_count}. "
            f"Target appliance: {target_hint} "
            f"(ranked #{scenario_idx} by TOU-peak kWh — choose a strategy appropriate for this appliance).\n"
        )

    if forced_appliance:
        msg += f"\nFocus your analysis on appliance: {forced_appliance}. Write the name, rationale, and negotiation levers specifically for this appliance.\n"

    return msg


# ── Core generation ───────────────────────────────────────────────────────────

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
    forced_appliance: Optional[str] = None,
) -> Optional[Dict[str, Any]]:

    user_msg = _build_user_message(
        client, tariff, annual_kwh, shape, appliance_curves,
        scenario_idx, total_count, extra_instruction, forced_appliance,
    )

    # Single AI call — understands the request, outputs params + narrative
    resp = cli.messages.create(
        model=MODEL_NAME,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
        tools=[SCENARIO_TOOL],
        tool_choice={"type": "tool", "name": "create_scenario"},
        max_tokens=MAX_TOKENS,
    )
    tu = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
    if not tu:
        logger.warning("scenario %d: no tool call", scenario_idx)
        return None

    ai_params = dict(tu.input or {})
    logger.info("scenario %d: AI chose appliance=%s action=%s", scenario_idx, ai_params.get("appliance"), ai_params.get("action"))

    # Server overrides appliance selection — AI only provides narrative
    if forced_appliance:
        matched = next((k for k in _DEFAULT_PARAMS if k.lower() == forced_appliance.lower()), None)
        real_app = matched or forced_appliance
        ai_params["appliance"] = real_app
        if matched:
            ai_params.update(_DEFAULT_PARAMS[matched])
        logger.info("scenario %d: forced appliance=%s (was %s)", scenario_idx, real_app, ai_params.get("appliance"))

    # Server runs all math
    sim = _run_simulation(appliance_curves, baseline_curve, tariff, annual_kwh, ai_params)
    if sim is None:
        logger.warning("scenario %d: simulation failed", scenario_idx)
        return None

    retailer_result = compute_retailer_comparison(sim["total_curve_after"], sim["new_annual_kwh"], tariff)

    saving_low  = sim["annual_saving_on_current_tariff"]
    saving_high = saving_low + retailer_result.get("max_saving_vs_current", 0)

    return {
        "name":             ai_params.get("name", f"{sim['appliance']} Load Shift"),
        "rationale":        ai_params.get("rationale", ""),
        "appliance_changes": [{
            "appliance":    sim["appliance"],
            "action":       sim["action"],
            "summary":      ai_params.get("rationale", ""),
            "before_curve": sim["before_curve"],
            "after_curve":  sim["after_curve"],
        }],
        "retailer_winner":     retailer_result.get("best", ""),
        "negotiation_levers":  ai_params.get("negotiation_levers", []),
        "memory_bullets":      ai_params.get("memory_bullets", []),
        "savings_annual_low":  max(0.0, saving_low),
        "savings_annual_high": max(0.0, saving_high),
        "shifted_curve":       sim["total_curve_after"],
        "baseline_curve":      [round(v, 3) for v in baseline_curve],
        "retailer_comparison": retailer_result,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def generate_single(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    extra_instruction: Optional[str] = None,
    forced_appliance: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)
    return _generate_one(cli, client, appliance_curves, baseline_curve, tariff, annual_kwh, shape, 1, 1, extra_instruction, forced_appliance)


def generate_scenarios(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    count: int = 3,
    extra_instruction: Optional[str] = None,
    on_scenario_done: Optional[Callable[[Dict[str, Any]], None]] = None,
    forced_appliance: Optional[str] = None,
) -> Dict[str, Any]:
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)

    scenarios: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(count, 4)) as pool:
        futures = {
            pool.submit(
                _generate_one,
                cli, client, appliance_curves, baseline_curve, tariff, annual_kwh,
                shape, i + 1, count, extra_instruction, forced_appliance,
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
                            logger.exception("on_scenario_done failed for scenario %d", idx)
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
