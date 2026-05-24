# Load Shape Lab — PRD

## Original problem statement
A web app where a business owner sees their current energy load shape rendered as a draggable curve, experiments by physically shifting blocks of load around the day, and watches the achievable retailer deals improve or worsen in real time. Page 2 lets the user describe their business to Claude which turns it into structured shift scenarios. Page 3 shows optimised future state side-by-side.

> **Iteration 3 pivot (Jan 2026)**: User explicitly removed the drag-and-drop shift simulator and asked for a clean stacked appliance-meter view. New model: each appliance is a "meter" you can toggle on/off; total load = sum of enabled appliances. The page is now a clean appliance-decomposition + retailer-comparison dashboard.

## User decisions (Jan 2026)
- Data: synthetic per-archetype load curves + retailer plans modeled on AER CDR public dataset.
- AI integration (Page 2): user-supplied Anthropic key, cheapest model. Deferred.
- Scope for v0: Page 1 only (Live Load Dashboard).
- Auth: skip — demo mode with pre-loaded sample meters.
- Design: Linear-style, white background, multicolored chart.
- **Iter 3**: Cafe chain of 10 sites. Remove drag-drop. Each appliance = a toggleable meter. Stacked area chart with hover tooltip. Clean Termina-style layout.

## Personas
- Small-business owner (cafe chain operator) reviewing energy strategy.
- Energy broker / advisor running scenarios for clients.

## Architecture
- **Backend** (FastAPI @ `/app/backend`, port 8001 via supervisor)
  - `server.py` — endpoints under `/api/` prefix
  - `seed_data.py` — 10 cafe meters, 12 retailer plans, 4 TOU zones, 8 cafe appliances with profile + color, NEM spot avg
  - `cost_engine.py` — annual-cost calculator (TOU / Flat / Demand), shape stats
- **Frontend** (React 18 + Tailwind 3.4 + lucide-react @ `/app/frontend`, port 3000)
  - `Dashboard.jsx` — state: selectedIds[], activeAppliances[]; sends `{meter_ids, active_appliances}` to `/api/rank`
  - `LoadCanvas.jsx` — pure SVG stacked area chart with hover tooltip
  - `AppliancePanel.jsx` — 8 toggleable appliance chips (Fridges locked as always-on)
  - `MeterRail.jsx` / `StatStrip.jsx` / `PlanStrip.jsx`
- **Storage**: MongoDB available but unused — data is in-process.

## Implemented (latest)
- [x] 10-site cafe chain portfolio across VIC / NSW / QLD / SA distribution zones.
- [x] **Appliance-level load decomposition** — total = sum of 8 appliances (fridges always-on, then espresso, ovens, HVAC, lighting, dishwasher, hot-water, misc).
- [x] **Stacked area chart** with 8 distinct colors, clean dashed gridlines, hover tooltip showing per-appliance kW + total at the hovered bucket.
- [x] Subtle TOU period band washes (peak peach, shoulder cream, off-peak white) — present but not overpowering the curve colors.
- [x] **Appliance toggle panel** — each appliance has a color swatch, name, daily kWh, and on/off switch. Fridges locked. Toggling removes the band from the chart and re-ranks plans live.
- [x] Multi-meter aggregation — shift-click to add sites or "Aggregate all sites" button. Header reflects single vs aggregated state.
- [x] Stat strip simplified to 4 cards: Annual spend, Best plan, Achievable saving, Peak demand (with MWh/yr & load factor).
- [x] Retailer plan strip — 12 plans (TOU + Flat + Demand) ranked by sum-of-per-meter cost. Each card shows annual cost, retailer, plan type chip, fragility note, source.
- [x] Real AER CDR live check via `/api/refresh-cdr`.
- [x] Backend pytest **14/14 pass**.
- [x] Removed: drag-and-drop, shift library, easy/medium/hard tags, asset_positions parameter, lane assignment, all "shift" semantics.

## Wow numbers
- Single site (Brunswick East): $7,419/yr → switch to OVO saves $1,354/yr.
- 10-site chain aggregated: $60,407/yr → switch saves **$10,559/yr**.
- Turning off HVAC (e.g. modelling a solar/storage replacement): saves another ~$1,200/yr at Brunswick East.

## Backlog (P0)
- [ ] **Page 2** — plain-language → structured scenarios via Claude (user-supplied Anthropic key, cheapest Haiku 4.5).
- [ ] **Page 3** — optimised future-state side-by-side comparison view.

## Backlog (P1)
- [ ] Scale slider per appliance (currently binary on/off) — "what if my HVAC was 30% smaller / efficient?"
- [ ] Per-site appliance overrides (e.g. Glenelg has 2 fridges, Carlton has 4).
- [ ] Shareable scenario link ("send to your CFO").
- [ ] Persist scenarios in Mongo with auth.

## Backlog (P2)
- [ ] Real-time CDR auto-merge into ranking universe.
- [ ] Seasonal profile selector (summer/winter/shoulder × weekday/weekend) using existing repo CSVs.
- [ ] Lead-gen wedge: one-click "Request this plan" on the BEST card → brokerage referral.

## Key business hook (revenue / conversion)
The "$10,559 chain-wide saving" is the strongest sales artefact in the product. Adding a one-click "Send this scenario to your CFO" (shareable link with the savings number locked in) turns the analytic tool into a viral lead-gen wedge for a brokerage business.
