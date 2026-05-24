import React from "react";

const RANGES = [
  { id: "24h", label: "24 hours" },
  { id: "month", label: "Last month" },
  { id: "year", label: "Last year" },
];

export default function TimeframeSelector({ value, onChange }) {
  return (
    <div
      data-testid="timeframe-selector"
      className="inline-flex rounded-md border border-line bg-white p-0.5 text-[11.5px] font-medium"
    >
      {RANGES.map((r) => (
        <button
          key={r.id}
          data-testid={`timeframe-${r.id}`}
          type="button"
          onClick={() => onChange(r.id)}
          className={`rounded-[5px] px-3 py-1 transition ${
            value === r.id
              ? "bg-forest text-white"
              : "text-ink-soft hover:text-ink"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
