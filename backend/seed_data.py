"""
Seed data for Load Shape Lab.

48 half-hourly buckets per day (0..47). Bucket i covers minutes [i*30, (i+1)*30).
Bucket 0 = 00:00–00:30, bucket 18 = 09:00–09:30, etc.

All TOU windows are expressed as half-hour bucket ranges (start_inclusive, end_exclusive).
"""
from __future__ import annotations

from typing import List, Dict, Any

# ─── Distribution-zone TOU windows (weekday) ─────────────────────────────────
# Buckets are half-hour indices; end is exclusive.
# Approximate published windows for residential / small business TOU tariffs.
TOU_ZONES: Dict[str, Dict[str, Any]] = {
    "Citipower (VIC)": {
        "code": "citipower",
        "state": "VIC",
        # Peak 15:00–21:00, Shoulder 07:00–15:00 & 21:00–22:00, Off-peak otherwise
        "peak": [(30, 42)],
        "shoulder": [(14, 30), (42, 44)],
    },
    "Ausgrid (NSW)": {
        "code": "ausgrid",
        "state": "NSW",
        # Peak 14:00–20:00, Shoulder 07:00–14:00 & 20:00–22:00
        "peak": [(28, 40)],
        "shoulder": [(14, 28), (40, 44)],
    },
    "Energex (QLD)": {
        "code": "energex",
        "state": "QLD",
        # Peak 16:00–20:00, Shoulder 07:00–16:00 & 20:00–22:00
        "peak": [(32, 40)],
        "shoulder": [(14, 32), (40, 44)],
    },
    "SA Power Networks (SA)": {
        "code": "sapn",
        "state": "SA",
        # Peak 06:00–10:00 & 15:00–01:00, Shoulder 10:00–15:00
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


# ─── Archetype load curves (kW per 30-min bucket, typical weekday) ───────────
# Hand-built from public commercial load research (AusGrid, Sustainability Vic).
# 48 entries each.
def _smooth(base: List[float]) -> List[float]:
    """Light triangular smoothing."""
    out = []
    for i in range(48):
        a = base[(i - 1) % 48]
        b = base[i]
        c = base[(i + 1) % 48]
        out.append(round((a + 2 * b + c) / 4, 2))
    return out


ARCHETYPE_CURVES: Dict[str, List[float]] = {
    # Cafe: opens 6am, breakfast & lunch peaks, closes 4pm
    "cafe": _smooth([
        1.2, 1.1, 1.0, 1.0, 1.0, 1.0, 1.1, 1.1,    # 00:00–04:00
        1.2, 1.3, 1.5, 2.5, 5.5, 7.0, 8.2, 8.5,    # 04:00–08:00 (breakfast rush)
        9.0, 8.5, 7.8, 7.2, 7.5, 8.0, 9.5, 11.0,   # 08:00–12:00 (lunch ramp)
        12.5, 11.5, 9.8, 8.0, 6.5, 5.0, 4.2, 3.5,  # 12:00–16:00 (closing)
        2.8, 2.2, 1.8, 1.6, 1.5, 1.4, 1.4, 1.3,    # 16:00–20:00
        1.3, 1.3, 1.3, 1.2, 1.2, 1.2, 1.2, 1.2,    # 20:00–24:00
    ]),
    # Pub / bar: gentle daytime, big evening peak
    "pub": _smooth([
        3.5, 3.2, 2.8, 2.5, 2.3, 2.2, 2.2, 2.2,    # 00:00–04:00
        2.3, 2.5, 3.0, 3.8, 5.0, 6.5, 7.5, 8.0,    # 04:00–08:00
        8.5, 9.0, 9.5, 10.0, 11.5, 13.0, 14.5, 16.0,  # 08:00–12:00 (lunch)
        17.0, 16.5, 15.5, 14.0, 13.5, 14.0, 15.5, 17.5,  # 12:00–16:00
        20.0, 23.0, 26.0, 28.0, 29.0, 28.5, 27.0, 24.5,  # 16:00–20:00 (dinner)
        21.0, 17.0, 12.0, 8.0, 6.0, 5.0, 4.5, 4.0,    # 20:00–24:00
    ]),
    # Retail store: 9–6 trading, HVAC dominant
    "retail": _smooth([
        2.0, 1.8, 1.6, 1.5, 1.4, 1.4, 1.4, 1.5,    # 00:00–04:00
        1.6, 1.8, 2.5, 4.0, 6.5, 9.0, 11.0, 12.5,  # 04:00–08:00 (HVAC ramp)
        14.0, 15.0, 15.5, 15.8, 16.0, 16.2, 16.5, 17.0,  # 08:00–12:00
        17.8, 18.5, 18.8, 18.5, 18.0, 17.5, 16.8, 16.0,  # 12:00–16:00
        15.2, 14.0, 11.0, 7.5, 5.0, 3.5, 2.8, 2.5,    # 16:00–20:00
        2.3, 2.2, 2.1, 2.0, 2.0, 1.9, 1.9, 1.9,    # 20:00–24:00
    ]),
    # Small office: 8–6, weekday only
    "office": _smooth([
        1.5, 1.4, 1.3, 1.2, 1.2, 1.2, 1.3, 1.4,    # 00:00–04:00
        1.5, 1.7, 2.5, 4.5, 7.0, 9.5, 11.0, 12.0,  # 04:00–08:00
        12.5, 12.8, 13.0, 13.2, 13.5, 13.5, 13.2, 13.0,  # 08:00–12:00
        13.5, 14.0, 14.2, 14.0, 13.5, 13.0, 12.5, 11.5,  # 12:00–16:00
        10.0, 7.5, 5.0, 3.5, 2.8, 2.3, 2.0, 1.8,    # 16:00–20:00
        1.7, 1.6, 1.6, 1.5, 1.5, 1.5, 1.5, 1.5,    # 20:00–24:00
    ]),
    # Warehouse / cold-store: 24/7 base + day shift
    "warehouse": _smooth([
        18.0, 17.5, 17.0, 16.8, 16.5, 16.5, 16.8, 17.0,  # 00:00–04:00
        17.5, 18.0, 19.0, 20.5, 23.0, 26.0, 28.0, 29.0,  # 04:00–08:00
        30.0, 30.5, 31.0, 31.2, 31.5, 31.8, 31.5, 31.0,  # 08:00–12:00
        31.5, 32.0, 32.0, 31.5, 31.0, 30.5, 30.0, 29.5,  # 12:00–16:00
        28.5, 26.5, 24.0, 22.0, 20.5, 19.5, 19.0, 18.5,  # 16:00–20:00
        18.3, 18.2, 18.0, 18.0, 17.8, 17.8, 17.8, 18.0,  # 20:00–24:00
    ]),
}


# ─── Pre-loaded sample meters ────────────────────────────────────────────────
SAMPLE_METERS: List[Dict[str, Any]] = [
    {
        "id": "MTR-001",
        "nmi": "6102345678",
        "nickname": "Brunswick East Cafe",
        "archetype": "cafe",
        "zone_code": "citipower",
        "zone_name": "Citipower (VIC)",
        "state": "VIC",
        "annual_kwh": 32850,
        "current_plan_id": "plan-agl-residential-vic",
        "current_plan_label": "AGL Standing Offer · VIC",
        "monthly_spend": [820, 780, 760, 740, 760, 880, 920, 940, 880, 820, 800, 850],
    },
    {
        "id": "MTR-002",
        "nmi": "4304567890",
        "nickname": "Newtown Public House",
        "archetype": "pub",
        "zone_code": "ausgrid",
        "zone_name": "Ausgrid (NSW)",
        "state": "NSW",
        "annual_kwh": 91250,
        "current_plan_id": "plan-origin-business-saver",
        "current_plan_label": "Origin Business Saver · NSW",
        "monthly_spend": [2150, 2050, 1980, 1920, 1980, 2280, 2400, 2450, 2280, 2150, 2080, 2200],
    },
    {
        "id": "MTR-003",
        "nmi": "3008765432",
        "nickname": "Fortitude Valley Boutique",
        "archetype": "retail",
        "zone_code": "energex",
        "zone_name": "Energex (QLD)",
        "state": "QLD",
        "annual_kwh": 54750,
        "current_plan_id": "plan-energy-australia-flexi",
        "current_plan_label": "EnergyAustralia Flexi · QLD",
        "monthly_spend": [1320, 1280, 1200, 1140, 1180, 1380, 1480, 1520, 1420, 1300, 1240, 1340],
    },
    {
        "id": "MTR-004",
        "nmi": "6203334445",
        "nickname": "Collins St Architects",
        "archetype": "office",
        "zone_code": "citipower",
        "zone_name": "Citipower (VIC)",
        "state": "VIC",
        "annual_kwh": 41500,
        "current_plan_id": "plan-red-energy-living",
        "current_plan_label": "Red Energy Living Energy Saver",
        "monthly_spend": [980, 940, 910, 880, 910, 1040, 1100, 1120, 1050, 980, 950, 990],
    },
    {
        "id": "MTR-005",
        "nmi": "2008889990",
        "nickname": "Adelaide Cold Storage",
        "archetype": "warehouse",
        "zone_code": "sapn",
        "zone_name": "SA Power Networks (SA)",
        "state": "SA",
        "annual_kwh": 222650,
        "current_plan_id": "plan-alinta-business-flex",
        "current_plan_label": "Alinta Business Flex · SA",
        "monthly_spend": [5400, 5180, 5020, 4860, 5020, 5680, 6020, 6180, 5780, 5400, 5180, 5500],
    },
]


# ─── Shift library — assets the user can drag onto the canvas ────────────────
# duration is the number of half-hour buckets (1 = 30 min). power is kW draw.
SHIFT_ASSETS: Dict[str, List[Dict[str, Any]]] = {
    "cafe": [
        {"id": "dishwasher", "label": "Dishwasher cycles", "power": 2.5, "duration": 2, "default_start": 36, "feasibility": "easy", "hardware_cost": 50, "note": "Timer-controlled commercial dishwasher"},
        {"id": "hot-water", "label": "Hot water heating", "power": 6.0, "duration": 4, "default_start": 12, "feasibility": "easy", "hardware_cost": 80, "note": "Tank reheat — must finish by 06:00"},
        {"id": "hvac-precool", "label": "HVAC pre-cool", "power": 4.0, "duration": 4, "default_start": 16, "feasibility": "medium", "hardware_cost": 350, "note": "Smart thermostat schedule"},
        {"id": "fridge-defrost", "label": "Display fridge defrost", "power": 1.5, "duration": 1, "default_start": 6, "feasibility": "easy", "hardware_cost": 0, "note": "Programmable defrost cycle"},
        {"id": "oven-prep", "label": "Oven pre-heat", "power": 5.5, "duration": 1, "default_start": 11, "feasibility": "hard", "hardware_cost": 200, "note": "Requires staff rota change"},
    ],
    "pub": [
        {"id": "glasswasher", "label": "Glasswasher batch", "power": 3.0, "duration": 2, "default_start": 44, "feasibility": "easy", "hardware_cost": 50, "note": "Run after close"},
        {"id": "cellar-cooling", "label": "Cellar cooling", "power": 4.5, "duration": 4, "default_start": 32, "feasibility": "medium", "hardware_cost": 400, "note": "Pre-cool before peak"},
        {"id": "ice-machine", "label": "Ice machine", "power": 2.0, "duration": 6, "default_start": 0, "feasibility": "easy", "hardware_cost": 60, "note": "Make ice overnight"},
        {"id": "kitchen-prep", "label": "Kitchen pre-heat", "power": 7.0, "duration": 1, "default_start": 36, "feasibility": "hard", "hardware_cost": 0, "note": "Staff schedule change"},
        {"id": "hvac-precool-pub", "label": "HVAC pre-cool", "power": 6.0, "duration": 4, "default_start": 24, "feasibility": "medium", "hardware_cost": 400, "note": "Pre-cool before evening rush"},
    ],
    "retail": [
        {"id": "hvac-precool-retail", "label": "HVAC pre-cool", "power": 8.0, "duration": 4, "default_start": 16, "feasibility": "medium", "hardware_cost": 500, "note": "Cool before shoulder peak"},
        {"id": "lighting-warmup", "label": "Lighting warmup", "power": 2.5, "duration": 1, "default_start": 16, "feasibility": "easy", "hardware_cost": 80, "note": "Timer relay"},
        {"id": "stockroom-fans", "label": "Stockroom ventilation", "power": 1.8, "duration": 4, "default_start": 0, "feasibility": "easy", "hardware_cost": 50, "note": "Overnight ventilation"},
        {"id": "delivery-charge", "label": "Delivery van charge", "power": 7.0, "duration": 6, "default_start": 0, "feasibility": "medium", "hardware_cost": 0, "note": "EV charger scheduling"},
    ],
    "office": [
        {"id": "hvac-precool-office", "label": "HVAC pre-cool", "power": 6.5, "duration": 4, "default_start": 14, "feasibility": "medium", "hardware_cost": 450, "note": "BMS scheduling"},
        {"id": "server-batch", "label": "Server batch jobs", "power": 3.0, "duration": 6, "default_start": 2, "feasibility": "easy", "hardware_cost": 0, "note": "Move backups to overnight"},
        {"id": "ev-charge-fleet", "label": "Fleet EV charging", "power": 11.0, "duration": 10, "default_start": 38, "feasibility": "medium", "hardware_cost": 800, "note": "OCPP smart charge schedule"},
        {"id": "hot-water-office", "label": "Hot water tank", "power": 3.5, "duration": 2, "default_start": 8, "feasibility": "easy", "hardware_cost": 60, "note": "Timer relay"},
    ],
    "warehouse": [
        {"id": "coolroom-precool", "label": "Coolroom pre-cool", "power": 15.0, "duration": 6, "default_start": 4, "feasibility": "medium", "hardware_cost": 1200, "note": "Drop setpoint overnight"},
        {"id": "compressor-stagger", "label": "Compressor stagger", "power": 8.0, "duration": 4, "default_start": 0, "feasibility": "medium", "hardware_cost": 900, "note": "Stagger start to flatten peak"},
        {"id": "forklift-charge", "label": "Forklift charging", "power": 10.0, "duration": 8, "default_start": 36, "feasibility": "easy", "hardware_cost": 200, "note": "Charge end of shift"},
        {"id": "loading-lights", "label": "Loading-bay lights", "power": 4.0, "duration": 4, "default_start": 12, "feasibility": "easy", "hardware_cost": 100, "note": "Daylight harvesting"},
    ],
}


# ─── Retailer plans (modeled on AER CDR public dataset) ─────────────────────
# Rates are c/kWh stored as $/kWh. Realistic 2025 figures for AU small-business.
SAMPLE_PLANS: List[Dict[str, Any]] = [
    {
        "id": "plan-agl-residential-vic",
        "retailer": "AGL",
        "name": "Standing Offer · Small Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0945,
        "peak_rate": 0.4287,
        "shoulder_rate": 0.2854,
        "offpeak_rate": 0.1925,
        "flat_rate": None,
        "tags": ["standing-offer"],
        "fragility": "No conditional discount",
        "source": "AER CDR public dataset (AGL)",
    },
    {
        "id": "plan-agl-solar-savers-vic",
        "retailer": "AGL",
        "name": "Solar Savers Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.1825,
        "peak_rate": 0.3895,
        "shoulder_rate": 0.2410,
        "offpeak_rate": 0.1685,
        "flat_rate": None,
        "tags": ["solar-friendly"],
        "fragility": "Better feed-in but higher supply",
        "source": "AER CDR public dataset (AGL)",
    },
    {
        "id": "plan-origin-business-saver",
        "retailer": "Origin",
        "name": "Business Saver",
        "plan_type": "TOU",
        "state": "NSW",
        "supply_charge": 1.2230,
        "peak_rate": 0.4520,
        "shoulder_rate": 0.2740,
        "offpeak_rate": 0.1810,
        "flat_rate": None,
        "tags": ["conditional-discount"],
        "fragility": "5% pay-on-time discount",
        "source": "AER CDR public dataset (Origin)",
    },
    {
        "id": "plan-origin-go-flat",
        "retailer": "Origin",
        "name": "Go Flat Business",
        "plan_type": "Flat",
        "state": "NSW",
        "supply_charge": 1.1450,
        "peak_rate": None,
        "shoulder_rate": None,
        "offpeak_rate": None,
        "flat_rate": 0.3245,
        "tags": ["simple"],
        "fragility": "No exit fee",
        "source": "AER CDR public dataset (Origin)",
    },
    {
        "id": "plan-energy-australia-flexi",
        "retailer": "EnergyAustralia",
        "name": "Flexi Business",
        "plan_type": "TOU",
        "state": "QLD",
        "supply_charge": 1.0820,
        "peak_rate": 0.4118,
        "shoulder_rate": 0.2615,
        "offpeak_rate": 0.1745,
        "flat_rate": None,
        "tags": ["smart-meter-required"],
        "fragility": "Requires Type-4 meter",
        "source": "AER CDR public dataset (EnergyAustralia)",
    },
    {
        "id": "plan-energy-australia-total",
        "retailer": "EnergyAustralia",
        "name": "Total Business",
        "plan_type": "Flat",
        "state": "QLD",
        "supply_charge": 1.0240,
        "peak_rate": None,
        "shoulder_rate": None,
        "offpeak_rate": None,
        "flat_rate": 0.3380,
        "tags": ["simple"],
        "fragility": "12-month benefit period",
        "source": "AER CDR public dataset (EnergyAustralia)",
    },
    {
        "id": "plan-red-energy-living",
        "retailer": "Red Energy",
        "name": "Living Energy Saver Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0510,
        "peak_rate": 0.4012,
        "shoulder_rate": 0.2520,
        "offpeak_rate": 0.1820,
        "flat_rate": None,
        "tags": ["qantas-points"],
        "fragility": "Bonus Qantas points",
        "source": "AER CDR public dataset (Red Energy)",
    },
    {
        "id": "plan-alinta-business-flex",
        "retailer": "Alinta Energy",
        "name": "Business Flex",
        "plan_type": "TOU",
        "state": "SA",
        "supply_charge": 1.3450,
        "peak_rate": 0.4895,
        "shoulder_rate": 0.3120,
        "offpeak_rate": 0.2010,
        "flat_rate": None,
        "tags": ["no-exit-fee"],
        "fragility": "Standing-offer fallback rate is steep",
        "source": "AER CDR public dataset (Alinta)",
    },
    {
        "id": "plan-momentum-smile",
        "retailer": "Momentum Energy",
        "name": "Smile Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0985,
        "peak_rate": 0.3978,
        "shoulder_rate": 0.2440,
        "offpeak_rate": 0.1695,
        "flat_rate": None,
        "tags": ["hydro-tas-backed"],
        "fragility": "100% Australian-owned",
        "source": "AER CDR public dataset (Momentum)",
    },
    {
        "id": "plan-powershop-business",
        "retailer": "Powershop",
        "name": "Powershop Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0720,
        "peak_rate": 0.3850,
        "shoulder_rate": 0.2380,
        "offpeak_rate": 0.1610,
        "flat_rate": None,
        "tags": ["100-renewable"],
        "fragility": "Pack-based prepay model",
        "source": "AER CDR public dataset (Powershop)",
    },
    {
        "id": "plan-ovo-business",
        "retailer": "OVO Energy",
        "name": "OVO Business",
        "plan_type": "TOU",
        "state": "VIC",
        "supply_charge": 1.0290,
        "peak_rate": 0.3680,
        "shoulder_rate": 0.2280,
        "offpeak_rate": 0.1520,
        "flat_rate": None,
        "tags": ["carbon-neutral"],
        "fragility": "Smaller retailer, less brand presence",
        "source": "AER CDR public dataset (OVO)",
    },
    {
        "id": "plan-simply-energy-business",
        "retailer": "Simply Energy",
        "name": "Business Plus",
        "plan_type": "Demand",
        "state": "VIC",
        "supply_charge": 0.8950,
        "peak_rate": 0.3120,
        "shoulder_rate": 0.2240,
        "offpeak_rate": 0.1450,
        "flat_rate": None,
        "demand_charge_per_kw_month": 18.50,
        "tags": ["demand-tariff"],
        "fragility": "Penalises peak kW — flatten your curve",
        "source": "AER CDR public dataset (Simply Energy)",
    },
]


# ─── Real NEM spot price overlay (averaged) ──────────────────────────────────
# Approximate VIC1 RRP half-hourly average from the existing repo's processed data,
# downsampled to 48 buckets. $/MWh.
NEM_SPOT_AVG_VIC: List[float] = [
    72, 71, 68, 65, 62, 60, 58, 56, 55, 54, 56, 62,
    74, 86, 94, 102, 108, 110, 112, 110, 105, 98, 92, 88,
    86, 88, 92, 98, 110, 130, 158, 192,
    218, 238, 246, 232, 198, 162, 132, 108,
    94, 84, 78, 74, 72, 70, 68, 66,
]
