import React from "react";
import { fmtNumber } from "../lib/api";
import { Lock } from "lucide-react";

function ApplianceChip({ appliance, active, onToggle }) {
  const locked = appliance.always_on;
  const isOn = active || locked;
  return (
    <button
      type="button"
      data-testid={`appliance-chip-${appliance.id}`}
      onClick={() => !locked && onToggle(appliance.id)}
      disabled={locked}
      title={appliance.note}
      className={`group flex items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition ${
        isOn
          ? "border-line bg-white hover:border-ink-mute"
          : "border-line bg-surface opacity-60 hover:opacity-100"
      } ${locked ? "cursor-default" : "cursor-pointer"}`}
    >
      <span
        className="inline-block h-3 w-3 shrink-0 rounded-sm transition-opacity"
        style={{
          background: appliance.color,
          opacity: isOn ? 1 : 0.25,
        }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <div className="truncate text-[12.5px] font-semibold text-ink leading-tight">
            {appliance.name}
          </div>
          {locked && <Lock size={9} className="shrink-0 text-ink-mute" strokeWidth={2.5} />}
        </div>
        <div className="mt-0.5 text-[10.5px] tabnum text-ink-mute">
          {fmtNumber(appliance.daily_kwh, 1)} kWh/day
        </div>
      </div>
      <div
        className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
          isOn ? "bg-accent" : "bg-slate-300"
        }`}
      >
        <span
          className={`absolute top-0.5 inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform ${
            isOn ? "translate-x-3.5" : "translate-x-0.5"
          }`}
        />
      </div>
    </button>
  );
}

export default function AppliancePanel({ appliances, activeIds, onToggle }) {
  if (!appliances?.length) return null;
  return (
    <div data-testid="appliance-panel" className="rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div>
          <div className="eyebrow">Load decomposition</div>
          <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
            Appliance meters
          </h3>
        </div>
        <div className="text-[11px] text-ink-mute">
          Total load = sum of enabled appliances
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 px-3 pb-3">
        {appliances.map((a) => (
          <ApplianceChip
            key={a.id}
            appliance={a}
            active={activeIds.includes(a.id) || a.always_on}
            onToggle={onToggle}
          />
        ))}
      </div>
    </div>
  );
}
