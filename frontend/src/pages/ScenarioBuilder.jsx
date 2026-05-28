import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight, Loader, AlertCircle, Sparkles, Trash2, ArrowRight, FileText, Check, ChevronDown, ChevronUp,
  Layers, Store,
} from 'lucide-react';
import {
  getClient, startGenerateScenarios, getGenerationJob, listScenarios, deleteScenario, clearClientScenarios, createReport, savePlanScenario, fmtCurrency, fmtNumber,
} from '../lib/api';
import { APPLIANCE_LAYERS } from '../components/StackedAreaChart';
import HourlyLineChart from '../components/HourlyLineChart';

const APPLIANCE_HINTS = [
  { label: 'Shift HVAC peak',       appliance: 'HVAC' },
  { label: 'Fridges overnight',     appliance: 'Fridges' },
  { label: 'Reschedule dishwasher', appliance: 'Dishwasher' },
  { label: 'Hot water off-peak',    appliance: 'Hot Water' },
  { label: 'Cut lighting peak',     appliance: 'Lighting' },
  { label: 'Shift ovens early',     appliance: 'Ovens' },
  { label: 'Full site plan',        isPlan: true },
];

// ── Appliance before/after bars ──────────────────────────────────────────────
function ApplianceChangeBars({ changes }) {
  if (!changes || changes.length === 0) return null;
  const rows = changes.map((c) => {
    const beforeTotal = (c.before_curve || []).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const afterTotal  = (c.after_curve  || []).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const totalDelta  = afterTotal - beforeTotal;
    // Peak window: buckets 30–42 = 3pm–9pm
    const beforePeak  = (c.before_curve || []).slice(30, 42).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const afterPeak   = (c.after_curve  || []).slice(30, 42).reduce((s, v) => s + (v || 0) * 0.5, 0);
    const peakDelta   = afterPeak - beforePeak;
    // Shift: total barely changes but peak drops — show peak kWh so bars differ visually
    const isShift = Math.abs(totalDelta) < 0.5 && Math.abs(peakDelta) > 0.05;
    const beforeKwh = isShift ? beforePeak : beforeTotal;
    const afterKwh  = isShift ? afterPeak  : afterTotal;
    const delta     = isShift ? peakDelta  : totalDelta;
    return { ...c, beforeKwh, afterKwh, delta, isShift };
  });
  const maxAbs = Math.max(...rows.map((r) => Math.max(r.beforeKwh, r.afterKwh)), 1);

  return (
    <div className="space-y-3" data-testid="appliance-change-bars">
      {rows.map((r, i) => {
        const layerColor = APPLIANCE_LAYERS.find((l) => l.key === r.appliance)?.color || '#5b4bff';
        const beforeW = (r.beforeKwh / maxAbs) * 100;
        const afterW  = (r.afterKwh  / maxAbs) * 100;
        const positive = r.delta < 0;
        const label = r.isShift
          ? `${positive ? '−' : '+'}${fmtNumber(Math.abs(r.delta), 1)} kWh peak · shifted off-peak`
          : `${positive ? '−' : '+'}${fmtNumber(Math.abs(r.delta), 0)} kWh/day · ${positive ? 'reduced' : 'added'}`;
        return (
          <div key={i} className="bg-white border border-line rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-forest-900 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: layerColor }} />
                {r.appliance}
                {r.isShift && <span className="text-[10px] font-normal text-ink-mute uppercase tracking-wide">peak window</span>}
              </span>
              <span className="text-[11px] text-ink-mute max-w-[60%] text-right leading-snug">{r.summary}</span>
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-12 text-ink-mute uppercase tracking-wide flex-shrink-0">Before</span>
                <div className="flex-1 bg-cream-200 rounded h-3 overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${beforeW}%`, backgroundColor: layerColor, opacity: 0.45 }} />
                </div>
                <span className="text-xs font-medium text-forest-800 tabnum w-16 text-right flex-shrink-0">
                  {fmtNumber(r.beforeKwh, 1)} kWh
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] w-12 text-ink-mute uppercase tracking-wide flex-shrink-0">After</span>
                <div className="flex-1 bg-cream-200 rounded h-3 overflow-hidden">
                  <div className="h-full rounded" style={{ width: `${afterW}%`, backgroundColor: layerColor }} />
                </div>
                <span className="text-xs font-medium text-forest-900 tabnum w-16 text-right flex-shrink-0">
                  {fmtNumber(r.afterKwh, 1)} kWh
                </span>
              </div>
              <div className="pl-14">
                <span className={`text-[11px] tabnum font-medium ${positive ? 'text-forest-700' : 'text-amber-600'}`}>
                  {label}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Retailer negotiation ──────────────────────────────────────────────────────
function RetailerNegotiation({ scenario }) {
  const winner = scenario.retailer_winner;
  const levers = scenario.negotiation_levers || [];
  return (
    <div className="bg-cream-50 border border-line rounded-xl p-4" data-testid="retailer-negotiation">
      <div className="flex items-baseline justify-between mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900">Negotiation Playbook</h4>
        {winner && (
          <span className="text-xs text-ink-soft">
            Recommended: <span className="font-semibold text-violet">{winner}</span>
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

// ── Scenario card ─────────────────────────────────────────────────────────────
function ScenarioCard({ scenario, selected, onToggleSelect, onDelete, expanded, onToggleExpand }) {
  const totalLow   = scenario.savings_annual_low  ?? 0;
  const totalHigh  = scenario.savings_annual_high ?? 0;

  return (
    <div
      data-testid={`scenario-card-${scenario.id}`}
      className={`bg-cream-50 border rounded-2xl shadow-card overflow-hidden transition-all ${
        selected ? 'border-violet ring-2 ring-violet/30' : 'border-line hover:border-forest-300'
      }`}
    >
      {/* Collapsed header — always visible */}
      <div className="p-5">
        <div className="flex items-center gap-4">
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
            <span className="text-[10px] uppercase tracking-wider text-ink-mute">Proposed Plan {scenario.rank}</span>
            <h3 className="font-display text-xl text-forest-900 leading-tight">{scenario.name}</h3>
            {scenario.appliance_changes?.[0] && (
              <p className="text-xs text-ink-soft mt-0.5">
                Shift <span className="font-medium text-forest-800">{scenario.appliance_changes[0].appliance}</span> off-peak
                {scenario.retailer_winner && <> → <span className="font-medium text-violet">{scenario.retailer_winner}</span></>}
                {' → '}save ~<span className="font-medium text-forest-700 tabnum">{fmtCurrency(scenario.savings_annual_low)}/yr</span>
              </p>
            )}
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
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

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-line bg-cream-100/50 px-5 py-6 space-y-6">

          {/* 1 — Before / After line charts: appliance curve + total demand */}
          {(() => {
            const change = scenario.appliance_changes?.[0];
            const appColor = APPLIANCE_LAYERS.find((l) => l.key === change?.appliance)?.color || '#5b4bff';
            return (
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                  Load Profile — Before vs After
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white border border-line rounded-xl p-3">
                    <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wide mb-2">Before</p>
                    <HourlyLineChart
                      series={scenario.baseline_curve || []}
                      overlay={change?.before_curve || null}
                      overlayColor={appColor}
                      height={200}
                      testId={`scenario-chart-before-${scenario.id}`}
                    />
                  </div>
                  <div className="bg-white border border-line rounded-xl p-3">
                    <p className="text-[11px] font-semibold text-violet uppercase tracking-wide mb-2">After</p>
                    <HourlyLineChart
                      series={scenario.shifted_curve || scenario.baseline_curve || []}
                      overlay={change?.after_curve || null}
                      overlayColor={appColor}
                      height={200}
                      testId={`scenario-chart-after-${scenario.id}`}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-5 mt-2 px-1">
                  <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
                    <span className="inline-block w-5 border-t-2 border-forest-900 opacity-70" />
                    Total demand
                  </span>
                  {change?.appliance && (
                    <span className="flex items-center gap-1.5 text-[11px] text-ink-soft">
                      <span className="inline-block w-5 border-t-2" style={{ borderColor: appColor }} />
                      {change.appliance}
                    </span>
                  )}
                </div>
              </div>
            );
          })()}

          {/* 2 — Appliance changes */}
          {scenario.appliance_changes && scenario.appliance_changes.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wider text-forest-900 mb-3">
                Appliance Changes
              </h4>
              <ApplianceChangeBars changes={scenario.appliance_changes} />
            </div>
          )}

          {/* 3 — Summary: rationale + savings + retailer */}
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-6">
              {scenario.rationale && (
                <p className="text-sm text-ink-soft leading-relaxed flex-1">{scenario.rationale}</p>
              )}
              <div className="text-right flex-shrink-0">
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Annual saving</p>
                <p className="text-lg font-display text-violet tabnum">
                  {fmtCurrency(totalLow)}
                  <span className="text-xs text-ink-mute mx-1">–</span>
                  {fmtCurrency(totalHigh)}
                </p>
              </div>
            </div>
            <RetailerNegotiation scenario={scenario} />
          </div>

        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ScenarioBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [client,           setClient]           = useState(null);
  const [scenarios,        setScenarios]        = useState([]);
  const count = 1;
  const [extraInstruction, setExtraInstruction] = useState('');
  const [targetAppliance,  setTargetAppliance]  = useState(null);
  const [generating,       setGenerating]       = useState(false);
  const [progress,         setProgress]         = useState('');
  const [error,            setError]            = useState('');
  const [selectedIds,      setSelectedIds]      = useState(new Set());
  const [expandedId,       setExpandedId]       = useState(null);
  const [creatingReport,   setCreatingReport]   = useState(false);
  const [storeContext,      setStoreContext]      = useState(null);
  const [combinedStreaming, setCombinedStreaming] = useState(false);
  const [combinedError,     setCombinedError]    = useState('');

  useEffect(() => {
    // Pick up any store context passed from baseline page
    const raw = sessionStorage.getItem(`scenario_store_context_${id}`);
    const ctx = raw ? (() => { try { return JSON.parse(raw); } catch { return null; } })() : null;
    if (ctx) setStoreContext(ctx);

    (async () => {
      try {
        const [clientRes, scenariosRes] = await Promise.all([getClient(id), listScenarios(id)]);
        setClient(clientRes.data);
        sessionStorage.setItem(`client_name_${id}`, clientRes.data.name);
        setScenarios(scenariosRes.data || []);
      } catch (err) {
        setError(err.response?.data?.detail || 'Failed to load page.');
      }
    })();
  }, [id]);

  const runGenerate = async () => {
    setGenerating(true);
    setError('');
    setProgress('Starting…');
    try {
      const aggStoreIds = storeContext?.store_ids?.length > 0 ? storeContext.store_ids : null;
      const res   = await startGenerateScenarios(id, count, extraInstruction.trim() || null, aggStoreIds, targetAppliance);
      const jobId = res.data.job_id;
      setProgress('Claude is analysing the site…');
      const start = Date.now();
      const poll  = async () => {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        const jobRes  = await getGenerationJob(jobId);
        const job     = jobRes.data;

        // Show partial results as they arrive, deduplicating by id
        const partial = job.scenarios || [];
        if (partial.length > 0) {
          setScenarios((cur) => {
            const existingIds = new Set(cur.map((s) => s.id));
            const newOnes = partial.filter((s) => !existingIds.has(s.id));
            if (newOnes.length === 0) return cur;
            if (newOnes[0]) setExpandedId(newOnes[0].id);
            return [...newOnes, ...cur];
          });
        }

        if (job.status === 'done') {
          setExtraInstruction('');
          setTargetAppliance(null);
          setGenerating(false);
          setProgress('');
        } else if (job.status === 'error') {
          setError(job.error || 'Generation failed.');
          setGenerating(false);
          setProgress('');
        } else {
          const completed = partial.length;
          setProgress(`Scenario ready · ${elapsed}s`);
          setTimeout(poll, 1000);
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
    setSelectedIds((cur) => { const next = new Set(cur); next.delete(sid); return next; });
  };

  const loadCombinedPlan = async () => {
    if (combinedStreaming) return;
    setCombinedStreaming(true);
    setCombinedError('');
    const collected = [];
    try {
      const res = await fetch(`/api/clients/${id}/analyse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: 'Full site reduction plan', history: [] }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') break;
          try { collected.push(JSON.parse(raw)); } catch { /* ignore partial chunks */ }
        }
      }
      // Save the resolved multi_scenario block as a proper scenario
      const planBlock = collected.find(b => b.type === 'multi_scenario' && b.resolved);
      if (planBlock) {
        const saveRes = await savePlanScenario(id, planBlock);
        const saved = saveRes.data;
        setScenarios(prev => {
          const existingIds = new Set(prev.map(s => s.id));
          if (existingIds.has(saved.id)) return prev;
          return [saved, ...prev];
        });
        setExpandedId(saved.id);
      }
    } catch (e) {
      setCombinedError(e.message || 'Failed to load combined plan.');
    } finally {
      setCombinedStreaming(false);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Delete all scenarios for this client?')) return;
    await clearClientScenarios(id);
    setScenarios([]);
    setSelectedIds(new Set());
  };

  const toggleSelect = (sid) => {
    setSelectedIds((cur) => {
      const next = new Set(cur);
      if (next.has(sid)) next.delete(sid); else next.add(sid);
      return next;
    });
  };

  const handleCreateReport = async () => {
    if (selectedIds.size === 0) { setError('Select at least one scenario to add to a report.'); return; }
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
            Claude shifts appliance load off-peak, compares retailers, and shows you where to save.
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
                <h2 className="font-display text-xl">Generate scenario</h2>
                <p className="text-xs text-forest-100/60">Add an optional focus or pick a suggestion below.</p>
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap mb-4">
              <input
                type="text"
                value={extraInstruction}
                onChange={(e) => setExtraInstruction(e.target.value)}
                placeholder="e.g. just make it cheaper, no big installs…"
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
              {APPLIANCE_HINTS.map((hint) => (
                <button
                  key={hint.label}
                  type="button"
                  onClick={() => {
                    if (hint.isPlan) { loadCombinedPlan(); }
                    else { setExtraInstruction(hint.label); setTargetAppliance(hint.appliance); }
                  }}
                  disabled={hint.isPlan && combinedStreaming}
                  className={`hint-bubble ${!hint.isPlan && extraInstruction === hint.label ? 'ring-2 ring-violet/50' : ''} ${hint.isPlan ? 'ring-2 ring-lime/40' : ''} disabled:opacity-60`}
                  style={{ background: 'rgba(255,255,255,0.06)', borderColor: 'rgba(196,233,74,0.3)', color: '#dde7c8' }}
                >
                  {hint.isPlan && combinedStreaming
                    ? <Loader size={11} className="animate-spin" />
                    : <Sparkles size={11} />}
                  {hint.isPlan && combinedStreaming ? 'Analysing…' : hint.label}
                </button>
              ))}
            </div>

            {combinedError && (
              <p className="mt-2 text-xs text-red-400">{combinedError}</p>
            )}
          </div>

          {/* Store context banner */}
          {storeContext && (
            <div className={`flex items-center gap-3 rounded-xl px-4 py-3 border text-sm ${
              storeContext.type === 'aggregate'
                ? 'bg-violet/8 border-violet/30 text-violet-900'
                : 'bg-forest-50 border-forest-200 text-forest-900'
            }`}>
              {storeContext.type === 'aggregate'
                ? <Layers size={15} className="text-violet flex-shrink-0" />
                : <Store size={15} className="text-forest-700 flex-shrink-0" />}
              <span>
                {storeContext.type === 'aggregate' ? (
                  <><span className="font-semibold">Aggregate view</span> — {storeContext.store_names.join(' + ')}</>
                ) : (
                  <><span className="font-semibold">Single store</span> — {storeContext.store_names[0]}</>
                )}
                <span className="text-ink-mute ml-2">· Scenarios will use this load profile</span>
              </span>
              <button
                type="button"
                onClick={() => { sessionStorage.removeItem(`scenario_store_context_${id}`); setStoreContext(null); }}
                className="ml-auto text-[11px] text-ink-mute hover:text-red-600 underline"
              >
                Clear
              </button>
            </div>
          )}

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

          {scenarios.length === 0 && !generating && (
            <div className="border-2 border-dashed border-line rounded-2xl bg-cream-50 p-12 text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-lime/40 rounded-xl mb-4">
                <Sparkles size={20} className="text-forest-800" />
              </div>
              <h3 className="font-display text-xl text-forest-900 mb-1">No scenarios yet.</h3>
              <p className="text-sm text-ink-mute">Add a focus or pick a suggestion above, then click <span className="font-semibold">Generate</span>.</p>
            </div>
          )}

          {scenarios.length > 0 && (
            <div className="flex items-center justify-between text-xs text-ink-mute pt-2">
              <p>
                <span className="font-semibold text-forest-800">{scenarios.length}</span> scenario{scenarios.length === 1 ? '' : 's'} ·
                <span className="font-semibold text-violet ml-1">{selectedIds.size}</span> selected
              </p>
              <button
                type="button"
                onClick={handleClearAll}
                data-testid="clear-scenarios-btn"
                className="text-xs inline-flex items-center gap-1 text-ink-mute hover:text-red-600"
              >
                <Trash2 size={12} /> Clear all
              </button>
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

        {/* Side rail — report bundler only */}
        <aside className="lg:col-span-2">
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
