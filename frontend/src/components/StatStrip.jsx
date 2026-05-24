import React from "react";
import { fmtCurrency, fmtNumber, fmtPct } from "../lib/api";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

function Delta({ value, suffix = "", invert = false }) {
  if (value === null || value === undefined || Math.abs(value) < 0.005) {
    return (
      <span className="inline-flex items-center gap-1 text-[11.5px] text-ink-mute">
        <Minus size={11} strokeWidth={2.5} /> no change
      </span>
    );
  }
  // For costs, lower is better → "down" = green. For load factor, higher is better.
  const better = invert ? value > 0 : value < 0;
  const Icon = value < 0 ? ArrowDownRight : ArrowUpRight;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11.5px] font-medium tabnum ${
        better ? "text-emerald-600" : "text-rose-600"
      }`}
    >
      <Icon size={12} strokeWidth={2.5} />
      {value > 0 ? "+" : ""}
      {typeof value === "number" ? fmtNumber(value, 1) : value}
      {suffix}
    </span>
  );
}

function StatCard({ label, value, sub, accent = false, testId }) {
  return (
    <div
      data-testid={testId}
      className={`flex flex-col justify-between rounded-xl border bg-white px-4 py-3.5 ${
        accent ? "border-accent/40 ring-1 ring-accent/15" : "border-line"
      }`}
    >
      <div className="text-[10.5px] uppercase tracking-wider text-ink-mute">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <div className="tabnum text-[20px] font-semibold tracking-tightish text-ink">
          {value}
        </div>
      </div>
      <div className="mt-1.5 min-h-[15px]">{sub}</div>
    </div>
  );
}

export default function StatStrip({ stats, ranked }) {
  if (!stats || !ranked) return null;
  const baseline = stats.baseline;
  const shifted = stats.shifted;
  const current = ranked.current;
  const best = ranked.best;
  const saving = ranked.achievable_saving;

  return (
    <div
      data-testid="stat-strip"
      className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5"
    >
      <StatCard
        testId="stat-annual-spend"
        label="Annual spend (current plan)"
        value={fmtCurrency(current.shifted_cost)}
        sub={
          <Delta
            value={current.shifted_cost - current.baseline_cost}
            suffix=" AUD/yr"
          />
        }
      />
      <StatCard
        testId="stat-best-plan-cost"
        label="Best available plan"
        value={fmtCurrency(best.shifted_cost)}
        sub={
          <div className="text-[11.5px] text-ink-soft truncate">
            {best.plan.retailer} · {best.plan.name}
          </div>
        }
        accent
      />
      <StatCard
        testId="stat-saving"
        label="Achievable saving"
        value={fmtCurrency(saving)}
        sub={
          <div className="text-[11.5px] tabnum text-emerald-600 font-medium">
            switch + shift
          </div>
        }
      />
      <StatCard
        testId="stat-load-factor"
        label="Load factor"
        value={fmtNumber(shifted.load_factor, 2)}
        sub={
          <Delta
            value={(shifted.load_factor - baseline.load_factor) * 100}
            suffix="pp"
            invert
          />
        }
      />
      <StatCard
        testId="stat-peak-kw"
        label="Peak demand"
        value={`${fmtNumber(shifted.peak_kw, 1)} kW`}
        sub={
          <Delta
            value={shifted.peak_kw - baseline.peak_kw}
            suffix=" kW"
          />
        }
      />
      <StatCard
        testId="stat-pct-peak"
        label="% usage in peak window"
        value={fmtPct(shifted.pct_in_peak, 1)}
        sub={
          <Delta
            value={(shifted.pct_in_peak - baseline.pct_in_peak) * 100}
            suffix="pp"
          />
        }
      />
    </div>
  );
}
