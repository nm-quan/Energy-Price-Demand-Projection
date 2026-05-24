import React, { useEffect, useRef, useState } from "react";
import { Lock, Minus, Plus } from "lucide-react";
import { fmtNumber } from "../lib/api";

const SCALE_STEPS = [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0];
const MAX_SCALE = 5.0;  // 500% upper bound for custom input

function nearestStep(v) {
  let best = SCALE_STEPS[0];
  let bestD = Math.abs(v - best);
  SCALE_STEPS.forEach((s) => {
    const d = Math.abs(v - s);
    if (d < bestD) { best = s; bestD = d; }
  });
  return best;
}

function stepUp(v) {
  // Snap to nearest step then go to the next one (or +25% if above range)
  if (v >= SCALE_STEPS[SCALE_STEPS.length - 1]) return Math.min(MAX_SCALE, v + 0.25);
  const s = nearestStep(v);
  const i = SCALE_STEPS.indexOf(s);
  if (s < v) return SCALE_STEPS[Math.min(SCALE_STEPS.length - 1, i + 1)];
  return s;
}

function stepDown(v) {
  if (v <= SCALE_STEPS[0]) return 0;
  if (v > SCALE_STEPS[SCALE_STEPS.length - 1]) return SCALE_STEPS[SCALE_STEPS.length - 1];
  const s = nearestStep(v);
  const i = SCALE_STEPS.indexOf(s);
  if (s > v) return SCALE_STEPS[Math.max(0, i - 1)];
  return SCALE_STEPS[Math.max(0, i - 1)];
}

function ScaleControl({ appliance, scale, onChange }) {
  const locked = appliance.always_on;
  const minScale = locked ? 1.0 : 0;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(Math.round(scale * 100)));
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  useEffect(() => {
    if (!editing) setDraft(String(Math.round(scale * 100)));
  }, [scale, editing]);

  const commit = () => {
    const n = parseFloat(draft);
    if (!isFinite(n)) {
      setEditing(false);
      setDraft(String(Math.round(scale * 100)));
      return;
    }
    let next = n / 100;
    next = Math.max(minScale, Math.min(MAX_SCALE, next));
    onChange(appliance.id, next);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(String(Math.round(scale * 100)));
    setEditing(false);
  };

  const stepDownClamped = () => {
    onChange(appliance.id, Math.max(minScale, stepDown(scale)));
  };
  const stepUpClamped = () => {
    onChange(appliance.id, Math.min(MAX_SCALE, stepUp(scale)));
  };

  const pct = Math.round(scale * 100);
  const isOn = scale > 0;

  return (
    <div className="flex items-center gap-1 shrink-0">
      <button
        data-testid={`appliance-down-${appliance.id}`}
        type="button"
        onClick={stepDownClamped}
        disabled={scale <= minScale}
        className={`inline-flex h-7 w-7 items-center justify-center rounded-md border border-line text-ink-soft transition ${
          scale <= minScale ? "opacity-30 cursor-not-allowed" : "hover:border-ink-soft hover:text-ink"
        }`}
      >
        <Minus size={12} strokeWidth={2.5} />
      </button>
      {editing ? (
        <div className="flex items-center">
          <input
            ref={inputRef}
            data-testid={`appliance-input-${appliance.id}`}
            type="number"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              else if (e.key === "Escape") cancel();
            }}
            className="tabnum w-14 rounded-md border border-accent bg-white px-1.5 py-0.5 text-center text-[12px] font-semibold text-ink outline-none focus:ring-2 focus:ring-accent/30"
            min={Math.round(minScale * 100)}
            max={Math.round(MAX_SCALE * 100)}
            step="5"
          />
          <span className="ml-0.5 text-[11px] font-medium text-ink-mute">%</span>
        </div>
      ) : (
        <button
          type="button"
          data-testid={`appliance-value-${appliance.id}`}
          onDoubleClick={() => setEditing(true)}
          onClick={() => setEditing(true)}
          title="Double-click or click to enter a custom value"
          className={`tabnum w-14 rounded-md text-center text-[12px] font-semibold transition hover:bg-surface ${
            isOn ? "text-ink" : "text-ink-mute"
          }`}
        >
          {pct}%
        </button>
      )}
      <button
        data-testid={`appliance-up-${appliance.id}`}
        type="button"
        onClick={stepUpClamped}
        disabled={scale >= MAX_SCALE}
        className={`inline-flex h-7 w-7 items-center justify-center rounded-md border border-line text-ink-soft transition ${
          scale >= MAX_SCALE ? "opacity-30 cursor-not-allowed" : "hover:border-ink-soft hover:text-ink"
        }`}
      >
        <Plus size={12} strokeWidth={2.5} />
      </button>
    </div>
  );
}

function ApplianceRow({ appliance, scale, onChange }) {
  const locked = appliance.always_on;
  const isOn = scale > 0;

  return (
    <div
      data-testid={`appliance-row-${appliance.id}`}
      className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition ${
        isOn ? "border-line bg-white" : "border-line bg-surface"
      }`}
    >
      <span
        className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm transition-opacity"
        style={{ background: appliance.color, opacity: isOn ? 1 : 0.25 }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1">
          <div className="truncate text-[13px] font-semibold text-ink leading-tight">
            {appliance.name}
          </div>
          {locked && <Lock size={9} className="shrink-0 text-ink-mute" strokeWidth={2.5} />}
        </div>
        <div className="mt-0.5 text-[10.5px] tabnum text-ink-mute">
          {fmtNumber(appliance.daily_kwh, 1)} kWh/day
        </div>
      </div>
      <ScaleControl appliance={appliance} scale={scale} onChange={onChange} />
    </div>
  );
}

export default function AppliancePanel({ appliances, scales, onChange }) {
  if (!appliances?.length) return null;
  return (
    <div data-testid="appliance-panel" className="rounded-xl border border-line bg-white">
      <div className="px-5 pt-4 pb-2">
        <div className="eyebrow">Load decomposition</div>
        <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
          Appliance meters
        </h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 px-3 pb-3">
        {appliances.map((a) => (
          <ApplianceRow
            key={a.id}
            appliance={a}
            scale={scales[a.id] ?? 1.0}
            onChange={onChange}
          />
        ))}
      </div>
    </div>
  );
}
