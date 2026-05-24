"""Backend API tests for Load Shape Lab — cafe chain portfolio."""
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
    assert j["status"] == "ok"


# ── Meters ────────────────────────────────────────────────────────────────
def test_list_meters(api):
    r = api.get(f"{BASE_URL}/api/meters")
    assert r.status_code == 200
    meters = r.json()
    assert len(meters) == 10
    ids = [m["id"] for m in meters]
    for i in range(1, 11):
        suffix = f"00{i}" if i < 10 else "010"
        assert f"MTR-{suffix}" in ids
    states = {m["state"] for m in meters}
    assert states == {"VIC", "NSW", "QLD", "SA"}
    for m in meters:
        assert m["archetype"] == "cafe"
        assert m["zone_code"]
        assert isinstance(m["annual_kwh"], (int, float))
        assert isinstance(m["monthly_spend"], list) and len(m["monthly_spend"]) == 12


def test_meter_detail(api):
    r = api.get(f"{BASE_URL}/api/meters/MTR-001")
    assert r.status_code == 200
    m = r.json()
    assert m["id"] == "MTR-001"
    assert len(m["baseline_shape"]) == 48
    # Appliance decomposition
    assert isinstance(m["appliances"], list) and len(m["appliances"]) == 8
    shiftable = [a for a in m["appliances"] if a["shiftable"]]
    assert {a["id"] for a in shiftable} == {"hvac", "dishwasher", "hot-water"}
    # Shift assets
    assert isinstance(m["shift_assets"], list) and len(m["shift_assets"]) == 3
    for a in m["shift_assets"]:
        for k in ("id", "label", "power", "duration", "default_start", "feasibility"):
            assert k in a
    # Sum of appliance profiles should equal baseline_shape
    summed = [0.0] * 48
    for a in m["appliances"]:
        for i, v in enumerate(a["profile"]):
            summed[i] += v
    for i in range(48):
        assert abs(summed[i] - m["baseline_shape"][i]) < 0.01


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


# ── Rank — single site ────────────────────────────────────────────────────
def test_rank_single_baseline(api):
    payload = {"meter_ids": ["MTR-001"], "asset_positions": {}, "active_assets": []}
    r = api.post(f"{BASE_URL}/api/rank", json=payload)
    assert r.status_code == 200
    j = r.json()
    assert j["n_sites"] == 1
    assert len(j["ranked"]) == 12
    costs = [p["shifted_cost"] for p in j["ranked"]]
    assert costs == sorted(costs)
    assert j["best"]["plan"]["id"] == j["ranked"][0]["plan"]["id"]
    assert j["current"]["plan"]["id"] == "plan-agl-residential-vic"
    assert "shape" in j and "baseline" in j["shape"] and "shifted" in j["shape"]
    assert len(j["shape"]["baseline"]) == 48
    for stat_key in ("peak_kw", "load_factor", "pct_in_peak", "annual_kwh"):
        assert stat_key in j["stats"]["baseline"]


def test_rank_requires_meter_ids(api):
    r = api.post(f"{BASE_URL}/api/rank", json={"meter_ids": [], "asset_positions": {}, "active_assets": []})
    assert r.status_code == 422


def test_rank_qld_meter(api):
    payload = {"meter_ids": ["MTR-007"], "asset_positions": {}, "active_assets": []}
    r = api.post(f"{BASE_URL}/api/rank", json=payload)
    assert r.status_code == 200
    j = r.json()
    qld_retailers = {p["plan"]["retailer"] for p in j["ranked"] if p["plan"]["state"] == "QLD"}
    assert "EnergyAustralia" in qld_retailers
    assert j["current"]["plan"]["id"] == "plan-energy-australia-flexi"


def test_rank_shift_reduces_cost(api):
    """Move dishwasher from peak (default ~33) to off-peak (10) → lower cost on TOU plans."""
    base = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "asset_positions": {}, "active_assets": [],
    }).json()
    shift = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"],
        "asset_positions": {"dishwasher": 10},
        "active_assets": ["dishwasher"],
    }).json()
    # All VIC TOU plans should see lower cost after the shift
    tou_vic = ["plan-agl-residential-vic", "plan-red-energy-living", "plan-momentum-smile",
               "plan-powershop-business", "plan-ovo-business", "plan-agl-solar-savers-vic"]
    base_map = {p["plan"]["id"]: p["shifted_cost"] for p in base["ranked"]}
    shift_map = {p["plan"]["id"]: p["shifted_cost"] for p in shift["ranked"]}
    for pid in tou_vic:
        assert shift_map[pid] < base_map[pid], (
            f"{pid}: shifted {shift_map[pid]} should be < baseline {base_map[pid]}"
        )


# ── Rank — multi site aggregation ─────────────────────────────────────────
def test_rank_aggregate_all_sites(api):
    all_ids = [f"MTR-{i:03d}" for i in range(1, 11)]
    r = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": all_ids, "asset_positions": {}, "active_assets": [],
    })
    assert r.status_code == 200
    j = r.json()
    assert j["n_sites"] == 10
    assert len(j["per_meter"]) == 10
    # Aggregated baseline should equal sum of per-meter baselines
    summed = [0.0] * 48
    for pm in j["per_meter"]:
        for i, v in enumerate(pm["baseline_shape"]):
            summed[i] += v
    for i in range(48):
        assert abs(summed[i] - j["shape"]["baseline"][i]) < 0.01
    # Aggregated cost should be roughly 10x a single-site cost
    single = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "asset_positions": {}, "active_assets": [],
    }).json()
    assert j["best"]["shifted_cost"] > 5 * single["best"]["shifted_cost"]


def test_rank_aggregate_shift_propagates(api):
    """Shifting an asset in aggregate mode should apply to all selected meters."""
    all_ids = [f"MTR-{i:03d}" for i in range(1, 11)]
    base = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": all_ids, "asset_positions": {}, "active_assets": [],
    }).json()
    shift = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": all_ids,
        "asset_positions": {"dishwasher": 10},
        "active_assets": ["dishwasher"],
    }).json()
    # Current-plan cost should drop materially across the chain
    assert shift["current"]["shifted_cost"] < base["current"]["shifted_cost"]
    delta = base["current"]["shifted_cost"] - shift["current"]["shifted_cost"]
    # Saving should scale with number of sites — at least 5x a single-site shift
    single_shift = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"],
        "asset_positions": {"dishwasher": 10},
        "active_assets": ["dishwasher"],
    }).json()
    single_base = api.post(f"{BASE_URL}/api/rank", json={
        "meter_ids": ["MTR-001"], "asset_positions": {}, "active_assets": [],
    }).json()
    single_delta = single_base["current"]["shifted_cost"] - single_shift["current"]["shifted_cost"]
    assert delta > 5 * single_delta


# ── Refresh CDR ───────────────────────────────────────────────────────────
def test_refresh_cdr(api):
    r = api.post(f"{BASE_URL}/api/refresh-cdr", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "queried" in j and isinstance(j["queried"], list) and len(j["queried"]) > 0
    assert "results" in j and isinstance(j["results"], dict)
