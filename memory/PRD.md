# Load Shape Lab — PRD

## Original problem statement
A web app where a business owner sees their current energy load shape rendered as a draggable curve, experiments by physically shifting blocks of load around the day, and watches the achievable retailer deals improve or worsen in real time. Page 2 lets the user describe their business to Claude which turns it into structured shift scenarios. Page 3 shows optimised future state side-by-side.

## User decisions (Jan 2026)
- Data: synthetic per-archetype load curves + retailer plans modeled on AER CDR public dataset.
- AI integration (Page 2): user-supplied Anthropic key, cheapest model. Deferred.
- Scope for v0: **Page 1 only** (Live Load Dashboard).
- Auth: skip — demo mode with pre-loaded sample meters.
- Design: Linear-style, white background, multicolored chart.

## Personas
- Small-business owner (cafe / pub / retail / office / warehouse operator) reviewing energy strategy.
- Energy broker / advisor running scenarios for clients.

## Architecture
- **Backend** (FastAPI @ `/app/backend`, served on :8001 via supervisor)
  - `server.py` — endpoints under `/api/` prefix
  - `seed_data.py` — 5 sample meters, 12 retailer plans, 4 TOU zones, 5 archetype curves, NEM spot avg
  - `cost_engine.py` — annual-cost calculator (TOU / Flat / Demand), shape stats
- **Frontend** (React 18 + Tailwind 3.4 + @dnd-kit + lucide-react @ `/app/frontend`, served on :3000)
  - `Dashboard.jsx` — orchestrator (data fetch, debounced /api/rank)
  - `LoadCanvas.jsx` — SVG chart, TOU bands, baseline ghost, shifted area, NEM spot overlay, draggable blocks with lane assignment
  - `MeterRail.jsx` / `StatStrip.jsx` / `ShiftLibrary.jsx` / `PlanStrip.jsx`
- **Storage**: MongoDB available (MONGO_URL/DB_NAME) but unused in MVP — data is in-process.

## Implemented (2026-01-24 → 2026-01-24 iter 2)
- [x] Pre-loaded 10-site **cafe chain** portfolio spanning 4 distribution zones (Citipower VIC, Ausgrid NSW, Energex QLD, SAPN SA). Annual usage 16.4–31.4 MWh per site.
- [x] **Appliance-level load decomposition** — each meter's curve is the sum of 8 named appliances (fridges, espresso, ovens, HVAC, lighting, dishwasher, hot-water, misc). Only HVAC, dishwasher, hot-water are shiftable; the rest contribute fixed baseline.
- [x] **Multi-meter aggregation** — shift-click a meter card to add to selection; "Aggregate all sites" button selects all 10. Aggregation banner lists every site; shifts apply chain-wide; plans ranked by sum of per-meter cost on each meter's own zone.
- [x] 48-bucket TOU period band overlays, zone-aware (peak red, shoulder amber, off-peak green).
- [x] NEM spot price overlay (real VIC1 averaged half-hourly RRP).
- [x] Draggable shift blocks with feasibility tags (easy/medium/hard), hardware-cost estimates, and constraint notes.
- [x] Live stat strip: annual spend, best plan cost, achievable saving, load factor, peak kW, % peak usage. Updates live as the user drags.
- [x] Bottom retailer-plan strip — 12 plans (TOU + Flat + Demand) modeled on AER CDR public dataset; re-ranks live; original (strikethrough) vs shifted with annual delta and % change.
- [x] Cost engine with TOU/Flat/Demand modes; peak-kW clamp guard for Demand plans.
- [x] Best-effort `/api/refresh-cdr` endpoint (live AER CDR public API check, returns per-retailer status).
- [x] Reset-per-asset and Reset-all-shifts controls.
- [x] Backend pytest suite **14/14 pass**, frontend e2e validated by testing agent (iterations 1 + 2 — 0 issues).
- [x] Aggregate single-shift saving scales linearly with chain size (verified test: 10× single-site delta).

## Wow numbers
- Single site (Brunswick East): **$1,354/yr** achievable by switching plan.
- 10-site chain aggregated: **$12,872/yr** by switching plan + extra **$2,310/yr** by shifting dishwasher cycles chain-wide.

## Backlog (P0)
- [ ] **Page 2** — Plain-language → structured shift scenarios via Claude (user-supplied Anthropic key, cheapest model).
- [ ] **Page 3** — Optimised future state with side-by-side comparison (original vs optimised load, original vs optimised cost, negotiating leverage badge).

## Backlog (P1)
- [ ] Multi-meter aggregation (shift-multi-select on meter rail → collective PPA view).
- [ ] Persist user sessions / saved scenarios in MongoDB.
- [ ] Auto-merge live AER CDR pulls into ranking universe (currently fetch-only).
- [ ] Seasonal profile selector (summer/winter/shoulder × weekday/weekend) — leverage the existing repo's processed CSVs.

## Backlog (P2)
- [ ] Export shifted-scenario PDF / share link.
- [ ] Lead-gen wedge: "send to your retailer for an indicative quote".
- [ ] Onboarding for real CDR consumer data (with consent flow).

## Key business hook (revenue / conversion)
The Best-plan card already shows a one-click switch CTA opportunity — a thin "Request this plan" button on the top-ranked card converts the demo into a brokerage lead. Next iteration could attach a referral fee per switch.
