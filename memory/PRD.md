# EnergyScope — Energy Broker Tool (PRD)

## Original Problem Statement (summary)
A broker tool where brokers create client sites, upload interval CSV data, assign tariffs, view baseline analyses, and run load-shift scenarios to surface savings. Four enhancements requested over the existing FastAPI + React app:

1. **Pre-loaded synthetic demo client** — seed `client-demo-001` "Brunswick East Café" + tariff `tariff-agl-tou-vic` + 17,520 half-hourly synthetic intervals so the app is never blank on first run.
2. **Termina palette + stacked area chart** — restore forest (#14532d) / lime (#84cc16) / mint (#f0fdf4) palette; replace single-line load chart with 8-appliance stacked-area chart + TOU band overlays; add appliance toggle + 0–200% scale slider chips.
3. **Claude-generated dynamic scenarios** — new `POST /api/clients/{id}/scenarios/generate` endpoint that drives `claude-sonnet-4-6` through a tool_use loop calling the existing `run_scenario` math; returns scenarios ranked by savings. Frontend redesigned around "Generate / Regenerate / Ask follow-up" UX. Graceful fallback to legacy 4-scenario engine.
4. **First-run UX** — demo client first in list with DEMO badge; dismissible banner on baseline; scenarios auto-trigger on first visit (sessionStorage cached).

Stack: FastAPI on :8001, React 18 + Tailwind on :3000, JSON-file in-memory data store. No authentication.

## Architecture
- **Backend** `/app/backend/`
  - `server.py` — FastAPI routes (clients, baseline, tariffs, scenarios). Startup seeds demo + pre-warms Claude scenarios in a background thread. Added `_split_appliance_curves` for the stacked-area chart payload.
  - `scenario_claude.py` (new) — Anthropic SDK tool-use loop. `generate_scenarios` + `fallback_scenarios` helpers. Drops net-cost scenarios, sorts by `total_low` desc.
  - `data_store.py` — JSON persistence + `seed_demo_data()` + AGL TOU VIC tariff. Path fixed to `/app/backend/data_store.json`.
  - `scenario_engine.py` — Unchanged math (`apply_pre_cool_hvac`, `apply_battery_dispatch`, `apply_demand_cap`, `apply_time_shift`); invoked through Claude tool.
  - `.env` — `ANTHROPIC_API_KEY` (user-provided), `MONGO_URL`, `DB_NAME` (unused).
- **Frontend** `/app/frontend/src/`
  - `App.js` — Sidebar redesigned with bg-forest + lime active state.
  - `pages/ClientList.jsx` — Demo card first with lime DEMO badge.
  - `pages/BaselineAnalysis.jsx` — Demo banner, stacked-area chart integration, appliance panel.
  - `pages/ScenarioBuilder.jsx` — Claude generate flow + auto-trigger + follow-up form.
  - `components/StackedAreaChart.jsx` — 8 appliance layers + 3 TOU band overlays.
  - `components/AppliancePanel.jsx` — Toggle chips with 0–200 % sliders.
  - `lib/api.js` — Uses `REACT_APP_BACKEND_URL`, exposes `generateScenarios`.
  - `tailwind.config.js` — Forest / lime / mint palette.

## User Personas
- **Energy broker** — primary user. Wants instant evidence of savings, defensible numbers for billing, indicative ranges for contract negotiations, and bespoke recommendations per site type.
- **Prospective broker / first-time visitor** — needs a demo experience without friction (handled by the pre-seeded Brunswick East Café demo).

## Core Requirements
- Demo client present on first launch, never blank.
- Forest / lime / mint palette across Baseline + Scenarios.
- 8-layer stacked area chart with TOU bands, hover tooltip, appliance toggle/scale sliders.
- Claude-ranked scenarios with billing-defensible + indicative ranges, follow-up prompting, regenerate.
- Graceful fallback when API key missing or Claude fails.
- All existing flows (client wizard, CSV upload, tariff library, report, print) untouched.

## Implemented (May 2026)
- ✅ **Change 1** – Demo client (`client-demo-001`) + AGL TOU VIC tariff + 17,520 synthetic intervals seeded on first startup (deterministic random seed).
- ✅ **Change 2** – Tailwind palette, sidebar, action buttons, page bg, StackedAreaChart with 8 appliance layers + 3 TOU overlays, AppliancePanel with toggle + 0–200 % sliders.
- ✅ **Change 3** – `POST /api/clients/{id}/scenarios/generate`, Claude tool_use loop (`claude-sonnet-4-6`, max_turns=8, max_tokens=2048), pre-warm at startup, cached default response per client, fallback header + legacy 4-scenario fallback, frontend Generate/Regenerate/Follow-up UI, sessionStorage caching.
- ✅ **Change 4** – DEMO badge in list, dismissible demo banner on baseline, auto-trigger generate on first scenarios load.
- ✅ Path fixes (`DATA_FILE`), axios baseURL→ `REACT_APP_BACKEND_URL`, `python-dotenv` loaded so backend reads `ANTHROPIC_API_KEY`.
- ✅ Backend pytest suite: 9/9 pass (`/app/backend/tests/test_energy_broker_api.py`).
- ✅ Frontend E2E (testing agent): clients → baseline → scenarios verified on production URL; no JS errors; all data-testids present; sliders/toggles/follow-up form functional.

## Backlog (P1/P2)
- **P1** — Mark net-cost scenarios in UI (currently dropped); show "0 saving scenarios found" state when all filtered out.
- **P1** — Stream Claude response to client (Server-Sent Events) so progress is visible during 30 s fresh generation.
- **P2** — Persist appliance toggle/scale state per client in localStorage.
- **P2** — Add print/export for the Scenarios page (currently only `Report` page).
- **P2** — Add scenario comparison side-by-side view.
- **P2** — Make `/scenarios/generate` async (FastAPI async + `run_in_threadpool`) to free event loop during Claude blocking call.
- **P2** — Replace daemon-thread prewarm with proper async startup task + lock.
- **P3** — Move scenario JSON cache out of `data_store.client_scenarios` to dedicated `client_claude_cache` namespace.
- **P3** — Cache invalidation when tariff or interval data changes for a client.

## Files Created or Touched
- New: `/app/backend/scenario_claude.py`, `/app/frontend/src/components/StackedAreaChart.jsx`, `/app/frontend/src/components/AppliancePanel.jsx`, `/app/backend/tests/test_energy_broker_api.py`.
- Major edits: `/app/backend/server.py`, `/app/backend/data_store.py`, `/app/frontend/src/App.js`, `/app/frontend/src/pages/ClientList.jsx`, `/app/frontend/src/pages/BaselineAnalysis.jsx`, `/app/frontend/src/pages/ScenarioBuilder.jsx`, `/app/frontend/src/lib/api.js`, `/app/frontend/tailwind.config.js`, `/app/backend/.env`.

## Notes
- No authentication — explicit per problem statement.
- Cloudflare proxy has a ~60 s timeout, so Claude generation must complete under that. Pre-warm + cache make the demo instant; follow-up calls take 25–35 s.
- Tariff `tariff-agl-tou-vic` is seeded with representative VIC business rates (peak 42.87 c/kWh, shoulder 28.54 c/kWh, off-peak 19.25 c/kWh, supply 109.45 c/day).
