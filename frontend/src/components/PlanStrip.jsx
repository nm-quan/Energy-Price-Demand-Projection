import React from "react";
import { Sparkles, ArrowDownRight } from "lucide-react";
import { fmtCurrency, fmtNumber } from "../lib/api";

function PlanCard({ entry, isCurrent, isBest, rank }) {
  const { plan, baseline_cost, shifted_cost, annual_delta, pct_delta } = entry;
  const improved = shifted_cost < baseline_cost;
  const borderCls = isBest
    ? "border-emerald-400 ring-1 ring-emerald-300/40 bg-emerald-50/30"
    : isCurrent
      ? "border-accent ring-1 ring-accent/30 bg-accent/[0.04]"
      : "border-line bg-white";

  return (
    <div
      data-testid={`plan-card-${plan.id}`}
      className={`flex w-[230px] shrink-0 flex-col gap-2.5 rounded-xl border px-4 py-3.5 ${borderCls}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span className="text-[10px] uppercase tracking-wider font-semibold text-ink-mute">
              #{rank}
            </span>
            {isBest && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-emerald-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-emerald-700">
                <Sparkles size={9} strokeWidth={2.5} /> Best
              </span>
            )}
            {isCurrent && !isBest && (
              <span className="inline-flex items-center rounded-md bg-accent/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent">
                Current
              </span>
            )}
          </div>
          <div className="text-[13.5px] font-semibold text-ink leading-tight truncate">
            {plan.retailer}
          </div>
          <div className="text-[11.5px] text-ink-mute truncate">{plan.name}</div>
        </div>
        <span className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wider text-ink-soft">
          {plan.plan_type}
        </span>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wider text-ink-mute font-semibold">
          Annual cost
        </div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <span className="tabnum text-[18px] font-bold text-ink leading-none">
            {fmtCurrency(shifted_cost)}
          </span>
          {improved && annual_delta !== 0 && (
            <span className="inline-flex items-center gap-0.5 text-[11px] font-medium tabnum text-emerald-600">
              <ArrowDownRight size={11} strokeWidth={2.5} />
              {fmtCurrency(Math.abs(annual_delta))}
            </span>
          )}
        </div>
        {improved && pct_delta !== 0 && (
          <div className="mt-0.5 text-[10.5px] tabnum text-emerald-700">
            {fmtNumber(pct_delta, 1)}% vs full load
          </div>
        )}
      </div>

      <div className="border-t border-line pt-2 text-[10.5px] text-ink-mute leading-tight">
        <div className="truncate" title={plan.fragility}>
          {plan.fragility}
        </div>
        <div className="mt-0.5 text-[9.5px] truncate">
          {plan.source}
        </div>
      </div>
    </div>
  );
}

export default function PlanStrip({ ranked, currentId, bestId }) {
  if (!ranked?.length) return null;
  return (
    <section data-testid="plan-strip" className="rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between px-6 pt-5 pb-2">
        <div>
          <div className="eyebrow">Live retailer deals</div>
          <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
            Retailer plans ranked
          </h3>
        </div>
        <div className="text-[11px] text-ink-mute">
          {ranked.length} plans · sorted by annual cost
        </div>
      </div>
      <div className="overflow-x-auto no-scrollbar snap-strip px-6 pb-5">
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
