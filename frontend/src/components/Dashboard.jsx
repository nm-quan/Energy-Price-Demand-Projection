import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Zap, Layers, RotateCcw } from "lucide-react";
import { api, fmtNumber } from "../lib/api";
import MeterRail from "./MeterRail";
import StatStrip from "./StatStrip";
import LoadCanvas from "./LoadCanvas";
import AppliancePanel from "./AppliancePanel";
import PlanStrip from "./PlanStrip";

const DEFAULT_APPLIANCES = [
  "fridges", "espresso", "ovens", "hvac",
  "lighting", "dishwasher", "hot-water", "misc",
];

export default function Dashboard() {
  const [meters, setMeters] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [activeAppliances, setActiveAppliances] = useState(DEFAULT_APPLIANCES);
  const [zones, setZones] = useState([]);
  const [rankData, setRankData] = useState(null);

  // ── boot ────────────────────────────────────────────────────────────
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

  // ── debounced rank request ─────────────────────────────────────────
  const rankTimer = useRef(null);
  useEffect(() => {
    if (!selectedIds.length) return;
    clearTimeout(rankTimer.current);
    rankTimer.current = setTimeout(async () => {
      try {
        const { data } = await api.post("/rank", {
          meter_ids: selectedIds,
          active_appliances: activeAppliances,
        });
        setRankData(data);
      } catch (e) {
        console.error("rank failed", e);
      }
    }, 120);
    return () => clearTimeout(rankTimer.current);
  }, [selectedIds, activeAppliances]);

  const onToggleAppliance = useCallback((id) => {
    setActiveAppliances((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }, []);

  const onResetAppliances = useCallback(() => {
    setActiveAppliances(DEFAULT_APPLIANCES);
  }, []);

  // ── derived ─────────────────────────────────────────────────────────
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
    // For the chart, return only active appliances IN order (preserves stack order).
    return rankData.appliance_breakdown.filter((a) => a.active || a.always_on);
  }, [rankData]);

  const isMulti = selectedIds.length > 1;
  const aggAnnualKwh = selectedMeters.reduce((s, m) => s + (m.annual_kwh || 0), 0);
  const title = isMulti
    ? `${selectedIds.length} sites · ${fmtNumber(aggAnnualKwh / 1000, 1)} MWh/yr`
    : selectedMeters[0]
      ? `${selectedMeters[0].nickname}`
      : "Loading…";

  const subtitle = isMulti
    ? "Aggregated portfolio · chain-wide load"
    : selectedMeters[0]
      ? `${selectedMeters[0].zone_name} · ${fmtNumber((selectedMeters[0].annual_kwh || 0) / 1000, 1)} MWh/yr`
      : "";

  const dirty = activeAppliances.length !== DEFAULT_APPLIANCES.length;

  return (
    <div className="flex min-h-screen">
      <MeterRail
        meters={meters}
        selectedIds={selectedIds}
        onSelect={selectMeter}
        onSelectAll={selectAll}
      />

      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-line bg-white px-7 py-4">
          <div className="flex items-center gap-3">
            <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white">
              {isMulti ? <Layers size={18} strokeWidth={2.5} /> : <Zap size={18} strokeWidth={2.5} />}
            </div>
            <div>
              <div className="text-[10.5px] uppercase tracking-[0.12em] font-semibold text-ink-mute">
                Load Shape Lab
              </div>
              <div className="text-[18px] font-bold tracking-tightish text-ink leading-tight">
                {title}
              </div>
              {subtitle && (
                <div className="text-[12px] text-ink-mute">{subtitle}</div>
              )}
            </div>
          </div>
          <button
            data-testid="reset-all-btn"
            type="button"
            onClick={onResetAppliances}
            disabled={!dirty}
            className={`inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-[12px] font-medium ${
              !dirty
                ? "text-ink-mute cursor-not-allowed"
                : "text-ink hover:border-ink-mute bg-white"
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
                activeIds={activeAppliances}
                onToggle={onToggleAppliance}
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
              Total load = sum of enabled appliance meters across selected sites.
              Retailer plans modeled on the AER CDR public Energy Product Reference Data API.
              Demo · no auth.
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
