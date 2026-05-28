"""
Generative block engine — AI composes typed blocks, server resolves data.

Flow:
  User prompt + full site data
       ↓
  Claude → compose_analysis tool call → [block, block, ...]
       ↓
  Server resolves each block (runs simulations, fetches data)
       ↓
  Yields resolved blocks as SSE events
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

import anthropic

from models import Tariff
from baseline_engine import compute_shape_metrics, compute_annual_cost_components
from scenario_claude import _run_simulation, _aggregate, compute_retailer_comparison

logger = logging.getLogger("ai_engine")

MODEL_NAME = "claude-sonnet-4-6"
MAX_TOKENS = 4096

PLAN_KEYWORDS = [
    "full site", "reduction plan", "top 3", "top three",
    "just make it cheaper", "make it cheaper",
    "peak hour reduction", "all appliances",
]

# Server-side simulation parameters — used when building multi_scenario blocks
# without relying on the AI to pick them.
DEFAULT_CHANGES: Dict[str, Dict[str, Any]] = {
    "Fridges":    {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 12],  "from_scale": 0.35},
    "HVAC":       {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 16],  "from_scale": 0.55},
    "Dishwasher": {"action": "shift_window", "from_window": [30, 42], "to_window": [2, 16],  "from_scale": 0.85},
    "Hot Water":  {"action": "shift_window", "from_window": [30, 42], "to_window": [0, 14],  "from_scale": 0.75},
    "Ovens":      {"action": "shift_window", "from_window": [24, 42], "to_window": [6, 18],  "from_scale": 0.50},
    "Espresso":   {"action": "shift_window", "from_window": [30, 42], "to_window": [16, 30], "from_scale": 0.50},
    "Lighting":   {"action": "set_off",      "from_window": [30, 42], "from_scale": 0.25},
    "Misc":       {"action": "set_off",      "from_window": [30, 42], "from_scale": 0.20},
}


# ── Tool schema ───────────────────────────────────────────────────────────────

COMPOSE_TOOL: Dict[str, Any] = {
    "name": "compose_analysis",
    "description": (
        "Compose an energy analysis response as an ordered array of typed blocks. "
        "Choose exactly the blocks needed to answer the user's request — no more, no less. "
        "Be opinionated. Tell the broker what matters and why, with specific numbers from the data."
    ),
    "input_schema": {
        "type": "object",
        "required": ["blocks"],
        "properties": {
            "blocks": {
                "type": "array",
                "description": "Ordered list of content blocks to render in sequence",
                "items": {
                    "type": "object",
                    "required": ["type"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "headline", "text", "kpi_row",
                                "load_chart", "scenario", "multi_scenario",
                                "retailer_table", "recommendation",
                            ],
                        },
                        # headline / text
                        "text":    {"type": "string"},
                        "variant": {
                            "type": "string",
                            "enum": ["body", "callout", "warning"],
                            "description": "Visual style for text blocks",
                        },
                        # kpi_row
                        "metrics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "value": {"type": "string"},
                                    "unit":  {"type": "string"},
                                    "delta": {"type": "string"},
                                    "dir":   {"type": "string", "enum": ["up", "down", "neutral"]},
                                },
                            },
                        },
                        # load_chart
                        "title":          {"type": "string"},
                        "appliance":      {"type": "string"},
                        "highlight_peak": {"type": "boolean"},
                        # scenario
                        "action":       {"type": "string", "enum": ["shift_window", "set_off", "scale"]},
                        "from_window":  {"type": "array", "items": {"type": "integer"}},
                        "to_window":    {"type": "array", "items": {"type": "integer"}},
                        "from_scale":   {"type": "number"},
                        "scale_factor": {"type": "number"},
                        "name":         {"type": "string"},
                        "rationale":    {"type": "string"},
                        # multi_scenario — ordered list of changes applied sequentially
                        "changes": {
                            "type": "array",
                            "description": "2–4 appliance changes applied sequentially to a shared load curve",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "appliance":    {"type": "string"},
                                    "action":       {"type": "string", "enum": ["shift_window", "set_off", "scale"]},
                                    "from_window":  {"type": "array", "items": {"type": "integer"}},
                                    "to_window":    {"type": "array", "items": {"type": "integer"}},
                                    "from_scale":   {"type": "number"},
                                    "scale_factor": {"type": "number"},
                                },
                            },
                        },
                        # recommendation
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                        "levers":   {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        },
    },
}


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert energy broker analyst for commercial sites in Victoria, Australia.

You receive a site's full energy data and a user request, then compose a structured analysis as typed content blocks.

=== YOUR ROLE ===
You are opinionated and specific. Look at the real numbers and tell the broker:
- What the biggest cost driver is at this exact site (use actual kWh and $ figures)
- What the most actionable change is with the specific saving
- What the retailer negotiation angle is with real rate differences
- Why your recommendation matters for this specific business

Never be generic. Always reference actual data from the site provided.

=== BLOCK TYPES ===

headline       One bold sentence — the key finding or direct answer. Required first block.

text           Body text. variant: "body" (default), "callout" (highlight box), "warning" (amber)

kpi_row        2–4 metrics side by side.
               metrics: [{ label, value, unit, delta, dir }]
               dir: "down"=green (cost/usage reduction good), "up"=red (bad), "neutral"=grey
               delta example: "-$119/yr", "+35% peak reduction", "19.3→18.9 c/kWh"

load_chart     Site load curve. Set appliance= to overlay that appliance's curve.
               title: short description of what the chart shows

scenario       A SINGLE-appliance load-shifting change. Server runs ALL math — you just specify:
               appliance: exact name from the list
               action: shift_window | set_off | scale
               from_window: [start, end] buckets to reduce. 0=midnight, 30=3pm, 42=9pm
               to_window: [start, end] buckets to receive load (shift_window only)
               from_scale: fraction 0.0–1.0 to move or reduce
               scale_factor: multiplier for scale action (e.g. 0.85)
               name: "Appliance Strategy — Description" (5–8 words, specific)
               rationale: 2 sentences — what changes and why it saves money

multi_scenario A COMBINED multi-appliance plan applied to a shared load curve.
               changes: array of 2–4 items, each with {appliance, action, from_window, to_window, from_scale, scale_factor}
               Server applies them SEQUENTIALLY — each change operates on the already-modified curve.
               Combined saving is greater than the sum of individual savings.
               name: "Full Site Peak Reduction — HVAC + Fridges + Dishwasher"
               rationale: paragraph explaining the combined strategy and total saving potential
               Order changes highest-impact first. Do NOT repeat appliances.

retailer_table Shows all retailer costs. Include after every scenario or multi_scenario.

recommendation Priority action with 3 levers containing real $ numbers.
               priority: "high" | "medium" | "low"
               levers: 3 specific talking points with actual figures from the data

=== WHEN TO USE WHICH BLOCKS ===

Specific appliance ("cut the fridge", "shift dishwasher", "pre-cool HVAC"):
  headline → text(callout, why this appliance) → load_chart(appliance=X) → scenario → retailer_table → recommendation

Multi-appliance plan ("full site reduction plan", "top 3 appliance saves", "peak hour reduction package", "just make it cheaper"):
  headline → kpi_row → multi_scenario (3 changes: top 3 by TOU-peak kWh) → retailer_table → recommendation

Usage question ("what uses most", "show load"):
  headline → kpi_row → load_chart (no appliance overlay)

Retailer question ("which retailer", "switch supplier"):
  headline → retailer_table → recommendation

Quick question ("what's my load factor", "when is peak"):
  headline → kpi_row (2–3 metrics)

Follow-up on a single appliance ("now show HVAC", "what about hot water"):
  headline → scenario → recommendation

=== SCENARIO PARAMETER GUIDE ===
shift_window (moves load from peak to off-peak):
  Fridges:    from_window=[30,42]  to_window=[0,12]   from_scale=0.35
  HVAC:       from_window=[30,42]  to_window=[0,16]   from_scale=0.55
  Dishwasher: from_window=[30,42]  to_window=[2,16]   from_scale=0.85
  Hot Water:  from_window=[30,42]  to_window=[0,14]   from_scale=0.75
  Ovens:      from_window=[24,42]  to_window=[6,18]   from_scale=0.50
  Espresso:   from_window=[30,42]  to_window=[16,30]  from_scale=0.50

set_off (reduces load without redistribution):
  Lighting:   from_window=[30,42]  from_scale=0.25
  Misc:       from_window=[30,42]  from_scale=0.20

scale (efficiency upgrade, applies to whole curve):
  LED retrofit → Lighting, scale_factor=0.40

=== NATURAL LANGUAGE MAPPING ===
"cut the fridge" → appliance=Fridges, shift_window
"shift dishwasher" → appliance=Dishwasher, shift_window
"HVAC" / "air con" → appliance=HVAC, shift_window
"hot water" → appliance=Hot Water, shift_window
"lighting" / "dim" → appliance=Lighting, set_off
"cheapest" / "just make it cheaper" / "no upfront" → multi_scenario (top 3 by TOU-peak kWh)
"fastest payback" → appliance with most TOU-peak kWh
"show load" / "usage" → load_chart, no scenario
"retailer" / "switch" → retailer_table + recommendation

=== SCENARIO NAMING RULES ===
MUST include appliance AND strategy:
  ✓ "Fridges Overnight Pre-Cool — 35% Peak Shift"
  ✓ "HVAC Pre-Cool Strategy — Shift 55% to Off-Peak"
  ✓ "Dishwasher Fully Rescheduled to 1–8am"
  ✗ "Energy Optimisation Plan"
  ✗ "Load Shifting Scenario"

Always be specific. Use actual numbers from the data in your rationale and levers.

=== MANDATORY ROUTING (OVERRIDES ALL OTHER RULES) ===
If the user request contains ANY of: "full site", "reduction plan", "top 3", "top three",
"just make it cheaper", "make it cheaper", "peak hour reduction", "all appliances" —
you MUST use type="multi_scenario". NEVER type="scenario" for these requests.
When using multi_scenario:
  → changes array MUST have exactly 3 items.
  → Appliance names MUST match EXACTLY from "Available appliances:" (case-sensitive).
  → Order highest TOU-peak kWh first."""


# ── Message builder ───────────────────────────────────────────────────────────

def _appliance_row(name: str, curve: List[float]) -> str:
    def kwh(r: range) -> float:
        return sum(curve[b] * 0.5 for b in r if b < len(curve))
    offpk = kwh(range(0, 16))
    mid   = kwh(range(16, 30))
    peak  = kwh(range(30, 42))
    eve   = kwh(range(42, 48))
    total = offpk + mid + peak + eve
    pct   = peak / total * 100 if total > 0 else 0
    peak_b = max(range(len(curve)), key=lambda b: curve[b])
    peak_h = f"{peak_b // 2:02d}:{(peak_b % 2) * 30:02d}"
    return (
        f"  {name:<14} off-pk {offpk:5.1f} | mid {mid:5.1f} | "
        f"TOU-peak {peak:5.1f} kWh ({pct:3.0f}%) | eve {eve:4.1f} | peaks at {peak_h}"
    )


def _build_messages(
    client: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    prompt: str,
    history: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    rates = tariff.energy_rates

    def tou_kwh(n: str) -> float:
        c = appliance_curves.get(n, [])
        return sum(c[b] * 0.5 for b in range(30, 42) if b < len(c))

    sorted_apps = sorted(appliance_curves, key=tou_kwh, reverse=True)
    rows = "\n".join(_appliance_row(n, appliance_curves[n]) for n in sorted_apps)
    top3_names = sorted_apps[:min(3, len(sorted_apps))]

    site_ctx = (
        f"Site: {client.get('name')} ({client.get('site_type', 'commercial')})\n"
        f"Annual: {annual_kwh:,.0f} kWh"
        f" · Peak demand: {shape.get('peak_kw', 0):.1f} kW"
        f" · Load factor: {shape.get('load_factor', 0) * 100:.0f}%"
        f" · {shape.get('peak_coincidence', 0) * 100:.0f}% of load in TOU peak (3–9pm)\n"
        f"Tariff: {tariff.retailer} {tariff.plan_name}"
        f" — peak ${rates.peak or 0:.3f} | shoulder ${rates.shoulder or 0:.3f}"
        f" | off-peak ${rates.offpeak or 0:.3f}/kWh\n"
        f"\nAppliance breakdown (sorted by TOU-peak kWh):\n"
        f"  {'Appliance':<14} off-pk        mid          TOU-peak             eve    peak hour\n"
        f"{rows}\n"
        f"\nTop 3 appliances by TOU-peak kWh (use these for multi_scenario): {', '.join(top3_names)}\n"
        f"Available appliances: {', '.join(appliance_curves.keys())}\n"
    )

    is_plan = any(kw in prompt.lower() for kw in PLAN_KEYWORDS)

    if is_plan:
        plan_hint = (
            f"\n\nThis is a combined plan request. The server will automatically run the "
            f"multi-appliance simulation for {', '.join(top3_names)}. "
            f"Generate: headline + kpi_row (2–3 current-state metrics) + recommendation. "
            f"Do NOT generate scenario or multi_scenario blocks — they will be added automatically."
        )
        user_content = f"{site_ctx}\nUser request: {prompt}{plan_hint}"
    else:
        user_content = f"{site_ctx}\nUser request: {prompt}"

    messages: List[Dict[str, Any]] = list(history)
    messages.append({"role": "user", "content": user_content})
    return messages


# ── AI call (sync — runs in thread) ──────────────────────────────────────────

def _call_ai(
    client: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    prompt: str,
    history: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    cli = anthropic.Anthropic(api_key=api_key)
    messages = _build_messages(client, tariff, annual_kwh, shape, appliance_curves, prompt, history)

    resp = cli.messages.create(
        model=MODEL_NAME,
        system=SYSTEM_PROMPT,
        messages=messages,
        tools=[COMPOSE_TOOL],
        tool_choice={"type": "tool", "name": "compose_analysis"},
        max_tokens=MAX_TOKENS,
    )

    tu = next((b for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
    if not tu:
        logger.warning("compose_analysis: no tool call in response")
        return [{"type": "text", "text": "Analysis could not be generated. Please try again.", "variant": "warning"}]

    blocks = list(tu.input.get("blocks") or [])
    logger.info("compose_analysis: %d blocks for prompt=%r", len(blocks), prompt[:60])
    return blocks


# ── Plan-request post-processor ───────────────────────────────────────────────

def _coerce_plan_blocks(
    blocks: List[Dict[str, Any]],
    top3: List[str],
) -> List[Dict[str, Any]]:
    """For plan requests: strip any AI-generated scenario/multi_scenario blocks and
    inject a server-built multi_scenario + retailer_table at the right position.
    The AI is only responsible for headline, kpi_row, recommendation text."""
    changes = []
    for app in top3:
        key = next((k for k in DEFAULT_CHANGES if k.lower() == app.lower()), None)
        params = DEFAULT_CHANGES[key] if key else {
            "action": "shift_window", "from_window": [30, 42], "to_window": [0, 14], "from_scale": 0.40,
        }
        changes.append({"appliance": app, **params})

    ms_block = {
        "type": "multi_scenario",
        "name": f"Full Site Peak Reduction — {' + '.join(top3)}",
        "rationale": (
            f"This combined plan targets your top {len(top3)} TOU-peak appliances "
            f"({', '.join(top3)}) and shifts their afternoon load to overnight. "
            "Each change is applied sequentially to the already-modified curve, so the "
            "combined saving exceeds any single shift alone."
        ),
        "changes": changes,
    }

    # Strip any scenario / multi_scenario / retailer_table the AI may have generated
    clean = [b for b in blocks if b.get("type") not in ("scenario", "multi_scenario", "retailer_table")]

    # Insert after the last kpi_row or headline block
    insert_pos = -1
    for i, b in enumerate(clean):
        if b.get("type") in ("kpi_row", "headline"):
            insert_pos = i

    clean.insert(insert_pos + 1, {"type": "retailer_table"})
    clean.insert(insert_pos + 1, ms_block)
    return clean


# ── Multi-scenario helpers ────────────────────────────────────────────────────

def _apply_change(
    working: Dict[str, List[float]],
    change: Dict[str, Any],
) -> tuple:
    """Apply one appliance change to the shared working dict.
    Returns (before_curve, after_curve) or (None, None) if appliance not found.
    Mutates working[appliance] in-place."""
    target = change.get("appliance", "")
    if target not in working:
        match = next((k for k in working if k.lower() == target.lower()), None)
        if not match:
            logger.warning("_apply_change: appliance '%s' not found", target)
            return None, None
        target = match

    before = list(working[target])
    after  = list(before)
    action = change.get("action", "shift_window")
    fs     = min(1.0, max(0.0, float(change.get("from_scale", 0.5))))

    if action == "shift_window":
        fw = change.get("from_window") or [30, 42]
        tw = change.get("to_window")   or [0, 14]
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
        fw = change.get("from_window") or [30, 42]
        f_s, f_e = int(fw[0]), int(fw[1])
        for b in range(max(0, f_s), min(48, f_e)):
            after[b] = before[b] * (1.0 - fs)
    elif action == "scale":
        sf = float(change.get("scale_factor", 1.0))
        after = [v * sf for v in before]

    working[target] = after
    return before, after


def _resolve_multi_scenario_block(
    block: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> Dict[str, Any]:
    working = {k: list(v) for k, v in appliance_curves.items()}
    appliance_changes: List[Dict[str, Any]] = []
    total_peak_shifted = 0.0

    for change in block.get("changes", []):
        before, after = _apply_change(working, change)
        if before is None:
            continue
        peak_b = sum(before[b] * 0.5 for b in range(30, 42))
        peak_a = sum(after[b]  * 0.5 for b in range(30, 42))
        total_peak_shifted += peak_b - peak_a
        appliance_changes.append({
            "appliance":    change.get("appliance", ""),
            "action":       change.get("action", "shift_window"),
            "before_curve": [round(v, 3) for v in before],
            "after_curve":  [round(v, 3) for v in after],
        })

    if not appliance_changes:
        return {**block, "resolved": True, "error": "No changes could be applied"}

    aggregate_before = _aggregate({k: list(v) for k, v in appliance_curves.items()})
    final_total  = _aggregate(working)
    baseline_sum = sum(aggregate_before)
    new_annual   = annual_kwh * (sum(final_total) / baseline_sum) if baseline_sum > 0 else annual_kwh
    base_cost    = compute_annual_cost_components(aggregate_before, tariff, annual_kwh)["grand_total"]
    new_cost     = compute_annual_cost_components(final_total, tariff, new_annual)["grand_total"]
    retailer     = compute_retailer_comparison(final_total, new_annual, tariff)
    saving_low   = base_cost - new_cost
    saving_high  = saving_low + retailer.get("max_saving_vs_current", 0)

    return {
        **block,
        "resolved":           True,
        "appliance_changes":  appliance_changes,
        "total_curve_before": [round(v, 3) for v in aggregate_before],
        "total_curve_after":  [round(v, 3) for v in final_total],
        "savings_annual_low":  max(0.0, saving_low),
        "savings_annual_high": max(0.0, saving_high),
        "peak_kwh_shifted":    round(total_peak_shifted, 2),
        "new_annual_kwh":      round(new_annual, 1),
        "retailer_comparison": retailer,
    }


# ── Block resolver (sync — runs in thread) ────────────────────────────────────

def _resolve_block(
    block: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> Dict[str, Any]:
    btype = block.get("type")

    if btype == "multi_scenario":
        return _resolve_multi_scenario_block(block, appliance_curves, baseline_curve, tariff, annual_kwh)

    if btype == "scenario":
        sim = _run_simulation(appliance_curves, baseline_curve, tariff, annual_kwh, block)
        if sim is None:
            return {**block, "resolved": True, "error": f"Could not simulate appliance '{block.get('appliance')}'"}
        retailer = compute_retailer_comparison(sim["total_curve_after"], sim["new_annual_kwh"], tariff)
        saving_low  = sim["annual_saving_on_current_tariff"]
        saving_high = saving_low + retailer.get("max_saving_vs_current", 0)
        return {
            **block,
            "resolved": True,
            "before_curve":       sim["before_curve"],
            "after_curve":        sim["after_curve"],
            "total_curve_before": [round(v, 3) for v in baseline_curve],
            "total_curve_after":  sim["total_curve_after"],
            "savings_annual_low":  max(0.0, saving_low),
            "savings_annual_high": max(0.0, saving_high),
            "peak_kwh_shifted":    sim["peak_kwh_shifted"],
            "new_annual_kwh":      sim["new_annual_kwh"],
            "retailer_comparison": retailer,
        }

    elif btype == "load_chart":
        app_name = block.get("appliance")
        overlay  = None
        if app_name:
            match = next((k for k in appliance_curves if k.lower() == app_name.lower()), None)
            if match:
                overlay = [round(v, 3) for v in appliance_curves[match]]
        return {
            **block,
            "resolved": True,
            "series":  [round(v, 3) for v in baseline_curve],
            "overlay": overlay,
        }

    elif btype == "retailer_table":
        retailer = compute_retailer_comparison(baseline_curve, annual_kwh, tariff)
        return {**block, "resolved": True, "retailer_comparison": retailer}

    return {**block, "resolved": True}


# ── SSE streaming (async generator) ──────────────────────────────────────────

async def stream_analysis(
    client: Dict[str, Any],
    appliance_curves: Dict[str, List[float]],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
    shape: Dict[str, Any],
    prompt: str,
    history: List[Dict[str, str]],
) -> AsyncGenerator[str, None]:
    is_plan = any(kw in prompt.lower() for kw in PLAN_KEYWORDS)

    if is_plan:
        def _tou(n: str) -> float:
            c = appliance_curves.get(n, [])
            return sum(c[b] * 0.5 for b in range(30, 42) if b < len(c))
        top3 = sorted(appliance_curves, key=_tou, reverse=True)[:3]

    try:
        blocks = await asyncio.to_thread(
            _call_ai,
            client, tariff, annual_kwh, shape, appliance_curves, prompt, history,
        )
    except Exception as exc:
        logger.exception("AI call failed for prompt=%r", prompt[:60])
        yield f"data: {json.dumps({'type': 'error', 'text': str(exc)[:300]})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if is_plan:
        blocks = _coerce_plan_blocks(blocks, top3)
        logger.info("plan coercion applied: top3=%s, block_types=%s",
                    top3, [b.get("type") for b in blocks])

    for block in blocks:
        try:
            resolved = await asyncio.to_thread(
                _resolve_block,
                block, appliance_curves, baseline_curve, tariff, annual_kwh,
            )
            yield f"data: {json.dumps(resolved)}\n\n"
        except Exception as exc:
            logger.exception("Block resolution failed: type=%s", block.get("type"))
            err_msg = f"Block error ({block.get('type')}): {exc}"
            yield f"data: {json.dumps({'type': 'error', 'text': err_msg})}\n\n"

    yield "data: [DONE]\n\n"
