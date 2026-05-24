"""Backend API tests for Load Shape Lab — cafe chain portfolio (v3 contract)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
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


# ── Meters ────────────────────────────────────────────────────────────────
def test_list_meters(api):
    meters = api.get(f"{BASE_URL}/api/meters").json()
    assert len(meters) == 10
    states = {m["state"] for m in meters}
    assert states == {"VIC", "NSW", "QLD", "SA"}
    for m in meters:
        assert m["archetype"] == "cafe"


def test_meter_detail(api):
    m = api.get(f"{BASE_URL}/api/meters/MTR-001").json()
    assert len(m["baseline_shape"]) == 48
    assert len(m["appliances"]) == 8
    ids = {a["id"] for a in m["appliances"]}
    assert ids == {
        "fridges", "espresso", "ovens", "hvac",
        "lighting", "dishwasher", "hot-water", "misc",
    }
    for a in m["appliances"]:
        assert a["color"].startswith("#")
        assert "always_on" in a
        assert len(a["profile"]) == 48
        assert "daily_kwh" in a
    fridges = next(a for a in m["appliances"] if a["id"] == "fridges")
    assert fridges["always_on"] is True
    # Sum of appliance profiles == baseline
    summed = [0.0] * 48
    for a in m["appliances"]:
        for i, v in enumerate(a["profile"]):
            summed[i] += v
    for i in range(48):
        assert abs(summed[i] - m["baseline_shape"][i]) < 0.01


def test_meter_detail_404(api):
    r = api.get(f"{BASE_URL}/api/meters/MTR-999")
    assert r.status_code == 404


# ── Plans / Zones / Spot ──────────────────────────────────────────────────
def test_list_plans(api):
    plans = api.get(f"{BASE_URL}/api/plans").json()
    assert len(plans) == 12
    for p in plans:
        assert p["plan_type"] in {"TOU", "Flat", "Demand"}


def test_list_zones(api):
    zones = api.get(f"{BASE_URL}/api/zones").json()
    assert {z["code"] for z in zones} == {"citipower", "ausgrid", "energex", "sapn"}


def test_spot(api):
    s = api.get(f"{BASE_URL}/api/spot").json()
    assert len(s["rrp_mwh"]) == 48


# ── Rank — new contract ────────────────────────────────────────────────────
def test_rank_default_all_on(api):
    """No appliance_scales (or empty) → all appliances at scale 1.0."""
    r = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    })
    assert r.status_code == 200
    j = r.json()
    assert j["n_sites"] == 1
    assert len(j["appliance_breakdown"]) == 8
    for a in j["appliance_breakdown"]:
        assert a["active"] is True
        assert a["scale"] == 1.0
    for i in range(48):
        assert abs(j["shape"]["active"][i] - j["shape"]["full"][i]) < 0.01


def test_rank_requires_meter_ids(api):
    r = api.post(f"{BASE_URL}/api/rank", json={"meter_ids": [], "appliance_scales": {}})
    assert r.status_code == 422


def test_rank_disable_appliance_reduces_cost(api):
    """Setting HVAC scale to 0 should reduce annual cost and peak kW."""
    full = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    }).json()
    no_hvac = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"],
        "appliance_scales": {"hvac": 0.0},
    }).json()
    assert no_hvac["current"]["shifted_cost"] < full["current"]["shifted_cost"]
    assert no_hvac["stats"]["active"]["peak_kw"] < full["stats"]["active"]["peak_kw"]
    hvac_entry = next(a for a in no_hvac["appliance_breakdown"] if a["id"] == "hvac")
    assert hvac_entry["active"] is False
    assert hvac_entry["scale"] == 0.0


def test_rank_scale_doubles_load(api):
    """Doubling HVAC scale should ~double its daily_kwh."""
    base = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    }).json()
    double = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {"hvac": 2.0},
    }).json()
    base_hvac = next(a for a in base["appliance_breakdown"] if a["id"] == "hvac")
    double_hvac = next(a for a in double["appliance_breakdown"] if a["id"] == "hvac")
    assert abs(double_hvac["daily_kwh"] - 2.0 * base_hvac["daily_kwh"]) < 0.05
    assert double_hvac["scale"] == 2.0


def test_rank_appliance_breakdown_colors_unique(api):
    j = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    }).json()
    colors = [a["color"] for a in j["appliance_breakdown"]]
    assert len(set(colors)) == 8


def test_rank_aggregate_all_sites(api):
    all_ids = [f"MTR-{i:03d}" for i in range(1, 11)]
    j = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": all_ids, "appliance_scales": {},
    }).json()
    assert j["n_sites"] == 10
    single = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    }).json()
    single_fridges = next(a for a in single["appliance_breakdown"] if a["id"] == "fridges")["daily_kwh"]
    multi_fridges = next(a for a in j["appliance_breakdown"] if a["id"] == "fridges")["daily_kwh"]
    assert multi_fridges > 7 * single_fridges


def test_rank_ranked_sorted(api):
    j = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "appliance_scales": {},
    }).json()
    costs = [p["shifted_cost"] for p in j["ranked"]]
    assert costs == sorted(costs)
    assert j["best"]["plan"]["id"] == j["ranked"][0]["plan"]["id"]


# ── Refresh CDR ───────────────────────────────────────────────────────────
def test_refresh_cdr(api):
    r = api.post(f"{BASE_URL}/api/refresh-cdr", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "queried" in j and len(j["queried"]) > 0
