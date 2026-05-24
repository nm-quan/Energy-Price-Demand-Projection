import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight, Loader, AlertCircle, Sparkles, Send, Trash2, ArrowRight, FileText, Brain, Check, ChevronDown, ChevronUp,
} from 'lucide-react';
import {
  getClient, startGenerateScenarios, getGenerationJob, listScenarios, deleteScenario, clearClientScenarios, createReport, fmtCurrency, fmtNumber,
} from '../lib/api';
import StackedAreaChart, { APPLIANCE_LAYERS } from '../components/StackedAreaChart';

const HINT_PROMPTS = [
  'Focus on HVAC pre-cooling',
  'Include a battery option',
  'Cheapest capex, fastest payback',
  'Switch retailer + shift load',
  'Aggressive load-shift to off-peak',
  'Minimise demand charges',
];

// ── Appliance before/after bar chart (per appliance kWh comparison) ─────────
function ApplianceChangeBars({ changes }) {
  if (!changes || changes.length === 0) return null;
  const rows = changes.map((c) => {
    const beforeKwh = (c.before_curve || []).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const afterKwh = (c.after_curve || []).reduce((s, v) => s + (v || 0) * 0.5, 0);
    return { ...c, beforeKwh, afterKwh, delta: afterKwh - beforeKwh };
  });
  const maxAbs = Math.max(...rows.map((r) => Math.max(r.beforeKwh, r.afterKwh)), 1);

  return (
    <div className="space-y-3" data-testid="appliance-change-bars">
      {rows.map((r, i) => {
        const layerColor = APPLIANCE_LAYERS.find((l) => l.key === r.appliance)?.color || '#5b4bff';
        const beforeW = (r.beforeKwh / maxAbs) * 100;
        const afterW = (r.afterKwh / maxAbs) * 100;
        return (
          <div key={i} className="bg-cream-50 border border-line rounded-xl p-3">
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="font-semibold text-forest-900 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: layerColor }} />
                {r.appliance}
              </span>
              <span className="text-ink-mute">{r.summary}</span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-12 text-ink-mute uppercase">Before</span>
                <div className="flex-1 bg-cream-200 rounded h-3 relative overflow-hidden">
                  <div className="h-full rounded transition-all" style={{ width: `${beforeW}%`, backgroundColor: layerColor, opacity: 0.5 }} />
                </div>
                <span className="text-xs font-medium text-forest-800 tabnum w-16 text-right">
                  {fmtNumber(r.beforeKwh, 0)} kWh
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-12 text-ink-mute uppercase">After</span>
                <div className="flex-1 bg-cream-200 rounded h-3 relative overflow-hidden">
                  <div className="h-full rounded transition-all" style={{ width: `${afterW}%`, backgroundColor: layerColor }} />
                </div>
                <span className="text-xs font-medium text-forest-900 tabnum w-16 text-right">
                  {fmtNumber(r.afterKwh, 0)} kWh
                </span>
              </div>
              <div className="flex items-center gap-2 pl-14">
                <span className={`text-[11px] tabnum font-medium ${r.delta < 0 ? 'text-forest-700' : 'text-amber-600'}`}>
                  {r.delta < 0 ? '−' : '+'}{fmtNumber(Math.abs(r.delta), 0)} kWh/day · {r.delta < 0 ? 'reduced' : 'added'}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Retailer comparison table (negotiation lever) ───────────────────────────
function RetailerNegotiation({ scenario }) {
  const winner = scenario.retailer_winner;
  const levers = scenario.negotiation_levers || [];

  return (
    <div className="bg-cream-50 border border-line rounded-xl p-4" data-testid="retailer-negotiation">
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900">Negotiation Playbook</h4>
        {winner && (
          <span className="text-xs text-ink-soft">
            Recommended retailer: <span className="font-semibold text-violet">{winner}</span>
          </span>
        )}
      </div>
      {levers.length > 0 && (
        <ul className="space-y-1.5 text-xs text-ink-soft">
          {levers.map((lever, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-violet font-bold flex-shrink-0 mt-0.5">→</span>
              <span>{lever}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Scenario card ──────────────────────────────────────────────────────────
function ScenarioCard({ scenario, selected, onToggleSelect, onDelete, expanded, onToggleExpand }) {
  const totalLow = scenario.savings_annual_low ?? 0;
  const totalHigh = scenario.savings_annual_high ?? 0;

  return (
    <div
      data-testid={`scenario-card-${scenario.id}`}
      className={`bg-cream-50 border rounded-2xl shadow-card overflow-hidden transition-all ${
        selected ? 'border-violet ring-2 ring-violet/30' : 'border-line hover:border-forest-300'
      }`}
    >
      <div className="p-5">
        <div className="flex items-start gap-4">
          <button
            type="button"
            onClick={onToggleSelect}
            data-testid={`select-scenario-${scenario.id}`}
            className={`flex-shrink-0 w-7 h-7 rounded-md border-2 flex items-center justify-center transition-colors ${
              selected ? 'bg-violet border-violet text-white' : 'bg-cream-50 border-line hover:border-violet'
            }`}
            aria-label="Add to report"
          >
            {selected && <Check size={15} strokeWidth={3} />}
          </button>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-wider text-ink-mute">#{scenario.rank}</span>
            </div>
            <h3 className="font-display text-xl text-forest-900 leading-tight">{scenario.name}</h3>
            {scenario.rationale && (
              <p className="text-sm text-ink-soft mt-2 leading-relaxed">{scenario.rationale}</p>
            )}
          </div>

          <div className="text-right flex-shrink-0">
            <p className="text-[10px] uppercase tracking-wider text-ink-mute">Annual saving</p>
            <p className="text-lg font-display text-violet tabnum">
              {fmtCurrency(totalLow)}
              <span className="text-xs text-ink-mute mx-1">–</span>
              {fmtCurrency(totalHigh)}
            </p>
            <div className="flex items-center gap-2 mt-2 justify-end">
              <button
                type="button"
                onClick={onToggleExpand}
                data-testid={`expand-scenario-${scenario.id}`}
                className="text-[11px] inline-flex items-center gap-1 text-forest-700 hover:text-violet font-medium"
              >
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                {expanded ? 'Hide' : 'Details'}
              </button>
              <button
                type="button"
                onClick={onDelete}
                data-testid={`delete-scenario-${scenario.id}`}
                className="text-[11px] inline-flex items-center gap-1 text-ink-mute hover:text-red-600"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-line bg-cream-100/50 px-5 py-5 space-y-5">
          {/* Hourly load curve overlay */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-2">
              Hourly Load — Before vs After
            </h4>
            <StackedAreaChart
              applianceCurves={scenario.baseline_appliance_curves || {}}
              scales={{}}
              height={200}
              baseline={scenario.baseline_curve}
              overlay={scenario.shifted_curve}
              testId={`scenario-chart-${scenario.id}`}
            />
            <div className="flex items-center gap-4 mt-2 text-[11px] text-ink-mute">
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-8 border-t-2 border-dashed border-forest-700" />
                Baseline
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block w-8 border-t-2 border-violet" />
                Optimised
              </span>
            </div>
          </div>

          {/* Appliance changes */}
          {scenario.appliance_changes && scenario.appliance_changes.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                Appliance Changes
              </h4>
              <ApplianceChangeBars changes={scenario.appliance_changes} />
            </div>
          )}

          {/* Retailer negotiation */}
          <RetailerNegotiation scenario={scenario} />
        </div>
      )}
    </div>
  );
}

// ── Agent Memory side panel ─────────────────────────────────────────────────
function AgentMemoryPanel({ memory }) {
  if (!memory || memory.length === 0) {
    return (
      <div className="memo-card p-4" data-testid="agent-memory-empty">
        <p className="flex items-center gap-2 text-forest-700 mb-2 font-sans font-semibold text-sm">
          <Brain size={14} /> Agent Memory
        </p>
        <p className="text-ink-mute font-sans text-xs">
          Generate scenarios to see what the agent learned about this site.
        </p>
      </div>
    );
  }
  return (
    <div className="memo-card p-4" data-testid="agent-memory-panel">
      <p className="flex items-center gap-2 text-forest-800 mb-3 font-sans font-semibold text-sm">
        <Brain size={14} className="text-violet" /> Agent Memory
      </p>
      <ul className="space-y-2">
        {memory.map((bullet, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-violet flex-shrink-0">·</span>
            <span>{bullet}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function ScenarioBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client, setClient] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [agentMemory, setAgentMemory] = useState([]);
  const [count, setCount] = useState(3);
  const [extraInstruction, setExtraInstruction] = useState('');
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [expandedId, setExpandedId] = useState(null);
  const [creatingReport, setCreatingReport] = useState(false);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [clientRes, scenariosRes] = await Promise.all([getClient(id), listScenarios(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        const list = scenariosRes.data || [];
        setScenarios(list);
        if (list.length > 0) {
          // Use the most recent batch's agent_memory
          setAgentMemory(list[0].agent_memory || []);
        }
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load page.');
      }
    };
    fetch();
  }, [id]);

  const runGenerate = async () => {
    setGenerating(true);
    setError('');
    setProgress('Starting…');
    try {
      const res = await startGenerateScenarios(id, count, extraInstruction.trim() || null);
      const jobId = res.data.job_id;
      setProgress(`Claude is analysing the site (count=${count})…`);
      // Poll until done
      const start = Date.now();
      const poll = async () => {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const jobRes = await getGenerationJob(jobId);
        const job = jobRes.data;
        if (job.status === 'done') {
          const newScenarios = job.scenarios || [];
          setScenarios((cur) => [...newScenarios, ...cur]);
          setAgentMemory(job.agent_memory || []);
          if (newScenarios[0]) setExpandedId(newScenarios[0].id);
          setExtraInstruction('');
          setGenerating(false);
          setProgress('');
        } else if (job.status === 'error') {
          setError(job.error || 'Generation failed.');
          setGenerating(false);
          setProgress('');
        } else {
          setProgress(`Generating ${count} scenario${count > 1 ? 's' : ''} in parallel · ${elapsed}s`);
          setTimeout(poll, 2500);
        }
      };
      setTimeout(poll, 1500);
    } catch (err) {
      setError(err.response?.data?.detail || 'Scenario generation failed. Try again.');
      setGenerating(false);
      setProgress('');
    }
  };

  const handleDelete = async (sid) => {
    await deleteScenario(sid);
    setScenarios((cur) => cur.filter((s) => s.id !== sid));
    setSelectedIds((cur) => {
      const next = new Set(cur);
      next.delete(sid);
      return next;
    });
  };

  const handleClearAll = async () => {
    if (!window.confirm('Delete all scenarios for this client?')) return;
    await clearClientScenarios(id);
    setScenarios([]);
    setSelectedIds(new Set());
    setAgentMemory([]);
  };

  const toggleSelect = (sid) => {
    setSelectedIds((cur) => {
      const next = new Set(cur);
      if (next.has(sid)) next.delete(sid); else next.add(sid);
      return next;
    });
  };

  const handleCreateReport = async () => {
    if (selectedIds.size === 0) {
      setError('Select at least one scenario to add to a report.');
      return;
    }
    setCreatingReport(true);
    try {
      const res = await createReport(id, {
        scenario_ids: Array.from(selectedIds),
        title: `${client?.name || 'Site'} — Energy Report`,
      });
      navigate(`/clients/${id}/report?focus=${res.data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create report.');
    } finally {
      setCreatingReport(false);
    }
  };

  return (
    <div className="p-10 max-w-7xl" data-testid="scenarios-page">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.15em] text-ink-mute mb-3">
        <Link to="/clients" className="hover:text-forest-700">Clients</Link>
        <ChevronRight size={12} />
        {client && (
          <Link to={`/clients/${id}/baseline`} className="hover:text-forest-700 text-forest-800 font-medium">
            {client.name}
          </Link>
        )}
        <ChevronRight size={12} />
        <span className="text-violet font-medium">Scenarios</span>
      </div>

      <div className="flex items-end justify-between mb-8 gap-6">
        <div>
          <h1 className="font-display text-5xl text-forest-900 leading-none">Load-shift scenarios.</h1>
          <p className="text-sm text-ink-soft mt-3 max-w-xl">
            Claude analyses the site, simulates appliance-level changes, compares retailers, and saves each scenario to your database.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">
        {/* Main column */}
        <div className="lg:col-span-5 space-y-5">
          {/* Generator card */}
          <div className="bg-forest-800 text-white rounded-2xl p-6 shadow-card">
            <div className="flex items-center gap-3 mb-4">
              <div className="bg-lime rounded-md w-8 h-8 flex items-center justify-center">
                <Sparkles size={16} className="text-forest-900" strokeWidth={2.5} />
              </div>
              <div>
                <h2 className="font-display text-xl">Generate scenarios</h2>
                <p className="text-xs text-forest-100/60">Pick how many. Add an optional focus. Claude does the rest.</p>
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap mb-4">
              <label className="text-[11px] uppercase tracking-wider text-forest-100/70">Count</label>
              <input
                type="number"
                min={1} max={10}
                value={count}
                onChange={(e) => setCount(Math.max(1, Math.min(10, parseInt(e.target.value || '1', 10))))}
                data-testid="scenario-count-input"
                className="w-16 bg-forest-700 border border-forest-600 rounded-lg px-3 py-1.5 text-sm tabnum focus:outline-none focus:border-lime"
              />
              <input
                type="text"
                value={extraInstruction}
                onChange={(e) => setExtraInstruction(e.target.value)}
                placeholder="Optional focus (e.g. battery only, no capex over $20k)…"
                data-testid="extra-instruction-input"
                className="flex-1 min-w-[200px] bg-forest-700 border border-forest-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-lime placeholder:text-forest-100/30"
              />
              <button
                type="button"
                onClick={runGenerate}
                disabled={generating}
                data-testid="generate-scenarios-btn"
                className="btn-violet inline-flex items-center gap-2 font-semibold rounded-full px-5 py-2 text-sm transition-all disabled:opacity-50"
              >
                {generating ? <Loader size={14} className="animate-spin" /> : <Sparkles size={14} strokeWidth={2.5} />}
                {generating ? 'Generating…' : 'Generate'}
              </button>
            </div>

            <div className="flex flex-wrap gap-2">
              {HINT_PROMPTS.map((hint) => (
                <button
                  key={hint}
                  type="button"
                  onClick={() => setExtraInstruction(hint)}
                  data-testid={`hint-${hint.toLowerCase().replace(/\W+/g, '-')}`}
                  className="hint-bubble"
                  style={{ background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(196,233,74,0.3)', color: '#dde7c8' }}
                >
                  <Sparkles size={11} /> {hint}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
              <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {generating && progress && (
            <div
              data-testid="generation-progress"
              className="flex items-center gap-3 bg-violet/10 border border-violet/30 rounded-xl px-4 py-3 text-sm text-violet-700"
            >
              <Loader size={16} className="animate-spin text-violet" />
              <span className="font-medium">{progress}</span>
            </div>
          )}

          {/* Scenario list */}
          {scenarios.length === 0 && !generating && (
            <div className="border-2 border-dashed border-line rounded-2xl bg-cream-50 p-12 text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-lime/40 rounded-xl mb-4">
                <Sparkles size={20} className="text-forest-800" />
              </div>
              <h3 className="font-display text-xl text-forest-900 mb-1">No scenarios yet.</h3>
              <p className="text-sm text-ink-mute">Set a count above and click <span className="font-semibold">Generate</span>.</p>
            </div>
          )}

          {scenarios.length > 0 && (
            <div className="flex items-center justify-between text-xs text-ink-mute pt-2">
              <p>
                <span className="font-semibold text-forest-800">{scenarios.length}</span> scenario{scenarios.length === 1 ? '' : 's'} ·
                <span className="font-semibold text-violet ml-1">{selectedIds.size}</span> selected
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleClearAll}
                  data-testid="clear-scenarios-btn"
                  className="text-xs inline-flex items-center gap-1 text-ink-mute hover:text-red-600"
                >
                  <Trash2 size={12} /> Clear all
                </button>
              </div>
            </div>
          )}

          <div className="space-y-3" data-testid="scenarios-list">
            {scenarios.map((s) => (
              <ScenarioCard
                key={s.id}
                scenario={s}
                selected={selectedIds.has(s.id)}
                onToggleSelect={() => toggleSelect(s.id)}
                onDelete={() => handleDelete(s.id)}
                expanded={expandedId === s.id}
                onToggleExpand={() => setExpandedId((cur) => (cur === s.id ? null : s.id))}
              />
            ))}
          </div>
        </div>

        {/* Side rail */}
        <aside className="lg:col-span-2 space-y-4">
          <AgentMemoryPanel memory={agentMemory} />

          {scenarios.length > 0 && (
            <div className="bg-violet/10 border border-violet/30 rounded-2xl p-4">
              <h3 className="font-display text-lg text-forest-900 mb-1">Bundle into a report</h3>
              <p className="text-xs text-ink-soft mb-3">
                Tick scenarios on the left, then create a saved report. PDF export from there.
              </p>
              <button
                type="button"
                onClick={handleCreateReport}
                disabled={selectedIds.size === 0 || creatingReport}
                data-testid="create-report-btn"
                className="btn-violet w-full inline-flex items-center justify-center gap-2 font-semibold rounded-full px-4 py-2.5 text-sm transition-all disabled:opacity-50"
              >
                {creatingReport ? <Loader size={14} className="animate-spin" /> : <FileText size={14} />}
                Create report ({selectedIds.size})
                {!creatingReport && <ArrowRight size={14} />}
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
