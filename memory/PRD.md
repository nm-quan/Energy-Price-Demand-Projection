# EnergyScope v2 — Energy Broker Tool (PRD)

## Original Problem Statement
Major rewrite addressing 5 user requests:
1. **Wipe prebuilt scenarios.** User picks N to generate; each saved to DB. Built-in hint bubbles. Side panel showing what the agent kept in memory.
2. **Reports** start blank. Bundle one-or-many scenarios into a saved report; export to PDF for client sharing.
3. **Baseline appliance sliders** trigger live recalc of metrics + cost.
4. **Scenario costs must be specific.** Show negotiation metrics, retailer comparison, per-appliance before/after as real frontend components — not raw JSON. Give Claude proper tools.
5. **UI matches termina.io** — dark forest sidebar, cream canvas, lime accents, violet primary CTA.
6. (Follow-up) Remove all auth.

## Architecture
- **Backend** `/app/backend/`
  - `server.py` — FastAPI; no auth, no demo seeding, baseline recalc endpoint, scenarios + reports CRUD.
  - `scenario_claude.py` — 4-tool Claude agent: `analyze_load_profile`, `compare_retailers`, `simulate_appliance_change`, `commit_scenario`. Emits `scenarios[]` + `agent_memory[]`.
  - `data_store.py` — JSON file store; only retailer tariffs seeded (AGL, Origin, EA, Alinta, Red). Scenario + report stores added.
  - `baseline_engine.py`, `scenario_engine.py`, `interval_parser.py` — unchanged math.
  - `.env` — `ANTHROPIC_API_KEY` from user.
- **Frontend** `/app/frontend/src/`
  - `App.js` — new Termina-styled layout (forest sidebar, cream canvas).
  - `tailwind.config.js` + `index.css` — full palette + font system (Fraunces display, Inter Tight body, JetBrains Mono memo).
  - `pages/ClientList.jsx` — no demo specialcase; cream cards.
  - `pages/ClientSetup.jsx` — 3-step wizard, Termina colors.
  - `pages/BaselineAnalysis.jsx` — debounced live recalc on appliance scale changes.
  - `pages/ScenarioBuilder.jsx` — generator card (N count + hint bubbles), scenario cards with selection checkbox, expanded view with `ApplianceChangeBars`, `RetailerNegotiation`, hourly load overlay; `Agent Memory` side rail.
  - `pages/Report.jsx` — left rail with saved reports list, right pane `ReportDocument`, PDF export via jspdf + html2canvas.
  - `components/StackedAreaChart.jsx`, `components/AppliancePanel.jsx` — restyled.
  - `lib/api.js` — full new API surface.

## API Endpoints (v2)
- `GET /api/health`
- Clients: `GET/POST /api/clients`, `GET/DELETE /api/clients/{id}`
- Intervals: `POST /api/clients/{id}/upload`, `GET /api/clients/{id}/intervals/summary`
- Tariffs: `GET/POST /api/tariffs`, `PUT /api/clients/{id}/tariff`
- Baseline: `GET /api/clients/{id}/baseline`, `POST /api/clients/{id}/baseline/recalc`
- Scenarios: `POST /api/clients/{id}/scenarios/generate` (body: `{count, extra_instruction}`), `GET/DELETE /api/clients/{id}/scenarios`, `DELETE /api/scenarios/{sid}`
- Reports: `POST/GET /api/clients/{id}/reports`, `GET/DELETE /api/reports/{rid}`

## User Personas
- **Energy broker** — primary user. Wants distinctive savings stories per site with concrete numbers and retailer leverage points for client conversations.

## Implemented (May 2026, v2)
- ✅ Termina palette: forest #0d2e2a sidebar, cream #f5f1e8 canvas, lime #c4e94a accents, violet #5b4bff primary, Fraunces display font.
- ✅ No auth, no demo client, no pre-warm.
- ✅ Live baseline recalc with debounced 350ms POST on slider change.
- ✅ Claude 4-tool agent loop with structured `appliance_changes`, retailer winner, negotiation levers, agent_memory bullets.
- ✅ Scenarios persisted as DB records with stable ids; agent memory stored per scenario.
- ✅ Reports CRUD; PDF export client-side.
- ✅ Hint bubbles + N-count selector on Scenarios page.
- ✅ Tested end-to-end via curl: client create → baseline → generate(2) → list scenarios → create report → PDF endpoint.

## Backlog (P1/P2)
- **P1** — SSE stream Claude turns so the UI can show "Calling analyze_load_profile…" progress.
- **P1** — Surface retailer comparison table inside scenario card (currently only shown via levers).
- **P2** — Async FastAPI for scenarios/generate (Claude call blocks event loop ~2 min for N=2).
- **P2** — Per-client localStorage for last-used N and focus hints.
- **P2** — Edit/rename saved reports.

## Notes
- Claude model: `claude-sonnet-4-5`. Each scenario costs ~30 tool calls; N=2 ≈ 2 minutes wall-clock.
- All scenario math runs server-side via the existing `scenario_engine` invoked from `simulate_appliance_change`.
- Cloudflare proxy has ~60 s timeout — for N≥3, expect ≥90 s; user-side spinner shows progress.
