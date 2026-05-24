"""
Claude-powered dynamic scenario generator with proper tools.

Tools available to Claude:
  1. analyze_load_profile     — One-shot site analytics (peak buckets, by-appliance %).
  2. compare_retailers        — Run the cost engine against each of the 5 retailers
                                for a given annual_kwh + load curve.
  3. simulate_appliance_change — Apply a per-appliance change (scale, shift, off)
                                 and return the new appliance curves + savings
                                 versus the current tariff.
  4. commit_scenario          — Echo a fully-structured scenario back; used as a
                                schema-enforced output channel.

The final response is parsed JSON with `scenarios` + `agent_memory` (plain bullets).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic

from models import Tariff
from baseline_engine import compute_annual_cost_components, compute_shape_metrics

logger = logging.getLogger("scenario_claude")

MODEL_NAME = "claude-sonnet-4-5"
MAX_TURNS = 16
MAX_TOKENS = 4096


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Tool schemas ────────────────────────────────────────────────────────────

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "analyze_load_profile",
        "description": (
            "Get analytics for the site's baseline load shape: top peak buckets, "
            "appliance share of energy, peak coincidence, suggested shift windows. "
            "Call this once at the start to understand the site."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "compare_retailers",
        "description": (
            "Compare the 5 AU retailers (AGL, Origin, EnergyAustralia, Alinta, Red Energy) "
            "against the supplied load curve and annual kWh. Returns per-retailer annual cost "
            "and delta vs the client's current tariff. Use AFTER simulate_appliance_change "
            "to find which retailer best fits the new shape."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "load_curve": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "48 half-hourly kW values for the SHIFTED profile",
                },
                "annual_kwh": {"type": "number", "description": "Annual consumption in kWh"},
            },
            "required": ["load_curve", "annual_kwh"],
        },
    },
    {
        "name": "simulate_appliance_change",
        "description": (
            "Apply a real operational change to ONE appliance and return the new appliance "
            "curves + total load curve + savings vs baseline on the current tariff. "
            "Use this MULTIPLE TIMES per scenario to model each appliance change you propose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appliance": {
                    "type": "string",
                    "description": "Appliance name (must match one from analyze_load_profile.appliance_share)",
                },
                "action": {
                    "type": "string",
                    "enum": ["scale", "shift_window", "set_off"],
                    "description": (
                        "scale=multiply this appliance by `scale_factor` across all buckets; "
                        "shift_window=move energy from `from_window` to `to_window`; "
                        "set_off=turn appliance off during `from_window`"
                    ),
                },
                "scale_factor": {
                    "type": "number",
                    "description": "Used when action=scale (e.g. 0.7 = run at 70% during whole day)",
                },
                "from_window": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[start_bucket, end_bucket] half-hour buckets 0–47",
                },
                "to_window": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[start_bucket, end_bucket] target window for shifted energy",
                },
                "from_scale": {
                    "type": "number",
                    "description": "Fraction of from_window energy to move (0–1). Used with shift_window/set_off.",
                },
            },
            "required": ["appliance", "action"],
        },
    },
    {
        "name": "commit_scenario",
        "description": (
            "Echo back the final, fully-structured scenario after all appliance changes and "
            "retailer comparisons have been done. Call this ONCE per scenario. The tool result "
            "is identical to your input but lets you confirm the schema before the final JSON."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rationale": {"type": "string", "description": "1–2 sentences plain English"},
                "appliance_changes": {
                    "type": "array",
                    "description": "List of changes applied (mirror the simulate_appliance_change calls used)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "appliance": {"type": "string"},
                            "action": {"type": "string"},
                            "summary": {"type": "string", "description": "Plain-English summary, e.g. 'Pre-cool HVAC 1pm–3pm at 70%'"},
                            "before_curve": {"type": "array", "items": {"type": "number"}},
                            "after_curve": {"type": "array", "items": {"type": "number"}},
                        },
                        "required": ["appliance", "action", "summary"],
                    },
                },
                "shifted_curve": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Final 48-bucket total kW curve after ALL changes",
                },
                "retailer_winner": {
                    "type": "string",
                    "description": "Name of the recommended retailer from compare_retailers",
                },
                "negotiation_levers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Bullet list of metrics the broker can use to negotiate with the retailer",
                },
                "savings_annual_low": {"type": "number"},
                "savings_annual_high": {"type": "number"},
            },
            "required": ["name", "rationale", "appliance_changes", "shifted_curve",
                         "retailer_winner", "negotiation_levers",
                         "savings_annual_low", "savings_annual_high"],
        },
    },
]


# ── Tool implementations ────────────────────────────────────────────────────

def _aggregate_appliance_curves(appliance_curves: Dict[str, List[float]]) -> List[float]:
    """Sum per-appliance curves into a total 48-bucket load curve."""
    if not appliance_curves:
        return [0.0] * 48
    total = [0.0] * 48
    for curve in appliance_curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


def _tool_analyze_load_profile(state: Dict[str, Any]) -> Dict[str, Any]:
    appliance_curves: Dict[str, List[float]] = state["appliance_curves"]
    total = state["baseline_curve"]
    tariff: Tariff = state["tariff"]
    annual_kwh = state["annual_kwh"]
    shape = compute_shape_metrics(total, annual_kwh)

    # Appliance share of total energy
    appliance_share: Dict[str, float] = {}
    total_kwh = sum(total) * 0.5
    for name, curve in appliance_curves.items():
        appliance_share[name] = round((sum(curve) * 0.5) / total_kwh, 4) if total_kwh > 0 else 0.0

    # Top 5 peak buckets
    indexed = sorted(enumerate(total), key=lambda kv: -kv[1])[:5]
    top_buckets = [
        {"bucket": b, "time": f"{b // 2:02d}:{(b % 2) * 30:02d}", "kw": round(v, 3)}
        for b, v in indexed
    ]

    return {
        "site_type": state["client"].get("site_type"),
        "shape_metrics": shape,
        "appliance_share": appliance_share,
        "top_peak_buckets": top_buckets,
        "tou_windows": {
            "peak": "buckets 30–42 (3pm–9pm)",
            "shoulder": "buckets 14–30 (7am–3pm), 42–44 (9pm–10pm)",
            "offpeak": "buckets 0–14 (midnight–7am), 44–48 (10pm–midnight)",
        },
        "current_tariff": {
            "retailer": tariff.retailer,
            "plan": tariff.plan_name,
            "peak_rate": tariff.energy_rates.peak,
            "shoulder_rate": tariff.energy_rates.shoulder,
            "offpeak_rate": tariff.energy_rates.offpeak,
        },
    }


def _tool_compare_retailers(state: Dict[str, Any], load_curve: List[float], annual_kwh: float) -> Dict[str, Any]:
    from data_store import RETAILER_TARIFFS

    current = state["tariff"]
    if not load_curve or len(load_curve) != 48:
        return {"error": "load_curve must be 48 numbers"}

    rows = []
    current_cost = compute_annual_cost_components(load_curve, current, annual_kwh)["grand_total"]
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
        })
    rows.sort(key=lambda r: r["annual_cost"])
    return {
        "current_retailer": current.retailer,
        "current_annual_cost": round(current_cost, 2),
        "comparison": rows,
        "best": rows[0]["retailer"] if rows else None,
        "max_saving_vs_current": round(current_cost - rows[0]["annual_cost"], 2) if rows else 0,
    }


def _tool_simulate_appliance_change(state: Dict[str, Any], inp: Dict[str, Any]) -> Dict[str, Any]:
    appliance_curves: Dict[str, List[float]] = {k: list(v) for k, v in state["working_curves"].items()}
    name = inp.get("appliance")
    action = inp.get("action")
    if name not in appliance_curves:
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
        # Distribute moved kWh evenly across to_window
        to_buckets = max(1, t_e - t_s)
        add_per_bucket = (moved_kwh / 0.5) / to_buckets  # kW per bucket
        for b in range(max(0, t_s), min(48, t_e)):
            after[b] = after[b] + add_per_bucket
    else:
        return {"error": f"unknown action {action}"}

    # Apply to working state so chained calls compose
    appliance_curves[name] = after
    state["working_curves"] = appliance_curves

    new_total = _aggregate_appliance_curves(appliance_curves)
    baseline_total = state["baseline_curve"]
    tariff: Tariff = state["tariff"]
    annual_kwh = state["annual_kwh"]

    # Scale annual kWh proportionally to new curve
    baseline_sum = sum(baseline_total)
    new_sum = sum(new_total)
    new_annual_kwh = annual_kwh * (new_sum / baseline_sum) if baseline_sum > 0 else annual_kwh

    base_cost = compute_annual_cost_components(baseline_total, tariff, annual_kwh)["grand_total"]
    new_cost = compute_annual_cost_components(new_total, tariff, new_annual_kwh)["grand_total"]
    saving = round(base_cost - new_cost, 2)

    return {
        "appliance": name,
        "action": action,
        "before_curve": [round(v, 3) for v in before],
        "after_curve": [round(v, 3) for v in after],
        "total_curve_after": [round(v, 3) for v in new_total],
        "annual_kwh_after": round(new_annual_kwh, 1),
        "annual_cost_before": round(base_cost, 2),
        "annual_cost_after": round(new_cost, 2),
        "annual_saving_on_current_tariff": saving,
        "peak_kw_after": round(max(new_total), 3) if new_total else 0,
    }


def _tool_commit_scenario(_state: Dict[str, Any], inp: Dict[str, Any]) -> Dict[str, Any]:
    # Echo back the scenario so Claude sees a clean schema confirmation.
    return {"committed": True, "scenario": inp}


# ── User message ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior energy savings analyst for a broker.
Your job: generate exactly N realistic, site-specific load-shift scenarios.

WORKFLOW PER REQUEST:
1. Call analyze_load_profile ONCE first to understand the site.
2. For EACH of the N scenarios:
   a. Decide the operational change (which appliance, action, window) based on the site type and shape.
   b. Call simulate_appliance_change for EACH appliance you want to change. Multiple calls compose.
   c. Once the final shape is good, call compare_retailers with the shifted curve to pick the best retailer.
   d. Call commit_scenario with the complete payload.
3. After ALL N scenarios are committed, output ONE final JSON object — no markdown, no commentary:

{
  "scenarios": [<scenario from each commit_scenario call, with rank added>],
  "agent_memory": [
    "Bullet 1 — concise insight you learned about THIS site",
    "Bullet 2 — ...",
    "Bullet 3 — ..."
  ]
}

CONSTRAINTS:
- Be creative and SPECIFIC to the site_type. A cafe is not an office.
- Each scenario must change at least one appliance.
- Scenarios should be distinct (don't propose the same battery twice).
- For TOU sites, focus on shifting load OUT of buckets 30–42 (3pm–9pm peak).
- agent_memory: 4–6 short, broker-useful bullets. Plain text, no markdown.
- Buckets are 0–47 half-hourly (0=midnight, 30=3pm, 42=9pm, 47=11:30pm).
- IMPORTANT: working_curves are reset between scenarios — each scenario starts from the original baseline."""


def _build_user_message(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    count: int,
    extra_instruction: Optional[str],
) -> str:
    shape = baseline.get("shape_metrics", {})
    rates = tariff.energy_rates
    msg = (
        f"Site: {client.get('name')}, {client.get('address') or 'address not provided'}\n"
        f"Site type: {client.get('site_type')}\n"
        f"Annual consumption: {shape.get('annual_kwh', annual_kwh):.0f} kWh\n"
        f"Peak demand: {shape.get('peak_kw', 0):.1f} kW\n"
        f"Load factor: {(shape.get('load_factor') or 0) * 100:.1f}%\n"
        f"Current tariff: {tariff.retailer} {tariff.plan_name}\n"
        f"  - Peak: {rates.peak or 0:.4f} $/kWh\n"
        f"  - Shoulder: {rates.shoulder or 0:.4f} $/kWh\n"
        f"  - Off-peak: {rates.offpeak or 0:.4f} $/kWh\n\n"
        f"Generate exactly {count} scenarios. Follow the workflow strictly."
    )
    if extra_instruction:
        msg += f"\n\nBroker focus: {extra_instruction}"
    return msg


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _extract_text(content_blocks: List[Any]) -> str:
    return "".join(getattr(b, "text", "") for b in content_blocks if getattr(b, "type", None) == "text")


def generate_scenarios(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    count: int = 3,
    extra_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """Drive Claude through tool-use loop and return scenarios + agent_memory."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))

    # Shared state that tools mutate (working_curves resets per simulate call chain;
    # we reset between scenarios via Claude's awareness — see system prompt).
    state: Dict[str, Any] = {
        "client": client,
        "tariff": tariff,
        "annual_kwh": annual_kwh,
        "baseline_curve": baseline_curve,
        "appliance_curves": appliance_curves,
        "working_curves": {k: list(v) for k, v in appliance_curves.items()},
    }

    user_msg = _build_user_message(client, baseline, tariff, annual_kwh, count, extra_instruction)
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": user_msg}]}
    ]

    committed_scenarios: List[Dict[str, Any]] = []

    for _turn in range(MAX_TURNS):
        resp = cli.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        assistant_blocks: List[Dict[str, Any]] = []
        tool_use_blocks: List[Any] = []
        for b in resp.content:
            btype = getattr(b, "type", None)
            if btype == "text":
                assistant_blocks.append({"type": "text", "text": b.text})
            elif btype == "tool_use":
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": b.input,
                })
                tool_use_blocks.append(b)

        messages.append({"role": "assistant", "content": assistant_blocks})

        if resp.stop_reason == "tool_use" and tool_use_blocks:
            tool_results = []
            for tu in tool_use_blocks:
                try:
                    if tu.name == "analyze_load_profile":
                        out = _tool_analyze_load_profile(state)
                    elif tu.name == "compare_retailers":
                        out = _tool_compare_retailers(
                            state,
                            tu.input.get("load_curve", []),
                            float(tu.input.get("annual_kwh", annual_kwh)),
                        )
                    elif tu.name == "simulate_appliance_change":
                        out = _tool_simulate_appliance_change(state, tu.input or {})
                    elif tu.name == "commit_scenario":
                        out = _tool_commit_scenario(state, tu.input or {})
                        committed_scenarios.append(tu.input or {})
                        # Reset working curves so the next scenario starts fresh
                        state["working_curves"] = {k: list(v) for k, v in appliance_curves.items()}
                    else:
                        out = {"error": f"unknown tool {tu.name}"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(out),
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tool %s failed", tu.name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # No more tools — parse final JSON
        final_text = _extract_text(resp.content)
        parsed = _try_parse_json(final_text)
        if parsed and isinstance(parsed.get("scenarios"), list):
            scenarios = parsed["scenarios"]
            memory = parsed.get("agent_memory") or []
            for i, s in enumerate(scenarios, start=1):
                s["rank"] = i
            return {"scenarios": scenarios, "agent_memory": memory, "source": "claude"}

        # Fallback: rebuild from committed_scenarios
        if committed_scenarios:
            for i, s in enumerate(committed_scenarios, start=1):
                s["rank"] = i
            return {
                "scenarios": committed_scenarios,
                "agent_memory": ["(agent memory unavailable — fell back to committed scenarios)"],
                "source": "claude-tools-only",
            }

        raise RuntimeError("Claude returned no parseable scenarios and no commit_scenario calls")

    raise RuntimeError(f"Claude tool-use loop exceeded {MAX_TURNS} turns")
