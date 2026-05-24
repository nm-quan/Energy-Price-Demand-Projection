import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight,
  Loader,
  AlertCircle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Send,
  FileText,
  ArrowRight,
} from 'lucide-react';
import { getBaseline, getClient, generateScenarios, fmtCurrency, fmtNumber } from '../lib/api';
import StackedAreaChart, { APPLIANCE_LAYERS } from '../components/StackedAreaChart';

const DEMO_CLIENT_ID = 'client-demo-001';

function ScenarioCard({ scenario, expanded, onToggleExpand, applianceCurves, scales, baselineCurve }) {
  const billing = scenario.savings?.billing_defensible || {};
  const indicative = scenario.savings?.indicative || {};
  const totalLow = scenario.savings?.total_low ?? 0;
  const totalHigh = scenario.savings?.total_high ?? 0;

  return (
    <div
      data-testid={`scenario-card-${scenario.rank}`}
      className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden hover:border-forest-300 transition-colors"
    >
      <div className="p-5">
        <div className="flex items-start gap-4">
          <div
            data-testid={`scenario-rank-${scenario.rank}`}
            className="flex-shrink-0 w-12 h-12 rounded-xl bg-forest-900 text-lime-400 font-bold text-lg flex items-center justify-center"
          >
            #{scenario.rank}
          </div>

          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-forest-900 leading-snug">
              {scenario.name}
            </h3>
            {scenario.rationale && (
              <p className="text-sm text-slate-600 mt-1 leading-relaxed">{scenario.rationale}</p>
            )}
            {scenario.type && (
              <span className="inline-block mt-2 px-2 py-0.5 bg-mint text-forest-800 border border-forest-100 rounded-full text-xs font-medium">
                {scenario.type}
              </span>
            )}
          </div>

          <div className="text-right flex-shrink-0">
            <p className="text-xs text-slate-500 mb-0.5">Annual saving</p>
            <p className="text-lg font-bold text-forest-800 tabnum">
              {fmtCurrency(totalLow)}
              <span className="text-sm font-normal text-slate-400 mx-1">–</span>
              {fmtCurrency(totalHigh)}
            </p>
            <button
              type="button"
              data-testid={`scenario-expand-${scenario.rank}`}
              onClick={onToggleExpand}
              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-forest-700 hover:text-forest-900"
            >
              {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {expanded ? 'Hide details' : 'Show details'}
            </button>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="px-5 pb-5 border-t border-slate-100 bg-mint/40">
          <div className="pt-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-forest-800 mb-2">
              Shifted load shape
            </h4>
            <StackedAreaChart
              applianceCurves={applianceCurves}
              scales={scales}
              height={200}
              baseline={baselineCurve}
              overlay={scenario.shifted_curve}
            />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
            <div className="bg-white rounded-lg p-3 border border-slate-200">
              <p className="text-xs text-slate-500">Energy saving</p>
              <p className="text-sm font-bold text-forest-800 tabnum">{fmtCurrency(billing.energy ?? 0)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-slate-200">
              <p className="text-xs text-slate-500">Demand saving</p>
              <p className="text-sm font-bold text-forest-800 tabnum">{fmtCurrency(billing.demand ?? 0)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-slate-200">
              <p className="text-xs text-slate-500">Billing-defensible</p>
              <p className="text-sm font-bold text-forest-900 tabnum">{fmtCurrency(billing.total ?? 0)}</p>
            </div>
            <div className="bg-white rounded-lg p-3 border border-slate-200">
              <p className="text-xs text-slate-500">Indicative contract</p>
              <p className="text-sm font-bold text-forest-700 tabnum">
                {fmtCurrency(indicative.contract_low ?? 0)}–{fmtCurrency(indicative.contract_high ?? 0)}
              </p>
            </div>
          </div>

          {scenario.parameters && Object.keys(scenario.parameters).length > 0 && (
            <details className="mt-4 text-xs">
              <summary className="text-forest-700 font-medium cursor-pointer">Parameters</summary>
              <pre className="mt-2 bg-white border border-slate-200 rounded-lg p-3 overflow-x-auto text-slate-700">
                {JSON.stringify(scenario.parameters, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default function ScenarioBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client, setClient] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState('');
  const [scenarios, setScenarios] = useState(null);
  const [source, setSource] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [extraInstruction, setExtraInstruction] = useState('');
  const autoTriggered = useRef(false);

  const isDemo = id === DEMO_CLIENT_ID;

  // baseline appliance scales (all on, 100%) for chart context
  const defaultScales = Object.fromEntries(APPLIANCE_LAYERS.map(({ key }) => [key, 1]));

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [clientRes, baselineRes] = await Promise.all([getClient(id), getBaseline(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setBaseline(baselineRes.data);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load scenario data.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const runGenerate = async (instruction = null) => {
    setGenerating(true);
    setGenError('');
    try {
      const res = await generateScenarios(id, instruction);
      setScenarios(res.data.scenarios || []);
      setSource(res.headers['x-scenario-source'] || res.data.source || 'claude');
      if ((res.data.scenarios || []).length > 0) {
        setExpanded(1);
      }
      // Cache on sessionStorage so demo doesn't keep regenerating
      try {
        sessionStorage.setItem(
          `scenarios_${id}`,
          JSON.stringify({
            scenarios: res.data.scenarios,
            source: res.headers['x-scenario-source'] || res.data.source || 'claude',
            baseline_curve: res.data.baseline_curve,
          })
        );
      } catch (_) {}
    } catch (err) {
      setGenError(err.response?.data?.detail || 'Scenario generation failed. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  // Demo: auto-trigger generation on first load (sessionStorage-cached)
  useEffect(() => {
    if (!isDemo || loading || baseline == null || autoTriggered.current) return;
    autoTriggered.current = true;
    try {
      const cached = sessionStorage.getItem(`scenarios_${id}`);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed?.scenarios?.length) {
          setScenarios(parsed.scenarios);
          setSource(parsed.source);
          setExpanded(1);
          return;
        }
      }
    } catch (_) {}
    runGenerate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, loading, baseline, id]);

  const handleFollowUp = (e) => {
    e.preventDefault();
    if (!extraInstruction.trim()) return;
    runGenerate(extraInstruction.trim());
    setExtraInstruction('');
  };

  return (
    <div className="p-8" data-testid="scenarios-page">
      <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
        <Link to="/clients" className="hover:text-forest-700 transition-colors">Clients</Link>
        <ChevronRight size={14} />
        {client && (
          <>
            <Link to={`/clients/${id}/baseline`} className="text-slate-700 hover:text-forest-700 font-medium transition-colors">
              {client.name}
            </Link>
            <ChevronRight size={14} />
          </>
        )}
        <span className="text-forest-900 font-medium">Scenarios</span>
      </div>

      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold text-forest-900">Load-Shift Scenarios</h1>
          <p className="text-sm text-slate-600 mt-1">
            Claude analyses this site's load shape and ranks bespoke savings opportunities.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {scenarios && (
            <button
              type="button"
              onClick={() => runGenerate()}
              disabled={generating}
              data-testid="regenerate-btn"
              className="inline-flex items-center gap-2 border border-forest-200 hover:border-forest-400 text-forest-800 font-medium rounded-lg px-3 py-2 text-sm transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={generating ? 'animate-spin' : ''} />
              Regenerate
            </button>
          )}
          <button
            type="button"
            onClick={() => runGenerate()}
            disabled={generating || loading}
            data-testid="generate-scenarios-btn"
            className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 disabled:bg-slate-300 disabled:text-slate-500 text-forest-900 font-semibold rounded-lg px-4 py-2.5 text-sm transition-colors"
          >
            <Sparkles size={15} />
            {scenarios ? 'Generate again' : 'Generate Scenarios'}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-6">
          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader size={24} className="animate-spin text-forest-700" />
        </div>
      ) : (
        <>
          {/* Loading state */}
          {generating && (
            <div
              data-testid="claude-loading"
              className="bg-white border border-forest-200 rounded-xl p-8 flex items-center gap-4 mb-6"
            >
              <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-forest-900 text-lime-400 flex items-center justify-center">
                <Sparkles size={20} className="animate-pulse" />
              </div>
              <div>
                <p className="text-forest-900 font-semibold">Claude is analysing your load data…</p>
                <p className="text-sm text-slate-500 mt-0.5">
                  Running scenario math, ranking by savings.
                </p>
              </div>
              <div className="ml-auto">
                <Loader size={20} className="animate-spin text-forest-700" />
              </div>
            </div>
          )}

          {genError && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm mb-6">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{genError}</span>
            </div>
          )}

          {source === 'fallback' && scenarios && (
            <div className="mb-4 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2" data-testid="fallback-notice">
              Showing fallback scenarios (Claude API unavailable).
            </div>
          )}

          {/* Empty state */}
          {!scenarios && !generating && (
            <div className="bg-white border border-dashed border-forest-300 rounded-xl p-12 text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 bg-mint rounded-2xl mb-4">
                <Sparkles size={24} className="text-forest-700" />
              </div>
              <h3 className="text-base font-medium text-forest-900 mb-1">
                Generate bespoke scenarios
              </h3>
              <p className="text-sm text-slate-500 mb-6">
                Claude will analyse this site's profile and rank load-shift opportunities by savings.
              </p>
              <button
                type="button"
                onClick={() => runGenerate()}
                className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 text-forest-900 font-semibold rounded-lg px-4 py-2.5 text-sm transition-colors"
              >
                <Sparkles size={15} />
                Generate Scenarios
              </button>
            </div>
          )}

          {/* Ranked scenarios */}
          {scenarios && scenarios.length > 0 && (
            <div className="space-y-4" data-testid="ranked-scenarios">
              {scenarios.map((s) => (
                <ScenarioCard
                  key={s.rank}
                  scenario={s}
                  expanded={expanded === s.rank}
                  onToggleExpand={() => setExpanded((cur) => (cur === s.rank ? null : s.rank))}
                  applianceCurves={baseline?.appliance_curves}
                  scales={defaultScales}
                  baselineCurve={baseline?.load_curve}
                />
              ))}
            </div>
          )}

          {/* Follow-up prompt */}
          {scenarios && scenarios.length > 0 && (
            <form
              onSubmit={handleFollowUp}
              data-testid="followup-form"
              className="mt-6 bg-white border border-slate-200 rounded-xl p-4 shadow-sm"
            >
              <label className="text-xs font-semibold uppercase tracking-wide text-forest-800 mb-2 block">
                Ask Claude for a different angle
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={extraInstruction}
                  onChange={(e) => setExtraInstruction(e.target.value)}
                  placeholder="e.g. What if we added solar? Show me battery options under $30k capex"
                  data-testid="followup-input"
                  className="flex-1 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500 focus:border-transparent"
                />
                <button
                  type="submit"
                  disabled={!extraInstruction.trim() || generating}
                  data-testid="followup-submit"
                  className="inline-flex items-center gap-2 bg-forest-900 hover:bg-forest-800 disabled:bg-slate-300 text-lime-400 disabled:text-slate-500 font-medium rounded-lg px-4 py-2 text-sm transition-colors"
                >
                  <Send size={14} />
                  Ask
                </button>
              </div>
            </form>
          )}

          {scenarios && scenarios.length > 0 && (
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => navigate(`/clients/${id}/report`)}
                data-testid="generate-report-btn"
                className="inline-flex items-center gap-2 bg-lime-500 hover:bg-lime-600 text-forest-900 font-semibold rounded-lg px-6 py-2.5 text-sm transition-colors"
              >
                <FileText size={15} />
                Generate Report
                <ArrowRight size={15} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
