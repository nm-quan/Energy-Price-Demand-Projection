"""Supabase client wrapper with graceful fallback if tables don't exist yet."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

logger = logging.getLogger("loadshapelab.supabase")


_client: Optional[Client] = None
_state: Dict[str, bool] = {"available": False, "checked": False}


def get_client() -> Optional[Client]:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            return None
        _client = create_client(url, key)
    return _client


def check_available(force: bool = False) -> bool:
    """Pings the scenarios table; caches result."""
    if _state["checked"] and not force:
        return _state["available"]
    cli = get_client()
    if not cli:
        _state["available"] = False
        _state["checked"] = True
        return False
    try:
        cli.table("scenarios").select("id").limit(1).execute()
        _state["available"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Supabase not ready: %s", str(exc)[:200])
        _state["available"] = False
    _state["checked"] = True
    return _state["available"]


def save_scenario(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not check_available():
        return None
    cli = get_client()
    try:
        if payload.get("id"):
            res = cli.table("scenarios").update(payload).eq("id", payload["id"]).execute()
        else:
            res = cli.table("scenarios").insert(payload).execute()
        return (res.data or [None])[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("save_scenario failed: %s", str(exc)[:200])
        return None


def list_scenarios(meter_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not check_available():
        return []
    cli = get_client()
    try:
        res = cli.table("scenarios").select("*").eq("meter_id", meter_id).order(
            "updated_at", desc=True
        ).limit(limit).execute()
        return res.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_scenarios failed: %s", str(exc)[:200])
        return []


def upsert_retailer_plans(plans: List[Dict[str, Any]]) -> int:
    """Push the in-memory seed plans into Supabase (idempotent)."""
    if not check_available():
        return 0
    cli = get_client()
    try:
        cli.table("retailer_plans").upsert(plans).execute()
        return len(plans)
    except Exception as exc:  # noqa: BLE001
        logger.warning("upsert_retailer_plans failed: %s", str(exc)[:200])
        return 0


def upsert_readings(rows: List[Dict[str, Any]]) -> int:
    """rows: [{meter_id, ts, kw}, ...]"""
    if not check_available():
        return 0
    cli = get_client()
    try:
        BATCH = 1000
        n = 0
        for i in range(0, len(rows), BATCH):
            chunk = rows[i:i + BATCH]
            cli.table("load_readings").upsert(chunk).execute()
            n += len(chunk)
        return n
    except Exception as exc:  # noqa: BLE001
        logger.warning("upsert_readings failed: %s", str(exc)[:200])
        return 0
