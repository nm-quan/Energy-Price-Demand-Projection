"""
Claude-powered dynamic scenario generator.

Calls the Claude API (claude-sonnet-4-6) with tool use. Claude receives
client context (load profile + tariff) and returns a ranked list of
bespoke load-shift scenarios. For each scenario Claude calls the
`run_scenario` tool to get real savings figures from scenario_engine.py,
then emits a final JSON response listing the scenarios sorted by savings.

If ANTHROPIC_API_KEY is missing, callers should fall back to the legacy
hardcoded scenarios.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic

from models import Tariff
from scenario_engine import run_scenarios

logger = logging.getLogger("scenario_claude")

MODEL_NAME = "claude-sonnet-4-6"
MAX_TURNS = 8
MAX_TOKENS = 2048


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


TOOLS: List[Dict[str, Any]] = [
    {
        "name": "run_scenario",
        "description": (
            "Run a load-shift scenario and get actual annual savings figures. "
            "Call this tool once per scenario you want to test, with the operational "
            "parameters that describe the change. Returns billing_defensible / indicative "
            "savings figures and the shifted half-hourly load curve."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario_name": {
                    "type": "string",
                    "description": "Short title for the scenario (e.g. 'Pre-cool HVAC before 3pm peak')."
                },
                "scenario_type": {
                    "type": "string",
                    "enum": [
                        "pre_cool_hvac",
                        "battery_dispatch",
                        "demand_cap",
                        "time_shift",
                        "custom",
                    ],
                    "description": "Which load-shift math to apply.",
                },
                "parameters": {
                    "type": "object",
                    "description": (
                        "Numeric parameters to pass to the shift function. Keys depend on scenario_type:\n"
                        "- pre_cool_hvac: hvac_fraction (0.1-0.8), pre_cool_start, pre_cool_end, peak_start, peak_end, efficiency_gain (0.5-1.0)\n"
                        "- battery_dispatch: capacity_kwh (10-500), power_kw (5-250), charge_start, charge_end, discharge_start, discharge_end, round_trip_efficiency (0.7-1.0)\n"
                        "- demand_cap: target_kw, shed_fraction (0-1)\n"
                        "- time_shift: shift_kw, from_start, from_end, to_start, to_end\n"
                        "Bucket numbers are 0-47 representing half-hourly slots from midnight."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": "1-2 sentences explaining the operational change in plain language.",
                },
            },
            "required": ["scenario_name", "scenario_type", "parameters", "rationale"],
        },
    }
]


SYSTEM_PROMPT = """You are an energy savings analyst. Given a client's load profile and tariff, generate a ranked list of practical load-shift scenarios ordered by annual savings (highest first). Be creative and specific to the business type.

Generate exactly 3 scenarios. Each scenario must be operationally realistic — something the client can actually implement.

For each scenario you must:
1. Call the `run_scenario` tool with name, type, parameters, and rationale to get actual savings figures.
2. After running all 3 scenarios, return a SINGLE final JSON object (no markdown, no commentary) with this exact shape:

{
  "scenarios": [
    {
      "rank": 1,
      "name": "<from run_scenario call>",
      "rationale": "<from run_scenario call>",
      "type": "<from run_scenario call>",
      "parameters": {...},
      "shifted_curve": [<48 floats from tool result>],
      "savings": {
        "billing_defensible": {"energy": <num>, "demand": <num>, "total": <num>},
        "indicative": {"contract_low": <num>, "contract_high": <num>},
        "total_low": <num>,
        "total_high": <num>
      }
    }
  ]
}

Sort by total_low descending. Use the exact savings numbers returned by the tool. Be concise — keep rationales to 1 sentence."""


def _build_user_message(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    tariff: Tariff,
    extra_instruction: Optional[str] = None,
) -> str:
    """Render the client-context user message that Claude receives."""
    cost = baseline.get("cost_stack", {})
    shape = baseline.get("shape_metrics", {})
    load_curve = baseline.get("load_curve", [])
    rates = tariff.energy_rates
    network = tariff.network_charges
    network_fixed = (
        (network.distribution + network.transmission + network.metering) * (shape.get("annual_kwh") or 0)
        + (network.service * 365.0)
        + (tariff.supply_charge * 365.0)
    )
    msg = (
        f"Site: {client.get('name')}, {client.get('address')}\n"
        f"Site type: {client.get('site_type')}\n"
        f"Annual consumption: {shape.get('annual_kwh', 0):.0f} kWh\n"
        f"Peak demand: {shape.get('peak_kw', 0):.1f} kW\n"
        f"Load factor: {(shape.get('load_factor') or 0) * 100:.1f}%\n"
        f"Tariff: {tariff.retailer} {tariff.plan_name} ({tariff.type})\n"
        f"  - Peak rate: {rates.peak or 0:.4f} $/kWh (buckets 30–42, 3pm–9pm)\n"
        f"  - Shoulder rate: {rates.shoulder or 0:.4f} $/kWh\n"
        f"  - Off-peak rate: {rates.offpeak or 0:.4f} $/kWh\n"
        f"  - Supply charge: {tariff.supply_charge:.4f} $/day\n"
        f"  - Demand charge: {tariff.demand_charge or 0:.2f} $/kW/month\n\n"
        f"Annual cost breakdown:\n"
        f"  - Energy peak: ${cost.get('energy_peak', 0):,.0f}\n"
        f"  - Energy shoulder: ${cost.get('energy_shoulder', 0):,.0f}\n"
        f"  - Energy off-peak: ${cost.get('energy_offpeak', 0):,.0f}\n"
        f"  - Demand charge: ${cost.get('demand_charge', 0):,.0f}\n"
        f"  - Network + fixed: ${network_fixed:,.0f}\n"
        f"  - Total: ${cost.get('total_annual', 0):,.0f}\n\n"
        f"Load shape (48 half-hourly kW, midnight to midnight):\n"
        f"{', '.join(f'{v:.3f}' for v in load_curve)}\n\n"
        f"Generate 3-8 ranked scenarios. Call run_scenario for each, then return the final JSON object."
    )
    if extra_instruction:
        msg += f"\n\nAdditional broker instruction: {extra_instruction}"
    return msg


def _execute_run_scenario(
    tool_input: Dict[str, Any],
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> Dict[str, Any]:
    """Execute the scenario math for a single Claude tool call."""
    scenario_type = tool_input.get("scenario_type", "custom")
    params = tool_input.get("parameters") or {}
    if scenario_type == "custom":
        # Custom scenarios fall back to time_shift if no obvious mapping
        scenario_type = "time_shift"
    cfg = [{"type": scenario_type, "parameters": params}]
    result = run_scenarios(baseline_curve, cfg, tariff, annual_kwh)
    # Round to keep tool result payload small
    return {
        "scenario_name": tool_input.get("scenario_name"),
        "scenario_type": tool_input.get("scenario_type"),
        "rationale": tool_input.get("rationale"),
        "parameters": params,
        "shifted_curve": [round(v, 3) for v in result["shifted_curve"]],
        "savings": result["savings"],
    }


def _extract_text(content_blocks: List[Any]) -> str:
    return "".join(getattr(b, "text", "") for b in content_blocks if getattr(b, "type", None) == "text")


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return None
    # Strip optional ```json ... ``` fences
    if text.startswith("```"):
        # Remove first line and trailing fence
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Try direct
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to extract the largest JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def generate_scenarios(
    client: Dict[str, Any],
    baseline: Dict[str, Any],
    tariff: Tariff,
    annual_kwh: float,
    extra_instruction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Drive Claude through the tool-use loop and return the final structured
    scenarios payload. Raises RuntimeError if the API key is missing or the
    flow fails.
    """
    cli = _get_client()
    baseline_curve = list(baseline.get("load_curve", []))
    user_msg = _build_user_message(client, baseline, tariff, extra_instruction)
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": user_msg}]}
    ]

    tool_results_cache: Dict[str, Dict[str, Any]] = {}

    for _turn in range(MAX_TURNS):
        resp = cli.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Build assistant message echo for history
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
            tool_results: List[Dict[str, Any]] = []
            for tu in tool_use_blocks:
                if tu.name != "run_scenario":
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps({"error": f"unknown tool {tu.name}"}),
                        "is_error": True,
                    })
                    continue
                try:
                    out = _execute_run_scenario(tu.input or {}, baseline_curve, tariff, annual_kwh)
                    tool_results_cache[tu.id] = out
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(out),
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.exception("run_scenario tool execution failed")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # No more tool calls — extract final JSON from text
        final_text = _extract_text(resp.content)
        parsed = _try_parse_json(final_text)
        if parsed and isinstance(parsed.get("scenarios"), list):
            scenarios = parsed["scenarios"]
            # Drop net-cost scenarios (broker UI only wants savings)
            scenarios = [s for s in scenarios if ((s.get("savings") or {}).get("total_high", 0) > 0)]
            # Sort by total_low desc and re-rank
            scenarios.sort(key=lambda s: (s.get("savings") or {}).get("total_low", 0), reverse=True)
            for i, s in enumerate(scenarios, start=1):
                s["rank"] = i
            return {"scenarios": scenarios, "source": "claude"}

        # Fallback: assemble scenarios from cached tool outputs if Claude
        # produced no usable JSON.
        if tool_results_cache:
            scenarios = []
            for v in tool_results_cache.values():
                scenarios.append({
                    "rank": 0,
                    "name": v.get("scenario_name"),
                    "rationale": v.get("rationale"),
                    "type": v.get("scenario_type"),
                    "parameters": v.get("parameters"),
                    "shifted_curve": v.get("shifted_curve"),
                    "savings": v.get("savings"),
                })
            scenarios.sort(key=lambda s: (s.get("savings") or {}).get("total_low", 0), reverse=True)
            for i, s in enumerate(scenarios, start=1):
                s["rank"] = i
            return {"scenarios": scenarios, "source": "claude-tools-only"}

        raise RuntimeError("Claude returned no parseable scenarios")

    raise RuntimeError("Claude tool-use loop exceeded max turns")


def fallback_scenarios(
    baseline_curve: List[float],
    tariff: Tariff,
    annual_kwh: float,
) -> Dict[str, Any]:
    """Hardcoded 4-scenario fallback when Claude is unavailable."""
    presets = [
        {
            "name": "Pre-cool HVAC before peak",
            "rationale": "Cool the space before the 3pm peak so HVAC runs less during peak rates.",
            "type": "pre_cool_hvac",
            "parameters": {
                "hvac_fraction": 0.35,
                "pre_cool_start": 24,
                "pre_cool_end": 30,
                "peak_start": 30,
                "peak_end": 42,
                "efficiency_gain": 0.85,
            },
        },
        {
            "name": "50 kWh battery dispatch",
            "rationale": "Charge off-peak overnight and discharge during the 3pm–9pm peak window.",
            "type": "battery_dispatch",
            "parameters": {
                "capacity_kwh": 50.0,
                "power_kw": 25.0,
                "charge_start": 2,
                "charge_end": 14,
                "discharge_start": 30,
                "discharge_end": 42,
                "round_trip_efficiency": 0.90,
            },
        },
        {
            "name": "Peak demand cap",
            "rationale": "Hard-cap the site demand by deferring non-critical load to off-peak hours.",
            "type": "demand_cap",
            "parameters": {"target_kw": max(baseline_curve) * 0.85, "shed_fraction": 0.4},
        },
        {
            "name": "Shift dishwasher + prep to off-peak",
            "rationale": "Move ~3 kW of cleaning and prep work from the peak window to early morning.",
            "type": "time_shift",
            "parameters": {
                "shift_kw": 3.0,
                "from_start": 30,
                "from_end": 42,
                "to_start": 2,
                "to_end": 12,
            },
        },
    ]
    scenarios = []
    for preset in presets:
        result = run_scenarios(
            baseline_curve,
            [{"type": preset["type"], "parameters": preset["parameters"]}],
            tariff,
            annual_kwh,
        )
        scenarios.append({
            "rank": 0,
            "name": preset["name"],
            "rationale": preset["rationale"],
            "type": preset["type"],
            "parameters": preset["parameters"],
            "shifted_curve": [round(v, 3) for v in result["shifted_curve"]],
            "savings": result["savings"],
        })
    scenarios.sort(key=lambda s: s["savings"]["total_low"], reverse=True)
    for i, s in enumerate(scenarios, start=1):
        s["rank"] = i
    return {"scenarios": scenarios, "source": "fallback"}
