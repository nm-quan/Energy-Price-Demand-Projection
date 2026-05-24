import React from "react";
import { fmtNumber } from "../lib/api";
import { CheckSquare } from "lucide-react";

function Sparkline({ values, color = "#1e40af" }) {
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
  const stateBadge = meter.state;
  return (
    <button
      type="button"
      data-testid={`meter-card-${meter.id}`}
      onClick={(e) => onSelect(meter.id, e.shiftKey || e.metaKey || e.ctrlKey)}
      className={`w-full text-left rounded-lg border px-3.5 py-2.5 transition ${
        selected
          ? "border-accent bg-accent/5 ring-1 ring-accent/30"
          : "border-line bg-white hover:border-ink-mute"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13.5px] font-semibold text-ink truncate">
            {meter.nickname}
          </div>
          <div className="mt-0.5 text-[11px] text-ink-mute tabnum">
            NMI {meter.nmi}
          </div>
        </div>
        <span className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-soft">
          {stateBadge}
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-ink-mute">Annual</div>
          <div className="tabnum text-[13px] font-semibold text-ink">
            {fmtNumber(meter.annual_kwh / 1000, 1)} MWh
          </div>
        </div>
        <Sparkline values={meter.monthly_spend} color={selected ? "#1e40af" : "#64748b"} />
      </div>
      <div className="mt-1.5 text-[11px] text-ink-soft truncate">
        {meter.current_plan_label}
      </div>
    </button>
  );
}

export default function MeterRail({ meters, selectedIds, onSelect, onSelectAll }) {
  const allSelected = meters.length > 0 && selectedIds.length === meters.length;
  return (
    <aside data-testid="meter-rail" className="hidden lg:flex w-72 shrink-0 flex-col border-r border-line bg-white">
      <div className="px-5 pt-6 pb-3">
        <div className="eyebrow">Portfolio</div>
        <h2 className="mt-1 text-[17px] font-semibold tracking-tightish text-ink">
          Cafe chain
        </h2>
        <p className="mt-1 text-[12px] text-ink-mute leading-snug">
          {meters.length} sites · {selectedIds.length} selected · shift-click to add
        </p>
      </div>

      <div className="px-3 pb-2">
        <button
          data-testid="select-all-btn"
          type="button"
          onClick={onSelectAll}
          className={`w-full inline-flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-[11.5px] font-medium transition ${
            allSelected
              ? "border-accent/40 bg-accent/10 text-accent"
              : "border-line bg-white text-ink-soft hover:border-ink-mute"
          }`}
        >
          <CheckSquare size={12} strokeWidth={2.5} />
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
