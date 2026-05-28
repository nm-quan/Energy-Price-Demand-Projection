import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Send, Loader, Sparkles } from 'lucide-react';
import { getClient } from '../lib/api';
import BlockRenderer from '../components/BlockRenderer';

const HINTS = [
  'Just make it cheaper',
  'Full site reduction plan',
  'Top 3 appliance saves',
  'Peak hour reduction package',
  'Cut the fridge',
  'Shift dishwasher',
  'Which retailer is best?',
  'Show load profile',
];

function summariseTurn(turn) {
  const headline = turn.blocks.find(b => b.type === 'headline');
  const scenarios = turn.blocks.filter(b => b.type === 'scenario');
  let text = headline?.text || 'Analysis completed.';
  if (scenarios.length > 0) {
    const names = scenarios.map(s => s.name || s.appliance).join('; ');
    const maxSaving = Math.max(...scenarios.map(s => s.savings_annual_low || 0));
    text += ` Scenarios covered: ${names}. Max saving: $${Math.round(maxSaving)}/yr.`;
  }
  return text;
}

export default function AIAnalysis() {
  const { id } = useParams();
  const [client, setClient] = useState(null);
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    getClient(id).then(r => {
      setClient(r.data);
      if (r.data?.name) sessionStorage.setItem(`client_name_${id}`, r.data.name);
    }).catch(() => {});
    return () => abortRef.current?.abort();
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [turns]);

  const send = useCallback(async (promptOverride) => {
    const text = (promptOverride ?? input).trim();
    if (!text || streaming) return;
    setInput('');
    setError('');
    setStreaming(true);

    const turnId = `turn-${Date.now()}`;
    setTurns(prev => [...prev, { id: turnId, prompt: text, blocks: [], done: false }]);

    const history = turns
      .filter(t => t.done)
      .flatMap(t => [
        { role: 'user', content: t.prompt },
        { role: 'assistant', content: summariseTurn(t) },
      ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`/api/clients/${id}/analyse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text, history }),
        signal: controller.signal,
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
          if (raw === '[DONE]') {
            setTurns(prev =>
              prev.map(t => t.id === turnId ? { ...t, done: true } : t)
            );
            setStreaming(false);
            inputRef.current?.focus();
            return;
          }
          try {
            const block = JSON.parse(raw);
            setTurns(prev =>
              prev.map(t =>
                t.id === turnId ? { ...t, blocks: [...t.blocks, block] } : t
              )
            );
          } catch {
            /* ignore partial chunks */
          }
        }
      }
      // Stream ended without [DONE]
      setTurns(prev => prev.map(t => t.id === turnId ? { ...t, done: true } : t));
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message || 'Analysis failed. Please try again.');
      setTurns(prev => prev.map(t => t.id === turnId ? { ...t, done: true } : t));
    } finally {
      setStreaming(false);
    }
  }, [id, input, streaming, turns]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col" style={{ height: '100vh' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 border-b border-line bg-cream-50/95 backdrop-blur px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-lime/40 flex items-center justify-center flex-shrink-0">
            <Sparkles size={16} className="text-forest-800" />
          </div>
          <div>
            <h1 className="font-display text-xl text-forest-900 leading-none">Chat</h1>
            {client && (
              <p className="text-xs text-ink-mute mt-0.5">
                {client.name} · {client.site_type}
              </p>
            )}
          </div>
        </div>
      </header>

      {/* ── Feed ───────────────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6 py-8 space-y-12">

          {/* Empty state */}
          {turns.length === 0 && (
            <div className="text-center pt-12">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-lime/30 rounded-2xl mb-5">
                <Sparkles size={28} className="text-forest-800" />
              </div>
              <h2 className="font-display text-3xl text-forest-900 mb-2">
                What would you like to know?
              </h2>
              <p className="text-sm text-ink-mute max-w-sm mx-auto">
                Ask anything about this site — energy costs, usage patterns,
                load-shifting strategies, or retailer comparisons.
              </p>
            </div>
          )}

          {/* Conversation turns */}
          {turns.map(turn => (
            <div key={turn.id} className="space-y-5">

              {/* User message */}
              <div className="flex justify-end">
                <div className="bg-forest-800 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm max-w-md shadow-sm">
                  {turn.prompt}
                </div>
              </div>

              {/* AI blocks */}
              <div className="space-y-4">
                {turn.blocks.map((block, i) => (
                  <div
                    key={i}
                    style={{
                      animation: 'blockFadeIn 0.25s ease-out both',
                      animationDelay: `${i * 40}ms`,
                    }}
                  >
                    <BlockRenderer block={block} />
                  </div>
                ))}

                {/* Thinking indicators */}
                {!turn.done && turn.blocks.length === 0 && (
                  <div className="flex items-center gap-2.5 text-sm text-ink-mute py-2">
                    <Loader size={14} className="animate-spin text-violet flex-shrink-0" />
                    <span>Analysing site data…</span>
                  </div>
                )}
                {!turn.done && turn.blocks.length > 0 && (
                  <div className="flex items-center gap-2 text-xs text-ink-mute pl-1">
                    <Loader size={12} className="animate-spin text-violet" />
                    <span>Building next block…</span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Global error */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div ref={bottomRef} className="h-1" />
        </div>
      </div>

      {/* ── Input ──────────────────────────────────────────────────────────── */}
      <div className="flex-shrink-0 border-t border-line bg-cream-50/95 backdrop-blur px-6 py-4 space-y-3">

        {/* Hint chips */}
        <div className="flex flex-wrap gap-2">
          {HINTS.map(hint => (
            <button
              key={hint}
              type="button"
              disabled={streaming}
              onClick={() => send(hint)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border transition-all
                         bg-forest-800/5 border-forest-700/20 text-forest-800
                         hover:bg-forest-800/10 hover:border-forest-700/40
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Sparkles size={10} />
              {hint}
            </button>
          ))}
        </div>

        {/* Text input row */}
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask anything about this site…"
            disabled={streaming}
            className="flex-1 bg-white border border-line rounded-xl px-4 py-2.5 text-sm
                       text-forest-900 placeholder:text-ink-mute
                       focus:outline-none focus:ring-2 focus:ring-violet/30 focus:border-violet/50
                       disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <button
            type="button"
            onClick={() => send()}
            disabled={!input.trim() || streaming}
            className="bg-forest-800 text-white rounded-xl px-5 py-2.5 inline-flex items-center
                       gap-2 text-sm font-medium hover:bg-forest-700 active:scale-95
                       transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {streaming
              ? <Loader size={15} className="animate-spin" />
              : <Send size={15} />}
            <span className="hidden sm:inline">
              {streaming ? 'Thinking…' : 'Send'}
            </span>
          </button>
        </div>
      </div>

      {/* Block fade-in animation */}
      <style>{`
        @keyframes blockFadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
