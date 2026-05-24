import React from 'react';
import { fmtCurrency, fmtNumber } from '../lib/api';

/**
 * Render the 5-retailer comparison as a clean sortable table.
 * Highlights the current plan (star) and the cheapest plan (lime row).
 */
export default function RetailerTable({ data, compact = false, testId = 'retailer-table' }) {
  if (!data || !data.comparison || data.comparison.length === 0) return null;
  const rows = data.comparison;
  const best = data.best;
  const max = Math.max(...rows.map((r) => r.annual_cost));

  return (
    <div className="w-full" data-testid={testId}>
      <div className="overflow-hidden rounded-xl border border-line bg-cream-50">
        <table className="w-full text-sm">
          <thead className="bg-forest-800 text-white">
            <tr>
              <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Retailer</th>
              <th className="text-left px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Plan</th>
              {!compact && <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Peak</th>}
              {!compact && <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Shldr</th>}
              {!compact && <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Off-peak</th>}
              <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider font-medium">Annual</th>
              <th className="text-right px-3 py-2 text-[10px] uppercase tracking-wider font-medium">vs current</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isBest = r.retailer === best;
              const barPct = (r.annual_cost / max) * 100;
              return (
                <tr
                  key={`${r.retailer}-${r.plan}`}
                  className={`border-t border-line ${isBest ? 'bg-lime/20' : ''}`}
                  data-testid={`retailer-row-${r.retailer.replace(/\W+/g, '-').toLowerCase()}`}
                >
                  <td className="px-3 py-2">
                    <span className="font-semibold text-forest-900 inline-flex items-center gap-1">
                      {r.is_current && <span className="text-violet text-xs">●</span>}
                      {isBest && <span className="text-[10px] text-lime-700 font-bold">BEST</span>}
                      {r.retailer}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-soft">{r.plan}</td>
                  {!compact && <td className="px-3 py-2 text-right tabnum text-[11px] text-ink-soft">{(r.peak_rate * 100).toFixed(1)}¢</td>}
                  {!compact && <td className="px-3 py-2 text-right tabnum text-[11px] text-ink-soft">{(r.shoulder_rate * 100).toFixed(1)}¢</td>}
                  {!compact && <td className="px-3 py-2 text-right tabnum text-[11px] text-ink-soft">{(r.offpeak_rate * 100).toFixed(1)}¢</td>}
                  <td className="px-3 py-2 text-right tabnum text-forest-900 font-medium relative">
                    <div className="absolute inset-y-1 right-2 left-2 bg-cream-200 rounded-sm overflow-hidden -z-0 opacity-50">
                      <div
                        className="h-full"
                        style={{ width: `${barPct}%`, backgroundColor: isBest ? '#c4e94a' : '#dcd2b8' }}
                      />
                    </div>
                    <span className="relative z-10">{fmtCurrency(r.annual_cost)}</span>
                  </td>
                  <td className={`px-3 py-2 text-right tabnum text-xs font-medium ${r.delta_vs_current < 0 ? 'text-forest-700' : r.delta_vs_current > 0 ? 'text-amber-600' : 'text-ink-mute'}`}>
                    {r.is_current ? '—' : (
                      <>
                        {r.delta_vs_current < 0 ? '−' : '+'}{fmtCurrency(Math.abs(r.delta_vs_current))}
                        <span className="text-[10px] text-ink-mute ml-1">({r.delta_pct > 0 ? '+' : ''}{fmtNumber(r.delta_pct, 1)}%)</span>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {data.max_saving_vs_current > 0 && (
        <p className="mt-2 text-xs text-ink-soft">
          Switching from <span className="font-semibold text-forest-900">{data.current_retailer}</span> to{' '}
          <span className="font-semibold text-violet">{best}</span> saves{' '}
          <span className="font-semibold text-violet tabnum">{fmtCurrency(data.max_saving_vs_current)}</span> per year on this load shape.
        </p>
      )}
    </div>
  );
}
