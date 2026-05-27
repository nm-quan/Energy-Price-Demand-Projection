import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronRight, ArrowRight, AlertCircle, Layers, Store, Zap, TrendingUp, Clock, BarChart2 } from 'lucide-react';
import { getBaseline, getClient, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';
import StackedAreaChart, { APPLIANCE_LAYERS } from '../components/StackedAreaChart';
import RetailerTable from '../components/RetailerTable';

const COST_COLORS = {
  energy_peak:    '#c44d3a',
  energy_shoulder:'#d4a843',
  energy_offpeak: '#3a6a5d',
  demand_charge:  '#5b4bff',
  network:        '#7a8a87',
  fixed_supply:   '#a89280',
  environmental:  '#1a504a',
};

const COST_LABELS = {
  energy_peak:    'Peak energy',
  energy_shoulder:'Shoulder energy',
  energy_offpeak: 'Off-peak energy',
  demand_charge:  'Demand charge',
  network:        'Network',
  fixed_supply:   'Fixed supply',
  environmental:  'Environmental',
};

function CostStackChart({ costStack }) {
  if (!costStack) return null;
  const items = [
    { key: 'energy_peak',    value: costStack.energy_peak },
    { key: 'energy_shoulder',value: costStack.energy_shoulder },
    { key: 'energy_offpeak', value: costStack.energy_offpeak },
    { key: 'demand_charge',  value: costStack.demand_charge },
    {
      key: 'network',
      value: (costStack.network_distribution || 0) + (costStack.network_transmission || 0) + (costStack.network_metering || 0),
    },
    { key: 'fixed_supply',   value: costStack.fixed_supply },
    { key: 'environmental',  value: costStack.environmental },
  ].filter((item) => item.value > 0);

  const total  = costStack.total_annual || items.reduce((s, i) => s + i.value, 0);
  const maxVal = Math.max(...items.map((i) => i.value));

  return (
    <div className="space-y-2.5" data-testid="cost-stack-chart">
      {items.map((item) => {
        const pct    = (item.value / total) * 100;
        const barPct = (item.value / maxVal) * 100;
        return (
          <div key={item.key} className="flex items-center gap-3">
            <div className="w-28 text-right text-[11px] text-ink-soft flex-shrink-0 leading-tight">{COST_LABELS[item.key]}</div>
            <div className="flex-1 bg-cream-200 rounded-full h-3.5 relative overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: COST_COLORS[item.key] }} />
            </div>
            <div className="w-16 text-right text-xs font-semibold text-forest-900 tabnum flex-shrink-0">{fmtCurrency(item.value)}</div>
            <div className="w-8 text-right text-[10px] text-ink-mute tabnum flex-shrink-0">{pct.toFixed(0)}%</div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 border-t-2 border-forest-900/10 pt-3 mt-1">
        <div className="w-28 text-right text-xs font-bold text-forest-900">Total / year</div>
        <div className="flex-1" />
        <div className="w-16 text-right text-lg font-bold text-violet tabnum">{fmtCurrency(total)}</div>
        <div className="w-8" />
      </div>
    </div>
  );
}

function KpiStrip({ metrics, costStack }) {
  const total = costStack?.total_annual || 0;
  const kpis = [
    { icon: <Zap size={16} className="text-amber-500" />,    label: 'Annual usage',      value: fmtNumber((metrics.annual_kwh || 0) / 1000, 1), unit: 'MWh' },
    { icon: <TrendingUp size={16} className="text-red-500" />, label: 'Peak demand',      value: fmtNumber(metrics.peak_kw || 0, 1),             unit: 'kW'  },
    { icon: <Clock size={16} className="text-violet" />,      label: 'In TOU peak',       value: fmtPct(metrics.peak_coincidence || 0, 0),       unit: ''    },
    { icon: <BarChart2 size={16} className="text-forest-600" />, label: 'Load factor',   value: fmtPct(metrics.load_factor || 0, 0),            unit: ''    },
    { icon: <span className="text-sm font-bold text-forest-700">$</span>, label: 'Annual cost', value: fmtCurrency(total), unit: '/yr' },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 divide-x divide-line border border-line rounded-2xl bg-cream-50 shadow-card mb-6 overflow-hidden">
      {kpis.map((k, i) => (
        <div key={i} className="flex flex-col items-center justify-center py-4 px-3 text-center gap-1">
          <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-mute">
            {k.icon} {k.label}
          </div>
          <div className="font-display text-xl text-forest-900 tabnum leading-tight">
            {k.value}{k.unit && <span className="text-xs font-normal text-ink-mute ml-0.5">{k.unit}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function BaselineAnalysis() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client,       setClient]       = useState(null);
  const [baseline,     setBaseline]     = useState(null);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState('');
  const [storeContext, setStoreContext] = useState(null);

  useEffect(() => {
    if (!id) return;
    const raw = sessionStorage.getItem(`store_context_${id}`);
    const ctx = raw ? (() => { try { return JSON.parse(raw); } catch { return null; } })() : null;

    if (ctx?.baseline) {
      setStoreContext(ctx);
      setBaseline(ctx.baseline);
      setLoading(false);
      getClient(id).then((r) => {
        setClient(r.data);
        sessionStorage.setItem(`client_name_${id}`, r.data.name);
      }).catch(() => {});
      return;
    }

    (async () => {
      setLoading(true);
      setError('');
      try {
        const [clientRes, baselineRes] = await Promise.all([getClient(id), getBaseline(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setBaseline(baselineRes.data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load baseline analysis.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handleBuildScenarios = () => {
    if (storeContext) {
      sessionStorage.setItem(`scenario_store_context_${id}`, JSON.stringify(storeContext));
    } else {
      sessionStorage.removeItem(`scenario_store_context_${id}`);
    }
    navigate(`/clients/${id}/scenarios`);
  };

  const metrics      = baseline?.shape_metrics   || {};
  const costStack    = baseline?.cost_stack       || {};
  const appCurves    = baseline?.appliance_curves || {};
  const retailerComp = baseline?.retailer_comparison;

  const activeAppliances = APPLIANCE_LAYERS.filter(
    ({ key }) => appCurves[key] && appCurves[key].some((v) => v > 0)
  );

  return (
    <div className="p-10 max-w-7xl" data-testid="baseline-page">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        {client && (
          <Link to={`/clients/${id}/portfolio`} className="hover:text-forest-700 text-forest-800 font-medium">
            {client.name}
          </Link>
        )}
        <ChevronRight size={12} />
        <span className="text-violet font-medium">Baseline</span>
      </div>

      {/* Header */}
      {client && (
        <div className="flex items-end justify-between mb-6 gap-4">
          <div>
            <h1 className="font-display text-5xl text-forest-900 leading-none">{client.name}</h1>
            {storeContext && (
              <div className={`inline-flex items-center gap-2 mt-2 text-xs px-3 py-1 rounded-full border ${
                storeContext.type === 'aggregate'
                  ? 'bg-violet/8 border-violet/30 text-violet-800'
                  : 'bg-forest-50 border-forest-200 text-forest-800'
              }`}>
                {storeContext.type === 'aggregate'
                  ? <Layers size={12} className="text-violet" />
                  : <Store size={12} className="text-forest-600" />}
                <span className="font-medium">
                  {storeContext.type === 'aggregate'
                    ? storeContext.store_names.join(' + ')
                    : storeContext.store_names[0]}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    sessionStorage.removeItem(`store_context_${id}`);
                    setStoreContext(null);
                    setLoading(true);
                    Promise.all([getClient(id), getBaseline(id)]).then(([c, b]) => {
                      setClient(c.data); setBaseline(b.data);
                    }).finally(() => setLoading(false));
                  }}
                  className="text-ink-mute hover:text-red-600 ml-1"
                >
                  ×
                </button>
              </div>
            )}
          </div>
          <button
            onClick={handleBuildScenarios}
            data-testid="build-scenarios-btn"
            className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-6 py-2.5 text-sm transition-all flex-shrink-0"
          >
            Build Scenarios <ArrowRight size={14} />
          </button>
        </div>
      )}

      {!loading && error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="space-y-4">
          <div className="h-20 bg-cream-100 rounded-2xl animate-pulse" />
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <div className="lg:col-span-3 h-96 bg-cream-100 rounded-2xl animate-pulse" />
            <div className="lg:col-span-2 h-96 bg-cream-100 rounded-2xl animate-pulse" />
          </div>
        </div>
      )}

      {!loading && baseline && (
        <div className="space-y-4">
          {/* KPI strip — full width */}
          <KpiStrip metrics={metrics} costStack={costStack} />

          {/* Main body: load chart (left) + cost breakdown (right) */}
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">

            {/* Load chart */}
            <div className="lg:col-span-3 bg-cream-50 border border-line rounded-2xl shadow-card overflow-hidden">
              <div className="px-6 pt-5 pb-3 border-b border-line">
                <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider">Hourly Load — Typical Weekday</h2>
                <p className="text-xs text-ink-mute mt-0.5">Half-hourly average kW by appliance</p>
              </div>
              <div className="p-6">
                <StackedAreaChart
                  applianceCurves={appCurves}
                  scales={{}}
                  height={280}
                  showLegend={false}
                  testId="baseline-stacked-chart"
                />
              </div>
              {activeAppliances.length > 0 && (
                <div className="px-6 pb-5 border-t border-line pt-4">
                  <div className="flex flex-wrap gap-2">
                    {activeAppliances.map(({ key, color }) => (
                      <span
                        key={key}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white border border-line text-[11px] font-medium text-forest-900"
                      >
                        <span className="w-2 h-2 rounded-sm flex-shrink-0" style={{ backgroundColor: color }} />
                        {key}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Cost breakdown */}
            <div className="lg:col-span-2 bg-cream-50 border border-line rounded-2xl shadow-card overflow-hidden flex flex-col">
              <div className="px-6 pt-5 pb-3 border-b border-line">
                <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider">Annual Cost Breakdown</h2>
                <p className="text-xs text-ink-mute mt-0.5">By tariff component</p>
              </div>
              <div className="p-6 flex-1">
                <CostStackChart costStack={costStack} />
              </div>
            </div>
          </div>

          {/* Retailer table — full width */}
          {retailerComp && (
            <div className="bg-cream-50 border border-line rounded-2xl shadow-card overflow-hidden" data-testid="baseline-retailer-section">
              <div className="px-6 pt-5 pb-3 border-b border-line flex items-baseline justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-forest-900 uppercase tracking-wider">Retailer Comparison</h2>
                  <p className="text-xs text-ink-mute mt-0.5">Modelled on this load shape · rates in c/kWh</p>
                </div>
                <span className="text-[11px] text-ink-mute">5 AU plans</span>
              </div>
              <div className="p-6">
                <RetailerTable data={retailerComp} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
