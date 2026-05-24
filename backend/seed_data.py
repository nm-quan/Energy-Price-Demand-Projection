"""
Seed data for Load Shape Lab — cafe-chain portfolio.

The meter-level load shape is composed as a SUM of appliance-level profiles.
Each appliance has a 48-bucket (30-min) kW profile. Shiftable appliances also
expose a `block` describing the user-facing moveable component:
  { start: bucket, duration: buckets, power: kW }

Moving the block from default_start to new_start:
  shape[default_start : default_start+duration] -= power
  shape[new_start : new_start+duration]         += power

baseline_meter_shape = sum_over_appliances(scaled appliance.profile)
where the scale factor matches the meter's target annual_kwh.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional

# ─── Distribution-zone TOU windows (weekday) ─────────────────────────────────
TOU_ZONES: Dict[str, Dict[str, Any]] = {
    "Citipower (VIC)": {
        "code": "citipower",
        "state": "VIC",
        "peak": [(30, 42)],
        "shoulder": [(14, 30), (42, 44)],
    },
    "Ausgrid (NSW)": {
        "code": "ausgrid",
        "state": "NSW",
        "peak": [(28, 40)],
        "shoulder": [(14, 28), (40, 44)],
    },
    "Energex (QLD)": {
        "code": "energex",
        "state": "QLD",
        "peak": [(32, 40)],
        "shoulder": [(14, 32), (40, 44)],
    },
    "SA Power Networks (SA)": {
        "code": "sapn",
        "state": "SA",
        "peak": [(12, 20), (30, 48), (0, 2)],
        "shoulder": [(20, 30)],
    },
}


def classify_bucket(zone_code: str, bucket: int) -> str:
    zone = next((z for z in TOU_ZONES.values() if z["code"] == zone_code), None)
    if not zone:
        return "offpeak"
    for a, b in zone["peak"]:
        if a <= bucket < b:
            return "peak"
    for a, b in zone["shoulder"]:
        if a <= bucket < b:
            return "shoulder"
    return "offpeak"


# ─── Appliance-level profiles for the CAFE archetype ─────────────────────────
# Designed so the sum approximates ~60 kWh/day = ~21,900 kWh/yr for a baseline cafe.
# Each profile is 48 entries (kW per 30-min bucket).

def _z(n: int) -> List[float]:
    return [0.0] * n


def _block(profile: List[float], start: int, duration: int, power: float) -> List[float]:
    out = profile[:]
    for i in range(start, min(start + duration, 48)):
        out[i] += power
    return out


# Fridges — 0.7 kW continuous baseline + small defrost spike at 03:00
_FRIDGES = [0.7] * 48
_FRIDGES = _block(_FRIDGES, 6, 1, 0.3)  # 03:00 defrost +0.3 kW

# Espresso machine — idle ~0, spikes during open hours 07:00–15:30
_ESPRESSO = (
    _z(14)
    + [0.6, 1.2, 2.1, 1.8, 1.9, 1.5, 1.0, 1.6, 1.9, 2.0, 1.4, 1.0, 0.8, 1.0, 1.2, 1.4, 0.6, 0.4]
    + _z(16)
)

# Ovens — food prep 07:30–14:00
_OVENS = (
    _z(15)
    + [1.2, 2.6, 2.9, 2.2, 1.4, 1.8, 1.0, 0.7, 0.4, 0.3, 0.2, 0.2, 0.1]
    + _z(20)
)

# HVAC — cooling tracks midday peak 09:00–17:00 (defined as a baseline curve,
# the pre-cool shift block is described separately on the appliance entry)
_HVAC = (
    _z(16)
    + [0.4, 0.8, 1.2, 1.6, 2.0, 2.3, 2.4, 2.5, 2.4, 2.2, 2.0, 1.7, 1.3, 0.9, 0.5, 0.3, 0.1]
    + _z(15)
)

# Lighting — open hours 06:00–18:00 at 0.6 kW
_LIGHTING = _z(12) + [0.6] * 24 + _z(12)

# Dishwasher — single cycle 16:30–17:30 (buckets 33–34) at 3.0 kW
_DISHWASHER = _z(48)
_DISHWASHER = _block(_DISHWASHER, 33, 2, 3.0)

# Hot water — overnight reheat 23:30–04:00 at 2.4 kW
_HOT_WATER = _z(48)
_HOT_WATER = _block(_HOT_WATER, 47, 1, 2.4)
_HOT_WATER = _block(_HOT_WATER, 0, 8, 2.4)

# Misc (POS, fans, AV) — 0.2 kW during open hours
_MISC = _z(13) + [0.2] * 22 + _z(13)


CAFE_APPLIANCES: List[Dict[str, Any]] = [
    {
        "id": "fridges",
        "name": "Fridges (3 units)",
        "color": "#64748b",
        "profile": _FRIDGES,
        "always_on": True,
        "note": "Continuous baseline 24/7 — refrigeration cannot be switched off",
    },
    {
        "id": "espresso",
        "name": "Espresso machine",
        "color": "#f59e0b",
        "profile": _ESPRESSO,
        "always_on": False,
        "note": "Idle then spikes during service",
    },
    {
        "id": "ovens",
        "name": "Ovens",
        "color": "#dc2626",
        "profile": _OVENS,
        "always_on": False,
        "note": "On during food prep 07:30–14:00",
    },
    {
        "id": "hvac",
        "name": "HVAC",
        "color": "#0ea5e9",
        "profile": _HVAC,
        "always_on": False,
        "note": "Cooling tracks midday peak 09:00–17:00",
    },
    {
        "id": "lighting",
        "name": "Lighting",
        "color": "#eab308",
        "profile": _LIGHTING,
        "always_on": False,
        "note": "Tied to trading hours",
    },
    {
        "id": "dishwasher",
        "name": "Dishwasher",
        "color": "#10b981",
        "profile": _DISHWASHER,
        "always_on": False,
        "note": "Timer-controlled cycle 16:30–17:30",
    },
    {
        "id": "hot-water",
        "name": "Hot water tank",
        "color": "#8b5cf6",
        "profile": _HOT_WATER,
        "always_on": False,
        "note": "Overnight reheat 23:30–04:00",
    },
    {
        "id": "misc",
        "name": "Misc (POS, fans)",
        "color": "#ec4899",
        "profile": _MISC,
        "always_on": False,
        "note": "Always-on when trading",
    },
]


# Baseline cafe daily kWh (un-scaled) — used to derive a per-meter scale factor
def _appliance_daily_kwh(profile: List[float]) -> float:
    return sum(max(v, 0.0) for v in profile) * 0.5


_CAFE_BASE_DAILY_KWH = sum(_appliance_daily_kwh(a["profile"]) for a in CAFE_APPLIANCES)


ARCHETYPE_APPLIANCES: Dict[str, List[Dict[str, Any]]] = {
    "cafe": CAFE_APPLIANCES,
}


def appliance_scale(archetype: str, target_annual_kwh: float) -> float:
    """Return the multiplicative scale factor so the sum of appliance profiles
    matches a meter's target annual kWh."""
    base_daily = {"cafe": _CAFE_BASE_DAILY_KWH}.get(archetype, _CAFE_BASE_DAILY_KWH)
    target_daily = target_annual_kwh / 365.0
    if base_daily <= 0:
        return 1.0
    return target_daily / base_daily


# ─── Pre-loaded portfolio — a 10-site cafe chain ─────────────────────────────
# Same brand, mixed states, varying turnover.
SAMPLE_METERS: List[Dict[str, Any]] = [
    {
        "id": "MTR-001", "nmi": "6102345671", "nickname": "Brunswick East",
        "archetype": "cafe", "zone_code": "citipower", "zone_name": "Citipower (VIC)",
        "state": "VIC", "annual_kwh": 24800,
        "current_plan_id": "plan-agl-residential-vic",
        "current_plan_label": "AGL Standing Offer · Small Business",
        "monthly_spend": [620, 590, 575, 560, 575, 670, 700, 715, 670, 620, 605, 645],
    },
    {
        "id": "MTR-002", "nmi": "6102345672", "nickname": "Fitzroy North",
        "archetype": "cafe", "zone_code": "citipower", "zone_name": "Citipower (VIC)",
        "state": "VIC", "annual_kwh": 22650,
        "current_plan_id": "plan-agl-residential-vic",
        "current_plan_label": "AGL Standing Offer · Small Business",
        "monthly_spend": [565, 545, 530, 515, 530, 615, 645, 660, 615, 570, 555, 590],
    },
    {
        "id": "MTR-003", "nmi": "6102345673", "nickname": "Carlton",
        "archetype": "cafe", "zone_code": "citipower", "zone_name": "Citipower (VIC)",
        "state": "VIC", "annual_kwh": 26900,
        "current_plan_id": "plan-momentum-smile",
        "current_plan_label": "Momentum Smile Business",
        "monthly_spend": [675, 645, 625, 610, 625, 730, 765, 780, 730, 680, 660, 700],
    },
    {
        "id": "MTR-004", "nmi": "4304567674", "nickname": "Newtown",
        "archetype": "cafe", "zone_code": "ausgrid", "zone_name": "Ausgrid (NSW)",
        "state": "NSW", "annual_kwh": 28200,
        "current_plan_id": "plan-origin-business-saver",
        "current_plan_label": "Origin Business Saver · NSW",
        "monthly_spend": [715, 685, 665, 650, 665, 770, 805, 820, 770, 720, 700, 735],
    },
    {
        "id": "MTR-005", "nmi": "4304567675", "nickname": "Surry Hills",
        "archetype": "cafe", "zone_code": "ausgrid", "zone_name": "Ausgrid (NSW)",
        "state": "NSW", "annual_kwh": 31400,
        "current_plan_id": "plan-origin-business-saver",
        "current_plan_label": "Origin Business Saver · NSW",
        "monthly_spend": [790, 755, 735, 720, 735, 855, 895, 910, 855, 800, 775, 825],
    },
    {
        "id": "MTR-006", "nmi": "4304567676", "nickname": "Bondi Junction",
        "archetype": "cafe", "zone_code": "ausgrid", "zone_name": "Ausgrid (NSW)",
        "state": "NSW", "annual_kwh": 19850,
        "current_plan_id": "plan-energy-australia-flexi",
        "current_plan_label": "EnergyAustralia Flexi · NSW",
        "monthly_spend": [500, 475, 460, 450, 460, 535, 560, 570, 535, 500, 485, 515],
    },
    {
        "id": "MTR-007", "nmi": "3008765677", "nickname": "Fortitude Valley",
        "archetype": "cafe", "zone_code": "energex", "zone_name": "Energex (QLD)",
        "state": "QLD", "annual_kwh": 23500,
        "current_plan_id": "plan-energy-australia-flexi",
        "current_plan_label": "EnergyAustralia Flexi · QLD",
        "monthly_spend": [590, 565, 550, 535, 550, 635, 665, 680, 635, 595, 575, 615],
    },
    {
        "id": "MTR-008", "nmi": "3008765678", "nickname": "South Bank",
        "archetype": "cafe", "zone_code": "energex", "zone_name": "Energex (QLD)",
        "state": "QLD", "annual_kwh": 21100,
        "current_plan_id": "plan-energy-australia-flexi",
        "current_plan_label": "EnergyAustralia Flexi · QLD",
        "monthly_spend": [530, 510, 495, 480, 495, 570, 600, 610, 570, 535, 520, 555],
    },
    {
        "id": "MTR-009", "nmi": "2008889679", "nickname": "North Adelaide",
        "archetype": "cafe", "zone_code": "sapn", "zone_name": "SA Power Networks (SA)",
        "state": "SA", "annual_kwh": 18750,
        "current_plan_id": "plan-alinta-business-flex",
        "current_plan_label": "Alinta Business Flex · SA",
        "monthly_spend": [475, 455, 440, 430, 440, 510, 535, 545, 510, 480, 465, 495],
    },
    {
        "id": "MTR-010", "nmi": "2008889680", "nickname": "Glenelg",
        "archetype": "cafe", "zone_code": "sapn", "zone_name": "SA Power Networks (SA)",
        "state": "SA", "annual_kwh": 16400,
        "current_plan_id": "plan-alinta-business-flex",
        "current_plan_label": "Alinta Business Flex · SA",
        "monthly_spend": [415, 395, 385, 375, 385, 445, 470, 475, 445, 420, 405, 430],
    },
]


# ─── Retailer plans (modeled on AER CDR public dataset) ─────────────────────
SAMPLE_PLANS: List[Dict[str, Any]] = [
    {"id": "plan-agl-residential-vic", "retailer": "AGL", "name": "Standing Offer · Small Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.0945, "peak_rate": 0.4287, "shoulder_rate": 0.2854, "offpeak_rate": 0.1925, "flat_rate": None, "tags": ["standing-offer"], "fragility": "No conditional discount", "source": "AER CDR public dataset (AGL)"},
    {"id": "plan-agl-solar-savers-vic", "retailer": "AGL", "name": "Solar Savers Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.1825, "peak_rate": 0.3895, "shoulder_rate": 0.2410, "offpeak_rate": 0.1685, "flat_rate": None, "tags": ["solar-friendly"], "fragility": "Better feed-in but higher supply", "source": "AER CDR public dataset (AGL)"},
    {"id": "plan-origin-business-saver", "retailer": "Origin", "name": "Business Saver", "plan_type": "TOU", "state": "NSW", "supply_charge": 1.2230, "peak_rate": 0.4520, "shoulder_rate": 0.2740, "offpeak_rate": 0.1810, "flat_rate": None, "tags": ["conditional-discount"], "fragility": "5% pay-on-time discount", "source": "AER CDR public dataset (Origin)"},
    {"id": "plan-origin-go-flat", "retailer": "Origin", "name": "Go Flat Business", "plan_type": "Flat", "state": "NSW", "supply_charge": 1.1450, "peak_rate": None, "shoulder_rate": None, "offpeak_rate": None, "flat_rate": 0.3245, "tags": ["simple"], "fragility": "No exit fee", "source": "AER CDR public dataset (Origin)"},
    {"id": "plan-energy-australia-flexi", "retailer": "EnergyAustralia", "name": "Flexi Business", "plan_type": "TOU", "state": "QLD", "supply_charge": 1.0820, "peak_rate": 0.4118, "shoulder_rate": 0.2615, "offpeak_rate": 0.1745, "flat_rate": None, "tags": ["smart-meter-required"], "fragility": "Requires Type-4 meter", "source": "AER CDR public dataset (EnergyAustralia)"},
    {"id": "plan-energy-australia-total", "retailer": "EnergyAustralia", "name": "Total Business", "plan_type": "Flat", "state": "QLD", "supply_charge": 1.0240, "peak_rate": None, "shoulder_rate": None, "offpeak_rate": None, "flat_rate": 0.3380, "tags": ["simple"], "fragility": "12-month benefit period", "source": "AER CDR public dataset (EnergyAustralia)"},
    {"id": "plan-red-energy-living", "retailer": "Red Energy", "name": "Living Energy Saver Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.0510, "peak_rate": 0.4012, "shoulder_rate": 0.2520, "offpeak_rate": 0.1820, "flat_rate": None, "tags": ["qantas-points"], "fragility": "Bonus Qantas points", "source": "AER CDR public dataset (Red Energy)"},
    {"id": "plan-alinta-business-flex", "retailer": "Alinta Energy", "name": "Business Flex", "plan_type": "TOU", "state": "SA", "supply_charge": 1.3450, "peak_rate": 0.4895, "shoulder_rate": 0.3120, "offpeak_rate": 0.2010, "flat_rate": None, "tags": ["no-exit-fee"], "fragility": "Standing-offer fallback rate is steep", "source": "AER CDR public dataset (Alinta)"},
    {"id": "plan-momentum-smile", "retailer": "Momentum Energy", "name": "Smile Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.0985, "peak_rate": 0.3978, "shoulder_rate": 0.2440, "offpeak_rate": 0.1695, "flat_rate": None, "tags": ["hydro-tas-backed"], "fragility": "100% Australian-owned", "source": "AER CDR public dataset (Momentum)"},
    {"id": "plan-powershop-business", "retailer": "Powershop", "name": "Powershop Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.0720, "peak_rate": 0.3850, "shoulder_rate": 0.2380, "offpeak_rate": 0.1610, "flat_rate": None, "tags": ["100-renewable"], "fragility": "Pack-based prepay model", "source": "AER CDR public dataset (Powershop)"},
    {"id": "plan-ovo-business", "retailer": "OVO Energy", "name": "OVO Business", "plan_type": "TOU", "state": "VIC", "supply_charge": 1.0290, "peak_rate": 0.3680, "shoulder_rate": 0.2280, "offpeak_rate": 0.1520, "flat_rate": None, "tags": ["carbon-neutral"], "fragility": "Smaller retailer, less brand presence", "source": "AER CDR public dataset (OVO)"},
    {"id": "plan-simply-energy-business", "retailer": "Simply Energy", "name": "Business Plus", "plan_type": "Demand", "state": "VIC", "supply_charge": 0.8950, "peak_rate": 0.3120, "shoulder_rate": 0.2240, "offpeak_rate": 0.1450, "flat_rate": None, "demand_charge_per_kw_month": 18.50, "tags": ["demand-tariff"], "fragility": "Penalises peak kW — flatten your curve", "source": "AER CDR public dataset (Simply Energy)"},
]


# ─── Real NEM spot price overlay (averaged) ──────────────────────────────────
NEM_SPOT_AVG_VIC: List[float] = [
    72, 71, 68, 65, 62, 60, 58, 56, 55, 54, 56, 62,
    74, 86, 94, 102, 108, 110, 112, 110, 105, 98, 92, 88,
    86, 88, 92, 98, 110, 130, 158, 192,
    218, 238, 246, 232, 198, 162, 132, 108,
    94, 84, 78, 74, 72, 70, 68, 66,
]


# ─── Helpers exported for cost engine ────────────────────────────────────────

def meter_appliances(meter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return appliances scaled to this meter's annual kWh."""
    apps = ARCHETYPE_APPLIANCES.get(meter["archetype"], [])
    k = appliance_scale(meter["archetype"], meter["annual_kwh"])
    out = []
    for a in apps:
        scaled_profile = [round(v * k, 4) for v in a["profile"]]
        out.append({
            "id": a["id"],
            "name": a["name"],
            "color": a["color"],
            "always_on": a.get("always_on", False),
            "note": a.get("note", ""),
            "profile": scaled_profile,
            "daily_kwh": round(sum(scaled_profile) * 0.5, 2),
        })
    return out


def meter_baseline_shape(meter: Dict[str, Any]) -> List[float]:
    apps = meter_appliances(meter)
    out = [0.0] * 48
    for a in apps:
        for i, v in enumerate(a["profile"]):
            out[i] += v
    return [round(v, 4) for v in out]


def meter_active_shape(meter: Dict[str, Any], appliance_scales: Dict[str, float]) -> List[float]:
    """Shape with each appliance scaled by its multiplier (default 1.0)."""
    apps = meter_appliances(meter)
    out = [0.0] * 48
    for a in apps:
        scale = appliance_scales.get(a["id"], 1.0)
        if scale <= 0:
            continue
        for i, v in enumerate(a["profile"]):
            out[i] += v * scale
    return [round(v, 4) for v in out]
