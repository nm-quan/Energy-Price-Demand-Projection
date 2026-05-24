import React from "react";
import { fmtCurrency, fmtNumber, fmtPct } from "../lib/api";
import { TrendingDown, TrendingUp } from "lucide-react";

function StatCard({ label, value, sub, accent = false, testId }) {
  return (
    <div
      data-testid={testId}
      className={`flex flex-col justify-between rounded-xl border bg-white px-5 py-4 ${
        accent ? "border-accent/40 ring-1 ring-accent/15" : "border-line"
      }`}
    >
      <div className="text-[10.5px] uppercase tracking-[0.08em] font-semibold text-ink-mute">
        {label}
      </div>
      <div className="mt-2 tabnum text-[24px] font-bold tracking-tightish text-ink leading-none">
        {value}
      </div>
      <div className="mt-2 min-h-[16px]">{sub}</div>
    </div>
  );
}

export default function StatStrip({ rank }) {
  if (!rank) return null;
  const stats = rank.stats.active;
  const current = rank.current;
  const best = rank.best;
  const saving = rank.achievable_saving;
  const savingPct = current.shifted_cost > 0
    ? (saving / current.shifted_cost) * 100
    : 0;

  return (
    <div
      data-testid="stat-strip"
      className="grid grid-cols-2 md:grid-cols-4 gap-3"
    >
      <StatCard
        testId="stat-annual-spend"
        label="Annual spend · current plan"
        value={fmtCurrency(current.shifted_cost)}
        sub={
          <div className="text-[11.5px] text-ink-soft truncate">
            {current.plan.retailer} · {current.plan.name}
          </div>
        }
      />
      <StatCard
        testId="stat-best-plan-cost"
        label="Best available plan"
        value={fmtCurrency(best.shifted_cost)}
        accent
        sub={
          <div className="text-[11.5px] text-ink-soft truncate">
            {best.plan.retailer} · {best.plan.name}
          </div>
        }
      />
      <StatCard
        testId="stat-saving"
        label="Achievable saving"
        value={fmtCurrency(saving)}
        sub={
          <span className="inline-flex items-center gap-1 text-[11.5px] font-medium tabnum text-emerald-600">
            <TrendingDown size={12} strokeWidth={2.5} />
            {fmtPct(savingPct / 100, 1)} vs current
          </span>
        }
      />
      <StatCard
        testId="stat-peak-kw"
        label="Peak demand"
        value={`${fmtNumber(stats.peak_kw, 1)} kW`}
        sub={
          <span className="text-[11.5px] tabnum text-ink-mute">
            {fmtNumber(stats.annual_kwh / 1000, 1)} MWh/yr · LF {fmtNumber(stats.load_factor, 2)}
          </span>
        }
      />
    </div>
  );
}
