"""Backend API tests for Load Shape Lab."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read from frontend .env as fallback for in-container testing
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Health ────────────────────────────────────────────────────────────────
def test_health(api):
    r = api.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    j = r.json()
    assert j["app"] == "Load Shape Lab"
    assert j["status"] == "ok"


# ── Meters ────────────────────────────────────────────────────────────────
def test_list_meters(api):
    r = api.get(f"{BASE_URL}/api/meters")
    assert r.status_code == 200
    meters = r.json()
    assert len(meters) == 5
    ids = [m["id"] for m in meters]
    for i in range(1, 6):
        assert f"MTR-00{i}" in ids
    for m in meters:
        assert m["archetype"] in {"cafe", "pub", "retail", "office", "warehouse"}
        assert m["zone_code"]
        assert isinstance(m["annual_kwh"], (int, float))
        assert isinstance(m["monthly_spend"], list) and len(m["monthly_spend"]) == 12


def test_meter_detail(api):
    r = api.get(f"{BASE_URL}/api/meters/MTR-001")
    assert r.status_code == 200
    m = r.json()
    assert m["id"] == "MTR-001"
    assert len(m["baseline_shape"]) == 48
    assert isinstance(m["shift_assets"], list) and len(m["shift_assets"]) > 0
    for a in m["shift_assets"]:
        for k in ("id", "label", "power", "duration", "default_start", "feasibility"):
            assert k in a


def test_meter_detail_404(api):
    r = api.get(f"{BASE_URL}/api/meters/MTR-999")
    assert r.status_code == 404


# ── Plans ─────────────────────────────────────────────────────────────────
def test_list_plans(api):
    r = api.get(f"{BASE_URL}/api/plans")
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 12
    required = {"id", "retailer", "name", "plan_type", "supply_charge", "fragility", "source"}
    for p in plans:
        assert required.issubset(p.keys())
        assert p["plan_type"] in {"TOU", "Flat", "Demand"}


# ── Zones ─────────────────────────────────────────────────────────────────
def test_list_zones(api):
    r = api.get(f"{BASE_URL}/api/zones")
    assert r.status_code == 200
    zones = r.json()
    assert len(zones) == 4
    codes = {z["code"] for z in zones}
    assert codes == {"citipower", "ausgrid", "energex", "sapn"}
    for z in zones:
        assert isinstance(z["peak_buckets"], list)
        assert isinstance(z["shoulder_buckets"], list)


# ── Spot ──────────────────────────────────────────────────────────────────
def test_spot(api):
    r = api.get(f"{BASE_URL}/api/spot")
    assert r.status_code == 200
    j = r.json()
    assert len(j["rrp_mwh"]) == 48
    assert len(j["rrp_kwh"]) == 48


# ── Rank ──────────────────────────────────────────────────────────────────
def _baseline(api, meter_id):
    return api.get(f"{BASE_URL}/api/meters/{meter_id}").json()["baseline_shape"]


def test_rank_baseline(api):
    shape = _baseline(api, "MTR-001")
    r = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-001", "shape": shape})
    assert r.status_code == 200
    j = r.json()
    assert len(j["ranked"]) == 12
    # Ascending by shifted_cost
    costs = [p["shifted_cost"] for p in j["ranked"]]
    assert costs == sorted(costs)
    assert j["best"]["plan"]["id"] == j["ranked"][0]["plan"]["id"]
    assert "current" in j and j["current"]["plan"]["id"] == "plan-agl-residential-vic"
    assert "achievable_saving" in j
    assert "baseline" in j["stats"] and "shifted" in j["stats"]
    for stat_key in ("peak_kw", "load_factor", "pct_in_peak", "annual_kwh"):
        assert stat_key in j["stats"]["baseline"]


def test_rank_validates_shape_length(api):
    r = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-001", "shape": [1.0] * 47})
    assert r.status_code == 422
    r2 = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-001", "shape": [1.0] * 49})
    assert r2.status_code == 422


def test_rank_qld_energex(api):
    shape = _baseline(api, "MTR-003")
    r = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-003", "shape": shape})
    assert r.status_code == 200
    j = r.json()
    # QLD plans should appear among results
    qld_retailers = {p["plan"]["retailer"] for p in j["ranked"] if p["plan"]["state"] == "QLD"}
    assert "EnergyAustralia" in qld_retailers
    assert j["current"]["plan"]["id"] == "plan-energy-australia-flexi"


def test_rank_shifting_load_reduces_cost(api):
    """Moving load from Citipower peak (30-42) to offpeak (0-12) should lower TOU costs."""
    shape = _baseline(api, "MTR-001")[:]
    r_base = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-001", "shape": shape})
    assert r_base.status_code == 200
    baseline_results = {p["plan"]["id"]: p["shifted_cost"] for p in r_base.json()["ranked"]}

    # Shift 4 kW from peak buckets 30..41 to offpeak buckets 0..11
    shifted = shape[:]
    for i in range(30, 42):
        shifted[i] = max(0.0, shifted[i] - 4.0)
    for i in range(0, 12):
        shifted[i] = shifted[i] + 4.0

    r_shift = api.post(f"{BASE_URL}/api/rank", json={"meter_id": "MTR-001", "shape": shifted})
    assert r_shift.status_code == 200
    shifted_results = {p["plan"]["id"]: p["shifted_cost"] for p in r_shift.json()["ranked"]}

    # All TOU plans for VIC should see lower cost
    tou_vic_plans = [
        "plan-agl-residential-vic",
        "plan-agl-solar-savers-vic",
        "plan-red-energy-living",
        "plan-momentum-smile",
        "plan-powershop-business",
        "plan-ovo-business",
    ]
    for pid in tou_vic_plans:
        assert shifted_results[pid] < baseline_results[pid], (
            f"Plan {pid}: shifted {shifted_results[pid]} should be < baseline {baseline_results[pid]}"
        )


# ── Refresh CDR ───────────────────────────────────────────────────────────
def test_refresh_cdr(api):
    r = api.post(f"{BASE_URL}/api/refresh-cdr", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "queried" in j and isinstance(j["queried"], list) and len(j["queried"]) > 0
    assert "results" in j and isinstance(j["results"], dict)
