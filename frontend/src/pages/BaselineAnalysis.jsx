import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronRight, ArrowRight, AlertCircle, X, Sparkles } from 'lucide-react';
import { getBaseline, getClient, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';
import StackedAreaChart, { APPLIANCE_LAYERS } from '../components/StackedAreaChart';
import AppliancePanel from '../components/AppliancePanel';

const DEMO_CLIENT_ID = 'client-demo-001';

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
    <div className="space-y-2" data-testid="cost-stack-chart">
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
                style={{ width: `${barPct}%`, backgroundColor: COST_COLORS[item.key], opacity: 0.85 }}
              />
            </div>
            <div className="w-20 text-right text-xs font-medium text-forest-900 tabnum flex-shrink-0">
              {fmtCurrency(item.value)}
            </div>
            <div className="w-10 text-right text-xs text-slate-400 tabnum flex-shrink-0">
              {pct.toFixed(0)}%
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 border-t border-slate-200 pt-2 mt-1">
        <div className="w-28 text-right text-xs font-semibold text-forest-900">Total</div>
        <div className="flex-1" />
        <div className="w-20 text-right text-sm font-bold text-forest-900 tabnum flex-shrink-0">
          {fmtCurrency(total)}
        </div>
        <div className="w-10 text-right text-xs text-slate-500 tabnum">100%</div>
      </div>
      <p className="text-xs text-slate-400 text-right">per year</p>
    </div>
  );
}

function MetricCard({ label, value, unit, hint, color = 'text-forest-800', testId }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm" data-testid={testId}>
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
    { label: 'Energy – Peak', cost: costStack.energy_peak, color: COST_COLORS.energy_peak },
    { label: 'Energy – Shoulder', cost: costStack.energy_shoulder, color: COST_COLORS.energy_shoulder },
    { label: 'Energy – Off-peak', cost: costStack.energy_offpeak, color: COST_COLORS.energy_offpeak },
    ...(costStack.demand_charge ? [{ label: 'Demand Charge', cost: costStack.demand_charge, color: COST_COLORS.demand_charge }] : []),
    ...(costStack.network_distribution ? [{ label: 'Network – Distribution', cost: costStack.network_distribution, color: COST_COLORS.network }] : []),
    ...(costStack.network_transmission ? [{ label: 'Network – Transmission', cost: costStack.network_transmission, color: COST_COLORS.network }] : []),
    ...(costStack.network_metering ? [{ label: 'Network – Metering', cost: costStack.network_metering, color: COST_COLORS.network }] : []),
    ...(costStack.fixed_supply ? [{ label: 'Fixed Supply Charge', cost: costStack.fixed_supply, color: COST_COLORS.fixed_supply }] : []),
    ...(costStack.environmental ? [{ label: 'Environmental / LRET', cost: costStack.environmental, color: COST_COLORS.environmental }] : []),
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
                <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: row.color }} />
                <span className="text-slate-700">{row.label}</span>
              </td>
              <td className="py-2 text-right text-forest-900 tabnum">{fmtCurrency(row.cost)}</td>
              <td className="py-2 text-right text-slate-400 tabnum">
                {((row.cost / total) * 100).toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td className="pt-3 font-semibold text-forest-900">Total Annual</td>
            <td className="pt-3 text-right font-bold text-forest-900 tabnum">{fmtCurrency(total)}</td>
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
        {[1, 2, 3, 4].map((i) => (<div key={i} className="h-20 bg-slate-100 rounded-xl" />))}
      </div>
    </div>
  );
}

function DemoBanner() {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div
      data-testid="demo-banner"
      className="mb-4 flex items-start gap-3 bg-lime-100 border border-lime-300 text-forest-900 rounded-xl px-4 py-3"
    >
      <Sparkles size={18} className="text-lime-700 mt-0.5 flex-shrink-0" />
      <div className="flex-1 text-sm">
        This is a demo site. Explore the baseline and scenarios, or create your own client.
      </div>
      <Link
        to="/clients/new"
        data-testid="demo-new-client-link"
        className="inline-flex items-center gap-1 text-sm font-semibold text-forest-800 hover:text-forest-900"
      >
        New Client <ArrowRight size={14} />
      </Link>
      <button
        type="button"
        onClick={() => setOpen(false)}
        data-testid="demo-banner-close"
        className="text-forest-700 hover:text-forest-900"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
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

  // Appliance UI state
  const [enabled, setEnabled] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, true]))
  );
  const [scales, setScales] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]))
  );
  const [lastScales, setLastScales] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]))
  );

  const isDemo = id === DEMO_CLIENT_ID;

  useEffect(() => {
    if (!id) return;
    const fetchAll = async () => {
      setLoading(true);
      setError('');
      try {
        const [clientRes, baselineRes] = await Promise.all([getClient(id), getBaseline(id)]);
        const c = clientRes.data;
        setClient(c);
        sessionStorage.setItem(`client_name_${id}`, c.name);
        setBaseline(baselineRes.data);
      } catch (err) {
        if (err.response?.status === 422 || err.response?.status === 404) {
          try {
            const clientRes = await getClient(id);
            setClient(clientRes.data);
          } catch (_) {}
          const detail = err.response?.data?.detail || '';
          if (detail.toLowerCase().includes('tariff')) {
            setNoTariff(true);
          } else {
            setError(detail || 'Could not load baseline analysis.');
          }
        } else {
          setError(err.response?.data?.detail || 'Failed to load baseline analysis.');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, [id]);

  const handleToggle = (name) => {
    setEnabled((prev) => {
      const newEnabled = { ...prev, [name]: !prev[name] };
      // Restore last scale when toggling on, save current scale when toggling off
      if (newEnabled[name]) {
        setScales((s) => ({ ...s, [name]: lastScales[name] || 1 }));
      } else {
        setLastScales((s) => ({ ...s, [name]: scales[name] || 1 }));
        setScales((s) => ({ ...s, [name]: 0 }));
      }
      return newEnabled;
    });
  };

  const handleScaleChange = (name, value) => {
    setScales((s) => ({ ...s, [name]: value }));
    setLastScales((s) => ({ ...s, [name]: value }));
    if (value > 0 && !enabled[name]) {
      setEnabled((e) => ({ ...e, [name]: true }));
    }
  };

  const metrics = baseline?.shape_metrics || {};
  const costStack = baseline?.cost_stack || {};
  const applianceCurves = baseline?.appliance_curves || {};

  return (
    <div className="p-8" data-testid="baseline-page">
      {isDemo && <DemoBanner />}

      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
        <Link to="/clients" className="hover:text-forest-700 transition-colors">Clients</Link>
        <ChevronRight size={14} />
        {client ? (
          <>
            <span className="text-slate-700 font-medium">{client.name}</span>
            <ChevronRight size={14} />
          </>
        ) : null}
        <span className="text-forest-900 font-medium">Baseline Analysis</span>
      </div>

      {client && (
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-forest-900">{client.name}</h1>
          <div className="flex items-center gap-4 mt-1 text-sm text-slate-500">
            {client.address && <span>{client.address}</span>}
            {client.nmi && (
              <span className="font-mono text-xs bg-mint px-2 py-0.5 rounded border border-forest-100">
                NMI: {client.nmi}
              </span>
            )}
          </div>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3"><SkeletonSection /></div>
          <div className="lg:col-span-2"><SkeletonSection /></div>
        </div>
      )}

      {!loading && noTariff && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 flex items-start gap-3">
          <AlertCircle size={20} className="text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-amber-800 font-medium mb-1">Tariff not configured</p>
            <p className="text-amber-700 text-sm mb-3">
              A tariff must be selected before baseline cost analysis can be run.
            </p>
            <Link to={`/clients/new`} className="inline-flex items-center gap-2 text-sm font-medium text-forest-700 hover:text-forest-900">
              Set up tariff <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!loading && baseline && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-4">
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-forest-900 mb-4">
                  Typical Weekday Load Profile
                </h2>
                <StackedAreaChart
                  applianceCurves={applianceCurves}
                  scales={scales}
                  height={260}
                />
                <div className="mt-4 pt-4 border-t border-slate-100">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-semibold text-forest-900 uppercase tracking-wide">
                      Appliance Mix
                    </h3>
                    <span className="text-xs text-slate-500">Toggle off or rescale (0–200%)</span>
                  </div>
                  <AppliancePanel
                    scales={scales}
                    enabled={enabled}
                    onToggle={handleToggle}
                    onScaleChange={handleScaleChange}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard
                  label="Load Factor"
                  value={metrics.load_factor != null ? fmtPct(metrics.load_factor, 0) : '—'}
                  hint="Avg ÷ peak"
                  color="text-forest-700"
                  testId="metric-load-factor"
                />
                <MetricCard
                  label="Peak Demand"
                  value={metrics.peak_kw != null ? fmtNumber(metrics.peak_kw, 1) : '—'}
                  unit="kW"
                  color="text-amber-600"
                  testId="metric-peak-kw"
                />
                <MetricCard
                  label="Peak Coincidence"
                  value={metrics.peak_coincidence != null ? fmtPct(metrics.peak_coincidence, 0) : '—'}
                  hint="Load in peak window"
                  color="text-red-600"
                  testId="metric-peak-coincidence"
                />
                <MetricCard
                  label="Annual Consumption"
                  value={metrics.annual_kwh != null ? fmtNumber(metrics.annual_kwh / 1000, 1) : '—'}
                  unit="MWh"
                  color="text-forest-800"
                  testId="metric-annual-kwh"
                />
              </div>
            </div>

            <div className="lg:col-span-2 space-y-4">
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-forest-900 mb-5">Annual Cost Breakdown</h2>
                <CostStackChart costStack={costStack} />
              </div>
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                <h2 className="text-sm font-semibold text-forest-900 mb-4">Cost Detail</h2>
                <CostBreakdownTable costStack={costStack} />
              </div>
            </div>
          </div>

          <div className="mt-8 flex items-center justify-between border-t border-forest-100 pt-6">
            <p className="text-sm text-slate-600">Ready to explore savings opportunities?</p>
            <button
              onClick={() => navigate(`/clients/${id}/scenarios`)}
              data-testid="build-scenarios-btn"
              className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 text-forest-900 font-semibold rounded-lg px-6 py-2.5 text-sm transition-colors"
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
