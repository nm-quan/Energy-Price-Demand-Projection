"""
Claude scenario builder — TOOL-USE edition.

Claude can:
  - adjust_appliance(id, scale)      → modify load curve on the dashboard
  - select_meters(meter_ids)         → change scope
  - run_optimization()               → return ranked plans (server invokes the in-memory rank engine)
  - set_constraint(section, bullets) → write to the constraints document
  - set_timeframe(range)             → switch dashboard graph between 24h / month / year

Each turn we loop:
  user message → claude (with tools) → if tool_use blocks → execute → return tool_result → re-call → final text.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger("loadshapelab.chat")

MODEL_NAME = "claude-haiku-4-5"

VALID_APPLIANCE_IDS = {
    "fridges", "espresso", "ovens", "hvac", "lighting", "dishwasher", "hot-water", "misc",
}
VALID_RANGES = {"24h", "month", "year"}
CONSTRAINT_SECTIONS = ["Operating", "Equipment", "Budget", "Other"]


_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


TOOLS = [
    {
        "name": "adjust_appliance",
        "description": "Change an appliance's load scale on the dashboard. scale=0 removes it, 1.0 is baseline, 2.0 doubles it. Use this when the user describes an upgrade (e.g. 'we'd add solar HW' → set hot-water to 0.2).",
        "input_schema": {
            "type": "object",
            "properties": {
                "appliance_id": {
                    "type": "string",
                    "enum": list(VALID_APPLIANCE_IDS),
                },
                "scale": {"type": "number", "minimum": 0, "maximum": 5},
            },
            "required": ["appliance_id", "scale"],
        },
    },
    {
        "name": "select_meters",
        "description": "Change which sites are in scope on the dashboard. Pass an array of meter ids like ['MTR-001','MTR-002']. Empty array means keep current selection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "meter_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["meter_ids"],
        },
    },
    {
        "name": "run_optimization",
        "description": "Run the retailer-plan optimisation on the current state and return the ranked plans + best recommendation. Use this when you have enough info, or when the user asks for a recommendation.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_constraint",
        "description": "Append or replace bullets in the constraints document under one of four sections. Use this often — every meaningful fact the user shares should turn into a bullet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "enum": CONSTRAINT_SECTIONS},
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Plain-English bullets to add. Keep each ≤120 chars.",
                },
                "mode": {"type": "string", "enum": ["append", "replace"], "default": "append"},
            },
            "required": ["section", "bullets"],
        },
    },
    {
        "name": "set_timeframe",
        "description": "Switch the dashboard graph timeframe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "range": {"type": "string", "enum": list(VALID_RANGES)},
            },
            "required": ["range"],
        },
    },
]


SYSTEM_PROMPT = """You are an energy-strategy dispatching agent embedded in Load Shape Lab — a dashboard for small Australian businesses (a 10-site cafe chain in the demo).

You can both CONVERSE with the user and CONTROL the dashboard via tools. After every meaningful user message you should:
1. Call `set_constraint` to record what you learned (one or more bullets in the right section).
2. Optionally call `adjust_appliance`, `select_meters` or `set_timeframe` if the user implies a change.
3. Reply briefly (1-3 short sentences). Don't list the schema or tool calls in your text.

When the user asks for a recommendation OR when the user says "run optimisation" / "go" — call `run_optimization`. If you have very little context, FIRST emit reasonable default constraints via `set_constraint` (e.g. "Default budget: $500", "Default goal: lowest annual cost"), then call `run_optimization`. Never refuse to optimise — generate defaults instead.

Constraint sections:
  - Operating  : hours, staff, services
  - Equipment  : appliances, capacities, age
  - Budget     : capex, payback expectations
  - Other      : preferences, ethics, future plans

Tone: friendly, concise, no markdown, no emojis."""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    meter_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    constraints_doc: Dict[str, List[str]] = Field(default_factory=dict)
    appliance_scales: Dict[str, float] = Field(default_factory=dict)
    selected_meter_ids: List[str] = Field(default_factory=list)
    timeframe: str = "24h"
    user_message: str
    auto_optimise_if_empty: bool = False


class ToolCall(BaseModel):
    name: str
    input: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    assistant_message: str
    constraints_doc: Dict[str, List[str]]
    appliance_scales: Dict[str, float]
    selected_meter_ids: List[str]
    timeframe: str
    optimisation: Optional[Dict[str, Any]] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)


def _apply_set_constraint(doc: Dict[str, List[str]], inp: Dict[str, Any]) -> Dict[str, Any]:
    section = inp.get("section")
    bullets = inp.get("bullets") or []
    mode = inp.get("mode", "append")
    if section not in CONSTRAINT_SECTIONS:
        return {"ok": False, "error": f"unknown section {section}"}
    current = doc.get(section, [])
    if mode == "replace":
        current = []
    for b in bullets:
        b = str(b).strip()
        if b and b not in current:
            current.append(b)
    doc[section] = current
    return {"ok": True, "section": section, "count": len(current)}


def _apply_adjust_appliance(scales: Dict[str, float], inp: Dict[str, Any]) -> Dict[str, Any]:
    aid = inp.get("appliance_id")
    scale = float(inp.get("scale", 1.0))
    if aid not in VALID_APPLIANCE_IDS:
        return {"ok": False, "error": f"unknown appliance {aid}"}
    scales[aid] = max(0.0, min(5.0, scale))
    return {"ok": True, "appliance_id": aid, "scale": scales[aid]}


def _apply_select_meters(state: Dict, inp: Dict[str, Any], available_ids: List[str]) -> Dict[str, Any]:
    ids = inp.get("meter_ids") or []
    ids = [i for i in ids if i in available_ids]
    if not ids:
        return {"ok": False, "error": "no valid meter ids"}
    state["selected_meter_ids"] = ids
    return {"ok": True, "selected_meter_ids": ids}


def _apply_set_timeframe(state: Dict, inp: Dict[str, Any]) -> Dict[str, Any]:
    r = inp.get("range")
    if r not in VALID_RANGES:
        return {"ok": False, "error": f"unknown range {r}"}
    state["timeframe"] = r
    return {"ok": True, "range": r}


def run_chat(req: ChatRequest, site_context: Dict[str, Any], optimise_fn, available_meter_ids: List[str]) -> ChatResponse:
    """
    optimise_fn(meter_ids, appliance_scales) -> dict (the /api/rank payload)
    """
    client = get_client()

    state: Dict[str, Any] = {
        "constraints_doc": {k: list(v) for k, v in (req.constraints_doc or {}).items()},
        "appliance_scales": dict(req.appliance_scales or {}),
        "selected_meter_ids": list(req.selected_meter_ids or [req.meter_id]),
        "timeframe": req.timeframe or "24h",
        "optimisation": None,
    }

    sdk_messages: List[Dict[str, Any]] = []
    for m in req.messages:
        if m.role in ("user", "assistant"):
            sdk_messages.append({"role": m.role, "content": m.content})
    user_msg = req.user_message
    if req.auto_optimise_if_empty:
        user_msg += "\n\n(System: please call run_optimization now. Add reasonable default constraints first if the doc is empty.)"
    sdk_messages.append({"role": "user", "content": user_msg})

    site_blurb = (
        f"\n\nSite context:\n"
        f"- Site: {site_context.get('nickname')} ({site_context.get('zone_name')}, {site_context.get('state')})\n"
        f"- NMI: {site_context.get('nmi')}\n"
        f"- Annual usage: {site_context.get('annual_kwh')} kWh\n"
        f"- Current plan: {site_context.get('current_plan_label')}\n"
        f"- Currently selected meters: {state['selected_meter_ids']}\n"
        f"- Constraints so far: {json.dumps(state['constraints_doc'], ensure_ascii=False)}\n"
        f"- Appliance scales now: {json.dumps(state['appliance_scales'], ensure_ascii=False)}"
    )
    system = SYSTEM_PROMPT + site_blurb

    tool_calls: List[ToolCall] = []
    final_text = ""
    MAX_TURNS = 5  # tool-use loop guard

    for turn in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL_NAME,
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=sdk_messages,
        )

        # Collect text + tool_use blocks
        text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        tu_blocks = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        final_text = "\n".join(t for t in text_blocks if t).strip()

        if not tu_blocks:
            break

        # Execute each tool call, then add assistant turn + tool_result turn back to messages
        assistant_blocks: List[Dict[str, Any]] = []
        for b in resp.content:
            if getattr(b, "type", None) == "text":
                assistant_blocks.append({"type": "text", "text": b.text})
            elif getattr(b, "type", None) == "tool_use":
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": b.input,
                })
        sdk_messages.append({"role": "assistant", "content": assistant_blocks})

        tool_results_block: List[Dict[str, Any]] = []
        for tu in tu_blocks:
            name = tu.name
            inp = tu.input or {}
            result: Dict[str, Any]
            if name == "set_constraint":
                result = _apply_set_constraint(state["constraints_doc"], inp)
            elif name == "adjust_appliance":
                result = _apply_adjust_appliance(state["appliance_scales"], inp)
            elif name == "select_meters":
                result = _apply_select_meters(state, inp, available_meter_ids)
            elif name == "set_timeframe":
                result = _apply_set_timeframe(state, inp)
            elif name == "run_optimization":
                opt = optimise_fn(state["selected_meter_ids"], state["appliance_scales"])
                state["optimisation"] = opt
                result = {
                    "ok": True,
                    "best": {
                        "retailer": opt["best"]["plan"]["retailer"],
                        "plan": opt["best"]["plan"]["name"],
                        "annual_cost": opt["best"]["shifted_cost"],
                    },
                    "achievable_saving": opt["achievable_saving"],
                    "n_sites": opt["n_sites"],
                }
            else:
                result = {"ok": False, "error": f"unknown tool {name}"}
            tool_calls.append(ToolCall(name=name, input=inp, result=result))
            tool_results_block.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result)[:4000],
            })
        sdk_messages.append({"role": "user", "content": tool_results_block})

        if resp.stop_reason != "tool_use":
            break

    return ChatResponse(
        assistant_message=final_text or "Got it.",
        constraints_doc=state["constraints_doc"],
        appliance_scales=state["appliance_scales"],
        selected_meter_ids=state["selected_meter_ids"],
        timeframe=state["timeframe"],
        optimisation=state["optimisation"],
        tool_calls=tool_calls,
    )
