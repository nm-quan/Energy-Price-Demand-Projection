import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ChevronRight, Loader, AlertCircle, Sparkles, Trash2, ArrowRight, FileText, Check, ChevronDown, ChevronUp,
  Layers, Store, Send, MessageCircle,
} from 'lucide-react';
import {
  getClient, startGenerateScenarios, getGenerationJob, listScenarios, deleteScenario, clearClientScenarios, createReport, chatWithClient, fmtCurrency, fmtNumber,
} from '../lib/api';
import { APPLIANCE_LAYERS } from '../components/StackedAreaChart';
import HourlyLineChart from '../components/HourlyLineChart';

const HINT_PROMPTS = [
  'Just make it cheaper',
  'No upfront cost',
  'Fastest payback',
  'Switch retailer too',
  'Cut the peak bill',
  'Overnight shift only',
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

// ── Chat view ─────────────────────────────────────────────────────────────────
function ChatView({ clientId, onScenarioGenerated }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi! I can explain your energy costs, what to shift, and which retailer gives the best deal. Ask me anything — or say \"generate a plan\" and I'll build one." },
  ]);
  const [input, setInput]   = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const res = await chatWithClient(clientId, history, text);
      const { reply, scenario } = res.data;
      setMessages(prev => [...prev, { role: 'assistant', content: reply, scenario }]);
      if (scenario) onScenarioGenerated(scenario);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }]);
    } finally {
      setLoading(false);
    }
  };

  const CHAT_HINTS = ['What uses the most power?', 'How does load shifting work?', 'Which retailer is cheapest?', 'Generate a plan'];

  return (
    <div className="bg-forest-800 rounded-2xl overflow-hidden flex flex-col" style={{ height: '560px' }}>
      <div className="flex-1 overflow-y-auto p-5 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[82%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user' ? 'bg-violet text-white' : 'bg-forest-700 text-forest-100'
            }`}>
              {m.content}
              {m.scenario && (
                <div className="mt-2.5 bg-forest-900/60 rounded-xl p-3 border border-forest-600">
                  <p className="text-[10px] uppercase tracking-wider text-forest-400 mb-1">Plan generated</p>
                  <p className="text-white font-semibold text-sm">{m.scenario.name}</p>
                  <p className="text-lime font-medium text-sm tabnum mt-0.5">
                    ~{fmtCurrency(m.scenario.savings_annual_low)}/yr → {m.scenario.retailer_winner}
                  </p>
                  <p className="text-forest-300 text-[11px] mt-1">Saved to Scenarios tab</p>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-forest-700 rounded-2xl px-4 py-3">
              <Loader size={14} className="animate-spin text-forest-300" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-forest-700 px-4 pt-3 pb-2 flex flex-wrap gap-2">
        {CHAT_HINTS.map(h => (
          <button
            key={h}
            onClick={() => { setInput(h); }}
            className="text-[11px] px-3 py-1 rounded-full border border-forest-600 text-forest-300 hover:border-lime hover:text-lime transition-colors"
          >
            {h}
          </button>
        ))}
      </div>

      <div className="px-4 pb-4 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask about this site's energy…"
          className="flex-1 bg-forest-700 border border-forest-600 rounded-xl px-4 py-2.5 text-sm text-white placeholder:text-forest-400 focus:outline-none focus:border-lime"
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="btn-violet flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center disabled:opacity-40"
        >
          <Send size={15} />
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ScenarioBuilder() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [activeTab,        setActiveTab]        = useState('scenarios');
  const [client,           setClient]           = useState(null);
  const [scenarios,        setScenarios]        = useState([]);
  const [count,            setCount]            = useState(3);
  const [extraInstruction, setExtraInstruction] = useState('');
  const [generating,       setGenerating]       = useState(false);
  const [progress,         setProgress]         = useState('');
  const [error,            setError]            = useState('');
  const [selectedIds,      setSelectedIds]      = useState(new Set());
  const [expandedId,       setExpandedId]       = useState(null);
  const [creatingReport,   setCreatingReport]   = useState(false);
  const [storeContext,     setStoreContext]      = useState(null);

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
      const res   = await startGenerateScenarios(id, count, extraInstruction.trim() || null, aggStoreIds);
      const jobId = res.data.job_id;
      setProgress(`Claude is analysing the site (count=${count})…`);
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
          setGenerating(false);
          setProgress('');
        } else if (job.status === 'error') {
          setError(job.error || 'Generation failed.');
          setGenerating(false);
          setProgress('');
        } else {
          const completed = partial.length;
          setProgress(`${completed} of ${count} scenario${count > 1 ? 's' : ''} ready · ${elapsed}s`);
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

  const handleScenarioFromChat = (scenario) => {
    setScenarios(prev => {
      const existingIds = new Set(prev.map(s => s.id));
      if (existingIds.has(scenario.id)) return prev;
      return [scenario, ...prev];
    });
    setExpandedId(scenario.id);
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
          <h1 className="font-display text-5xl text-forest-900 leading-none">
            {activeTab === 'scenarios' ? 'Load-shift scenarios.' : 'Chat with your data.'}
          </h1>
          <p className="text-sm text-ink-soft mt-3 max-w-xl">
            {activeTab === 'scenarios'
              ? 'Claude shifts appliance load off-peak, compares retailers, and shows you where to save.'
              : 'Ask about energy costs, what to shift, which retailer is best — or say "generate a plan".'}
          </p>
        </div>
        <div className="flex gap-1 bg-forest-100 rounded-full p-1 flex-shrink-0">
          <button
            onClick={() => setActiveTab('scenarios')}
            className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
              activeTab === 'scenarios' ? 'bg-white text-forest-900 shadow-sm' : 'text-ink-mute hover:text-forest-900'
            }`}
          >
            <Sparkles size={13} />Scenarios
          </button>
          <button
            onClick={() => setActiveTab('chat')}
            className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
              activeTab === 'chat' ? 'bg-white text-forest-900 shadow-sm' : 'text-ink-mute hover:text-forest-900'
            }`}
          >
            <MessageCircle size={13} />Chat
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-7 gap-6">

        {activeTab === 'chat' && (
          <div className="lg:col-span-7">
            <ChatView clientId={id} onScenarioGenerated={handleScenarioFromChat} />
          </div>
        )}

        {/* Main column — scenarios tab */}
        <div className={`lg:col-span-5 space-y-5 ${activeTab === 'chat' ? 'hidden' : ''}`}>

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
              <p className="text-sm text-ink-mute">Set a count above and click <span className="font-semibold">Generate</span>.</p>
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
        <aside className={`lg:col-span-2 ${activeTab === 'chat' ? 'hidden' : ''}`}>
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
