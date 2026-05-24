"""
Synthetic historical readings — one year of half-hourly data per meter.

Used by the dashboard timeframe selector:
  - 24h  → today (or most recent)
  - month → last 30 days, daily mean
  - year  → last 365 days, weekly mean

Variance model:
  base = appliance-sum profile (scaled to meter.annual_kwh)
  weekday_factor: weekends 0.65× (cafes quieter, except espresso peaks similar)
  seasonal_factor: summer 1.15× (HVAC), winter 1.05× (hot water), shoulder 1.0×
  noise: ±5% gaussian
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from seed_data import meter_baseline_shape


def _season_factor(day_of_year: int) -> float:
    # Australia: summer ~Dec-Feb (354-60), shoulder Mar-May & Sep-Nov, winter Jun-Aug (152-243)
    if 152 <= day_of_year <= 243:
        return 1.05  # winter
    if day_of_year >= 354 or day_of_year <= 60:
        return 1.15  # summer
    return 1.0


def _weekday_factor(weekday: int) -> float:
    # 0=Mon, 5=Sat, 6=Sun. Cafes busier weekends → flat 0.95-1.05
    return [1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 0.85][weekday]


def generate_year(meter: Dict, end: datetime = None, days: int = 365, seed: int = None) -> List[Tuple[datetime, float]]:
    """Returns [(ts, kw), ...] of half-hourly readings for one meter."""
    if end is None:
        end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if seed is None:
        seed = int(meter["id"][-3:]) if meter["id"][-3:].isdigit() else 7
    rng = random.Random(seed)
    base = meter_baseline_shape(meter)  # 48 buckets, weekday typical
    start = end - timedelta(days=days)
    out: List[Tuple[datetime, float]] = []
    cur = start
    while cur < end:
        doy = cur.timetuple().tm_yday
        wf = _weekday_factor(cur.weekday())
        sf = _season_factor(doy)
        for bucket in range(48):
            ts = cur + timedelta(minutes=30 * bucket)
            kw_base = base[bucket]
            noise = 1.0 + rng.gauss(0, 0.05)
            kw = max(0.0, kw_base * wf * sf * noise)
            out.append((ts, round(kw, 4)))
        cur = cur + timedelta(days=1)
    return out


def aggregate(readings: List[Tuple[datetime, float]], grain: str) -> List[Dict]:
    """
    grain ∈ {'halfhour','daily','weekly','monthly'}.
    Returns [{ts: iso, kw_avg: float, kw_peak: float, kwh: float}, ...].
    """
    if not readings:
        return []
    if grain == "halfhour":
        return [
            {"ts": ts.isoformat(), "kw_avg": kw, "kw_peak": kw, "kwh": round(kw * 0.5, 3)}
            for ts, kw in readings
        ]

    buckets: Dict[str, Dict] = {}
    for ts, kw in readings:
        if grain == "daily":
            key = ts.date().isoformat()
            label_ts = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        elif grain == "weekly":
            iso_year, iso_week, _ = ts.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            monday = ts - timedelta(days=ts.weekday())
            label_ts = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # monthly
            key = f"{ts.year}-{ts.month:02d}"
            label_ts = ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        b = buckets.setdefault(key, {"label_ts": label_ts, "sum": 0.0, "peak": 0.0, "kwh": 0.0, "n": 0})
        b["sum"] += kw
        b["peak"] = max(b["peak"], kw)
        b["kwh"] += kw * 0.5
        b["n"] += 1

    out = []
    for key, b in sorted(buckets.items(), key=lambda kv: kv[1]["label_ts"]):
        out.append({
            "ts": b["label_ts"].isoformat(),
            "kw_avg": round(b["sum"] / max(b["n"], 1), 3),
            "kw_peak": round(b["peak"], 3),
            "kwh": round(b["kwh"], 2),
        })
    return out


def synthesize_for_range(meter: Dict, range_key: str) -> Dict:
    """
    range_key:
      '24h'   → 48 half-hour points of the most recent day
      'month' → 30 daily aggregates
      'year'  → 52 weekly aggregates (≈ 1 year)
    """
    if range_key == "24h":
        readings = generate_year(meter, days=2)[-48:]
        return {
            "range": "24h",
            "grain": "halfhour",
            "points": aggregate(readings, "halfhour"),
        }
    if range_key == "month":
        readings = generate_year(meter, days=30)
        return {
            "range": "month",
            "grain": "daily",
            "points": aggregate(readings, "daily"),
        }
    if range_key == "year":
        readings = generate_year(meter, days=365)
        return {
            "range": "year",
            "grain": "weekly",
            "points": aggregate(readings, "weekly"),
        }
    raise ValueError(f"unknown range: {range_key}")
