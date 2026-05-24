import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ChevronRight, Play, Loader, AlertCircle, CheckSquare, Square, FileText, ArrowRight, TrendingDown } from 'lucide-react';
import { getBaseline, getScenarioLibrary, runScenarios, getClient, fmtCurrency, fmtNumber, fmtPct } from '../lib/api';

// ---------- Shared chart (reused from BaselineAnalysis) ----------
const X_LABELS = [
  { bucket: 0, label: '12am' },
  { bucket: 8, label: '4am' },
  { bucket: 16, label: '8am' },
  { bucket: 24, label: '12pm' },
  { bucket: 32, label: '4pm' },
  { bucket: 40, label: '8pm' },
  { bucket: 47, label: '11:30pm' },
];

function MiniLoadChart({ data, baselineData = null, height = 160 }) {
  if (!data || data.length === 0) return null;

  const svgW = 560, svgH = height;
  const padL = 44, padR = 12, padT = 10, padB = 26;
  const cW = svgW - padL - padR;
  const cH = svgH - padT - padB;

  const allVals = [...(data || []), ...(baselineData || [])];
  const maxVal = Math.max(...allVals) * 1.1 || 1;

  const xPos = (b) => padL + (b / 47) * cW;
  const yPos = (v) => padT + cH - (v / maxVal) * cH;

  const buildPath = (arr) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`).join(' ');

  const touBands = [
    { start: 0, end: 14, color: '#22c55e', opacity: 0.07 },
    { start: 14, end: 30, color: '#f59e0b', opacity: 0.08 },
    { start: 30, end: 42, color: '#ef4444', opacity: 0.10 },
    { start: 42, end: 44, color: '#f59e0b', opacity: 0.08 },
    { start: 44, end: 48, color: '#22c55e', opacity: 0.07 },
  ];

  const yTicks = 3;
  const yTickStep = maxVal / yTicks;

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: 'auto' }}
      >
        {touBands.map((b, i) => (
          <rect key={i} x={xPos(b.start)} y={padT} width={xPos(b.end) - xPos(b.start)} height={cH}
            fill={b.color} opacity={b.opacity} />
        ))}

        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const v = yTickStep * i;
          const y = yPos(v);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={padL + cW} y2={y} stroke="#e2e8f0" strokeWidth={1} />
              <text x={padL - 4} y={y + 3} textAnchor="end" fontSize={8} fill="#94a3b8">{fmtNumber(v, 0)}</text>
            </g>
          );
        })}

        {baselineData && (
          <path d={buildPath(baselineData)} fill="none" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3" />
        )}
        <path d={buildPath(data)} fill="none" stroke="#6366f1" strokeWidth={2} strokeLinecap="round" />

        {X_LABELS.map(({ bucket, label }) => (
          <text key={bucket} x={xPos(bucket)} y={padT + cH + 14} textAnchor="middle" fontSize={8} fill="#94a3b8">
            {label}
          </text>
        ))}

        {baselineData && (
          <g transform={`translate(${padL + 6}, ${padT + 6})`}>
            <rect x={0} y={0} width={90} height={28} rx={3} fill="white" opacity={0.9} />
            <line x1={5} y1={8} x2={16} y2={8} stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3" />
            <text x={19} y={11} fontSize={7.5} fill="#64748b">Baseline</text>
            <line x1={5} y1={20} x2={16} y2={20} stroke="#6366f1" strokeWidth={2} />
            <text x={19} y={23} fontSize={7.5} fill="#64748b">Optimised</text>
          </g>
        )}
      </svg>
    </div>
  );
}

// ---------- Parameter input based on schema ----------
function ParamInput({ name, schema, value, onChange }) {
  const label = schema.title || name;
  const type = schema.type === 'integer' || schema.type === 'number' ? 'number' : 'text';

  return (
    <div>
      <label className="block text-xs font-medium text-slate-600 mb-1">{label}</label>
      {schema.description && (
        <p className="text-xs text-slate-400 mb-1">{schema.description}</p>
      )}
      <input
        type={type}
        value={value ?? schema.default ?? ''}
        onChange={(e) =>
          onChange(name, type === 'number' ? parseFloat(e.target.value) : e.target.value)
        }
        min={schema.minimum}
        max={schema.maximum}
        step={schema.type === 'integer' ? 1 : 0.1}
        className="w-full border border-slate-300 rounded-lg px-2.5 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
      />
    </div>
  );
}

// ---------- Scenario card in left panel ----------
function ScenarioCard({ scenario, checked, params, onToggle, onParamChange }) {
  return (
    <div
      className={`border rounded-xl overflow-hidden transition-colors ${
        checked ? 'border-indigo-300 bg-indigo-50' : 'border-slate-200 bg-white'
      }`}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-4 text-left"
      >
        <span className={`mt-0.5 flex-shrink-0 ${checked ? 'text-indigo-600' : 'text-slate-400'}`}>
          {checked ? <CheckSquare size={16} /> : <Square size={16} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-900 leading-snug">{scenario.name}</p>
          {scenario.description && (
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">{scenario.description}</p>
          )}
          {scenario.type && (
            <span className="inline-block mt-2 px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs">
              {scenario.type}
            </span>
          )}
        </div>
      </button>

      {checked && scenario.parameters_schema && Object.keys(scenario.parameters_schema.properties || {}).length > 0 && (
        <div className="px-4 pb-4 space-y-3 border-t border-indigo-200 pt-3">
          <p className="text-xs font-medium text-indigo-700">Parameters</p>
          {Object.entries(scenario.parameters_schema.properties || {}).map(([key, schema]) => (
            <ParamInput
              key={key}
              name={key}
              schema={schema}
              value={params?.[key]}
              onChange={onParamChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- Savings card ----------
function SavingsCard({ title, color, children }) {
  const styles = {
    green: 'bg-emerald-50 border-emerald-200',
    blue: 'bg-blue-50 border-blue-200',
    indigo: 'bg-indigo-50 border-indigo-200',
    slate: 'bg-slate-50 border-slate-200',
  };
  return (
    <div className={`border rounded-xl p-4 ${styles[color] || styles.slate}`}>
      <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">{title}</p>
      {children}
    </div>
  );
}

export default function ScenarioBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client, setClient] = useState(null);
  const [library, setLibrary] = useState([]);
  const [baselineCurve, setBaselineCurve] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Selected scenarios state: { [scenarioId]: { checked, params } }
  const [scenarioState, setScenarioState] = useState({});

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState('');
  const [results, setResults] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [clientRes, libraryRes, baselineRes] = await Promise.all([
          getClient(id),
          getScenarioLibrary(),
          getBaseline(id),
        ]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setLibrary(libraryRes.data);
        setBaselineCurve(baselineRes.data?.load_curve || null);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load scenario data.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const toggleScenario = (scenario) => {
    setScenarioState((prev) => {
      const existing = prev[scenario.id];
      if (existing?.checked) {
        return { ...prev, [scenario.id]: { ...existing, checked: false } };
      }
      // Initialize params with defaults
      const defaults = {};
      const props = scenario.parameters_schema?.properties || {};
      Object.entries(props).forEach(([k, v]) => {
        if (v.default !== undefined) defaults[k] = v.default;
      });
      return { ...prev, [scenario.id]: { checked: true, params: defaults } };
    });
  };

  const updateParam = (scenarioId, paramName, value) => {
    setScenarioState((prev) => ({
      ...prev,
      [scenarioId]: {
        ...prev[scenarioId],
        params: { ...(prev[scenarioId]?.params || {}), [paramName]: value },
      },
    }));
  };

  const selectedScenarios = library.filter((s) => scenarioState[s.id]?.checked);

  const handleRun = async () => {
    if (selectedScenarios.length === 0) return;
    setRunning(true);
    setRunError('');
    setResults(null);
    try {
      const scenarios = selectedScenarios.map((s) => ({
        type: s.type,
        parameters: scenarioState[s.id]?.params || {},
      }));
      const res = await runScenarios(id, scenarios);
      setResults(res.data);
    } catch (err) {
      setRunError(err.response?.data?.detail || 'Scenario run failed. Please try again.');
    } finally {
      setRunning(false);
    }
  };

  const savings = results?.savings;
  const newMetrics = results?.new_shape_metrics;

  return (
    <div className="p-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
        <Link to="/clients" className="hover:text-indigo-600 transition-colors">Clients</Link>
        <ChevronRight size={14} />
        {client && (
          <>
            <Link to={`/clients/${id}/baseline`} className="text-slate-700 hover:text-indigo-600 font-medium transition-colors">
              {client.name}
            </Link>
            <ChevronRight size={14} />
          </>
        )}
        <span className="text-slate-900 font-medium">Scenarios</span>
      </div>

      <h1 className="text-2xl font-semibold text-slate-900 mb-6">Scenario Builder</h1>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-6">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader size={24} className="animate-spin text-indigo-600" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Left: scenario controls */}
          <div className="lg:col-span-2 space-y-4">
            <h2 className="text-sm font-semibold text-slate-700">Available Scenarios</h2>

            {library.length === 0 ? (
              <p className="text-sm text-slate-500 py-8 text-center">No scenarios available.</p>
            ) : (
              <div className="space-y-3">
                {library.map((scenario) => (
                  <ScenarioCard
                    key={scenario.id}
                    scenario={scenario}
                    checked={!!scenarioState[scenario.id]?.checked}
                    params={scenarioState[scenario.id]?.params}
                    onToggle={() => toggleScenario(scenario)}
                    onParamChange={(name, value) => updateParam(scenario.id, name, value)}
                  />
                ))}
              </div>
            )}

            {runError && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-3 py-2.5 text-xs">
                <AlertCircle size={14} className="mt-0.5 flex-shrink-0" />
                <span>{runError}</span>
              </div>
            )}

            <button
              onClick={handleRun}
              disabled={selectedScenarios.length === 0 || running}
              className="w-full inline-flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:text-slate-500 text-white font-medium rounded-lg px-4 py-2.5 text-sm transition-colors"
            >
              {running ? (
                <>
                  <Loader size={15} className="animate-spin" />
                  Running analysis…
                </>
              ) : (
                <>
                  <Play size={15} />
                  Run Analysis
                  {selectedScenarios.length > 0 && ` (${selectedScenarios.length})`}
                </>
              )}
            </button>
          </div>

          {/* Right: results panel */}
          <div className="lg:col-span-3 space-y-4">
            {/* Chart */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">Load Profile</h2>
              {results ? (
                <MiniLoadChart
                  data={results.shifted_curve}
                  baselineData={results.baseline_curve}
                  height={180}
                />
              ) : baselineCurve ? (
                <>
                  <MiniLoadChart data={baselineCurve} height={160} />
                  <p className="text-xs text-slate-400 mt-3 text-center">
                    Select a scenario on the left to see the impact
                  </p>
                </>
              ) : (
                <p className="text-xs text-slate-400 text-center py-8">No baseline data available</p>
              )}
            </div>

            {/* Savings results */}
            {results && savings && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  {/* Billing-defensible */}
                  <SavingsCard title="Billing-Defensible Savings" color="green">
                    <div className="space-y-1.5">
                      {savings.billing_defensible?.energy != null && (
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-600">Energy savings</span>
                          <span className="font-semibold text-emerald-700 tabnum">
                            {fmtCurrency(savings.billing_defensible.energy)}
                          </span>
                        </div>
                      )}
                      {savings.billing_defensible?.demand != null && (
                        <div className="flex justify-between text-sm">
                          <span className="text-slate-600">Demand savings</span>
                          <span className="font-semibold text-emerald-700 tabnum">
                            {fmtCurrency(savings.billing_defensible.demand)}
                          </span>
                        </div>
                      )}
                      <div className="flex justify-between text-sm border-t border-emerald-200 pt-1.5 mt-1">
                        <span className="font-semibold text-slate-700">Total</span>
                        <span className="font-bold text-emerald-700 tabnum">
                          {fmtCurrency(savings.billing_defensible?.total)}
                        </span>
                      </div>
                    </div>
                  </SavingsCard>

                  {/* Indicative contract */}
                  <SavingsCard title="Indicative Contract Uplift" color="blue">
                    <div className="space-y-1.5">
                      {savings.indicative && (
                        <div className="text-center py-2">
                          <p className="text-xl font-bold text-blue-700 tabnum">
                            {fmtCurrency(savings.indicative.contract_low)}
                            <span className="text-sm font-normal text-blue-500 mx-1">–</span>
                            {fmtCurrency(savings.indicative.contract_high)}
                          </p>
                          <p className="text-xs text-blue-600 mt-1">indicative range</p>
                        </div>
                      )}
                    </div>
                  </SavingsCard>
                </div>

                {/* Total saving range */}
                <div className="bg-indigo-600 rounded-xl p-5 text-white">
                  <div className="flex items-center gap-2 mb-3">
                    <TrendingDown size={18} />
                    <span className="text-sm font-semibold">Total Saving Range</span>
                  </div>
                  <p className="text-3xl font-bold tabnum">
                    {fmtCurrency(savings.total_low)}
                    <span className="text-lg font-normal text-indigo-300 mx-2">–</span>
                    {fmtCurrency(savings.total_high)}
                  </p>
                  <p className="text-indigo-300 text-xs mt-1">per year (billing-defensible + indicative)</p>
                </div>

                {/* New shape metrics */}
                {newMetrics && (
                  <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                    <h3 className="text-sm font-semibold text-slate-700 mb-3">New Shape Metrics</h3>
                    <div className="grid grid-cols-2 gap-3">
                      {newMetrics.load_factor != null && (
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500">New Load Factor</p>
                          <p className="text-lg font-bold text-emerald-600 tabnum">
                            {fmtPct(newMetrics.load_factor / 100, 0)}
                          </p>
                        </div>
                      )}
                      {newMetrics.peak_kw != null && (
                        <div className="bg-slate-50 rounded-lg p-3">
                          <p className="text-xs text-slate-500">New Peak Demand</p>
                          <p className="text-lg font-bold text-amber-600 tabnum">
                            {fmtNumber(newMetrics.peak_kw, 1)} kW
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Applied scenarios list */}
                <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                  <h3 className="text-sm font-semibold text-slate-700 mb-3">Scenarios Applied</h3>
                  <div className="space-y-2">
                    {selectedScenarios.map((s) => (
                      <div key={s.id} className="flex items-start gap-3 text-sm">
                        <span className="mt-0.5 text-indigo-500"><CheckSquare size={15} /></span>
                        <div>
                          <p className="font-medium text-slate-800">{s.name}</p>
                          {scenarioState[s.id]?.params && Object.keys(scenarioState[s.id].params).length > 0 && (
                            <p className="text-xs text-slate-500 mt-0.5">
                              {Object.entries(scenarioState[s.id].params)
                                .map(([k, v]) => `${k}: ${v}`)
                                .join(', ')}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Generate report CTA */}
                <div className="flex justify-end">
                  <button
                    onClick={() => navigate(`/clients/${id}/report`)}
                    className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded-lg px-6 py-2.5 text-sm transition-colors"
                  >
                    <FileText size={15} />
                    Generate Report
                    <ArrowRight size={15} />
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
