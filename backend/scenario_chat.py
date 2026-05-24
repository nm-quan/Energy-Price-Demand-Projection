"""
Claude scenario-builder chat.

Each turn → Claude returns a single JSON object:
  {
    "assistant_message": "...",
    "profile_delta": { ... fields it could newly extract ... }
  }

We merge the delta into the stored profile and return both to the frontend.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import anthropic
from pydantic import BaseModel, Field

MODEL_NAME = "claude-haiku-4-5"


_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


PROFILE_FIELDS = [
    "business_type",
    "hours",
    "sites",
    "major_loads",
    "shiftable",
    "fixed",
    "capex_budget",
    "constraints",
]

REQUIRED_FOR_OPTIMISATION = ["hours", "major_loads", "capex_budget"]


SYSTEM_PROMPT = """You are an energy-strategy assistant embedded in "Load Shape Lab", a dashboard for small Australian businesses (currently a 10-site cafe chain demo).

Your job in this conversation:
1) Have a natural, helpful exchange with the business owner about how their site operates.
2) From everything said so far, infer a structured BUSINESS PROFILE that the rest of the app will use to recommend retailer plans and load-shifts.

OUTPUT FORMAT — you MUST always respond with a single valid JSON object and nothing else. No prose before or after. The schema is:

{
  "assistant_message": "<your next reply to the user, 1-3 short sentences, conversational tone, no markdown>",
  "profile_delta": {
    "business_type":   { "value": "<string or null>",                "confidence": "high|medium|low" },
    "hours":           { "value": "<e.g. 'Tue–Sun, 7am–4pm' or null>","confidence": "high|medium|low" },
    "sites":           { "value": "<integer or null>",               "confidence": "high|medium|low" },
    "major_loads":     { "value": ["espresso","ovens",...] or null,  "confidence": "high|medium|low" },
    "shiftable":       { "value": ["Dishwasher (4 kWh, 4:30pm)",...] or null, "confidence": "high|medium|low" },
    "fixed":           { "value": ["Fridges (continuous)",...] or null,       "confidence": "high|medium|low" },
    "capex_budget":    { "value": "<e.g. '$200 max' or null>",       "confidence": "high|medium|low" },
    "constraints":     { "value": ["Staff finish 5pm",...] or null,  "confidence": "high|medium|low" }
  }
}

Only include keys in `profile_delta` for fields where you have NEW information from the latest user message (or stronger evidence than before). Fields you don't update should be OMITTED from `profile_delta`, not set to null.

Confidence rules:
- "high"   = the user stated it explicitly.
- "medium" = you inferred it from context with reasonable certainty.
- "low"    = a guess, please confirm.

Conversational rules:
- Open with a single short question if the user hasn't said much yet. Don't pile up multiple questions.
- Once `hours`, `major_loads`, and `capex_budget` are all filled, end your message with: "I have enough to run an optimisation when you're ready."
- Never include the JSON schema in your message text.
- Keep replies short — this is a sidebar chat.

Remember: output JSON ONLY. The very first character of your response MUST be `{`."""


class ChatMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class ChatRequest(BaseModel):
    meter_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    profile: Dict[str, Any] = Field(default_factory=dict)
    user_message: str


class ChatResponse(BaseModel):
    assistant_message: str
    profile: Dict[str, Any]
    profile_delta: Dict[str, Any]
    ready_for_optimisation: bool


def _extract_json(text: str) -> Dict[str, Any]:
    """Tolerant JSON parser — strips code fences or stray prose."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        # remove leading 'json\n' if any
        if s.lower().startswith("json"):
            s = s[4:]
    # Find the first { and the matching last }
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object in response: {text!r}")
    return json.loads(s[start : end + 1])


def _merge_profile(profile: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(profile)
    for field, payload in (delta or {}).items():
        if field not in PROFILE_FIELDS:
            continue
        if not isinstance(payload, dict):
            continue
        value = payload.get("value")
        conf = payload.get("confidence", "medium")
        if value in (None, "", [], {}):
            continue
        out[field] = {"value": value, "confidence": conf}
    return out


def _ready(profile: Dict[str, Any]) -> bool:
    return all(profile.get(f, {}).get("value") for f in REQUIRED_FOR_OPTIMISATION)


def run_chat(req: ChatRequest, site_context: Dict[str, Any]) -> ChatResponse:
    client = get_client()

    # Build conversation history for Claude
    sdk_messages: List[Dict[str, Any]] = []
    for m in req.messages:
        if m.role not in ("user", "assistant"):
            continue
        sdk_messages.append({"role": m.role, "content": m.content})
    sdk_messages.append({"role": "user", "content": req.user_message})

    site_blurb = (
        f"Site context:\n"
        f"- Nickname: {site_context.get('nickname')}\n"
        f"- NMI: {site_context.get('nmi')}\n"
        f"- State: {site_context.get('state')} ({site_context.get('zone_name')})\n"
        f"- Annual usage: {site_context.get('annual_kwh')} kWh\n"
        f"- Current plan: {site_context.get('current_plan_label')}\n"
        f"\nKnown profile so far (do not re-extract these unless the user contradicts): "
        f"{json.dumps({k: v.get('value') for k, v in (req.profile or {}).items()}, ensure_ascii=False)}"
    )

    system = SYSTEM_PROMPT + "\n\n" + site_blurb

    resp = client.messages.create(
        model=MODEL_NAME,
        max_tokens=800,
        system=system,
        messages=sdk_messages,
    )
    text_parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    raw = "".join(text_parts).strip()

    try:
        payload = _extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        # Fallback: treat the entire reply as the assistant_message with no delta
        return ChatResponse(
            assistant_message=raw or f"(parse error: {exc})",
            profile=req.profile,
            profile_delta={},
            ready_for_optimisation=_ready(req.profile),
        )

    assistant_msg = str(payload.get("assistant_message") or "").strip()
    delta = payload.get("profile_delta") or {}
    new_profile = _merge_profile(req.profile or {}, delta)

    return ChatResponse(
        assistant_message=assistant_msg or "Tell me more about your business and equipment.",
        profile=new_profile,
        profile_delta=delta,
        ready_for_optimisation=_ready(new_profile),
    )
