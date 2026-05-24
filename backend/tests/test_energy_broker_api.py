"""Backend API tests for the Energy Broker app (Brunswick East Café demo)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

DEMO_ID = "client-demo-001"
EXPECTED_APPLIANCES = {
    "Fridges", "Espresso", "Ovens", "HVAC",
    "Lighting", "Dishwasher", "Hot Water", "Misc",
}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Health ────────────────────────────────────────────────────────────────
def test_health(api):
    r = api.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── Clients ───────────────────────────────────────────────────────────────
def test_list_clients_includes_demo(api):
    r = api.get(f"{BASE_URL}/api/clients")
    assert r.status_code == 200
    clients = r.json()
    assert isinstance(clients, list)
    demo = next((c for c in clients if c["id"] == DEMO_ID), None)
    assert demo is not None, "Demo client not found"
    assert demo["name"] == "Brunswick East Café"
    assert demo["annual_kwh"] == 24800
    assert demo["tariff_id"] == "tariff-agl-tou-vic"
    assert demo["has_interval_data"] is True
    assert demo["has_tariff"] is True
    assert demo["site_type"] == "cafe"


def test_get_demo_client(api):
    r = api.get(f"{BASE_URL}/api/clients/{DEMO_ID}")
    assert r.status_code == 200
    c = r.json()
    assert c["id"] == DEMO_ID
    assert c["name"] == "Brunswick East Café"


def test_get_nonexistent_client_404(api):
    r = api.get(f"{BASE_URL}/api/clients/does-not-exist")
    assert r.status_code == 404


# ── Tariffs ───────────────────────────────────────────────────────────────
def test_list_tariffs_includes_agl(api):
    r = api.get(f"{BASE_URL}/api/tariffs")
    assert r.status_code == 200
    tariffs = r.json()
    agl = next((t for t in tariffs if t.get("id") == "tariff-agl-tou-vic"), None)
    assert agl is not None
    assert agl.get("retailer") == "AGL"
    # Must be a TOU style tariff
    assert str(agl.get("type", "")).lower() == "tou"
    rates = agl.get("energy_rates") or {}
    assert rates.get("peak") and rates.get("offpeak")


# ── Baseline ──────────────────────────────────────────────────────────────
def test_baseline_demo(api):
    r = api.get(f"{BASE_URL}/api/clients/{DEMO_ID}/baseline")
    assert r.status_code == 200
    b = r.json()
    # Load curve
    assert "load_curve" in b
    assert len(b["load_curve"]) == 48
    assert all(isinstance(v, (int, float)) for v in b["load_curve"])

    # Cost stack
    assert "cost_stack" in b
    total = b["cost_stack"]["total_annual"]
    assert 8000 <= total <= 11000, f"total_annual={total} out of expected range"

    # Shape metrics
    assert "shape_metrics" in b
    sm = b["shape_metrics"]
    for k in ("load_factor", "peak_kw", "peak_coincidence", "annual_kwh"):
        assert k in sm

    # Appliance curves
    assert "appliance_curves" in b
    ac = b["appliance_curves"]
    assert set(ac.keys()) == EXPECTED_APPLIANCES
    for name, curve in ac.items():
        assert len(curve) == 48, f"{name} curve length != 48"

    # Sum of appliance curves ~ load_curve at each bucket
    for i in range(48):
        s = sum(ac[name][i] for name in EXPECTED_APPLIANCES)
        assert abs(s - b["load_curve"][i]) < 0.05, f"bucket {i}: sum={s} vs load={b['load_curve'][i]}"


# ── Claude scenarios ──────────────────────────────────────────────────────
def test_generate_scenarios_default_cached(api):
    """First call (no extra_instruction) should return cached/claude scenarios fast."""
    r = api.post(
        f"{BASE_URL}/api/clients/{DEMO_ID}/scenarios/generate",
        json={},
        timeout=90,
    )
    assert r.status_code == 200
    source = r.headers.get("X-Scenario-Source", "")
    assert source in ("claude", "claude-cached", "fallback")
    if source == "fallback":
        pytest.skip(f"Backend returned fallback scenarios: {r.headers.get('X-Scenario-Error')}")

    j = r.json()
    assert "scenarios" in j
    scenarios = j["scenarios"]
    assert isinstance(scenarios, list)
    assert len(scenarios) >= 3, f"Expected 3+ scenarios, got {len(scenarios)}"

    # baseline_curve at top-level
    assert "baseline_curve" in j
    assert len(j["baseline_curve"]) == 48

    # Shape of each scenario
    for s in scenarios:
        for k in ("rank", "name", "rationale", "type", "parameters", "shifted_curve", "savings"):
            assert k in s, f"missing {k} in scenario"
        assert len(s["shifted_curve"]) == 48
        sav = s["savings"]
        for k in ("billing_defensible", "indicative", "total_low", "total_high"):
            assert k in sav

    # Sorted by total_low desc
    lows = [s["savings"]["total_low"] for s in scenarios]
    assert lows == sorted(lows, reverse=True), f"scenarios not sorted by total_low desc: {lows}"

    # Ranks 1..N
    ranks = [s["rank"] for s in scenarios]
    assert ranks == list(range(1, len(scenarios) + 1))


def test_generate_scenarios_with_extra_instruction(api):
    """extra_instruction must trigger a fresh Claude call (not cached)."""
    r = api.post(
        f"{BASE_URL}/api/clients/{DEMO_ID}/scenarios/generate",
        json={"extra_instruction": "Show me battery options"},
        timeout=120,
    )
    assert r.status_code == 200
    source = r.headers.get("X-Scenario-Source", "")
    assert source != "claude-cached", "extra_instruction should bypass cache"
    if source == "fallback":
        pytest.skip(f"Backend fell back: {r.headers.get('X-Scenario-Error')}")
    j = r.json()
    assert len(j.get("scenarios", [])) >= 1
    assert "baseline_curve" in j


def test_generate_scenarios_404(api):
    r = api.post(
        f"{BASE_URL}/api/clients/no-such/scenarios/generate",
        json={},
    )
    assert r.status_code == 404
