import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Zap, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import MeterRail from "./MeterRail";
import StatStrip from "./StatStrip";
import LoadCanvas from "./LoadCanvas";
import ShiftLibrary from "./ShiftLibrary";
import PlanStrip from "./PlanStrip";

function applyAssetDeltas(baseline, assets, activeIds, { clampDisplay = false } = {}) {
  const out = baseline.slice();
  assets.forEach((a) => {
    if (!activeIds.includes(a.id)) return;
    if (a.current_start === a.default_start) return;
    for (let i = a.default_start; i < a.default_start + a.duration; i++) {
      if (i >= 0 && i < 48) out[i] = out[i] - a.power;
    }
    for (let i = a.current_start; i < a.current_start + a.duration; i++) {
      if (i >= 0 && i < 48) out[i] = out[i] + a.power;
    }
  });
  if (clampDisplay) return out.map((v) => Math.max(0, v));
  return out;
}

export default function Dashboard() {
  const [meters, setMeters] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [meter, setMeter] = useState(null);
  const [assets, setAssets] = useState([]);
  const [activeIds, setActiveIds] = useState([]);
  const [zones, setZones] = useState([]);
  const [spot, setSpot] = useState(null);
  const [rankData, setRankData] = useState(null);
  const [loading, setLoading] = useState(false);

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
      if (mRes.data.length) setSelectedId(mRes.data[0].id);
    })();
  }, []);

  // ── load selected meter ────────────────────────────────────────────
  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    api.get(`/meters/${selectedId}`).then((res) => {
      setMeter(res.data);
      const initialAssets = (res.data.shift_assets || []).map((a) => ({
        ...a,
        current_start: a.default_start,
      }));
      setAssets(initialAssets);
      // Default: activate the easy & medium ones so the canvas shows blocks immediately
      setActiveIds(initialAssets.filter((a) => a.feasibility !== "hard").map((a) => a.id));
      setLoading(false);
    });
  }, [selectedId]);

  const baseline = meter?.baseline_shape || Array(48).fill(0);
  const shape = useMemo(
    () => applyAssetDeltas(baseline, assets, activeIds, { clampDisplay: false }),
    [baseline, assets, activeIds]
  );
  const displayShape = useMemo(
    () => shape.map((v) => Math.max(0, v)),
    [shape]
  );
  const activeAssets = useMemo(
    () => assets.filter((a) => activeIds.includes(a.id)),
    [assets, activeIds]
  );

  // ── debounced ranking ───────────────────────────────────────────────
  const rankTimer = useRef(null);
  useEffect(() => {
    if (!selectedId || !shape.length) return;
    clearTimeout(rankTimer.current);
    rankTimer.current = setTimeout(async () => {
      try {
        const { data } = await api.post("/rank", {
          meter_id: selectedId,
          shape,
        });
        setRankData(data);
      } catch (e) {
        console.error("rank failed", e);
      }
    }, 120);
    return () => clearTimeout(rankTimer.current);
  }, [selectedId, shape]);

  const onAssetMove = useCallback((id, newStart) => {
    setAssets((prev) =>
      prev.map((a) => (a.id === id ? { ...a, current_start: newStart } : a))
    );
  }, []);

  const onToggle = useCallback((id) => {
    setActiveIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const onReset = useCallback((id) => {
    setAssets((prev) =>
      prev.map((a) => (a.id === id ? { ...a, current_start: a.default_start } : a))
    );
  }, []);

  const onResetAll = useCallback(() => {
    setAssets((prev) => prev.map((a) => ({ ...a, current_start: a.default_start })));
  }, []);

  const zone = useMemo(() => {
    if (!meter || !zones.length) return null;
    return zones.find((z) => z.code === meter.zone_code);
  }, [meter, zones]);

  const totalMoved = activeAssets.filter((a) => a.current_start !== a.default_start).length;

  return (
    <div className="flex min-h-screen">
      <MeterRail meters={meters} selectedId={selectedId} onSelect={setSelectedId} />

      <main className="flex-1 min-w-0 flex flex-col">
        {/* Top bar */}
        <header className="flex items-center justify-between gap-4 border-b border-line bg-white px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
              <Zap size={18} strokeWidth={2.5} />
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-ink-mute">
                Load Shape Lab
              </div>
              <div className="text-[15px] font-semibold tracking-tightish text-ink">
                {meter ? `${meter.nickname} · ${meter.zone_name}` : "Live load dashboard"}
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
            {/* Stat strip */}
            {rankData && <StatStrip stats={rankData.stats} ranked={rankData} />}

            {/* Canvas + library */}
            <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-4">
              {loading || !meter ? (
                <div className="rounded-xl border border-line bg-white h-[360px] flex items-center justify-center text-ink-mute text-[13px]">
                  Loading meter…
                </div>
              ) : (
                <LoadCanvas
                  shape={displayShape}
                  baseline={baseline}
                  zone={zone}
                  spot={spot}
                  activeAssets={activeAssets}
                  onAssetMove={onAssetMove}
                  onAssetRemove={onToggle}
                />
              )}
              <ShiftLibrary
                assets={assets}
                activeIds={activeIds}
                onToggle={onToggle}
                onReset={onReset}
              />
            </div>

            {/* Plan strip */}
            {rankData && (
              <PlanStrip
                ranked={rankData.ranked}
                currentId={rankData.current_plan_id}
                bestId={rankData.best.plan.id}
              />
            )}

            <footer className="pt-2 pb-6 text-[11px] text-ink-mute">
              Retailer plans modeled on the AER CDR public Energy Product Reference Data API.
              Spot price overlay sourced from VIC1 NEM half-hourly RRP averages (existing repo dataset).
              Demo mode · no auth.
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
