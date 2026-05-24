import React from "react";
import { Check, Clock } from "lucide-react";
import { fmtCurrency, bucketToTime } from "../lib/api";

const FEAS = {
  easy: { label: "Easy", color: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  medium: { label: "Medium", color: "text-amber-700 bg-amber-50 border-amber-200" },
  hard: { label: "Hard", color: "text-rose-700 bg-rose-50 border-rose-200" },
};

function AssetRow({ asset, active, onToggle, onReset }) {
  const f = FEAS[asset.feasibility] || FEAS.medium;
  const moved = asset.current_start !== asset.default_start;
  return (
    <div
      data-testid={`asset-row-${asset.id}`}
      className={`rounded-lg border p-3 transition ${
        active ? "border-accent/40 bg-accent/[0.03]" : "border-line bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold ${f.color}`}
            >
              {f.label}
            </span>
            <div className="truncate text-[13px] font-semibold text-ink">
              {asset.label}
            </div>
          </div>
          <div className="mt-1.5 text-[11.5px] text-ink-mute leading-snug">
            {asset.note}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] tabnum text-ink-soft">
            <span>{asset.power} kW · {asset.duration * 30} min</span>
            <span className="text-ink-mute">·</span>
            <span className="inline-flex items-center gap-1">
              <Clock size={11} className="text-ink-mute" />
              {bucketToTime(asset.current_start)}–{bucketToTime(asset.current_start + asset.duration)}
            </span>
            {asset.hardware_cost > 0 && (
              <>
                <span className="text-ink-mute">·</span>
                <span>~{fmtCurrency(asset.hardware_cost)} hw</span>
              </>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <button
            data-testid={`asset-toggle-${asset.id}`}
            onClick={() => onToggle(asset.id)}
            type="button"
            className={`inline-flex h-6 w-6 items-center justify-center rounded-md border transition ${
              active
                ? "border-accent bg-accent text-white"
                : "border-line bg-white text-ink-mute hover:border-ink-mute"
            }`}
            aria-label={active ? "Remove from canvas" : "Add to canvas"}
            title={active ? "Remove from canvas" : "Add to canvas"}
          >
            <Check size={13} strokeWidth={3} />
          </button>
          {active && moved && (
            <button
              data-testid={`asset-reset-${asset.id}`}
              type="button"
              onClick={() => onReset(asset.id)}
              className="text-[10.5px] font-medium text-ink-mute hover:text-accent"
            >
              reset
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ShiftLibrary({ assets, activeIds, onToggle, onReset }) {
  if (!assets || !assets.length) return null;
  return (
    <aside
      data-testid="shift-library"
      className="rounded-xl border border-line bg-white"
    >
      <div className="px-4 pt-4 pb-2">
        <div className="eyebrow">Shift library</div>
        <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
          Shiftable assets
        </h3>
        <p className="mt-1 text-[11.5px] text-ink-mute">
          Toggle on, drag the block on the canvas to a cheaper window.
        </p>
      </div>
      <div className="space-y-2 px-3 pb-3">
        {assets.map((a) => (
          <AssetRow
            key={a.id}
            asset={a}
            active={activeIds.includes(a.id)}
            onToggle={onToggle}
            onReset={onReset}
          />
        ))}
      </div>
    </aside>
  );
}
