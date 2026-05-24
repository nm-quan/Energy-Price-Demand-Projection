import React from "react";
import { Sparkles, AlertTriangle } from "lucide-react";
import { fmtCurrency, fmtNumber } from "../lib/api";

function PlanCard({ entry, isCurrent, isBest, rank }) {
  const { plan, baseline_cost, shifted_cost, annual_delta, pct_delta } = entry;
  const improved = shifted_cost < baseline_cost;
  const accentColor = isBest ? "border-emerald-400 ring-1 ring-emerald-300/40 bg-emerald-50/30" :
                      isCurrent ? "border-accent ring-1 ring-accent/30 bg-accent/5" :
                      "border-line bg-white";
  return (
    <div
      data-testid={`plan-card-${plan.id}`}
      className={`flex w-[260px] shrink-0 flex-col gap-2 rounded-xl border px-4 py-3.5 ${accentColor}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[10.5px] uppercase tracking-wider font-semibold text-ink-mute">
              #{rank}
            </span>
            {isBest && (
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-emerald-700">
                <Sparkles size={9} /> Best
              </span>
            )}
            {isCurrent && (
              <span className="inline-flex items-center rounded-md bg-accent/10 px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-accent">
                Current
              </span>
            )}
          </div>
          <div className="mt-1 text-[13.5px] font-semibold text-ink leading-tight">
            {plan.retailer}
          </div>
          <div className="text-[12px] text-ink-soft truncate">{plan.name}</div>
        </div>
        <span className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-ink-soft">
          {plan.plan_type}
        </span>
      </div>

      <div className="mt-1 grid grid-cols-2 gap-2">
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-ink-mute">
            Original
          </div>
          <div className={`tabnum text-[14px] font-medium ${improved ? "text-ink-mute line-through" : "text-ink"}`}>
            {fmtCurrency(baseline_cost)}
          </div>
        </div>
        <div>
          <div className="text-[10.5px] uppercase tracking-wider text-ink-mute">
            With shift
          </div>
          <div className={`tabnum text-[14px] font-semibold ${improved ? "text-emerald-700" : "text-ink"}`}>
            {fmtCurrency(shifted_cost)}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] tabnum">
        <span className={`font-medium ${annual_delta < 0 ? "text-emerald-700" : annual_delta > 0 ? "text-rose-600" : "text-ink-mute"}`}>
          {annual_delta < 0 ? "-" : annual_delta > 0 ? "+" : ""}
          {fmtCurrency(Math.abs(annual_delta))}/yr ({pct_delta > 0 ? "+" : ""}
          {fmtNumber(pct_delta, 1)}%)
        </span>
      </div>

      <div className="mt-1 flex items-center gap-1 border-t border-line pt-2 text-[10.5px] text-ink-mute">
        <AlertTriangle size={10} className="text-amber-500" />
        <span className="truncate" title={plan.fragility}>{plan.fragility}</span>
      </div>
      <div className="text-[9.5px] text-ink-mute leading-tight">
        {plan.source}
      </div>
    </div>
  );
}

export default function PlanStrip({ ranked, currentId, bestId }) {
  if (!ranked || !ranked.length) return null;
  return (
    <section
      data-testid="plan-strip"
      className="rounded-xl border border-line bg-white"
    >
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div>
          <div className="eyebrow">Live retailer deals</div>
          <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
            Plans re-rank as you reshape the curve
          </h3>
        </div>
        <div className="text-[11px] text-ink-mute">
          {ranked.length} plans · sorted by annual cost
        </div>
      </div>
      <div className="overflow-x-auto no-scrollbar snap-strip px-5 pb-4">
        <div className="flex gap-3">
          {ranked.map((r, i) => (
            <PlanCard
              key={r.plan.id}
              entry={r}
              rank={i + 1}
              isCurrent={r.plan.id === currentId}
              isBest={r.plan.id === bestId}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
