import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronRight, ArrowRight, AlertCircle, Loader } from 'lucide-react';
import { getBaseline, getClient, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';

// TOU period definitions (bucket indices)
const TOU_PERIODS = {
  peak: { start: 30, end: 42, color: '#ef4444', label: 'Peak', opacity: 0.12 },
  shoulder_am: { start: 14, end: 30, color: '#f59e0b', label: 'Shoulder', opacity: 0.10 },
  shoulder_pm: { start: 42, end: 44, color: '#f59e0b', label: 'Shoulder', opacity: 0.10 },
  offpeak: { start: 0, end: 14, color: '#22c55e', label: 'Off-peak', opacity: 0.07 },
  offpeak2: { start: 44, end: 48, color: '#22c55e', label: 'Off-peak', opacity: 0.07 },
};

const X_LABELS = [
  { bucket: 0, label: '12am' },
  { bucket: 8, label: '4am' },
  { bucket: 16, label: '8am' },
  { bucket: 24, label: '12pm' },
  { bucket: 32, label: '4pm' },
  { bucket: 40, label: '8pm' },
  { bucket: 47, label: '11:30pm' },
];

function LoadCurveChart({ data, height = 200, showBaseline = false, baselineData = null, compact = false }) {
  if (!data || data.length === 0) return null;

  const svgWidth = 600;
  const svgHeight = height;
  const padL = 50, padR = 16, padT = 12, padB = 28;
  const chartW = svgWidth - padL - padR;
  const chartH = svgHeight - padT - padB;

  const allData = [...data, ...(baselineData || [])];
  const maxVal = Math.max(...allData) * 1.08 || 1;
  const minVal = 0;

  const xPos = (bucket) => padL + (bucket / 47) * chartW;
  const yPos = (val) => padT + chartH - ((val - minVal) / (maxVal - minVal)) * chartH;

  // Build smooth polyline path
  const buildPath = (arr) =>
    arr
      .map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`)
      .join(' ');

  const buildAreaPath = (arr) => {
    const line = buildPath(arr);
    const lastX = xPos(arr.length - 1).toFixed(1);
    const firstX = xPos(0).toFixed(1);
    const base = yPos(0).toFixed(1);
    return `${line} L${lastX},${base} L${firstX},${base} Z`;
  };

  const touBands = [
    { ...TOU_PERIODS.offpeak },
    { ...TOU_PERIODS.offpeak2 },
    { ...TOU_PERIODS.shoulder_am },
    { ...TOU_PERIODS.shoulder_pm },
    { ...TOU_PERIODS.peak },
  ];

  const yTicks = 4;
  const yTickStep = maxVal / yTicks;

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: 'auto' }}
      >
        {/* TOU band overlays */}
        {touBands.map((band, idx) => (
          <rect
            key={idx}
            x={xPos(band.start)}
            y={padT}
            width={xPos(Math.min(band.end, 47)) - xPos(band.start)}
            height={chartH}
            fill={band.color}
            opacity={band.opacity}
          />
        ))}

        {/* Y-axis grid lines */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const val = (yTickStep * i);
          const y = yPos(val);
          return (
            <g key={i}>
              <line
                x1={padL}
                y1={y}
                x2={padL + chartW}
                y2={y}
                stroke="#e2e8f0"
                strokeWidth={1}
              />
              <text x={padL - 5} y={y + 4} textAnchor="end" fontSize={9} fill="#94a3b8">
                {fmtNumber(val, 0)}
              </text>
            </g>
          );
        })}

        {/* Baseline area fill (if overlay mode) */}
        {showBaseline && baselineData && (
          <path
            d={buildAreaPath(baselineData)}
            fill="#94a3b8"
            opacity={0.12}
          />
        )}

        {/* Main area fill */}
        <path
          d={buildAreaPath(data)}
          fill={showBaseline ? 'none' : '#6366f1'}
          opacity={showBaseline ? 0 : 0.08}
        />

        {/* Baseline line (overlay) */}
        {showBaseline && baselineData && (
          <path
            d={buildPath(baselineData)}
            fill="none"
            stroke="#94a3b8"
            strokeWidth={2}
            strokeDasharray="4 3"
          />
        )}

        {/* Main line */}
        <path
          d={buildPath(data)}
          fill="none"
          stroke={showBaseline ? '#6366f1' : '#6366f1'}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* X-axis labels */}
        {X_LABELS.map(({ bucket, label }) => (
          <text
            key={bucket}
            x={xPos(bucket)}
            y={padT + chartH + 16}
            textAnchor="middle"
            fontSize={9}
            fill="#94a3b8"
          >
            {label}
          </text>
        ))}

        {/* Y-axis label */}
        <text
          x={10}
          y={padT + chartH / 2}
          textAnchor="middle"
          fontSize={9}
          fill="#94a3b8"
          transform={`rotate(-90, 10, ${padT + chartH / 2})`}
        >
          kW
        </text>

        {/* Legend */}
        {showBaseline && (
          <g transform={`translate(${padL + 8}, ${padT + 8})`}>
            <rect x={0} y={0} width={60} height={32} rx={4} fill="white" opacity={0.85} />
            <line x1={6} y1={10} x2={20} y2={10} stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 3" />
            <text x={24} y={13} fontSize={8} fill="#64748b">Baseline</text>
            <line x1={6} y1={22} x2={20} y2={22} stroke="#6366f1" strokeWidth={2} />
            <text x={24} y={25} fontSize={8} fill="#64748b">Optimised</text>
          </g>
        )}

        {/* TOU legend */}
        {!compact && (
          <g transform={`translate(${padL + chartW - 160}, ${padT + 4})`}>
            <rect x={0} y={0} width={160} height={20} rx={3} fill="white" opacity={0.85} />
            {[
              { color: '#ef4444', label: 'Peak' },
              { color: '#f59e0b', label: 'Shoulder' },
              { color: '#22c55e', label: 'Off-peak' },
            ].map((item, i) => (
              <g key={i} transform={`translate(${i * 52 + 4}, 4)`}>
                <rect x={0} y={3} width={9} height={9} rx={2} fill={item.color} opacity={0.5} />
                <text x={12} y={11} fontSize={8} fill="#64748b">{item.label}</text>
              </g>
            ))}
          </g>
        )}
      </svg>
    </div>
  );
}

const COST_COLORS = {
  energy_peak: '#ef4444',
  energy_shoulder: '#f59e0b',
  energy_offpeak: '#22c55e',
  demand_charge: '#8b5cf6',
  network: '#64748b',
  fixed_supply: '#94a3b8',
  environmental: '#10b981',
};

const COST_LABELS = {
  energy_peak: 'Energy (Peak)',
  energy_shoulder: 'Energy (Shoulder)',
  energy_offpeak: 'Energy (Off-peak)',
  demand_charge: 'Demand Charge',
  network: 'Network',
  fixed_supply: 'Fixed Supply',
  environmental: 'Environmental',
};

function CostStackChart({ costStack }) {
  if (!costStack) return null;

  const items = [
    { key: 'energy_peak', value: costStack.energy_peak },
    { key: 'energy_shoulder', value: costStack.energy_shoulder },
    { key: 'energy_offpeak', value: costStack.energy_offpeak },
    { key: 'demand_charge', value: costStack.demand_charge },
    {
      key: 'network',
      value:
        (costStack.network_distribution || 0) +
        (costStack.network_transmission || 0) +
        (costStack.network_metering || 0),
    },
    { key: 'fixed_supply', value: costStack.fixed_supply },
    { key: 'environmental', value: costStack.environmental },
  ].filter((item) => item.value > 0);

  const total = costStack.total_annual || items.reduce((s, i) => s + i.value, 0);
  const maxVal = Math.max(...items.map((i) => i.value));

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const pct = (item.value / total) * 100;
        const barPct = (item.value / maxVal) * 100;
        return (
          <div key={item.key} className="flex items-center gap-3">
            <div className="w-28 text-right text-xs text-slate-600 flex-shrink-0">
              {COST_LABELS[item.key]}
            </div>
            <div className="flex-1 bg-slate-100 rounded-full h-5 relative overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${barPct}%`,
                  backgroundColor: COST_COLORS[item.key],
                  opacity: 0.85,
                }}
              />
            </div>
            <div className="w-20 text-right text-xs font-medium text-slate-800 tabnum flex-shrink-0">
              {fmtCurrency(item.value)}
            </div>
            <div className="w-10 text-right text-xs text-slate-400 tabnum flex-shrink-0">
              {pct.toFixed(0)}%
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 border-t border-slate-200 pt-2 mt-1">
        <div className="w-28 text-right text-xs font-semibold text-slate-900">Total</div>
        <div className="flex-1" />
        <div className="w-20 text-right text-sm font-bold text-indigo-700 tabnum flex-shrink-0">
          {fmtCurrency(total)}
        </div>
        <div className="w-10 text-right text-xs text-slate-500 tabnum">100%</div>
      </div>
      <p className="text-xs text-slate-400 text-right">per year</p>
    </div>
  );
}

function MetricCard({ label, value, unit, hint, color = 'text-indigo-700' }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-xl font-bold tabnum ${color}`}>
        {value}
        {unit && <span className="text-sm font-normal text-slate-400 ml-1">{unit}</span>}
      </p>
      {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

function CostBreakdownTable({ costStack }) {
  if (!costStack) return null;

  const rows = [
    {
      label: 'Energy – Peak',
      rate: 'TOU peak rate',
      cost: costStack.energy_peak,
      color: COST_COLORS.energy_peak,
    },
    {
      label: 'Energy – Shoulder',
      rate: 'TOU shoulder rate',
      cost: costStack.energy_shoulder,
      color: COST_COLORS.energy_shoulder,
    },
    {
      label: 'Energy – Off-peak',
      rate: 'TOU off-peak rate',
      cost: costStack.energy_offpeak,
      color: COST_COLORS.energy_offpeak,
    },
    ...(costStack.demand_charge
      ? [{ label: 'Demand Charge', rate: '$/kW/mo', cost: costStack.demand_charge, color: COST_COLORS.demand_charge }]
      : []),
    ...(costStack.network_distribution
      ? [{ label: 'Network – Distribution', rate: 'c/kWh', cost: costStack.network_distribution, color: COST_COLORS.network }]
      : []),
    ...(costStack.network_transmission
      ? [{ label: 'Network – Transmission', rate: 'c/kWh', cost: costStack.network_transmission, color: COST_COLORS.network }]
      : []),
    ...(costStack.network_metering
      ? [{ label: 'Network – Metering', rate: '$/day', cost: costStack.network_metering, color: COST_COLORS.network }]
      : []),
    ...(costStack.fixed_supply
      ? [{ label: 'Fixed Supply Charge', rate: '$/day', cost: costStack.fixed_supply, color: COST_COLORS.fixed_supply }]
      : []),
    ...(costStack.environmental
      ? [{ label: 'Environmental / LRET', rate: 'c/kWh', cost: costStack.environmental, color: COST_COLORS.environmental }]
      : []),
  ].filter((r) => r.cost > 0);

  const total = costStack.total_annual || rows.reduce((s, r) => s + r.cost, 0);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="text-left text-xs font-medium text-slate-500 pb-2">Line Item</th>
            <th className="text-right text-xs font-medium text-slate-500 pb-2">Annual Cost</th>
            <th className="text-right text-xs font-medium text-slate-500 pb-2">Share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-slate-100">
              <td className="py-2 flex items-center gap-2">
                <span
                  className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                  style={{ backgroundColor: row.color }}
                />
                <span className="text-slate-700">{row.label}</span>
              </td>
              <td className="py-2 text-right text-slate-800 tabnum">{fmtCurrency(row.cost)}</td>
              <td className="py-2 text-right text-slate-400 tabnum">
                {((row.cost / total) * 100).toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="pt-3 font-semibold text-slate-900">Total Annual</td>
            <td className="pt-3 text-right font-bold text-indigo-700 tabnum">{fmtCurrency(total)}</td>
            <td className="pt-3 text-right text-slate-500">100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function SkeletonSection() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-6 bg-slate-200 rounded w-1/3" />
      <div className="h-48 bg-slate-100 rounded-xl" />
      <div className="grid grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-20 bg-slate-100 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export default function BaselineAnalysis() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client, setClient] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [noTariff, setNoTariff] = useState(false);

  useEffect(() => {
    if (!id) return;

    // Cache client name for sidebar
    const fetchAll = async () => {
      setLoading(true);
      setError('');
      try {
        const [clientRes, baselineRes] = await Promise.all([
          getClient(id),
          getBaseline(id),
        ]);
        const c = clientRes.data;
        setClient(c);
        sessionStorage.setItem(`client_name_${id}`, c.name);
        setBaseline(baselineRes.data);
      } catch (err) {
        if (err.response?.status === 422 || err.response?.status === 404) {
          // Likely no tariff / no data
          try {
            const clientRes = await getClient(id);
            setClient(clientRes.data);
          } catch (_) {}
          const detail = err.response?.data?.detail || '';
          if (detail.toLowerCase().includes('tariff') || detail.toLowerCase().includes('no tariff')) {
            setNoTariff(true);
          } else {
            setError(detail || 'Could not load baseline analysis. Ensure interval data and tariff are configured.');
          }
        } else {
          setError(
            err.response?.data?.detail ||
              'Failed to load baseline analysis. Please try again.'
          );
        }
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [id]);

  const metrics = baseline?.shape_metrics || {};
  const costStack = baseline?.cost_stack || {};
  const loadCurve = baseline?.load_curve || [];

  return (
    <div className="p-8">
      {/* Breadcrumb + header */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
        <Link to="/clients" className="hover:text-indigo-600 transition-colors">Clients</Link>
        <ChevronRight size={14} />
        {client ? (
          <>
            <span className="text-slate-700 font-medium">{client.name}</span>
            <ChevronRight size={14} />
          </>
        ) : null}
        <span className="text-slate-900 font-medium">Baseline Analysis</span>
      </div>

      {/* Client header */}
      {client && (
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-slate-900">{client.name}</h1>
          <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
            {client.address && <span>{client.address}</span>}
            {client.nmi && (
              <span className="font-mono text-xs bg-slate-100 px-2 py-0.5 rounded">
                NMI: {client.nmi}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3"><SkeletonSection /></div>
          <div className="lg:col-span-2"><SkeletonSection /></div>
        </div>
      )}

      {/* No tariff state */}
      {!loading && noTariff && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 flex items-start gap-3">
          <AlertCircle size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-amber-800 font-medium mb-1">Tariff not configured</p>
            <p className="text-amber-700 text-sm mb-3">
              A tariff must be selected before baseline cost analysis can be run.
            </p>
            <Link
              to={`/clients/new`}
              className="inline-flex items-center gap-2 text-sm font-medium text-indigo-700 hover:text-indigo-900"
            >
              Set up tariff <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      )}

      {/* General error */}
      {!loading && error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main content */}
      {!loading && baseline && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Left: Load curve + shape metrics */}
            <div className="lg:col-span-3 space-y-4">
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-slate-700 mb-4">
                  Typical Weekday Load Profile
                </h2>
                <LoadCurveChart data={loadCurve} height={220} />
              </div>

              {/* Shape metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard
                  label="Load Factor"
                  value={metrics.load_factor != null ? fmtPct(metrics.load_factor / 100, 0) : '—'}
                  hint="Avg ÷ peak — higher is better"
                  color="text-emerald-600"
                />
                <MetricCard
                  label="Peak Demand"
                  value={metrics.peak_kw != null ? fmtNumber(metrics.peak_kw, 1) : '—'}
                  unit="kW"
                  color="text-amber-600"
                />
                <MetricCard
                  label="Peak Coincidence"
                  value={
                    metrics.peak_coincidence != null
                      ? fmtPct(metrics.peak_coincidence / 100, 0)
                      : '—'
                  }
                  hint="Load in peak TOU window"
                  color="text-red-600"
                />
                <MetricCard
                  label="Annual Consumption"
                  value={
                    metrics.annual_kwh != null
                      ? fmtNumber(metrics.annual_kwh / 1000, 1)
                      : '—'
                  }
                  unit="MWh"
                  color="text-indigo-700"
                />
              </div>
            </div>

            {/* Right: Cost stack */}
            <div className="lg:col-span-2 space-y-4">
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-slate-700 mb-5">Annual Cost Breakdown</h2>
                <CostStackChart costStack={costStack} />
              </div>
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-slate-700 mb-4">Cost Detail</h2>
                <CostBreakdownTable costStack={costStack} />
              </div>
            </div>
          </div>

          {/* Action bar */}
          <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-6">
            <p className="text-sm text-slate-500">
              Ready to explore savings opportunities?
            </p>
            <button
              onClick={() => navigate(`/clients/${id}/scenarios`)}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
            >
              Build Scenarios
              <ArrowRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
