import React from "react";
import { fmtNumber } from "../lib/api";

function Sparkline({ values, color = "#5EEAD4" }) {
  if (!values || !values.length) return null;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const w = 90;
  const h = 22;
  const step = w / (values.length - 1);
  const pts = values
    .map((v, i) => {
      const x = i * step;
      const y = h - ((v - min) / Math.max(max - min, 1)) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} className="sparkline shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MeterCard({ meter, selected, onSelect }) {
  return (
    <button
      type="button"
      data-testid={`meter-card-${meter.id}`}
      onClick={(e) => onSelect(meter.id, e.shiftKey || e.metaKey || e.ctrlKey)}
      className={`w-full text-left rounded-lg border px-3.5 py-2.5 transition ${
        selected
          ? "border-mint/60 bg-white/10"
          : "border-white/10 bg-white/[0.04] hover:border-white/25 hover:bg-white/[0.07]"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13.5px] font-semibold text-white truncate">
            {meter.nickname}
          </div>
          <div className="mt-0.5 text-[11px] text-white/50 tabnum">
            NMI {meter.nmi}
          </div>
        </div>
        <span className="shrink-0 rounded-md bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/70">
          {meter.state}
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-white/50">Annual</div>
          <div className="tabnum text-[13px] font-semibold text-white">
            {fmtNumber(meter.annual_kwh / 1000, 1)} MWh
          </div>
        </div>
        <Sparkline values={meter.monthly_spend} color={selected ? "#C8E000" : "#5EEAD4"} />
      </div>
      <div className="mt-1.5 text-[11px] text-white/55 truncate">
        {meter.current_plan_label}
      </div>
    </button>
  );
}

export default function MeterRail({ meters, selectedIds, onSelect, onSelectAll }) {
  const allSelected = meters.length > 0 && selectedIds.length === meters.length;
  return (
    <aside data-testid="meter-rail" className="hidden lg:flex w-72 shrink-0 flex-col bg-forest text-white">
      <div className="px-5 pt-6 pb-3">
        <div className="text-[10px] uppercase tracking-[0.14em] font-semibold text-mint/70">
          Portfolio
        </div>
        <h2 className="mt-1 text-[17px] font-semibold tracking-tightish text-white">
          Cafe chain
        </h2>
        <p className="mt-1 text-[12px] text-white/50 leading-snug">
          {meters.length} sites · {selectedIds.length} selected · shift-click to add
        </p>
      </div>

      <div className="px-3 pb-2">
        <button
          data-testid="select-all-btn"
          type="button"
          onClick={onSelectAll}
          className={`w-full rounded-md border px-2 py-1.5 text-[11.5px] font-medium transition ${
            allSelected
              ? "border-mint/50 bg-mint/10 text-mint"
              : "border-white/15 bg-white/[0.04] text-white/80 hover:border-white/30 hover:bg-white/[0.08]"
          }`}
        >
          {allSelected ? "All sites selected" : "Aggregate all sites"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-6 space-y-2">
        {meters.map((m) => (
          <MeterCard
            key={m.id}
            meter={m}
            selected={selectedIds.includes(m.id)}
            onSelect={onSelect}
          />
        ))}
      </div>
    </aside>
  );
}
