import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Zap, RefreshCw, Layers } from "lucide-react";
import { api, fmtNumber } from "../lib/api";
import MeterRail from "./MeterRail";
import StatStrip from "./StatStrip";
import LoadCanvas from "./LoadCanvas";
import ShiftLibrary from "./ShiftLibrary";
import PlanStrip from "./PlanStrip";

function applyAssetDeltas(baseline, shiftAssets, assetPositions, activeIds) {
  const out = baseline.slice();
  shiftAssets.forEach((a) => {
    if (!activeIds.includes(a.id)) return;
    const curStart = assetPositions[a.id] ?? a.default_start;
    if (curStart === a.default_start) return;
    for (let i = a.default_start; i < a.default_start + a.duration; i++) {
      if (i >= 0 && i < 48) out[i] = out[i] - a.power;
    }
    for (let i = curStart; i < curStart + a.duration; i++) {
      if (i >= 0 && i < 48) out[i] = out[i] + a.power;
    }
  });
  return out;
}

function sumShapes(shapes) {
  const out = new Array(48).fill(0);
  shapes.forEach((s) => s.forEach((v, i) => { out[i] += v; }));
  return out;
}

export default function Dashboard() {
  const [meters, setMeters] = useState([]);
  const [metersById, setMetersById] = useState({}); // id → full meter detail
  const [selectedIds, setSelectedIds] = useState([]);
  const [assetPositions, setAssetPositions] = useState({}); // assetId → currentStart
  const [activeIds, setActiveIds] = useState([]); // active asset ids
  const [zones, setZones] = useState([]);
  const [spot, setSpot] = useState(null);
  const [rankData, setRankData] = useState(null);

  // ── boot ────────────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      const [mRes, zRes, sRes] = await Promise.all([
        api.get("/meters"),
        api.get("/zones"),
        api.get("/spot"),
      ]);
      setMeters(mRes.data);
      setZones(zRes.data);
      setSpot(sRes.data);
      if (mRes.data.length) setSelectedIds([mRes.data[0].id]);
      // Eagerly fetch every meter's detail (small + parallel)
      const details = await Promise.all(
        mRes.data.map((m) => api.get(`/meters/${m.id}`).then((r) => r.data))
      );
      const map = {};
      details.forEach((d) => { map[d.id] = d; });
      setMetersById(map);
      // Initialise asset positions + active set from the first meter's assets
      if (details.length) {
        const first = details[0];
        const positions = {};
        first.shift_assets.forEach((a) => { positions[a.id] = a.default_start; });
        setAssetPositions(positions);
        setActiveIds(first.shift_assets.filter((a) => a.feasibility !== "hard").map((a) => a.id));
      }
    })();
  }, []);

  // ── selection helpers ──────────────────────────────────────────────
  const selectMeter = useCallback((id, additive) => {
    if (additive) {
      setSelectedIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    } else {
      setSelectedIds([id]);
    }
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(meters.map((m) => m.id));
  }, [meters]);

  // Ensure at least one meter selected
  useEffect(() => {
    if (selectedIds.length === 0 && meters.length) {
      setSelectedIds([meters[0].id]);
    }
  }, [selectedIds, meters]);

  // ── derived shapes (client-side optimistic) ────────────────────────
  const selectedMeters = useMemo(
    () => selectedIds.map((id) => metersById[id]).filter(Boolean),
    [selectedIds, metersById]
  );

  // The shift library is the union of shiftable assets across selected meters.
  // For our cafe chain they're identical, so just take the first.
  const shiftAssets = useMemo(() => {
    if (!selectedMeters.length) return [];
    return selectedMeters[0].shift_assets || [];
  }, [selectedMeters]);

  // Per-meter shapes
  const perMeterShapes = useMemo(() => {
    return selectedMeters.map((m) => {
      const baseline = m.baseline_shape || new Array(48).fill(0);
      const shifted = applyAssetDeltas(baseline, m.shift_assets || [], assetPositions, activeIds);
      return { baseline, shifted };
    });
  }, [selectedMeters, assetPositions, activeIds]);

  const aggBaseline = useMemo(
    () => sumShapes(perMeterShapes.map((p) => p.baseline)),
    [perMeterShapes]
  );
  const aggShifted = useMemo(
    () => sumShapes(perMeterShapes.map((p) => p.shifted)),
    [perMeterShapes]
  );
  const displayShape = useMemo(
    () => aggShifted.map((v) => Math.max(0, v)),
    [aggShifted]
  );

  const activeAssetsWithPositions = useMemo(
    () => shiftAssets
      .filter((a) => activeIds.includes(a.id))
      .map((a) => ({ ...a, current_start: assetPositions[a.id] ?? a.default_start })),
    [shiftAssets, activeIds, assetPositions]
  );

  // ── debounced ranking call ─────────────────────────────────────────
  const rankTimer = useRef(null);
  useEffect(() => {
    if (!selectedIds.length || !shiftAssets.length) return;
    clearTimeout(rankTimer.current);
    rankTimer.current = setTimeout(async () => {
      try {
        const { data } = await api.post("/rank", {
          meter_ids: selectedIds,
          asset_positions: assetPositions,
          active_assets: activeIds,
        });
        setRankData(data);
      } catch (e) {
        console.error("rank failed", e);
      }
    }, 140);
    return () => clearTimeout(rankTimer.current);
  }, [selectedIds, assetPositions, activeIds, shiftAssets.length]);

  // ── handlers ───────────────────────────────────────────────────────
  const onAssetMove = useCallback((id, newStart) => {
    setAssetPositions((prev) => ({ ...prev, [id]: newStart }));
  }, []);

  const onToggle = useCallback((id) => {
    setActiveIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const onReset = useCallback((id) => {
    const a = shiftAssets.find((x) => x.id === id);
    if (!a) return;
    setAssetPositions((prev) => ({ ...prev, [id]: a.default_start }));
  }, [shiftAssets]);

  const onResetAll = useCallback(() => {
    const positions = {};
    shiftAssets.forEach((a) => { positions[a.id] = a.default_start; });
    setAssetPositions(positions);
  }, [shiftAssets]);

  const zone = useMemo(() => {
    if (!selectedMeters.length || !zones.length) return null;
    // Use first meter's zone for the TOU band wash. In multi-zone aggregation
    // we still show a representative band (cleaner than a striped union).
    return zones.find((z) => z.code === selectedMeters[0].zone_code);
  }, [selectedMeters, zones]);

  const totalMoved = activeAssetsWithPositions.filter(
    (a) => a.current_start !== a.default_start
  ).length;

  const isMulti = selectedIds.length > 1;
  const aggAnnualKwh = selectedMeters.reduce((s, m) => s + (m.annual_kwh || 0), 0);
  const title = isMulti
    ? `Aggregated · ${selectedIds.length} sites · ${fmtNumber(aggAnnualKwh / 1000, 1)} MWh/yr`
    : selectedMeters[0]
      ? `${selectedMeters[0].nickname} · ${selectedMeters[0].zone_name}`
      : "Live load dashboard";

  return (
    <div className="flex min-h-screen">
      <MeterRail
        meters={meters}
        selectedIds={selectedIds}
        onSelect={selectMeter}
        onSelectAll={selectAll}
      />

      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-line bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
              {isMulti ? <Layers size={18} strokeWidth={2.5} /> : <Zap size={18} strokeWidth={2.5} />}
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-ink-mute">
                Load Shape Lab · cafe chain portfolio
              </div>
              <div className="text-[15px] font-semibold tracking-tightish text-ink">
                {title}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="reset-all-btn"
              type="button"
              onClick={onResetAll}
              disabled={totalMoved === 0}
              className={`inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-[12px] font-medium ${
                totalMoved === 0
                  ? "text-ink-mute cursor-not-allowed"
                  : "text-ink hover:border-ink-mute bg-white"
              }`}
            >
              <RefreshCw size={12} /> Reset shifts
            </button>
            <span className="text-[11.5px] tabnum text-ink-mute">
              {totalMoved} {totalMoved === 1 ? "block" : "blocks"} moved
            </span>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1500px] px-6 py-5 space-y-5">
            {isMulti && (
              <div
                data-testid="aggregation-banner"
                className="rounded-xl border border-accent/30 bg-accent/[0.04] px-4 py-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <Layers size={16} className="text-accent" strokeWidth={2.5} />
                  <div>
                    <div className="text-[12.5px] font-semibold text-ink">
                      Portfolio view · {selectedIds.length} sites aggregated
                    </div>
                    <div className="text-[11.5px] text-ink-mute">
                      Shifts apply chain-wide. Each plan is ranked by sum of per-site cost on its own distribution zone.
                    </div>
                  </div>
                </div>
                <div className="text-[11px] tabnum text-ink-soft">
                  {selectedMeters.map((m) => m.nickname).join(" · ")}
                </div>
              </div>
            )}

            {rankData && <StatStrip stats={rankData.stats} ranked={rankData} />}

            <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
              {!selectedMeters.length ? (
                <div className="rounded-xl border border-line bg-white h-[360px] flex items-center justify-center text-ink-mute text-[13px]">
                  Loading meters…
                </div>
              ) : (
                <LoadCanvas
                  shape={displayShape}
                  baseline={aggBaseline}
                  zone={zone}
                  spot={spot}
                  activeAssets={activeAssetsWithPositions}
                  onAssetMove={onAssetMove}
                  multiSiteCount={isMulti ? selectedIds.length : 0}
                />
              )}
              <ShiftLibrary
                assets={shiftAssets.map((a) => ({ ...a, current_start: assetPositions[a.id] ?? a.default_start }))}
                activeIds={activeIds}
                onToggle={onToggle}
                onReset={onReset}
                multiSiteCount={isMulti ? selectedIds.length : 0}
              />
            </div>

            {rankData && (
              <PlanStrip
                ranked={rankData.ranked}
                currentId={rankData.current_plan_id}
                bestId={rankData.best.plan.id}
              />
            )}

            <footer className="pt-2 pb-6 text-[11px] text-ink-mute">
              Retailer plans modeled on the AER CDR public Energy Product Reference Data API.
              Load shapes composed as a sum of appliance-level profiles (fridges, espresso, ovens, HVAC, lighting,
              dishwasher, hot water, misc) — shifts move only the shiftable components. Demo · no auth.
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
