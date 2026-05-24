import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ChevronRight, Printer, AlertCircle, Loader, Zap } from 'lucide-react';
import { getReport, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';

// ---------- Inline chart for print (pure SVG) ----------
const X_LABELS = [
  { bucket: 0, label: '12am' },
  { bucket: 8, label: '4am' },
  { bucket: 16, label: '8am' },
  { bucket: 24, label: '12pm' },
  { bucket: 32, label: '4pm' },
  { bucket: 40, label: '8pm' },
  { bucket: 47, label: '11:30pm' },
];

function ReportChart({ data, baselineData = null, height = 140 }) {
  if (!data || data.length === 0) return null;
  const svgW = 520, svgH = height;
  const pL = 44, pR = 12, pT = 8, pB = 24;
  const cW = svgW - pL - pR, cH = svgH - pT - pB;
  const all = [...data, ...(baselineData || [])];
  const maxV = Math.max(...all) * 1.1 || 1;
  const xPos = (b) => pL + (b / 47) * cW;
  const yPos = (v) => pT + cH - (v / maxV) * cH;
  const buildPath = (arr) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`).join(' ');

  const touBands = [
    { start: 0, end: 14, color: '#22c55e', opacity: 0.06 },
    { start: 14, end: 30, color: '#f59e0b', opacity: 0.08 },
    { start: 30, end: 42, color: '#ef4444', opacity: 0.10 },
    { start: 42, end: 44, color: '#f59e0b', opacity: 0.08 },
    { start: 44, end: 48, color: '#22c55e', opacity: 0.06 },
  ];

  return (
    <div style={{ width: '100%' }}>
      <svg viewBox={`0 0 ${svgW} ${svgH}`} style={{ width: '100%', height: 'auto' }}>
        {touBands.map((b, i) => (
          <rect key={i} x={xPos(b.start)} y={pT} width={xPos(b.end) - xPos(b.start)} height={cH}
            fill={b.color} opacity={b.opacity} />
        ))}
        {[0, 1, 2, 3].map((i) => {
          const v = (maxV / 3) * i;
          const y = yPos(v);
          return (
            <g key={i}>
              <line x1={pL} y1={y} x2={pL + cW} y2={y} stroke="#e2e8f0" strokeWidth={0.8} />
              <text x={pL - 4} y={y + 3} textAnchor="end" fontSize={7} fill="#94a3b8">{fmtNumber(v, 0)}</text>
            </g>
          );
        })}
        {baselineData && (
          <path d={buildPath(baselineData)} fill="none" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 2" />
        )}
        <path d={buildPath(data)} fill="none" stroke="#6366f1" strokeWidth={2} strokeLinecap="round" />
        {X_LABELS.map(({ bucket, label }) => (
          <text key={bucket} x={xPos(bucket)} y={pT + cH + 14} textAnchor="middle" fontSize={7} fill="#94a3b8">
            {label}
          </text>
        ))}
      </svg>
    </div>
  );
}

// ---------- Section wrapper ----------
function Section({ title, children }) {
  return (
    <div className="mb-8">
      <h2 className="text-base font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">{title}</h2>
      {children}
    </div>
  );
}

// ---------- Cost stack table ----------
function CostTable({ costStack }) {
  if (!costStack) return null;
  const rows = [
    { label: 'Energy – Peak', value: costStack.energy_peak },
    { label: 'Energy – Shoulder', value: costStack.energy_shoulder },
    { label: 'Energy – Off-peak', value: costStack.energy_offpeak },
    { label: 'Demand Charge', value: costStack.demand_charge },
    {
      label: 'Network (total)',
      value: (costStack.network_distribution || 0) + (costStack.network_transmission || 0) + (costStack.network_metering || 0),
    },
    { label: 'Fixed Supply Charge', value: costStack.fixed_supply },
    { label: 'Environmental', value: costStack.environmental },
  ].filter((r) => r.value > 0);

  const total = costStack.total_annual || rows.reduce((s, r) => s + r.value, 0);

  return (
    <table className="w-full text-sm border border-slate-200 rounded-lg overflow-hidden">
      <thead>
        <tr className="bg-slate-50">
          <th className="text-left px-3 py-2 text-xs font-semibold text-slate-600">Line Item</th>
          <th className="text-right px-3 py-2 text-xs font-semibold text-slate-600">Annual Cost</th>
          <th className="text-right px-3 py-2 text-xs font-semibold text-slate-600">Share</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-t border-slate-100">
            <td className="px-3 py-2 text-slate-700">{row.label}</td>
            <td className="px-3 py-2 text-right tabnum text-slate-800">{fmtCurrency(row.value)}</td>
            <td className="px-3 py-2 text-right tabnum text-slate-400">{((row.value / total) * 100).toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr className="border-t-2 border-slate-300 bg-slate-50">
          <td className="px-3 py-2 font-bold text-slate-900">Total Annual</td>
          <td className="px-3 py-2 text-right font-bold tabnum text-indigo-700">{fmtCurrency(total)}</td>
          <td className="px-3 py-2 text-right text-slate-500">100%</td>
        </tr>
      </tfoot>
    </table>
  );
}

export default function Report() {
  const { id } = useParams();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getReport(id)
      .then((res) => setReport(res.data))
      .catch((err) => setError(err.response?.data?.detail || 'Failed to load report.'))
      .finally(() => setLoading(false));
  }, [id]);

  const handlePrint = () => window.print();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader size={24} className="animate-spin text-indigo-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      </div>
    );
  }

  const client = report?.client || {};
  const baseline = report?.baseline || {};
  const scenarios = report?.scenarios || [];
  const savings = report?.savings || {};
  const generatedAt = report?.generated_at
    ? new Date(report.generated_at).toLocaleDateString('en-AU', {
        day: 'numeric', month: 'long', year: 'numeric',
      })
    : new Date().toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' });

  const costStack = baseline?.cost_stack || {};
  const shapeMetrics = baseline?.shape_metrics || {};
  const loadCurve = baseline?.load_curve || [];
  const shiftedCurve = report?.shifted_curve || null;

  const totalSavLow = savings.total_low;
  const totalSavHigh = savings.total_high;
  const billingTotal = savings.billing_defensible?.total;
  const indicativeLow = savings.indicative?.contract_low;
  const indicativeHigh = savings.indicative?.contract_high;

  return (
    <div className="min-h-screen bg-slate-50">
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: white; }
          .print-page { box-shadow: none !important; margin: 0 !important; max-width: 100% !important; }
        }
      `}</style>

      {/* Controls bar (no-print) */}
      <div className="no-print bg-white border-b border-slate-200 px-8 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Link to="/clients" className="hover:text-indigo-600 transition-colors">Clients</Link>
          <ChevronRight size={14} />
          <Link to={`/clients/${id}/scenarios`} className="hover:text-indigo-600 transition-colors font-medium text-slate-700">
            {client.name || 'Client'}
          </Link>
          <ChevronRight size={14} />
          <span className="text-slate-900 font-medium">Report</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to={`/clients/${id}/scenarios`}
            className="text-sm text-slate-600 hover:text-indigo-600 transition-colors"
          >
            ← Back to Scenarios
          </Link>
          <button
            onClick={handlePrint}
            className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg px-4 py-2 text-sm transition-colors"
          >
            <Printer size={15} />
            Print / Export PDF
          </button>
        </div>
      </div>

      {/* Report page */}
      <div className="print-page max-w-3xl mx-auto bg-white shadow-sm my-6 rounded-xl overflow-hidden">
        {/* Report Header */}
        <div className="bg-slate-900 text-white px-8 py-8">
          <div className="flex items-center gap-3 mb-6">
            <div className="bg-indigo-600 rounded-lg p-2">
              <Zap size={18} className="text-white" />
            </div>
            <span className="text-lg font-semibold">EnergyScope</span>
          </div>
          <h1 className="text-2xl font-bold mb-1">Energy Analysis Report</h1>
          <p className="text-slate-400 text-sm">Generated {generatedAt}</p>
          <div className="mt-5 pt-5 border-t border-slate-700">
            <p className="text-lg font-medium">{client.name}</p>
            {client.address && <p className="text-slate-400 text-sm mt-1">{client.address}</p>}
            {client.nmi && (
              <p className="text-slate-500 text-xs mt-1 font-mono">NMI: {client.nmi}</p>
            )}
          </div>
        </div>

        {/* Report body */}
        <div className="px-8 py-8">

          {/* 1. Executive Summary */}
          <Section title="Executive Summary">
            <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-sm text-indigo-900 leading-relaxed">
              {totalSavLow && totalSavHigh ? (
                <p>
                  Analysis of {client.name || 'this site'} indicates an annual consumption of{' '}
                  <strong>{shapeMetrics.annual_kwh ? fmtNumber(shapeMetrics.annual_kwh / 1000, 1) + ' MWh' : '—'}</strong>{' '}
                  at a peak demand of{' '}
                  <strong>{shapeMetrics.peak_kw ? fmtNumber(shapeMetrics.peak_kw, 1) + ' kW' : '—'}</strong>.{' '}
                  Recommended load-management scenarios project total savings of{' '}
                  <strong>{fmtCurrency(totalSavLow)}–{fmtCurrency(totalSavHigh)}</strong> per year,
                  comprising billing-defensible energy and demand reductions plus indicative contract uplift.
                </p>
              ) : (
                <p>
                  This report summarises the baseline energy analysis for{' '}
                  {client.name || 'this site'}, including load profile characteristics, cost breakdown, and recommended optimisation scenarios.
                </p>
              )}
            </div>
          </Section>

          {/* 2. Baseline Profile */}
          <Section title="Baseline Load Profile">
            {loadCurve.length > 0 && (
              <div className="mb-5">
                <p className="text-xs text-slate-500 mb-2">Typical Weekday Load Profile</p>
                <ReportChart data={loadCurve} height={140} />
              </div>
            )}

            {/* Shape metrics */}
            {(shapeMetrics.load_factor || shapeMetrics.peak_kw || shapeMetrics.annual_kwh) && (
              <div className="grid grid-cols-4 gap-3 mb-5">
                {shapeMetrics.load_factor != null && (
                  <div className="bg-slate-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-500 mb-1">Load Factor</p>
                    <p className="text-lg font-bold text-emerald-600 tabnum">
                      {fmtPct(shapeMetrics.load_factor / 100, 0)}
                    </p>
                  </div>
                )}
                {shapeMetrics.peak_kw != null && (
                  <div className="bg-slate-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-500 mb-1">Peak Demand</p>
                    <p className="text-lg font-bold text-amber-600 tabnum">
                      {fmtNumber(shapeMetrics.peak_kw, 1)} kW
                    </p>
                  </div>
                )}
                {shapeMetrics.peak_coincidence != null && (
                  <div className="bg-slate-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-500 mb-1">Peak Coincidence</p>
                    <p className="text-lg font-bold text-red-600 tabnum">
                      {fmtPct(shapeMetrics.peak_coincidence / 100, 0)}
                    </p>
                  </div>
                )}
                {shapeMetrics.annual_kwh != null && (
                  <div className="bg-slate-50 rounded-lg p-3 text-center">
                    <p className="text-xs text-slate-500 mb-1">Annual Use</p>
                    <p className="text-lg font-bold text-indigo-700 tabnum">
                      {fmtNumber(shapeMetrics.annual_kwh / 1000, 1)} MWh
                    </p>
                  </div>
                )}
              </div>
            )}

            <CostTable costStack={costStack} />
          </Section>

          {/* 3. Recommended Scenarios */}
          {scenarios && scenarios.length > 0 && (
            <Section title="Recommended Scenario(s)">
              <div className="space-y-3">
                {scenarios.map((s, i) => (
                  <div key={i} className="border border-slate-200 rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold text-slate-900">{s.name}</span>
                      {s.type && (
                        <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs">
                          {s.type}
                        </span>
                      )}
                    </div>
                    {s.description && (
                      <p className="text-sm text-slate-600 mb-2">{s.description}</p>
                    )}
                    {s.parameters && Object.keys(s.parameters).length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(s.parameters).map(([k, v]) => (
                          <span key={k} className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded font-mono">
                            {k}: {String(v)}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* 4. Savings Projection */}
          {(billingTotal || indicativeLow || totalSavLow) && (
            <Section title="Savings Projection">
              <div className="grid grid-cols-2 gap-4 mb-4">
                {billingTotal != null && (
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
                    <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wide mb-3">
                      Billing-Defensible Savings
                    </p>
                    {savings.billing_defensible?.energy != null && (
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-slate-600">Energy savings</span>
                        <span className="font-medium tabnum text-emerald-700">
                          {fmtCurrency(savings.billing_defensible.energy)}
                        </span>
                      </div>
                    )}
                    {savings.billing_defensible?.demand != null && (
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-slate-600">Demand savings</span>
                        <span className="font-medium tabnum text-emerald-700">
                          {fmtCurrency(savings.billing_defensible.demand)}
                        </span>
                      </div>
                    )}
                    <div className="flex justify-between text-sm border-t border-emerald-200 pt-2">
                      <span className="font-bold text-slate-900">Total</span>
                      <span className="font-bold tabnum text-emerald-700">{fmtCurrency(billingTotal)}</span>
                    </div>
                  </div>
                )}
                {(indicativeLow != null || indicativeHigh != null) && (
                  <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                    <p className="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-3">
                      Indicative Contract Uplift
                    </p>
                    <p className="text-xl font-bold text-blue-700 tabnum text-center mt-4">
                      {fmtCurrency(indicativeLow)}
                      <span className="text-sm font-normal text-blue-400 mx-1">–</span>
                      {fmtCurrency(indicativeHigh)}
                    </p>
                    <p className="text-xs text-blue-500 text-center mt-1">indicative range</p>
                  </div>
                )}
              </div>

              {totalSavLow != null && totalSavHigh != null && (
                <div className="bg-indigo-600 text-white rounded-xl p-5 mb-4">
                  <p className="text-sm font-semibold mb-2">Total Annual Saving Range</p>
                  <p className="text-2xl font-bold tabnum">
                    {fmtCurrency(totalSavLow)}
                    <span className="text-lg font-normal text-indigo-300 mx-2">–</span>
                    {fmtCurrency(totalSavHigh)}
                  </p>
                  <p className="text-indigo-300 text-xs mt-1">per year</p>
                </div>
              )}

              {/* 3-year estimate */}
              {totalSavLow != null && totalSavHigh != null && (
                <div className="border border-slate-200 rounded-xl p-4 bg-slate-50">
                  <p className="text-sm font-semibold text-slate-700 mb-2">3-Year Total Estimate</p>
                  <p className="text-xl font-bold text-indigo-700 tabnum">
                    {fmtCurrency(totalSavLow * 3)}
                    <span className="text-base font-normal text-slate-400 mx-2">–</span>
                    {fmtCurrency(totalSavHigh * 3)}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">Based on savings × 3 years (indicative)</p>
                </div>
              )}
            </Section>
          )}

          {/* 5. New Load Profile (overlay chart) */}
          {shiftedCurve && loadCurve.length > 0 && (
            <Section title="New Load Profile">
              <p className="text-xs text-slate-500 mb-2">Baseline vs. Optimised</p>
              <ReportChart data={shiftedCurve} baselineData={loadCurve} height={140} />
              <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-8 border-t-2 border-dashed border-slate-400" />
                  Baseline
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-8 border-t-2 border-indigo-600" />
                  Optimised
                </span>
              </div>
            </Section>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 px-8 py-4 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
          <span>Generated by EnergyScope</span>
          <span>
            {generatedAt}
          </span>
        </div>
      </div>
    </div>
  );
}
