"""
Scenario generator powered by Claude (Haiku — direct Anthropic SDK).

Each scenario is its own conversation, run in parallel via a thread pool.
Tools available per scenario:
  1. compare_retailers          — Cost engine vs 5 AU retailers for the SHIFTED load curve.
  2. simulate_appliance_change  — Apply a per-appliance change; chained calls compose.
  3. commit_scenario            — Final structured payload (curves filled in server-side).
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
MAX_TURNS = 8
MAX_TOKENS = 2048


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Tool schemas (Anthropic format) ─────────────────────────────────────────

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "compare_retailers",
        "description": (
            "Compare 5 AU retailers (AGL, Origin, EnergyAustralia, Alinta, Red Energy) against "
            "the supplied SHIFTED load curve. Returns per-retailer annual cost and delta vs the "
            "client's current tariff. Call ONCE per scenario after the final shifted curve is set."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "load_curve": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "48 half-hourly kW values for the SHIFTED profile",
                },
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
                "action": {
                    "type": "string",
                    "enum": ["scale", "shift_window", "set_off"],
                    "description": (
                        "scale=multiply this appliance by scale_factor across all buckets; "
                        "shift_window=move fraction of energy from from_window to to_window; "
                        "set_off=turn appliance off (1-from_scale) during from_window"
                    ),
                },
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
        "description": "Return the final scenario summary. Call exactly ONCE. Curves are filled in server-side from your simulate_appliance_change history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rationale": {"type": "string"},
                "appliance_changes": {
                    "type": "array",
                    "description": "Brief summary of each change (no curves — server adds them).",
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
                    "description": "2-3 plain-English insights about THIS site (shown to the broker as quick context).",
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


# ── Tool implementations (server-side) ──────────────────────────────────────

def _aggregate_appliance_curves(appliance_curves: Dict[str, List[float]]) -> List[float]:
    if not appliance_curves:
        return [0.0] * 48
    total = [0.0] * 48
    for curve in appliance_curves.values():
        for i, v in enumerate(curve[:48]):
            total[i] += float(v or 0.0)
    return total


def compute_retailer_comparison(load_curve: List[float], annual_kwh: float, current_tariff: Tariff) -> Dict[str, Any]:
    """Pure helper — used by Claude AND by the /baseline endpoint (no AI needed)."""
    from data_store import RETAILER_TARIFFS

    if not load_curve or len(load_curve) != 48:
        return {"error": "load_curve must be 48 numbers"}

    rows = []
    current_cost = compute_annual_cost_components(load_curve, current_tariff, annual_kwh)["grand_total"]
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

MANDATORY WORKFLOW — follow this exact sequence, no deviations:
STEP 1: Call simulate_appliance_change at least once (you MUST do this — never skip it).
         Pick a meaningful operational change for the site_type (e.g. shift HVAC pre-cooling,
         reduce oven peak usage, shift dishwasher from peak to off-peak).
         Use realistic factors: scale 0.5–0.9 for reductions, shift 30–50% of load from peak (buckets 30–42) to off-peak.
STEP 2: Optionally call simulate_appliance_change again for a second appliance if it makes sense.
STEP 3: Call compare_retailers ONCE with the final shifted curve from your last simulate_appliance_change result.
STEP 4: Call commit_scenario ONCE with the complete payload.

RULES:
- You MUST call simulate_appliance_change before commit_scenario. If you skip it, the scenario will have 0 savings and be discarded.
- savings_annual_low and savings_annual_high MUST both be > 0 (based on the annual_saving_on_current_tariff from simulate + retailer delta).
- savings_annual_high >= savings_annual_low.
- Buckets: 0–47 half-hourly (bucket 0=midnight, 16=8am, 30=3pm peak start, 42=9pm peak end).
- For TOU tariffs: focus on shifting load OUT of peak window buckets 30–42.
- Be SPECIFIC to the site_type: a cafe has espresso machines and ovens; an office has HVAC and lighting; etc.
- memory_bullets: 2–3 plain-English insights specific to THIS site. Not generic advice.
- Do NOT respond with plain text or markdown. Only call the tools."""


def _build_user_message_one(
    client: Dict[str, Any],
    shape: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
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
        client, shape, tariff, annual_kwh, appliance_share,
        scenario_idx, total_count, extra_instruction, avoid_themes,
    )
    # System prompt is passed separately in the Anthropic SDK
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": user_msg},
    ]
    committed: Optional[Dict[str, Any]] = None
    last_retailer_table: Optional[Dict[str, Any]] = None

    for _turn in range(MAX_TURNS):
        resp = cli.messages.create(
            model=MODEL_NAME,
            system=PER_SCENARIO_SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=MAX_TOKENS,
        )

        tu_blocks = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        text_blocks = [b for b in resp.content if getattr(b, "type", None) == "text"]

        # Build assistant content list for message history
        assistant_content: List[Dict[str, Any]] = []
        for b in resp.content:
            if getattr(b, "type", None) == "text":
                assistant_content.append({"type": "text", "text": b.text})
            elif getattr(b, "type", None) == "tool_use":
                assistant_content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        messages.append({"role": "assistant", "content": assistant_content})

        if tu_blocks:
            tool_results: List[Dict[str, Any]] = []
            for tu in tu_blocks:
                fname = tu.name
                args = tu.input or {}  # already a dict in Anthropic SDK
                try:
                    if fname == "compare_retailers":
                        out = compute_retailer_comparison(
                            args.get("load_curve", []),
                            float(args.get("annual_kwh", annual_kwh)),
                            tariff,
                        )
                        if "comparison" in out:
                            last_retailer_table = out
                    elif fname == "simulate_appliance_change":
                        out = _tool_simulate_appliance_change(state, args)
                    elif fname == "commit_scenario":
                        if not state.get("sim_history"):
                            out = {
                                "error": (
                                    "You must call simulate_appliance_change at least once before commit_scenario. "
                                    "Go back to STEP 1 and simulate a real appliance change first."
                                )
                            }
                        else:
                            committed = args
                            out = {"committed": True}
                    else:
                        out = {"error": f"unknown tool {fname}"}
                except Exception as exc:  # noqa: BLE001
                    logger.exception("tool %s failed", fname)
                    out = {"error": str(exc)}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out),
                })

            # All tool results go in a single user message
            messages.append({"role": "user", "content": tool_results})

            if committed:
                return _finalize_committed(committed, state, last_retailer_table)
            continue

        # No tool-use blocks in this turn
        if committed:
            return _finalize_committed(committed, state, last_retailer_table)

        # Maybe Claude returned JSON inline in text
        inline_text = "\n".join(b.text for b in text_blocks if b.text).strip()
        parsed = _try_parse_json(inline_text)
        if parsed and parsed.get("appliance_changes"):
            return _finalize_committed(parsed, state, last_retailer_table)

        # Nudge it to use the tools
        messages.append({
            "role": "user",
            "content": "Please proceed by calling the tools (simulate_appliance_change → compare_retailers → commit_scenario). Do not respond in plain text.",
        })
        continue

    logger.warning("scenario hit MAX_TURNS=%d without commit", MAX_TURNS)
    return _finalize_committed(committed, state, last_retailer_table) if committed else None


def _finalize_committed(
    committed: Dict[str, Any],
    state: Dict[str, Any],
    retailer_table: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Attach load curves + retailer comparison to the committed payload."""
    sim_history: List[Dict[str, Any]] = state.get("sim_history", [])
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

    working = state.get("working_curves") or {}
    shifted = _aggregate_appliance_curves(working)
    committed["shifted_curve"] = [round(v, 3) for v in shifted]

    if retailer_table:
        committed["retailer_comparison"] = retailer_table
    return committed


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
    """Generate N scenarios in parallel via thread pool."""
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    shape = compute_shape_metrics(baseline_curve, annual_kwh)

    total_kwh = sum(baseline_curve) * 0.5
    appliance_share: Dict[str, float] = {}
    for name, curve in appliance_curves.items():
        appliance_share[name] = (sum(curve) * 0.5) / total_kwh if total_kwh > 0 else 0.0

    avoid_themes: List[str] = []
    scenarios: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=min(count, 3)) as pool:
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
                    if on_scenario_done is not None:
                        try:
                            on_scenario_done(result)
                        except Exception:  # noqa: BLE001
                            logger.exception("on_scenario_done callback raised for scenario %d", idx)
                else:
                    logger.warning("scenario %d returned no committed payload (result=%s)", idx, bool(result))
            except Exception as exc:  # noqa: BLE001
                logger.exception("scenario %d failed: %s", idx, exc)

    if not scenarios:
        raise RuntimeError("All scenario generations failed")

    scenarios.sort(key=lambda s: s.get("savings_annual_low", 0), reverse=True)
    for i, s in enumerate(scenarios, start=1):
        s["rank"] = i

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
