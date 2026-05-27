import React, { useState } from 'react';
import { TrendingDown, TrendingUp, Minus, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';
import HourlyLineChart from './HourlyLineChart';
import { APPLIANCE_LAYERS } from './StackedAreaChart';
import { fmtCurrency, fmtNumber } from '../lib/api';

// ── Headline ──────────────────────────────────────────────────────────────────
function HeadlineBlock({ block }) {
  return (
    <h2 className="font-display text-2xl text-forest-900 leading-snug">
      {block.text}
    </h2>
  );
}

// ── Text / insight ────────────────────────────────────────────────────────────
function TextBlock({ block }) {
  const v = block.variant || 'body';
  if (v === 'callout') {
    return (
      <div className="bg-lime/20 border border-lime/40 rounded-xl px-4 py-3">
        <p className="text-sm text-forest-900 leading-relaxed">{block.text}</p>
      </div>
    );
  }
  if (v === 'warning') {
    return (
      <div className="flex gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
        <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-amber-800 leading-relaxed">{block.text}</p>
      </div>
    );
  }
  return <p className="text-sm text-ink-soft leading-relaxed">{block.text}</p>;
}

// ── KPI row ───────────────────────────────────────────────────────────────────
function KpiRowBlock({ block }) {
  const metrics = block.metrics || [];
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${Math.min(metrics.length, 4)}, 1fr)` }}
    >
      {metrics.map((m, i) => {
        const Icon = m.dir === 'down' ? TrendingDown : m.dir === 'up' ? TrendingUp : Minus;
        const dColor = m.dir === 'down' ? 'text-forest-700' : m.dir === 'up' ? 'text-red-600' : 'text-ink-mute';
        return (
          <div key={i} className="bg-cream-50 border border-line rounded-xl p-4">
            <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">{m.label}</p>
            <div className="flex items-baseline gap-1 flex-wrap">
              <span className="font-display text-2xl text-forest-900 tabnum">{m.value}</span>
              {m.unit && <span className="text-xs text-ink-mute">{m.unit}</span>}
            </div>
            {m.delta && (
              <div className={`flex items-center gap-1 mt-1 text-xs ${dColor}`}>
                <Icon size={12} />
                <span>{m.delta}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Load chart ────────────────────────────────────────────────────────────────
function LoadChartBlock({ block }) {
  const appColor = block.appliance
    ? (APPLIANCE_LAYERS.find(l => l.key === block.appliance)?.color || '#5b4bff')
    : undefined;

  return (
    <div className="bg-cream-50 border border-line rounded-xl p-4">
      {block.title && (
        <p className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">{block.title}</p>
      )}
      <HourlyLineChart
        series={block.series || []}
        overlay={block.overlay || null}
        overlayColor={appColor}
        height={220}
      />
      <div className="flex items-center gap-5 mt-2 px-1">
        <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
          <span className="inline-block w-5 border-t-2 border-forest-900 opacity-70" />
          Total demand
        </span>
        {block.appliance && (
          <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
            <span className="inline-block w-5 border-t-2" style={{ borderColor: appColor }} />
            {block.appliance}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Scenario ──────────────────────────────────────────────────────────────────
function ScenarioBlock({ block }) {
  const [expanded, setExpanded] = useState(false);

  const appColor = block.appliance
    ? (APPLIANCE_LAYERS.find(l => l.key === block.appliance)?.color || '#5b4bff')
    : '#5b4bff';

  if (block.error) {
    return (
      <div className="flex gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
        <AlertTriangle size={15} className="text-red-500 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-red-700">Scenario error: {block.error}</p>
      </div>
    );
  }

  const savLow  = block.savings_annual_low  || 0;
  const savHigh = block.savings_annual_high || 0;
  const rc = block.retailer_comparison || {};
  const bestRetailer = rc.best;
  const actionLabel =
    block.action === 'shift_window' ? 'shifted off-peak' :
    block.action === 'set_off'      ? 'reduced in peak' :
    'scaled down';

  return (
    <div className="bg-cream-50 border border-line rounded-xl overflow-hidden">
      {/* Collapsed header */}
      <button
        type="button"
        className="w-full text-left p-4 hover:bg-cream-100/60 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <span className="text-[10px] uppercase tracking-wider text-ink-mute">Scenario</span>
            <h3 className="font-display text-lg text-forest-900 leading-snug">
              {block.name || `${block.appliance} Load Shift`}
            </h3>
            <p className="text-xs text-ink-soft mt-0.5">
              <span className="font-medium" style={{ color: appColor }}>{block.appliance}</span>
              {' → '}{actionLabel}
              {bestRetailer && <> → <span className="font-medium text-violet">{bestRetailer}</span></>}
            </p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-[10px] uppercase tracking-wider text-ink-mute">Save</p>
            <p className="font-display text-xl text-forest-700 tabnum">
              {fmtCurrency(savLow)}
              {savHigh > savLow && (
                <span className="text-sm text-ink-mute"> – {fmtCurrency(savHigh)}</span>
              )}
            </p>
            <p className="text-[10px] text-ink-mute">/yr</p>
          </div>
          <div className="flex-shrink-0 self-center">
            {expanded ? <ChevronUp size={15} className="text-ink-mute" /> : <ChevronDown size={15} className="text-ink-mute" />}
          </div>
        </div>
      </button>

      {/* Expanded */}
      {expanded && (
        <div className="border-t border-line px-4 py-5 space-y-5">

          {/* Before / After charts */}
          {block.before_curve && block.after_curve && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                {block.appliance} Load — Before vs After
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white border border-line rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wide mb-2">Before</p>
                  <HourlyLineChart
                    series={block.total_curve_before || []}
                    overlay={block.before_curve}
                    overlayColor={appColor}
                    height={160}
                  />
                </div>
                <div className="bg-white border border-line rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-violet uppercase tracking-wide mb-2">After</p>
                  <HourlyLineChart
                    series={block.total_curve_after || []}
                    overlay={block.after_curve}
                    overlayColor={appColor}
                    height={160}
                  />
                </div>
              </div>
              <div className="flex items-center gap-5 mt-2 px-1">
                <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
                  <span className="inline-block w-5 border-t-2 border-forest-900 opacity-70" />
                  Total demand
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
                  <span className="inline-block w-5 border-t-2" style={{ borderColor: appColor }} />
                  {block.appliance}
                </span>
              </div>
            </div>
          )}

          {/* Rationale */}
          {block.rationale && (
            <p className="text-sm text-ink-soft leading-relaxed">{block.rationale}</p>
          )}

          {/* Savings row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-forest-50 border border-forest-200 rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-forest-600 mb-1">On current tariff</p>
              <p className="font-display text-lg text-forest-800 tabnum">{fmtCurrency(savLow)}/yr</p>
            </div>
            <div className="bg-violet/8 border border-violet/25 rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-violet/70 mb-1">Best retailer too</p>
              <p className="font-display text-lg text-violet tabnum">{fmtCurrency(savHigh)}/yr</p>
            </div>
            <div className="bg-cream-50 border border-line rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">Peak kWh shifted</p>
              <p className="font-display text-lg text-forest-900 tabnum">
                {fmtNumber(block.peak_kwh_shifted || 0, 1)} kWh
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Retailer table ────────────────────────────────────────────────────────────
function RetailerTableBlock({ block }) {
  const rc = block.retailer_comparison || {};
  const rows = rc.comparison || [];
  if (!rows.length) return null;

  return (
    <div className="bg-cream-50 border border-line rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-forest-900">Retailer Comparison</p>
        {rc.max_saving_vs_current > 0 && (
          <span className="text-xs text-forest-700 font-medium">
            Up to {fmtCurrency(rc.max_saving_vs_current)}/yr by switching
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-cream-100">
            <tr>
              {['Retailer', 'Plan', 'Peak ¢', 'Off-peak ¢', 'Annual', 'vs Current'].map(h => (
                <th key={h} className="px-3 py-2 text-left text-[10px] uppercase tracking-wider text-ink-mute font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r, i) => (
              <tr key={i} className={r.is_current ? 'bg-violet/5' : 'hover:bg-cream-100/60 transition-colors'}>
                <td className="px-3 py-2.5 font-medium text-forest-900 whitespace-nowrap">
                  {r.retailer}
                  {i === 0 && !r.is_current && (
                    <span className="ml-1.5 text-[9px] bg-lime text-forest-900 px-1.5 py-0.5 rounded font-semibold uppercase">
                      Best
                    </span>
                  )}
                  {r.is_current && (
                    <span className="ml-1.5 text-[9px] bg-cream-200 text-ink-mute px-1.5 py-0.5 rounded font-semibold uppercase">
                      Current
                    </span>
                  )}
                </td>
                <td className="px-3 py-2.5 text-ink-soft">{r.plan}</td>
                <td className="px-3 py-2.5 text-ink-soft tabnum">{((r.peak_rate || 0) * 100).toFixed(1)}</td>
                <td className="px-3 py-2.5 text-ink-soft tabnum">{((r.offpeak_rate || 0) * 100).toFixed(1)}</td>
                <td className="px-3 py-2.5 font-medium text-forest-900 tabnum">{fmtCurrency(r.annual_cost)}</td>
                <td className={`px-3 py-2.5 tabnum font-medium ${
                  r.delta_vs_current < -0.01 ? 'text-forest-700' :
                  r.delta_vs_current > 0.01  ? 'text-red-600' : 'text-ink-mute'
                }`}>
                  {Math.abs(r.delta_vs_current) < 0.01 ? '—' :
                   r.delta_vs_current < 0
                     ? `−${fmtCurrency(Math.abs(r.delta_vs_current))}`
                     : `+${fmtCurrency(r.delta_vs_current)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Recommendation ────────────────────────────────────────────────────────────
function RecommendationBlock({ block }) {
  const cfg = {
    high:   { wrap: 'bg-red-50 border-red-200',    badge: 'bg-red-100 text-red-700',    label: 'High Priority' },
    medium: { wrap: 'bg-amber-50 border-amber-200', badge: 'bg-amber-100 text-amber-700', label: 'Medium Priority' },
    low:    { wrap: 'bg-forest-50 border-forest-200', badge: 'bg-forest-100 text-forest-700', label: 'Low Priority' },
  }[block.priority] || { wrap: 'bg-cream-50 border-line', badge: 'bg-cream-200 text-ink-mute', label: 'Note' };

  return (
    <div className={`rounded-xl border p-4 ${cfg.wrap}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <p className="text-sm font-semibold text-forest-900 leading-snug flex-1">{block.text}</p>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide flex-shrink-0 ${cfg.badge}`}>
          {cfg.label}
        </span>
      </div>
      {(block.levers || []).length > 0 && (
        <ul className="space-y-1.5">
          {block.levers.map((lever, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-ink-soft">
              <span className="text-violet font-bold flex-shrink-0 mt-0.5">→</span>
              <span>{lever}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Multi-scenario (combined appliance plan) ──────────────────────────────────
function ApplChangeBars({ changes }) {
  if (!changes || changes.length === 0) return null;
  const rows = changes.map(c => {
    const beforePeak = (c.before_curve || []).slice(30, 42).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const afterPeak  = (c.after_curve  || []).slice(30, 42).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const delta      = afterPeak - beforePeak;
    return { ...c, beforePeak, afterPeak, delta };
  });
  const maxVal = Math.max(...rows.map(r => r.beforePeak), 1);

  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const color    = APPLIANCE_LAYERS.find(l => l.key === r.appliance)?.color || '#5b4bff';
        const beforeW  = (r.beforePeak / maxVal) * 100;
        const afterW   = (r.afterPeak  / maxVal) * 100;
        const positive = r.delta < 0;
        return (
          <div key={i} className="bg-white border border-line rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-forest-900 flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                {r.appliance}
                <span className="text-[10px] font-normal text-ink-mute uppercase tracking-wide">peak window</span>
              </span>
              <span className={`text-xs font-medium tabnum ${positive ? 'text-forest-700' : 'text-amber-600'}`}>
                {positive ? '−' : '+'}{fmtNumber(Math.abs(r.delta), 1)} kWh
              </span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-10 text-ink-mute uppercase tracking-wide flex-shrink-0">Before</span>
                <div className="flex-1 bg-cream-200 rounded h-2.5 overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${beforeW}%`, backgroundColor: color, opacity: 0.45 }} />
                </div>
                <span className="text-xs tabnum text-ink-soft w-14 text-right">{fmtNumber(r.beforePeak, 1)} kWh</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-10 text-ink-mute uppercase tracking-wide flex-shrink-0">After</span>
                <div className="flex-1 bg-cream-200 rounded h-2.5 overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${afterW}%`, backgroundColor: color }} />
                </div>
                <span className="text-xs tabnum text-forest-900 font-medium w-14 text-right">{fmtNumber(r.afterPeak, 1)} kWh</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MultiScenarioBlock({ block }) {
  const [expanded, setExpanded] = useState(false);

  if (block.error) {
    return (
      <div className="flex gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
        <AlertTriangle size={15} className="text-red-500 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-red-700">Multi-scenario error: {block.error}</p>
      </div>
    );
  }

  const savLow  = block.savings_annual_low  || 0;
  const savHigh = block.savings_annual_high || 0;
  const changes = block.appliance_changes   || [];
  const rc      = block.retailer_comparison || {};

  return (
    <div className="bg-cream-50 border-2 border-violet/30 rounded-xl overflow-hidden">
      {/* Header */}
      <button
        type="button"
        className="w-full text-left p-4 hover:bg-violet/5 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <span className="text-[10px] uppercase tracking-wider text-violet/70">Combined Plan</span>
            <h3 className="font-display text-lg text-forest-900 leading-snug">
              {block.name || 'Full Site Reduction Plan'}
            </h3>
            {/* Appliance colour dots */}
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {changes.map((c, i) => {
                const color = APPLIANCE_LAYERS.find(l => l.key === c.appliance)?.color || '#5b4bff';
                return (
                  <span key={i} className="flex items-center gap-1 text-xs text-ink-soft">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                    {c.appliance}
                  </span>
                );
              })}
            </div>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-[10px] uppercase tracking-wider text-ink-mute">Combined saving</p>
            <p className="font-display text-xl text-forest-700 tabnum">
              {fmtCurrency(savLow)}
              {savHigh > savLow && <span className="text-sm text-ink-mute"> – {fmtCurrency(savHigh)}</span>}
            </p>
            <p className="text-[10px] text-ink-mute">/yr</p>
          </div>
          <div className="self-center flex-shrink-0">
            {expanded ? <ChevronUp size={15} className="text-ink-mute" /> : <ChevronDown size={15} className="text-ink-mute" />}
          </div>
        </div>
      </button>

      {/* Expanded */}
      {expanded && (
        <div className="border-t border-violet/20 px-4 py-5 space-y-5">

          {/* Combined before / after chart */}
          {block.total_curve_before && block.total_curve_after && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                Total Site Demand — Before vs After
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white border border-line rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wide mb-2">Before</p>
                  <HourlyLineChart series={block.total_curve_before} height={140} />
                </div>
                <div className="bg-white border border-line rounded-xl p-3">
                  <p className="text-[11px] font-semibold text-violet uppercase tracking-wide mb-2">After</p>
                  <HourlyLineChart series={block.total_curve_after} height={140} />
                </div>
              </div>
            </div>
          )}

          {/* Per-appliance contribution bars */}
          {changes.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                Peak Reduction by Appliance
              </p>
              <ApplChangeBars changes={changes} />
            </div>
          )}

          {/* Rationale */}
          {block.rationale && (
            <p className="text-sm text-ink-soft leading-relaxed">{block.rationale}</p>
          )}

          {/* Savings row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-forest-50 border border-forest-200 rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-forest-600 mb-1">On current tariff</p>
              <p className="font-display text-lg text-forest-800 tabnum">{fmtCurrency(savLow)}/yr</p>
            </div>
            <div className="bg-violet/8 border border-violet/25 rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-violet/70 mb-1">Best retailer too</p>
              <p className="font-display text-lg text-violet tabnum">{fmtCurrency(savHigh)}/yr</p>
            </div>
            <div className="bg-cream-50 border border-line rounded-xl p-3 text-center">
              <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">Total peak shifted</p>
              <p className="font-display text-lg text-forest-900 tabnum">
                {fmtNumber(block.peak_kwh_shifted || 0, 1)} kWh
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Error ─────────────────────────────────────────────────────────────────────
function ErrorBlock({ block }) {
  return (
    <div className="flex gap-2 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
      <AlertTriangle size={15} className="text-red-500 mt-0.5 flex-shrink-0" />
      <p className="text-sm text-red-700">{block.text || 'An error occurred'}</p>
    </div>
  );
}

// ── Main renderer ─────────────────────────────────────────────────────────────
export default function BlockRenderer({ block }) {
  if (!block || !block.type) return null;
  switch (block.type) {
    case 'headline':       return <HeadlineBlock block={block} />;
    case 'text':           return <TextBlock block={block} />;
    case 'kpi_row':        return <KpiRowBlock block={block} />;
    case 'load_chart':     return <LoadChartBlock block={block} />;
    case 'scenario':       return <ScenarioBlock block={block} />;
    case 'multi_scenario': return <MultiScenarioBlock block={block} />;
    case 'retailer_table': return <RetailerTableBlock block={block} />;
    case 'recommendation': return <RecommendationBlock block={block} />;
    case 'error':          return <ErrorBlock block={block} />;
    default:               return null;
  }
}
