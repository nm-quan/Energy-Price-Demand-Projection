"""
Scenario generator — 2 fixed API calls per scenario, no multi-turn loop.

Flow per scenario:
  Call 1  forced simulate_appliance_change  →  server gets shifted curve
  Server  compute_retailer_comparison()     →  pure math, no AI
  Call 2  forced commit_scenario            →  Claude writes the summary
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
MAX_TOKENS = 1024


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Tool schemas ─────────────────────────────────────────────────────────────

SIMULATE_TOOL: Dict[str, Any] = {
    "name": "simulate_appliance_change",
    "description": "Shift or reduce one appliance's load to cut peak costs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "appliance": {"type": "string", "description": "Exact appliance name from the list provided"},
            "action": {
                "type": "string",
                "enum": ["scale", "shift_window", "set_off"],
                "description": (
                    "scale=multiply usage by scale_factor; "
                    "shift_window=move fraction from peak window to off-peak window; "
                    "set_off=turn off during a window"
                ),
            },
            "scale_factor": {"type": "number"},
            "from_window": {"type": "array", "items": {"type": "integer"}, "description": "[start_bucket, end_bucket]"},
            "to_window": {"type": "array", "items": {"type": "integer"}},
            "from_scale": {"type": "number", "description": "Fraction to move/reduce (0.0–1.0)"},
        },
        "required": ["appliance", "action"],
    },
}

COMMIT_TOOL: Dict[str, Any] = {
    "name": "commit_scenario",
    "description": "Write the final scenario summary based on the simulation and retailer data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short scenario name, 5–8 words"},
            "rationale": {"type": "string", "description": "1–2 sentences: what changes and why it saves money"},
            "appliance_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "appliance": {"type": "string"},
                        "action": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["appliance", "action", "summary"],
                },
            },
            "retailer_winner": {"type": "string"},
            "negotiation_levers": {"type": "array", "items": {"type": "string"}},
            "memory_bullets": {"type": "array", "items": {"type": "string"}},
            "savings_annual_low": {"type": "number"},
            "savings_annual_high": {"type": "number"},
        },
        "required": [
            "name", "rationale", "appliance_changes", "retailer_winner",
            "negotiation_levers", "memory_bullets", "savings_annual_low", "savings_annual_high",
        ],
    },
}

SIMULATE_SYSTEM = """You are an energy analyst. Given a site's load profile, pick ONE appliance to shift for cost savings.

For TOU tariffs, shift load OUT of peak buckets 30–42 (3pm–9pm) to off-peak buckets 0–16 (midnight–8am).
Use shift_window with from_scale 0.5–0.7 for a meaningful result.
Use the exact appliance name as given in the user message."""

COMMIT_SYSTEM = """You are an energy analyst writing a scenario summary. Be concise and specific.

- savings_annual_low  = annual_saving_on_current_tariff from the simulation result
- savings_annual_high = savings_annual_low + max_saving_vs_current from the retailer comparison
- retailer_winner     = cheapest retailer from the comparison table
- negotiation_levers  = 2–3 specific things the broker can use when negotiating
- memory_bullets      = 2–3 plain-English facts about THIS site
Both savings values must be > 0."""


# ── Tool implementations ─────────────────────────────────────────────────────

def _aggregate_appliance_curves(appliance_curves: Dict[str, List[float]]) -> List[float]:
    if not appliance_curves:
        return [0.0] * 48
    total = [0.0] * 48
    for curve in appliance_curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


def compute_retailer_comparison(load_curve: List[float], annual_kwh: float, current_tariff: Tariff) -> Dict[str, Any]:
    """Pure math — no AI. Used by scenario generation and the /baseline endpoint."""
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


def _tool_simulate_appliance_change(state: Dict[str, Any], inp: Dict[str, Any]) -> Dict[str, Any]:
    appliance_curves: Dict[str, List[float]] = {k: list(v) for k, v in state["working_curves"].items()}
    name = inp.get("appliance", "")
    action = inp.get("action")

    # Case-insensitive name matching
    if name not in appliance_curves:
        matched = next((k for k in appliance_curves if k.lower() == name.lower()), None)
        if matched:
            name = matched
        else:
            return {"error": f"Unknown appliance '{name}'. Available: {list(appliance_curves.keys())}"}

    before = list(appliance_curves[name])
    after = list(before)

    if action == "scale":
        factor = float(inp.get("scale_factor", 1.0))
        after = [v * factor for v in before]
    elif action == "set_off":
        win = inp.get("from_window") or [0, 48]
        s, e = int(win[0]), int(win[1])
        fs = float(inp.get("from_scale", 1.0))
        for b in range(max(0, s), min(48, e)):
            after[b] = before[b] * (1.0 - fs)
    elif action == "shift_window":
        fw = inp.get("from_window") or [0, 0]
        tw = inp.get("to_window") or [0, 0]
        fs = float(inp.get("from_scale", 1.0))
        f_s, f_e = int(fw[0]), int(fw[1])
        t_s, t_e = int(tw[0]), int(tw[1])
        if f_e <= f_s or t_e <= t_s:
            return {"error": "from_window and to_window must be increasing ranges"}
        moved_kwh = 0.0
        for b in range(max(0, f_s), min(48, f_e)):
            delta = before[b] * fs
            after[b] = before[b] - delta
            moved_kwh += delta * 0.5
        to_buckets = max(1, t_e - t_s)
        add_per_bucket = (moved_kwh / 0.5) / to_buckets
        for b in range(max(0, t_s), min(48, t_e)):
            after[b] = after[b] + add_per_bucket
    else:
        return {"error": f"unknown action '{action}'"}

    appliance_curves[name] = after
    state["working_curves"] = appliance_curves
    state.setdefault("sim_history", []).append({
        "appliance": name,
        "action": action,
        "before_curve": [round(v, 4) for v in before],
        "after_curve": [round(v, 4) for v in after],
    })

    new_total = _aggregate_appliance_curves(appliance_curves)
    baseline_total = state["baseline_curve"]
    tariff: Tariff = state["tariff"]
    annual_kwh = state["annual_kwh"]
    baseline_sum = sum(baseline_total)
    new_sum = sum(new_total)
    new_annual_kwh = annual_kwh * (new_sum / baseline_sum) if baseline_sum > 0 else annual_kwh
    base_cost = compute_annual_cost_components(baseline_total, tariff, annual_kwh)["grand_total"]
    new_cost = compute_annual_cost_components(new_total, tariff, new_annual_kwh)["grand_total"]

    return {
        "appliance": name,
        "before_curve": [round(v, 3) for v in before],
        "after_curve": [round(v, 3) for v in after],
        "total_curve_after": [round(v, 3) for v in new_total],
        "annual_cost_before": round(base_cost, 2),
        "annual_cost_after": round(new_cost, 2),
        "annual_saving_on_current_tariff": round(base_cost - new_cost, 2),
        "peak_kw_after": round(max(new_total), 3) if new_total else 0,
    }


# ── Core generation ──────────────────────────────────────────────────────────

def _build_user_message(
    client: Dict[str, Any],
    shape: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    appliance_share: Dict[str, float],
    scenario_idx: int,
    total_count: int,
    extra_instruction: Optional[str],
) -> str:
    rates = tariff.energy_rates
    top = sorted(appliance_share.items(), key=lambda kv: -kv[1])[:4]
    appliance_str = ", ".join(f"{k} {v*100:.0f}%" for k, v in top)
    msg = (
        f"Site: {client.get('name')}, {client.get('site_type')}\n"
        f"Annual: {annual_kwh:.0f} kWh · Peak: {shape.get('peak_kw', 0):.1f} kW\n"
        f"Peak coincidence (3–9pm): {(shape.get('peak_coincidence') or 0)*100:.0f}%\n"
        f"Top appliances: {appliance_str}\n"
        f"Appliance names (use exactly): {', '.join(appliance_share.keys())}\n"
        f"Tariff: {tariff.retailer} {tariff.plan_name} — peak ${rates.peak or 0:.3f}, off-peak ${rates.offpeak or 0:.3f}/kWh\n"
        f"\nScenario {scenario_idx} of {total_count}."
    )
    if extra_instruction:
        msg += f"\nFocus: {extra_instruction}"
    return msg


def _finalize(
    committed: Dict[str, Any],
    state: Dict[str, Any],
    retailer_table: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sim_history = state.get("sim_history", [])
    by_appliance = {rec["appliance"]: rec for rec in sim_history}

    for ch in committed.get("appliance_changes", []) or []:
        rec = by_appliance.get(ch.get("appliance"))
        if rec:
            ch["before_curve"] = rec["before_curve"]
            ch["after_curve"] = rec["after_curve"]

    committed["shifted_curve"] = [
        round(v, 3) for v in _aggregate_appliance_curves(state.get("working_curves") or {})
    ]
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
    appliance_share: Dict[str, float],
    scenario_idx: int,
    total_count: int,
    extra_instruction: Optional[str],
) -> Optional[Dict[str, Any]]:
    state: Dict[str, Any] = {
        "tariff": tariff,
        "annual_kwh": annual_kwh,
        "baseline_curve": baseline_curve,
        "working_curves": {k: list(v) for k, v in appliance_curves.items()},
    }
    user_msg = _build_user_message(
        client, shape, tariff, annual_kwh, appliance_share,
        scenario_idx, total_count, extra_instruction,
    )

    # ── CALL 1: force simulate_appliance_change ──────────────────────────────
    resp1 = cli.messages.create(
        model=MODEL_NAME,
        system=SIMULATE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        tools=[SIMULATE_TOOL],
        tool_choice={"type": "tool", "name": "simulate_appliance_change"},
        max_tokens=MAX_TOKENS,
    )
    tu1 = next((b for b in resp1.content if getattr(b, "type", None) == "tool_use"), None)
    if not tu1:
        logger.warning("scenario %d: no simulate tool call", scenario_idx)
        return None

    args = dict(tu1.input or {})
    sim_result = _tool_simulate_appliance_change(state, args)
    if "error" in sim_result:
        logger.warning("scenario %d simulate error: %s", scenario_idx, sim_result["error"])
        return None

    # ── Server-side retailer comparison (pure math, no AI) ───────────────────
    shifted_curve = sim_result["total_curve_after"]
    baseline_sum = sum(baseline_curve)
    new_sum = sum(shifted_curve)
    new_annual_kwh = annual_kwh * (new_sum / baseline_sum) if baseline_sum > 0 else annual_kwh
    retailer_result = compute_retailer_comparison(shifted_curve, new_annual_kwh, tariff)

    # ── CALL 2: force commit_scenario ────────────────────────────────────────
    messages = [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": [{"type": "tool_use", "id": tu1.id, "name": tu1.name, "input": tu1.input}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tu1.id, "content": json.dumps(sim_result)}]},
        {"role": "user", "content": (
            f"Retailer comparison: {json.dumps(retailer_result)}\n"
            f"annual_saving_on_current_tariff = {sim_result['annual_saving_on_current_tariff']}\n"
            f"max_saving_vs_current (by switching retailer) = {retailer_result.get('max_saving_vs_current', 0)}\n"
            "Now call commit_scenario."
        )},
    ]
    resp2 = cli.messages.create(
        model=MODEL_NAME,
        system=COMMIT_SYSTEM,
        messages=messages,
        tools=[COMMIT_TOOL],
        tool_choice={"type": "tool", "name": "commit_scenario"},
        max_tokens=MAX_TOKENS,
    )
    tu2 = next((b for b in resp2.content if getattr(b, "type", None) == "tool_use"), None)
    if not tu2:
        logger.warning("scenario %d: no commit tool call", scenario_idx)
        return None

    return _finalize(tu2.input, state, retailer_result)


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
    total_kwh = sum(baseline_curve) * 0.5
    appliance_share = {
        name: (sum(curve) * 0.5) / total_kwh if total_kwh > 0 else 0.0
        for name, curve in appliance_curves.items()
    }
    return _generate_one(cli, client, appliance_curves, baseline_curve, tariff, annual_kwh, shape, appliance_share, 1, 1, extra_instruction)


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
    """Generate N scenarios in parallel."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)
    total_kwh = sum(baseline_curve) * 0.5
    appliance_share = {
        name: (sum(curve) * 0.5) / total_kwh if total_kwh > 0 else 0.0
        for name, curve in appliance_curves.items()
    }

    scenarios: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(count, 3)) as pool:
        futures = {
            pool.submit(
                _generate_one,
                cli, client, appliance_curves, baseline_curve, tariff, annual_kwh,
                shape, appliance_share, i + 1, count, extra_instruction,
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
                        except Exception:  # noqa: BLE001
                            logger.exception("on_scenario_done callback failed for scenario %d", idx)
                else:
                    logger.warning("scenario %d: empty result", idx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("scenario %d failed: %s", idx, exc)

    if not scenarios:
        raise RuntimeError("All scenario generations failed")

    scenarios.sort(key=lambda s: s.get("savings_annual_low", 0), reverse=True)
    for i, s in enumerate(scenarios, start=1):
        s["rank"] = i

    return {"scenarios": scenarios, "source": "claude"}
