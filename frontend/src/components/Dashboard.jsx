import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import { api, fmtNumber } from "../lib/api";
import MeterRail from "./MeterRail";
import StatStrip from "./StatStrip";
import LoadCanvas from "./LoadCanvas";
import HistoricalCanvas from "./HistoricalCanvas";
import AppliancePanel from "./AppliancePanel";
import PlanStrip from "./PlanStrip";
import TimeframeSelector from "./TimeframeSelector";

const APPLIANCE_IDS = [
  "fridges", "espresso", "ovens", "hvac",
  "lighting", "dishwasher", "hot-water", "misc",
];

function defaultScales() {
  const o = {};
  APPLIANCE_IDS.forEach((id) => { o[id] = 1.0; });
  return o;
}

export default function Dashboard({ onNavigate = () => {} }) {
  const [meters, setMeters] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [scales, setScales] = useState(defaultScales);
  const [zones, setZones] = useState([]);
  const [rankData, setRankData] = useState(null);

  useEffect(() => {
    (async () => {
      const [mRes, zRes] = await Promise.all([
        api.get("/meters"),
        api.get("/zones"),
      ]);
      setMeters(mRes.data);
      setZones(zRes.data);
      if (mRes.data.length) setSelectedIds([mRes.data[0].id]);
    })();
  }, []);

  const selectMeter = useCallback((id, additive) => {
    if (additive) {
      setSelectedIds((prev) =>
        prev.includes(id)
          ? prev.filter((x) => x !== id) || [prev[0]]
          : [...prev, id]
      );
    } else {
      setSelectedIds([id]);
    }
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(meters.map((m) => m.id));
  }, [meters]);

  useEffect(() => {
    if (selectedIds.length === 0 && meters.length) {
      setSelectedIds([meters[0].id]);
    }
  }, [selectedIds, meters]);

  const rankTimer = useRef(null);
  useEffect(() => {
    if (!selectedIds.length) return;
    clearTimeout(rankTimer.current);
    rankTimer.current = setTimeout(async () => {
      try {
        const { data } = await api.post("/rank", {
          meter_ids: selectedIds,
          appliance_scales: scales,
        });
        setRankData(data);
      } catch (e) {
        console.error("rank failed", e);
      }
    }, 120);
    return () => clearTimeout(rankTimer.current);
  }, [selectedIds, scales]);

  const onScaleChange = useCallback((id, value) => {
    setScales((prev) => ({ ...prev, [id]: value }));
  }, []);

  const onResetAll = useCallback(() => {
    setScales(defaultScales());
  }, []);

  const selectedMeters = useMemo(
    () => selectedIds.map((id) => meters.find((m) => m.id === id)).filter(Boolean),
    [selectedIds, meters]
  );

  const zone = useMemo(() => {
    if (!rankData || !zones.length) return null;
    return zones.find((z) => z.code === rankData.agg_zone);
  }, [rankData, zones]);

  const activeApplianceObjs = useMemo(() => {
    if (!rankData) return [];
    return rankData.appliance_breakdown.filter((a) => a.active);
  }, [rankData]);

  const isMulti = selectedIds.length > 1;
  const aggAnnualKwh = selectedMeters.reduce((s, m) => s + (m.annual_kwh || 0), 0);
  const title = isMulti
    ? `${selectedIds.length} sites · ${fmtNumber(aggAnnualKwh / 1000, 1)} MWh/yr`
    : selectedMeters[0]
      ? selectedMeters[0].nickname
      : "Loading…";

  const dirty = APPLIANCE_IDS.some((id) => (scales[id] ?? 1.0) !== 1.0);

  return (
    <div className="flex min-h-screen">
      <MeterRail
        meters={meters}
        selectedIds={selectedIds}
        onSelect={selectMeter}
        onSelectAll={selectAll}
        page="dashboard"
        onNavigate={onNavigate}
      />

      <main className="flex-1 min-w-0 flex flex-col">
        {/* Termina-style dark teal header */}
        <header className="flex items-center justify-between gap-4 bg-forest px-7 py-4 text-white">
          <div>
            <div className="text-[20px] font-bold tracking-tightish leading-tight">
              {title}
            </div>
          </div>
          <button
            data-testid="reset-all-btn"
            type="button"
            onClick={onResetAll}
            disabled={!dirty}
            className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[12px] font-medium transition ${
              !dirty
                ? "border-white/15 text-white/30 cursor-not-allowed"
                : "border-white/30 text-white hover:bg-white/10"
            }`}
          >
            <RotateCcw size={12} strokeWidth={2.5} /> Reset appliances
          </button>
        </header>

        <div className="flex-1 overflow-y-auto bg-surface">
          <div className="mx-auto max-w-[1400px] px-7 py-6 space-y-5">
            {rankData && <StatStrip rank={rankData} />}

            <section className="rounded-xl border border-line bg-white">
              <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-2">
                <div>
                  <div className="eyebrow">Load curve · typical weekday</div>
                  <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
                    Stacked appliance load
                  </h3>
                </div>
                <div className="flex items-center gap-3 text-[10.5px] text-ink-mute">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block w-3.5 h-2 rounded-sm" style={{ background: "#fee2e2" }} />
                    Peak
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block w-3.5 h-2 rounded-sm" style={{ background: "#fef3c7" }} />
                    Shoulder
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block w-3.5 h-2 rounded-sm bg-white border border-line" />
                    Off-peak
                  </span>
                </div>
              </div>
              <div className="px-3 pb-4">
                {!rankData ? (
                  <div className="h-[360px] flex items-center justify-center text-ink-mute text-[13px]">
                    Loading load curve…
                  </div>
                ) : (
                  <LoadCanvas appliances={activeApplianceObjs} zone={zone} />
                )}
              </div>
            </section>

            {rankData && (
              <AppliancePanel
                appliances={rankData.appliance_breakdown}
                scales={scales}
                onChange={onScaleChange}
              />
            )}

            {rankData && (
              <PlanStrip
                ranked={rankData.ranked}
                currentId={rankData.current_plan_id}
                bestId={rankData.best.plan.id}
              />
            )}

            <footer className="pt-2 pb-8 text-[11px] text-ink-mute leading-relaxed">
              Retailer plans modeled on the AER CDR public Energy Product Reference Data API.
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
