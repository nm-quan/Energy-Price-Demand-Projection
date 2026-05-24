"""
Backend regression tests for EnergyScope async scenario generation (iteration 5).

Targets the FIX for the prev critical issue (iteration_4): scenario generation is now
an async job; POST returns 202 + job_id immediately; client polls
GET /api/scenarios/jobs/{job_id} for status='done'.

Run:
  pytest /app/backend/tests/test_async_scenarios.py -v \
    --junitxml=/app/test_reports/pytest/iter5_results.xml
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://agent-memory-14.preview.emergentagent.com").rstrip("/")
DEMO_CLIENT_ID = "client-demo-001"


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def test_client(api):
    """Create a TEST_ prefixed client. Cleaned up after test."""
    payload = {
        "name": f"TEST_async_{uuid.uuid4().hex[:6]}",
        "address": "1 Test St",
        "nmi": "TEST" + uuid.uuid4().hex[:6].upper(),
        "site_type": "cafe",
    }
    r = api.post(f"{BASE_URL}/api/clients", json=payload)
    assert r.status_code == 201, r.text
    c = r.json()
    # Assign AGL tariff so generation can run
    r2 = api.put(f"{BASE_URL}/api/clients/{c['id']}/tariff",
                 json={"tariff_id": "tariff-agl-tou-vic"})
    assert r2.status_code == 200, r2.text
    yield c
    # Teardown: cascade delete
    api.delete(f"{BASE_URL}/api/clients/{c['id']}")


# ── Basic checks (sanity) ───────────────────────────────────────────────────

class TestHealthAndSeed:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d.get("claude") is True

    def test_no_auth_endpoint(self, api):
        r = api.get(f"{BASE_URL}/api/auth/login", timeout=10)
        assert r.status_code == 404

    def test_demo_client_seeded(self, api):
        r = api.get(f"{BASE_URL}/api/clients", timeout=10)
        assert r.status_code == 200
        clients = r.json()
        demo = next((c for c in clients if c["id"] == DEMO_CLIENT_ID), None)
        assert demo is not None, "Demo client client-demo-001 not seeded"
        assert demo["name"] == "Brunswick East Cafe"
        assert demo["has_interval_data"] is True
        assert demo["tariff_id"] == "tariff-agl-tou-vic"

    def test_five_tariffs(self, api):
        r = api.get(f"{BASE_URL}/api/tariffs", timeout=10)
        assert r.status_code == 200
        tariffs = r.json()
        assert len(tariffs) >= 5
        retailers = {t.get("retailer") for t in tariffs}
        for expected in {"AGL", "Origin Energy", "EnergyAustralia", "Alinta Energy", "Red Energy"}:
            assert expected in retailers, f"Missing retailer {expected} in {retailers}"


# ── Baseline ────────────────────────────────────────────────────────────────

class TestBaseline:
    def test_get_baseline(self, api):
        r = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/baseline", timeout=20)
        assert r.status_code == 200
        d = r.json()
        # Required keys
        for k in ("load_curve", "cost_stack", "appliance_curves"):
            assert k in d, f"Missing key {k} in baseline"
        assert isinstance(d["appliance_curves"], dict) and len(d["appliance_curves"]) > 0
        # Each appliance curve should be a list (length 48 is expected from synthetic split)
        for name, curve in d["appliance_curves"].items():
            assert isinstance(curve, list) and len(curve) == 48, f"{name} curve len {len(curve)}"
        assert d["cost_stack"].get("total_annual", 0) > 0

    def test_baseline_recalc_with_scales(self, api):
        # First fetch baseline
        r0 = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/baseline", timeout=20)
        base = r0.json()
        base_total = base["cost_stack"]["total_annual"]
        base_peak = max(base["load_curve"])

        r = api.post(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/baseline/recalc",
                     json={"scales": {"HVAC": 0.5}}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        new_peak = max(d["load_curve"])
        new_total = d["cost_stack"]["total_annual"]
        assert new_peak < base_peak, f"Peak should drop: was {base_peak}, now {new_peak}"
        assert new_total < base_total, f"Cost should drop: was {base_total}, now {new_total}"


# ── Async generation flow (the critical fix) ────────────────────────────────

class TestAsyncScenarioGeneration:
    @pytest.fixture(scope="class")
    def generated_job(self, request):
        """Class-scoped: kick off ONE generation (count=3) and reuse across tests."""
        sess = requests.Session()
        t0 = time.time()
        r = sess.post(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios/generate",
                      json={"count": 3}, timeout=15)
        elapsed = time.time() - t0
        assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text[:300]}"
        assert elapsed < 5.0, f"POST took {elapsed:.1f}s — should return immediately"
        body = r.json()
        assert "job_id" in body
        assert body.get("status") == "running"
        job_id = body["job_id"]
        # Poll until done (max ~150s)
        final = None
        for _ in range(60):
            time.sleep(3)
            rp = sess.get(f"{BASE_URL}/api/scenarios/jobs/{job_id}", timeout=15)
            assert rp.status_code == 200, rp.text
            j = rp.json()
            if j["status"] in ("done", "error"):
                final = j
                break
        assert final is not None, "Job did not finish in 180s"
        if final["status"] == "error":
            pytest.fail(f"Job errored: {final.get('error')}")
        # cleanup persisted TEST scenarios from this run after class
        def teardown():
            # Only clear scenarios produced for demo client during this test run
            for s in final.get("scenarios", []):
                sess.delete(f"{BASE_URL}/api/scenarios/{s['id']}")
        request.addfinalizer(teardown)
        return final

    def test_post_returns_202_immediately(self, api):
        """Just verify the 202 contract again, without waiting."""
        t0 = time.time()
        r = api.post(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios/generate",
                     json={"count": 1}, timeout=15)
        elapsed = time.time() - t0
        assert r.status_code == 202
        assert elapsed < 5.0, f"Endpoint not async: took {elapsed:.1f}s"
        body = r.json()
        assert "job_id" in body and body["job_id"].startswith("job-")
        # Best-effort: wait briefly then clear so we don't leak
        job_id = body["job_id"]
        for _ in range(50):
            time.sleep(3)
            j = api.get(f"{BASE_URL}/api/scenarios/jobs/{job_id}", timeout=10).json()
            if j["status"] in ("done", "error"):
                if j["status"] == "done":
                    for s in j.get("scenarios", []):
                        api.delete(f"{BASE_URL}/api/scenarios/{s['id']}")
                break

    def test_job_completes_with_scenarios(self, generated_job):
        j = generated_job
        assert j["status"] == "done"
        scns = j.get("scenarios", [])
        assert len(scns) == 3, f"expected 3 scenarios, got {len(scns)}"

    def test_scenario_schema(self, generated_job):
        j = generated_job
        for idx, s in enumerate(j["scenarios"]):
            for key in ("id", "rank", "name", "rationale", "appliance_changes",
                        "shifted_curve", "retailer_winner", "negotiation_levers",
                        "savings_annual_low", "savings_annual_high",
                        "baseline_curve", "baseline_appliance_curves", "agent_memory"):
                assert key in s, f"scenario[{idx}] missing key '{key}'"
            assert isinstance(s["shifted_curve"], list) and len(s["shifted_curve"]) == 48
            assert isinstance(s["appliance_changes"], list) and len(s["appliance_changes"]) >= 1
            for ch in s["appliance_changes"]:
                for ck in ("appliance", "action", "summary", "before_curve", "after_curve"):
                    assert ck in ch, f"appliance_change missing '{ck}': {list(ch.keys())}"
                assert isinstance(ch["before_curve"], list) and len(ch["before_curve"]) == 48
                assert isinstance(ch["after_curve"], list) and len(ch["after_curve"]) == 48
            assert isinstance(s["negotiation_levers"], list) and len(s["negotiation_levers"]) >= 1
            assert s["savings_annual_low"] <= s["savings_annual_high"]
            assert isinstance(s["baseline_curve"], list) and len(s["baseline_curve"]) == 48

    def test_agent_memory_at_root(self, generated_job):
        mem = generated_job.get("agent_memory", [])
        assert isinstance(mem, list)
        assert 1 <= len(mem) <= 6, f"agent_memory should have <=6 bullets, got {len(mem)}"
        # Dedupe check
        assert len(mem) == len(set(mem)), "agent_memory bullets should be deduped"

    def test_scenarios_persisted(self, generated_job, api):
        """Generated scenarios should appear in GET /clients/{id}/scenarios."""
        r = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios", timeout=15)
        assert r.status_code == 200
        listed = r.json()
        listed_ids = {s["id"] for s in listed}
        for s in generated_job["scenarios"]:
            assert s["id"] in listed_ids, f"scenario {s['id']} not persisted"


# ── Scenario CRUD ───────────────────────────────────────────────────────────

class TestScenarioCRUD:
    def test_delete_single_scenario(self, api, test_client):
        # Start a job count=1 so we have a real scenario to delete
        r = api.post(f"{BASE_URL}/api/clients/{test_client['id']}/scenarios/generate",
                     json={"count": 1}, timeout=15)
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        # Poll
        final = None
        for _ in range(60):
            time.sleep(3)
            j = api.get(f"{BASE_URL}/api/scenarios/jobs/{job_id}", timeout=10).json()
            if j["status"] in ("done", "error"):
                final = j; break
        assert final and final["status"] == "done", f"job did not complete: {final}"
        sid = final["scenarios"][0]["id"]
        # delete
        rd = api.delete(f"{BASE_URL}/api/scenarios/{sid}")
        assert rd.status_code == 200
        # confirm gone
        rl = api.get(f"{BASE_URL}/api/clients/{test_client['id']}/scenarios").json()
        assert sid not in {s["id"] for s in rl}

    def test_clear_all_scenarios(self, api, test_client):
        # Pre-condition: client may have 0 scenarios
        rd = api.delete(f"{BASE_URL}/api/clients/{test_client['id']}/scenarios")
        assert rd.status_code == 200
        assert "deleted" in rd.json()


# ── Reports CRUD (depends on at least one persisted scenario for demo) ─────

class TestReports:
    def test_report_flow(self, api):
        # Use demo client's existing scenarios (created by TestAsyncScenarioGeneration class)
        # or generate one quickly if none.
        r = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios", timeout=15)
        scns = r.json()
        if not scns:
            # generate 1 quickly
            jr = api.post(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios/generate",
                          json={"count": 1}, timeout=15)
            jid = jr.json()["job_id"]
            for _ in range(60):
                time.sleep(3)
                j = api.get(f"{BASE_URL}/api/scenarios/jobs/{jid}", timeout=10).json()
                if j["status"] in ("done", "error"):
                    break
            scns = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/scenarios").json()
        assert scns, "no scenarios available for report test"
        sid = scns[0]["id"]

        # CREATE
        rc = api.post(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/reports",
                      json={"title": "TEST_report", "scenario_ids": [sid]}, timeout=20)
        assert rc.status_code == 201, rc.text
        rep = rc.json()
        rid = rep["id"]
        assert rep["title"] == "TEST_report"
        assert len(rep["scenarios"]) == 1
        assert "baseline" in rep and "tariff" in rep

        # LIST
        rl = api.get(f"{BASE_URL}/api/clients/{DEMO_CLIENT_ID}/reports").json()
        assert rid in {r["id"] for r in rl}

        # GET BY ID
        rg = api.get(f"{BASE_URL}/api/reports/{rid}")
        assert rg.status_code == 200
        assert rg.json()["id"] == rid

        # DELETE
        rdel = api.delete(f"{BASE_URL}/api/reports/{rid}")
        assert rdel.status_code == 200
        # confirm gone
        rcheck = api.get(f"{BASE_URL}/api/reports/{rid}")
        assert rcheck.status_code == 404


# ── Cascade delete & orphan guard ───────────────────────────────────────────

class TestCascadeDelete:
    def test_cascade_delete_removes_scenarios_and_reports(self, api):
        # New client
        pl = {"name": f"TEST_cascade_{uuid.uuid4().hex[:6]}",
              "address": "X", "nmi": "CASC" + uuid.uuid4().hex[:6].upper(),
              "site_type": "cafe"}
        cli = api.post(f"{BASE_URL}/api/clients", json=pl).json()
        cid = cli["id"]
        api.put(f"{BASE_URL}/api/clients/{cid}/tariff",
                json={"tariff_id": "tariff-agl-tou-vic"})

        # Generate 1 scenario
        jr = api.post(f"{BASE_URL}/api/clients/{cid}/scenarios/generate",
                      json={"count": 1}, timeout=15).json()
        jid = jr["job_id"]
        final = None
        for _ in range(60):
            time.sleep(3)
            j = api.get(f"{BASE_URL}/api/scenarios/jobs/{jid}", timeout=10).json()
            if j["status"] in ("done", "error"):
                final = j; break
        assert final and final["status"] == "done"
        sid = final["scenarios"][0]["id"]

        # Create report
        rep = api.post(f"{BASE_URL}/api/clients/{cid}/reports",
                       json={"title": "TEST_cascade_rep", "scenario_ids": [sid]}).json()
        rid = rep["id"]

        # DELETE client
        rd = api.delete(f"{BASE_URL}/api/clients/{cid}")
        assert rd.status_code == 200

        # scenarios for client should 404
        assert api.get(f"{BASE_URL}/api/clients/{cid}/scenarios").status_code == 404
        # report should be gone
        assert api.get(f"{BASE_URL}/api/reports/{rid}").status_code == 404

    def test_orphan_guard_when_client_deleted_during_generation(self, api):
        """Start a job, immediately delete the client. After job finishes, no scenario should be persisted with that client_id."""
        pl = {"name": f"TEST_orphan_{uuid.uuid4().hex[:6]}",
              "address": "X", "nmi": "ORPH" + uuid.uuid4().hex[:6].upper(),
              "site_type": "cafe"}
        cli = api.post(f"{BASE_URL}/api/clients", json=pl).json()
        cid = cli["id"]
        api.put(f"{BASE_URL}/api/clients/{cid}/tariff",
                json={"tariff_id": "tariff-agl-tou-vic"})

        jr = api.post(f"{BASE_URL}/api/clients/{cid}/scenarios/generate",
                      json={"count": 1}, timeout=15)
        assert jr.status_code == 202
        jid = jr.json()["job_id"]

        # Delete client right away (before job finishes)
        time.sleep(2)
        rd = api.delete(f"{BASE_URL}/api/clients/{cid}")
        assert rd.status_code == 200

        # Wait for job to terminate
        final = None
        for _ in range(60):
            time.sleep(3)
            j = api.get(f"{BASE_URL}/api/scenarios/jobs/{jid}", timeout=10).json()
            if j["status"] in ("done", "error"):
                final = j; break
        assert final is not None

        # Now check that no orphan scenarios exist for cid in the global store.
        # We don't have a global list endpoint, but we can check the demo client's list does not contain
        # anything pointing to cid, and that querying scenarios for cid is 404.
        rcheck = api.get(f"{BASE_URL}/api/clients/{cid}/scenarios")
        assert rcheck.status_code == 404
        # If job ended status=done despite client deleted, that's the guard failure.
        # Acceptable outcomes: status=error with 'Client deleted...' OR status=done with empty list.
        if final["status"] == "done":
            assert len(final.get("scenarios", [])) == 0, \
                f"orphan scenarios persisted after client delete: {final.get('scenarios')}"
        else:
            assert final["status"] == "error"
            assert "deleted" in (final.get("error", "").lower())
