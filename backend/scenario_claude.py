"""
Claude-powered dynamic scenario generator.

Each scenario is its own Claude conversation, run in parallel via a thread pool.
This brings N=3 generation down from ~6 minutes to ~45 seconds.

Tools (per scenario):
  1. compare_retailers          — Run cost engine vs each of 5 retailers for a load curve.
  2. simulate_appliance_change  — Apply a per-appliance change; return appliance + total curves + savings.
  3. commit_scenario            — Echo a schema-conformant scenario payload back as confirmation.

`analyze_load_profile` data is baked into the system message (no extra tool round-trip).
Each scenario emits its own `memory_bullets`; we dedupe/cap to 6 across the batch.
"""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import anthropic

from models import Tariff
from baseline_engine import compute_annual_cost_components, compute_shape_metrics

logger = logging.getLogger("scenario_claude")

MODEL_NAME = "claude-sonnet-4-5"
MAX_TURNS = 12
MAX_TOKENS = 2048


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
        "name": "compare_retailers",
        "description": (
            "Compare 5 AU retailers (AGL, Origin, EnergyAustralia, Alinta, Red Energy) against "
            "the supplied SHIFTED load curve. Returns per-retailer annual cost and delta vs the "
            "client's current tariff. Call ONCE per scenario after you have the final shifted curve."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "load_curve": {"type": "array", "items": {"type": "number"}},
                "annual_kwh": {"type": "number"},
            },
            "required": ["load_curve", "annual_kwh"],
        },
    },
    {
        "name": "simulate_appliance_change",
        "description": (
            "Apply ONE operational change to ONE appliance. Returns before/after appliance "
            "curves, the new total load curve, and savings vs baseline on the current tariff. "
            "Chain multiple calls — state persists across calls within this scenario."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appliance": {"type": "string"},
                "action": {"type": "string", "enum": ["scale", "shift_window", "set_off"]},
                "scale_factor": {"type": "number"},
                "from_window": {"type": "array", "items": {"type": "integer"}},
                "to_window": {"type": "array", "items": {"type": "integer"}},
                "from_scale": {"type": "number"},
            },
            "required": ["appliance", "action"],
        },
    },
    {
        "name": "commit_scenario",
        "description": "Return the final scenario summary. Call exactly ONCE. The server will fill in load curves from your simulate_appliance_change history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rationale": {"type": "string"},
                "appliance_changes": {
                    "type": "array",
                    "description": "Brief summary of each change you made (no curves — server adds them).",
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
                "memory_bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1–3 plain-English insights about the site (used in agent memory side panel)",
                },
                "savings_annual_low": {"type": "number"},
                "savings_annual_high": {"type": "number"},
            },
            "required": [
                "name", "rationale", "appliance_changes",
                "retailer_winner", "negotiation_levers", "memory_bullets",
                "savings_annual_low", "savings_annual_high",
            ],
        },
    },
]


# ── Tool implementations ────────────────────────────────────────────────────

def _aggregate_appliance_curves(appliance_curves: Dict[str, List[float]]) -> List[float]:
    if not appliance_curves:
        return [0.0] * 48
    total = [0.0] * 48
    for curve in appliance_curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


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
        to_buckets = max(1, t_e - t_s)
        add_per_bucket = (moved_kwh / 0.5) / to_buckets
        for b in range(max(0, t_s), min(48, t_e)):
            after[b] = after[b] + add_per_bucket
    else:
        return {"error": f"unknown action {action}"}

    appliance_curves[name] = after
    state["working_curves"] = appliance_curves

    # Track simulation history so commit_scenario can later look up curves
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


# ── Per-scenario system prompt ──────────────────────────────────────────────

PER_SCENARIO_SYSTEM = """You are an energy savings analyst. Generate ONE realistic load-shift scenario for this site.

WORKFLOW:
1. Call simulate_appliance_change one or more times to model the operational change.
   - The working curves persist across calls within this scenario.
   - Use scale, shift_window, or set_off actions on real appliances from the site.
2. Call compare_retailers ONCE with the final shifted curve to find the best retailer.
3. Call commit_scenario ONCE with the complete payload (name, rationale, appliance_changes, shifted_curve, retailer_winner, negotiation_levers, memory_bullets, savings_annual_low/high).

CONSTRAINTS:
- Be SPECIFIC to the site_type. A cafe is not an office.
- Buckets are 0–47 half-hourly (0=midnight, 30=3pm peak start, 42=9pm peak end).
- For TOU sites, focus on moving load OUT of 30–42 (3pm–9pm peak).
- savings_annual_high should be ≥ savings_annual_low. Use the compare_retailers delta + the appliance simulation savings to estimate the range.
- memory_bullets: 2–3 short insights about THIS site (not generic advice). Plain text.
- After commit_scenario returns, output EXACTLY: DONE"""


def _build_user_message_one(
    client: Dict[str, Any],
    shape: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    load_curve: List[float],
    appliance_share: Dict[str, float],
    scenario_idx: int,
    total_count: int,
    extra_instruction: Optional[str],
    avoid_themes: List[str],
) -> str:
    rates = tariff.energy_rates
    top_appliances = sorted(appliance_share.items(), key=lambda kv: -kv[1])[:4]
    appliance_str = ", ".join(f"{k} {v*100:.0f}%" for k, v in top_appliances)
    msg = (
        f"Site: {client.get('name')}, {client.get('address') or 'address not provided'}\n"
        f"Site type: {client.get('site_type')}\n"
        f"Annual: {annual_kwh:.0f} kWh · Peak: {shape.get('peak_kw', 0):.1f} kW · Load factor: {(shape.get('load_factor') or 0) * 100:.0f}%\n"
        f"Peak coincidence (3–9pm share): {(shape.get('peak_coincidence') or 0) * 100:.0f}%\n"
        f"Top appliances: {appliance_str}\n"
        f"Current tariff: {tariff.retailer} {tariff.plan_name} — Peak ${rates.peak or 0:.3f}, Shoulder ${rates.shoulder or 0:.3f}, Off-peak ${rates.offpeak or 0:.3f} per kWh\n\n"
        f"This is scenario {scenario_idx} of {total_count}. Generate ONE load-shift scenario."
    )
    if avoid_themes:
        msg += f"\nDo NOT propose any of these (already taken): {', '.join(avoid_themes)}"
    if extra_instruction:
        msg += f"\nBroker focus: {extra_instruction}"
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
    avoid_themes: List[str],
) -> Optional[Dict[str, Any]]:
    state: Dict[str, Any] = {
        "tariff": tariff,
        "annual_kwh": annual_kwh,
        "baseline_curve": baseline_curve,
        "working_curves": {k: list(v) for k, v in appliance_curves.items()},
    }
    user_msg = _build_user_message_one(
        client, shape, tariff, annual_kwh, baseline_curve, appliance_share,
        scenario_idx, total_count, extra_instruction, avoid_themes,
    )
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": user_msg}]}
    ]
    committed: Optional[Dict[str, Any]] = None

    for _turn in range(MAX_TURNS):
        resp = cli.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=PER_SCENARIO_SYSTEM,
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

        if tool_use_blocks:
            tool_results = []
            for tu in tool_use_blocks:
                try:
                    if tu.name == "compare_retailers":
                        out = _tool_compare_retailers(
                            state,
                            tu.input.get("load_curve", []),
                            float(tu.input.get("annual_kwh", annual_kwh)),
                        )
                    elif tu.name == "simulate_appliance_change":
                        out = _tool_simulate_appliance_change(state, tu.input or {})
                    elif tu.name == "commit_scenario":
                        out = {"committed": True}
                        committed = tu.input or {}
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
            # If we already committed, attach curves from sim history and return
            if committed:
                return _finalize_committed(committed, state)
            continue

        # end_turn — no tool calls this round
        if committed:
            return _finalize_committed(committed, state)
        # Maybe Claude returned the payload inline as JSON
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        parsed = _try_parse_json(text)
        if parsed and parsed.get("appliance_changes"):
            return _finalize_committed(parsed, state)
        # Nudge Claude to actually use the tools
        messages.append({
            "role": "user",
            "content": [{
                "type": "text",
                "text": (
                    "Please proceed by calling simulate_appliance_change, then compare_retailers, "
                    "and finally commit_scenario. Do not respond with plain text."
                ),
            }],
        })
        continue

    logger.warning("scenario hit MAX_TURNS=%d without commit_scenario", MAX_TURNS)
    return _finalize_committed(committed, state) if committed else None


def _finalize_committed(committed: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Attach load curves to the committed payload using simulation history."""
    sim_history: List[Dict[str, Any]] = state.get("sim_history", [])
    # For each appliance_changes entry, find the FIRST matching sim_history record by appliance name.
    # Multiple changes to the same appliance: pop them in order so each gets a unique record.
    history_by_app: Dict[str, List[Dict[str, Any]]] = {}
    for rec in sim_history:
        history_by_app.setdefault(rec["appliance"], []).append(rec)

    enriched_changes: List[Dict[str, Any]] = []
    for ch in committed.get("appliance_changes", []) or []:
        ch_copy = dict(ch)
        records = history_by_app.get(ch_copy.get("appliance"), [])
        if records:
            rec = records.pop(0)
            ch_copy["before_curve"] = rec["before_curve"]
            ch_copy["after_curve"] = rec["after_curve"]
        enriched_changes.append(ch_copy)
    committed["appliance_changes"] = enriched_changes

    # Always recompute shifted_curve from final working state
    working = state.get("working_curves") or {}
    shifted = _aggregate_appliance_curves(working)
    committed["shifted_curve"] = [round(v, 3) for v in shifted]
    return committed


def generate_scenarios(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    tariff: Tariff,
    annual_kwh: float,
    count: int = 3,
    extra_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate N scenarios in parallel via thread pool."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)

    # Pre-compute appliance share (no extra Claude tool call)
    total_kwh = sum(baseline_curve) * 0.5
    appliance_share: Dict[str, float] = {}
    for name, curve in appliance_curves.items():
        appliance_share[name] = (sum(curve) * 0.5) / total_kwh if total_kwh > 0 else 0.0

    avoid_themes: List[str] = []
    scenarios: List[Dict[str, Any]] = []

    # Generate in parallel (cap workers at 2 to stay under Anthropic 30k tokens/min rate limit)
    with ThreadPoolExecutor(max_workers=min(count, 2)) as pool:
        futures = {
            pool.submit(
                _generate_one,
                cli, client, appliance_curves, baseline_curve, tariff, annual_kwh,
                shape, appliance_share, i + 1, count, extra_instruction, avoid_themes,
            ): i + 1
            for i in range(count)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                result = fut.result()
                if result and result.get("shifted_curve"):
                    scenarios.append(result)
                else:
                    logger.warning("scenario %d returned no committed payload (result=%s)", idx, bool(result))
            except Exception as exc:  # noqa: BLE001
                logger.exception("scenario %d failed: %s", idx, exc)

    if not scenarios:
        raise RuntimeError("All scenario generations failed")

    # Sort by savings_low desc, re-rank
    scenarios.sort(key=lambda s: s.get("savings_annual_low", 0), reverse=True)
    for i, s in enumerate(scenarios, start=1):
        s["rank"] = i

    # Combine memory bullets: dedupe (case-insensitive prefix) and cap at 6
    seen = set()
    memory: List[str] = []
    for s in scenarios:
        for bullet in s.get("memory_bullets", []) or []:
            key = bullet.strip().lower()[:60]
            if key and key not in seen:
                seen.add(key)
                memory.append(bullet.strip())
            if len(memory) >= 6:
                break
        if len(memory) >= 6:
            break

    return {"scenarios": scenarios, "agent_memory": memory, "source": "claude"}
