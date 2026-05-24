import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronRight, ArrowRight, AlertCircle, RotateCcw } from 'lucide-react';
import { getBaseline, getClient, recalcBaseline, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';
import HourlyLineChart from '../components/HourlyLineChart';
import { APPLIANCE_LAYERS } from '../components/StackedAreaChart';
import AppliancePanel from '../components/AppliancePanel';
import RetailerTable from '../components/RetailerTable';

const COST_COLORS = {
  energy_peak: '#c44d3a',
  energy_shoulder: '#d4a843',
  energy_offpeak: '#3a6a5d',
  demand_charge: '#5b4bff',
  network: '#7a8a87',
  fixed_supply: '#a89280',
  environmental: '#1a504a',
};

const COST_LABELS = {
  energy_peak: 'Energy — Peak',
  energy_shoulder: 'Energy — Shoulder',
  energy_offpeak: 'Energy — Off-peak',
  demand_charge: 'Demand charge',
  network: 'Network',
  fixed_supply: 'Fixed supply',
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
            <div className="w-32 text-right text-xs text-ink-soft flex-shrink-0">{COST_LABELS[item.key]}</div>
            <div className="flex-1 bg-cream-200 rounded-full h-4 relative overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${barPct}%`, backgroundColor: COST_COLORS[item.key], opacity: 0.9 }}
              />
            </div>
            <div className="w-20 text-right text-xs font-semibold text-forest-900 tabnum flex-shrink-0">
              {fmtCurrency(item.value)}
            </div>
            <div className="w-10 text-right text-[11px] text-ink-mute tabnum flex-shrink-0">{pct.toFixed(0)}%</div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 border-t border-line pt-3 mt-2">
        <div className="w-32 text-right text-xs font-semibold text-forest-900">Total annual</div>
        <div className="flex-1" />
        <div className="w-20 text-right text-base font-bold text-violet tabnum flex-shrink-0">{fmtCurrency(total)}</div>
        <div className="w-10 text-right text-[11px] text-ink-mute tabnum">100%</div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit, hint, accent = 'forest', testId }) {
  const accentClass = {
    forest: 'text-forest-800',
    violet: 'text-violet',
    lime: 'text-lime-700',
    amber: 'text-amber-600',
    red: 'text-red-600',
  }[accent];
  return (
    <div className="bg-cream-50 border border-line rounded-2xl p-4 shadow-card" data-testid={testId}>
      <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">{label}</p>
      <p className={`text-2xl font-display tabnum ${accentClass}`}>
        {value}
        {unit && <span className="text-sm font-normal text-ink-mute ml-1">{unit}</span>}
      </p>
      {hint && <p className="text-xs text-ink-mute mt-1">{hint}</p>}
    </div>
  );
}

export default function BaselineAnalysis() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client, setClient] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [recalcing, setRecalcing] = useState(false);
  const [error, setError] = useState('');

  const [enabled, setEnabled] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, true]))
  );
  const [scales, setScales] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]))
  );
  const [lastScales, setLastScales] = useState(
    Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]))
  );

  const recalcTimer = useRef(null);
  const initialBaseline = useRef(null);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [clientRes, baselineRes] = await Promise.all([getClient(id), getBaseline(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setBaseline(baselineRes.data);
        initialBaseline.current = baselineRes.data;
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load baseline analysis.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  useEffect(() => {
    if (!initialBaseline.current) return;
    if (recalcTimer.current) clearTimeout(recalcTimer.current);
    recalcTimer.current = setTimeout(async () => {
      setRecalcing(true);
      try {
        const res = await recalcBaseline(id, scales);
        setBaseline(res.data);
      } catch (_) { /* ignore */ }
      finally { setRecalcing(false); }
    }, 350);
    return () => recalcTimer.current && clearTimeout(recalcTimer.current);
  }, [scales, id]);

  const handleToggle = (name) => {
    setEnabled((prev) => {
      const newEnabled = { ...prev, [name]: !prev[name] };
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

  const resetScales = () => {
    const ones = Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]));
    setScales(ones);
    setLastScales(ones);
    setEnabled(Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, true])));
  };

  const metrics = baseline?.shape_metrics || {};
  const costStack = baseline?.cost_stack || {};
  const loadCurve = baseline?.load_curve || [];
  const retailerComp = baseline?.retailer_comparison;

  const isModified = Object.values(scales).some((v) => Math.abs(v - 1) > 0.001);

  return (
    <div className="p-10 max-w-7xl" data-testid="baseline-page">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        <span className="text-violet font-medium">Baseline</span>
      </div>

      {client && (
        <div className="mb-8">
          <h1 className="font-display text-5xl text-forest-900 leading-none">{client.name}</h1>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-3 h-96 bg-cream-100 rounded-2xl animate-pulse" />
          <div className="lg:col-span-2 h-96 bg-cream-100 rounded-2xl animate-pulse" />
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!loading && baseline && (
        <>
          {/* Row 1: Load shape + cost stack */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <div className="lg:col-span-3 space-y-4">
              <div className="bg-cream-50 border border-line rounded-2xl shadow-card p-6">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider">
                    Hourly Load — Typical Weekday
                  </h2>
                  {recalcing && (
                    <span className="text-[11px] text-violet animate-pulse" data-testid="recalc-indicator">
                      recalculating…
                    </span>
                  )}
                </div>
                <HourlyLineChart series={loadCurve} height={240} />
                <div className="mt-5 pt-5 border-t border-line">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-[11px] font-semibold text-forest-900 uppercase tracking-wider">
                      Appliance Tuning
                    </h3>
                    {isModified && (
                      <button
                        type="button"
                        onClick={resetScales}
                        data-testid="reset-scales-btn"
                        className="inline-flex items-center gap-1 text-[11px] text-violet hover:text-violet-700"
                      >
                        <RotateCcw size={11} /> reset
                      </button>
                    )}
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
                <MetricCard label="Load Factor" value={fmtPct(metrics.load_factor || 0, 0)} hint="Avg ÷ peak" accent="forest" testId="metric-load-factor" />
                <MetricCard label="Peak Demand" value={fmtNumber(metrics.peak_kw || 0, 1)} unit="kW" accent="amber" testId="metric-peak-kw" />
                <MetricCard label="Peak Coincidence" value={fmtPct(metrics.peak_coincidence || 0, 0)} hint="Load in 3–9pm" accent="red" testId="metric-peak-coincidence" />
                <MetricCard label="Annual" value={fmtNumber((metrics.annual_kwh || 0) / 1000, 1)} unit="MWh" accent="violet" testId="metric-annual-kwh" />
              </div>
            </div>

            <div className="lg:col-span-2 space-y-4">
              <div className="bg-cream-50 border border-line rounded-2xl shadow-card p-6">
                <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider mb-5">Annual Cost</h2>
                <CostStackChart costStack={costStack} />
              </div>
            </div>
          </div>

          {/* Row 2: Retailer pricing */}
          {retailerComp && (
            <div className="mt-6 bg-cream-50 border border-line rounded-2xl shadow-card p-6" data-testid="baseline-retailer-section">
              <div className="flex items-baseline justify-between mb-4">
                <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider">
                  Retailer Pricing — for this load shape
                </h2>
                <span className="text-[11px] text-ink-mute">5 AU plans · rates in c/kWh</span>
              </div>
              <RetailerTable data={retailerComp} />
            </div>
          )}

          <div className="mt-8 flex justify-end">
            <button
              onClick={() => navigate(`/clients/${id}/scenarios`)}
              data-testid="build-scenarios-btn"
              className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-3 text-sm transition-all"
            >
              Build Scenarios
              <ArrowRight size={15} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
