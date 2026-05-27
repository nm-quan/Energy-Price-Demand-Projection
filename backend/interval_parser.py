"""
Parse uploaded CSV interval data into a normalised list of {timestamp, kwh} dicts.

Supported formats
-----------------
1. Simple two-column: datetime/timestamp col + kwh OR kw column.
2. NEM12-style flat: header row with 'datetime'/'timestamp' + 'kwh'/'kw'.
3. NEM12 record-type format: rows starting with 200 (site), 300 (readings), 900 (end).
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import List

logger = logging.getLogger("interval_parser")


# ── Datetime parsing ──────────────────────────────────────────────────────────

_DT_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%Y%m%d%H%M%S",
    "%Y%m%d %H%M%S",
]


def _parse_dt(s: str) -> datetime:
    s = s.strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    raise ValueError(f"Cannot parse datetime: {s!r}")


# ── NEM12 record-type parser ──────────────────────────────────────────────────

def _parse_nem12(lines: List[str]) -> List[dict]:
    """
    Parse NEM12 record-type format.
    200 record: NMI description
    300 record: date YYYYMMDD + up to 48 interval values + quality flags
    900 record: end of file
    """
    results: List[dict] = []
    current_date: datetime | None = None
    interval_length = 30  # minutes; default for NEM12

    for raw in lines:
        parts = raw.strip().split(",")
        if not parts:
            continue
        rec_type = parts[0].strip()

        if rec_type == "200":
            # 200,NMI,NMIConfig,RegisterID,NMISuffix,MDMDataStreamIdentifier,MeterSerialNumber,UOM,IntervalLength,NextScheduledReadDate
            try:
                interval_length = int(parts[8]) if len(parts) > 8 and parts[8].strip().isdigit() else 30
            except (IndexError, ValueError):
                interval_length = 30

        elif rec_type == "300":
            # 300,YYYYMMDD,v1,v2,...,vN,QualityMethod,ReasonCode,ReasonDescription,UpdateDateTime,MSATSLoadDateTime
            if len(parts) < 3:
                continue
            try:
                current_date = datetime.strptime(parts[1].strip(), "%Y%m%d")
            except ValueError:
                continue

            # Values are parts[2] through parts[2 + intervals - 1]
            intervals_per_day = 1440 // interval_length
            for i in range(intervals_per_day):
                idx = 2 + i
                if idx >= len(parts):
                    break
                raw_val = parts[idx].strip()
                try:
                    kwh = float(raw_val)
                except ValueError:
                    continue
                ts = current_date + timedelta(minutes=interval_length * i)
                results.append({"timestamp": ts.isoformat(), "kwh": kwh})

    return results


# ── Main parser ───────────────────────────────────────────────────────────────

def parse_interval_csv(file_content: bytes) -> List[dict]:
    """
    Parse CSV bytes into a list of {timestamp: ISO string, kwh: float}.
    Auto-detects format. Returns records sorted by timestamp.
    """
    text = file_content.decode("utf-8", errors="replace").strip()
    lines = text.splitlines()

    if not lines:
        return []

    # ── Check for NEM12 record-type format ──────────────────────────────────
    first_token = lines[0].split(",")[0].strip()
    if first_token == "100":
        logger.info("Detected NEM12 record-type format")
        return sorted(_parse_nem12(lines), key=lambda r: r["timestamp"])

    # ── CSV with header row ──────────────────────────────────────────────────
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

    # Identify timestamp column
    ts_col = None
    for candidate in ("datetime", "timestamp", "date_time", "interval_start", "time"):
        if candidate in fieldnames:
            ts_col = candidate
            break
    if ts_col is None and fieldnames:
        ts_col = fieldnames[0]  # fallback: first column

    # Identify value column — prefer kwh, then kw
    val_col = None
    val_is_kw = False
    for candidate in ("kwh", "kw_h", "energy_kwh", "kwh_30min"):
        if candidate in fieldnames:
            val_col = candidate
            val_is_kw = False
            break
    if val_col is None:
        for candidate in ("kw", "kw_avg", "demand_kw", "power_kw", "demand"):
            if candidate in fieldnames:
                val_col = candidate
                val_is_kw = True
                break
    if val_col is None:
        # Try second column as value
        if len(fieldnames) >= 2:
            val_col = fieldnames[1]
            # Guess kW vs kWh from column name
            val_is_kw = "kw" in fieldnames[1] and "kwh" not in fieldnames[1]

    results: List[dict] = []
    orig_fields = [f.strip() for f in (reader.fieldnames or [])]
    ts_col_orig = orig_fields[fieldnames.index(ts_col)] if ts_col else None
    val_col_orig = orig_fields[fieldnames.index(val_col)] if val_col else None

    for row in rows:
        # Use original field names for lookup (DictReader preserves them)
        ts_raw = row.get(ts_col_orig) or row.get(ts_col) or ""
        val_raw = row.get(val_col_orig) or row.get(val_col) or ""
        ts_raw = ts_raw.strip()
        val_raw = val_raw.strip()
        if not ts_raw or not val_raw:
            continue
        try:
            dt = _parse_dt(ts_raw)
            value = float(val_raw)
        except (ValueError, TypeError):
            continue

        kwh = value * 0.5 if val_is_kw else value  # kW * 0.5h = kWh
        results.append({"timestamp": dt.isoformat(), "kwh": kwh})

    results.sort(key=lambda r: r["timestamp"])
    logger.info("Parsed %d interval records", len(results))
    return results


# ── Analytics helpers ─────────────────────────────────────────────────────────

def build_typical_weekday(intervals: List[dict]) -> List[float]:
    """
    Compute the average weekday profile (48 half-hourly kW values).
    Uses Mon-Fri data. Falls back to all days if no weekday data.
    """
    buckets: dict[int, list] = defaultdict(list)

    for rec in intervals:
        try:
            dt = datetime.fromisoformat(rec["timestamp"])
        except ValueError:
            continue
        if dt.weekday() < 5:  # Mon-Fri
            bucket = (dt.hour * 60 + dt.minute) // 30
            if 0 <= bucket < 48:
                # Convert kWh per 30-min to kW
                buckets[bucket].append(rec["kwh"] * 2.0)

    if not buckets:
        # Fallback: use all days
        for rec in intervals:
            try:
                dt = datetime.fromisoformat(rec["timestamp"])
            except ValueError:
                continue
            bucket = (dt.hour * 60 + dt.minute) // 30
            if 0 <= bucket < 48:
                buckets[bucket].append(rec["kwh"] * 2.0)

    profile = []
    for b in range(48):
        vals = buckets.get(b, [])
        profile.append(round(sum(vals) / len(vals), 4) if vals else 0.0)
    return profile


def compute_interval_stats(intervals: List[dict]) -> dict:
    """
    Returns:
        annual_kwh   : float — extrapolated to 365 days
        peak_kw      : float — maximum half-hourly kW
        load_factor  : float — avg_kw / peak_kw
        date_range   : {start: ISO, end: ISO}
    """
    if not intervals:
        return {
            "annual_kwh": 0.0,
            "peak_kw": 0.0,
            "load_factor": 0.0,
            "date_range": {"start": "", "end": ""},
        }

    total_kwh = sum(r["kwh"] for r in intervals)
    peak_kw = max(r["kwh"] * 2.0 for r in intervals)  # kWh → kW

    timestamps = sorted(r["timestamp"] for r in intervals)
    start_dt = datetime.fromisoformat(timestamps[0])
    end_dt = datetime.fromisoformat(timestamps[-1])

    # Estimate actual data span in days
    span_days = max((end_dt - start_dt).total_seconds() / 86400.0, 1.0)
    annual_kwh = total_kwh * (365.0 / span_days)

    n = len(intervals)
    avg_kw = (total_kwh / n) * 2.0 if n > 0 else 0.0
    load_factor = round(avg_kw / peak_kw, 4) if peak_kw > 0 else 0.0

    return {
        "annual_kwh": round(annual_kwh, 2),
        "peak_kw": round(peak_kw, 3),
        "load_factor": load_factor,
        "date_range": {"start": timestamps[0], "end": timestamps[-1]},
    }
