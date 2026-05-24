import React, { useEffect, useMemo, useRef, useState } from "react";
import { Send, Pencil, Check, X, ArrowRight } from "lucide-react";
import { api, fmtCurrency, fmtNumber } from "../lib/api";
import MeterRail from "./MeterRail";

const PROFILE_FIELDS = [
  { id: "business_type", label: "Type" },
  { id: "hours", label: "Hours" },
  { id: "sites", label: "Sites" },
  { id: "major_loads", label: "Major loads" },
  { id: "shiftable", label: "Shiftable" },
  { id: "fixed", label: "Fixed" },
  { id: "capex_budget", label: "Capex budget" },
  { id: "constraints", label: "Constraints" },
];

const REQUIRED = ["hours", "major_loads", "capex_budget"];

const CONF_DOT = {
  high: "bg-emerald-500",
  medium: "bg-amber-500",
  low: "bg-slate-300",
};

const SUGGESTIONS = [
  "Describe your operating hours",
  "List your major equipment",
  "What changes would you consider?",
];

const INITIAL_CLAUDE_MSG =
  "Tell me about your business — what you do, when you're open, what equipment you have, and what changes you'd be willing to consider. I'll use this to recommend the best plan and load schedule for you.";

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function SiteHeader({ meter, currentPlan }) {
  if (!meter) {
    return (
      <div className="rounded-xl border border-line bg-white px-5 py-3 text-[12.5px] text-ink-mute">
        Loading site…
      </div>
    );
  }
  return (
    <div
      data-testid="site-header"
      className="rounded-xl border border-line bg-white px-5 py-3 flex flex-wrap items-baseline gap-x-4 gap-y-1"
    >
      <span className="text-[15px] font-bold text-ink tracking-tightish">
        {meter.nickname}
      </span>
      <span className="text-[12px] text-ink-mute tabnum">
        NMI {meter.nmi}
      </span>
      <span className="text-[12px] text-ink-mute tabnum">
        Annual {fmtNumber(meter.annual_kwh / 1000, 1)} MWh
      </span>
      <span className="text-[12px] text-ink-mute">
        Current plan: <span className="text-ink-soft font-medium">{meter.current_plan_label}</span>
        {currentPlan && (
          <span className="tabnum ml-1.5 text-ink">· {fmtCurrency(currentPlan.shifted_cost)}/yr</span>
        )}
      </span>
    </div>
  );
}

function MessageBubble({ role, content, error }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        data-testid={`chat-bubble-${role}`}
        className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-forest text-white rounded-br-md"
            : error
              ? "bg-rose-50 text-rose-700 border border-rose-200 rounded-bl-md"
              : "bg-slate-100 text-ink rounded-bl-md"
        }`}
      >
        {content}
      </div>
    </div>
  );
}

function ProfileRow({ field, entry, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(
    Array.isArray(entry?.value) ? entry.value.join(", ") : (entry?.value ?? "")
  );
  useEffect(() => {
    setDraft(
      Array.isArray(entry?.value) ? entry.value.join(", ") : (entry?.value ?? "")
    );
  }, [entry]);

  const hasValue = entry?.value !== undefined && entry?.value !== null && entry?.value !== "";
  const conf = entry?.confidence || "low";

  const commit = () => {
    let v = draft.trim();
    // Preserve array shape for list-like fields
    const arrayFields = ["major_loads", "shiftable", "fixed", "constraints"];
    let parsed;
    if (arrayFields.includes(field.id)) {
      parsed = v ? v.split(",").map((x) => x.trim()).filter(Boolean) : null;
    } else if (field.id === "sites") {
      const n = parseInt(v, 10);
      parsed = isFinite(n) ? n : null;
    } else {
      parsed = v || null;
    }
    onEdit(field.id, parsed);
    setEditing(false);
  };

  return (
    <div data-testid={`profile-row-${field.id}`} className="grid grid-cols-[110px_1fr_auto] items-start gap-2 py-2 border-b border-line last:border-b-0">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-ink-mute pt-0.5">
        {field.label}
      </div>
      {editing ? (
        <div className="flex items-center gap-1.5">
          <input
            data-testid={`profile-input-${field.id}`}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              else if (e.key === "Escape") setEditing(false);
            }}
            className="flex-1 min-w-0 rounded-md border border-accent bg-white px-2 py-1 text-[12px] outline-none focus:ring-2 focus:ring-accent/30"
            autoFocus
          />
          <button onClick={commit} className="text-emerald-600 hover:text-emerald-800" type="button" aria-label="save">
            <Check size={14} strokeWidth={2.5} />
          </button>
          <button onClick={() => setEditing(false)} className="text-ink-mute hover:text-rose-600" type="button" aria-label="cancel">
            <X size={14} strokeWidth={2.5} />
          </button>
        </div>
      ) : (
        <div className={`text-[12.5px] leading-relaxed ${hasValue ? "text-ink" : "text-ink-mute italic"}`}>
          {hasValue ? formatValue(entry.value) : "Not provided"}
        </div>
      )}
      <div className="flex items-center gap-1.5 pt-0.5">
        <span
          className={`inline-block h-2 w-2 rounded-full ${CONF_DOT[conf]}`}
          title={`Confidence: ${conf}`}
        />
        {!editing && (
          <button
            data-testid={`profile-edit-${field.id}`}
            type="button"
            onClick={() => setEditing(true)}
            className="text-ink-mute hover:text-accent"
            aria-label="edit"
          >
            <Pencil size={11} strokeWidth={2.5} />
          </button>
        )}
      </div>
    </div>
  );
}

function ChatPane({ messages, sending, onSend }) {
  const [input, setInput] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const submit = () => {
    const v = input.trim();
    if (!v || sending) return;
    setInput("");
    onSend(v);
  };

  return (
    <div className="flex flex-col rounded-xl border border-line bg-white h-[640px]">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-5 space-y-3">
        {messages.map((m, i) => (
          <MessageBubble key={i} role={m.role} content={m.content} error={m.error} />
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-slate-100 px-3.5 py-2.5 text-[13px] text-ink-mute">
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-ink-mute animate-pulse" />
                <span className="h-1.5 w-1.5 rounded-full bg-ink-mute animate-pulse [animation-delay:120ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-ink-mute animate-pulse [animation-delay:240ms]" />
              </span>
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-line px-4 py-3 space-y-2">
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              data-testid={`suggestion-${s.slice(0, 12)}`}
              onClick={() => setInput(s)}
              disabled={sending}
              className="rounded-full border border-line bg-surface px-2.5 py-1 text-[11px] text-ink-soft hover:border-ink-soft hover:text-ink transition disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            data-testid="chat-input"
            type="text"
            placeholder="Tell Claude about your business…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            disabled={sending}
            className="flex-1 rounded-lg border border-line bg-white px-3 py-2 text-[13px] outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:opacity-50"
          />
          <button
            data-testid="chat-send-btn"
            type="button"
            onClick={submit}
            disabled={!input.trim() || sending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send size={13} strokeWidth={2.5} />
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function ProfilePane({ profile, ready, onFieldEdit, onOptimise, optimising }) {
  return (
    <div className="flex flex-col rounded-xl border border-line bg-white h-[640px]">
      <div className="px-5 pt-4 pb-2">
        <div className="eyebrow">Extracted</div>
        <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
          Business profile
        </h3>
        <p className="mt-1 text-[11.5px] text-ink-mute">
          Updates as Claude listens. Click any value's ✎ to override.
        </p>
      </div>
      <div data-testid="profile-list" className="flex-1 overflow-y-auto px-5 pb-2">
        {PROFILE_FIELDS.map((f) => (
          <ProfileRow
            key={f.id}
            field={f}
            entry={profile[f.id]}
            onEdit={onFieldEdit}
          />
        ))}
      </div>
      <div className="border-t border-line px-5 py-4 space-y-2">
        <button
          data-testid="optimise-btn"
          type="button"
          onClick={onOptimise}
          disabled={!ready || optimising}
          className={`w-full inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-bold transition ${
            ready
              ? "bg-lime text-forest hover:brightness-95"
              : "bg-slate-100 text-ink-mute cursor-not-allowed"
          }`}
        >
          {optimising ? "Optimising…" : (
            <>
              Run Optimisation
              <ArrowRight size={14} strokeWidth={3} />
            </>
          )}
        </button>
        <div className="text-[10.5px] text-ink-mute leading-relaxed">
          {ready
            ? "Uses Claude to balance your constraints against ~70 retailer plans."
            : `Fill ${REQUIRED.filter((r) => !profile[r]?.value).map((r) => PROFILE_FIELDS.find((f) => f.id === r)?.label.toLowerCase()).join(", ")} to enable.`}
        </div>
      </div>
    </div>
  );
}

function OptimisationResult({ result, meter }) {
  if (!result) return null;
  return (
    <section
      data-testid="optimisation-result"
      className="rounded-xl border border-lime ring-2 ring-lime/30 bg-lime-soft/30 px-6 py-4"
    >
      <div className="text-[10.5px] uppercase tracking-wider font-semibold text-forest">
        Optimisation result
      </div>
      <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-mute">Recommended plan</div>
          <div className="mt-1 tabnum text-[18px] font-bold text-ink">
            {result.best.plan.retailer}
          </div>
          <div className="text-[12px] text-ink-soft">{result.best.plan.name}</div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-mute">Annual cost</div>
          <div className="mt-1 tabnum text-[18px] font-bold text-ink">
            {fmtCurrency(result.best.shifted_cost)}
          </div>
          <div className="text-[12px] text-emerald-700">
            saves {fmtCurrency(result.achievable_saving)} vs current
          </div>
        </div>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-mute">Peak demand</div>
          <div className="mt-1 tabnum text-[18px] font-bold text-ink">
            {fmtNumber(result.stats.active.peak_kw, 1)} kW
          </div>
          <div className="text-[12px] text-ink-soft">
            {fmtNumber(result.stats.active.annual_kwh / 1000, 1)} MWh/yr · LF {fmtNumber(result.stats.active.load_factor, 2)}
          </div>
        </div>
      </div>
    </section>
  );
}

export default function ScenarioBuilder({ onNavigate = () => {} }) {
  const [meters, setMeters] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [messages, setMessages] = useState([
    { role: "assistant", content: INITIAL_CLAUDE_MSG },
  ]);
  const [profile, setProfile] = useState({});
  const [sending, setSending] = useState(false);
  const [ready, setReady] = useState(false);
  const [optimisationResult, setOptimisationResult] = useState(null);
  const [optimising, setOptimising] = useState(false);

  useEffect(() => {
    (async () => {
      const mRes = await api.get("/meters");
      setMeters(mRes.data);
      if (mRes.data.length) setSelectedIds([mRes.data[0].id]);
    })();
  }, []);

  const meter = useMemo(
    () => meters.find((m) => m.id === selectedIds[0]),
    [meters, selectedIds]
  );

  // Reset chat when site changes
  const meterId = meter?.id;
  useEffect(() => {
    if (!meterId) return;
    setMessages([{ role: "assistant", content: INITIAL_CLAUDE_MSG }]);
    setProfile({});
    setOptimisationResult(null);
    setReady(false);
  }, [meterId]);

  const onSend = async (text) => {
    if (!meter) return;
    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setSending(true);
    try {
      const { data } = await api.post("/chat", {
        meter_id: meter.id,
        messages: next.slice(0, -1),
        profile,
        user_message: text,
      });
      setMessages([...next, { role: "assistant", content: data.assistant_message }]);
      setProfile(data.profile || {});
      setReady(!!data.ready_for_optimisation);
    } catch (e) {
      console.error("chat err", e);
      setMessages([
        ...next,
        { role: "assistant", content: "Sorry — I couldn't reach Claude just now. Try again?", error: true },
      ]);
    } finally {
      setSending(false);
    }
  };

  const onFieldEdit = (id, value) => {
    setProfile((prev) => {
      const updated = { ...prev };
      if (value === null || value === "" || (Array.isArray(value) && value.length === 0)) {
        delete updated[id];
      } else {
        updated[id] = { value, confidence: "high" };
      }
      const isReady = REQUIRED.every((r) => updated[r]?.value);
      setReady(isReady);
      return updated;
    });
  };

  const onOptimise = async () => {
    if (!meter) return;
    setOptimising(true);
    try {
      // For v0: optimisation = run the rank engine on the current site at default appliance scales.
      const { data } = await api.post("/rank", {
        meter_ids: [meter.id],
        appliance_scales: {},
      });
      setOptimisationResult(data);
    } catch (e) {
      console.error("optimise err", e);
    } finally {
      setOptimising(false);
    }
  };

  const selectMeter = (id) => setSelectedIds([id]);
  const selectAll = () => {};  // single-site only on this page

  return (
    <div className="flex min-h-screen">
      <MeterRail
        meters={meters}
        selectedIds={selectedIds}
        onSelect={selectMeter}
        onSelectAll={selectAll}
        page="scenarios"
        onNavigate={onNavigate}
      />

      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between bg-forest px-7 py-4 text-white">
          <div className="text-[20px] font-bold tracking-tightish leading-tight">
            Scenario Builder
          </div>
          <div className="text-[11px] text-white/50">
            Claude Haiku 4.5 · live profile extraction
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-surface">
          <div className="mx-auto max-w-[1400px] px-7 py-6 space-y-5">
            <SiteHeader meter={meter} currentPlan={null} />

            <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-5">
              <ChatPane messages={messages} sending={sending} onSend={onSend} />
              <ProfilePane
                profile={profile}
                ready={ready}
                onFieldEdit={onFieldEdit}
                onOptimise={onOptimise}
                optimising={optimising}
              />
            </div>

            <OptimisationResult result={optimisationResult} meter={meter} />

            <footer className="pt-2 pb-8 text-[11px] text-ink-mute">
              All conversation is sent to Anthropic's Claude Haiku 4.5 model and stays scoped to this site.
            </footer>
          </div>
        </div>
      </main>
    </div>
  );
}
