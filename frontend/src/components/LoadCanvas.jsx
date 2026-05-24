import React, { useEffect, useMemo, useRef, useState } from "react";
import { bucketToTime, fmtNumber } from "../lib/api";

const PAD = { l: 56, r: 16, t: 16, b: 38 };

function useElementWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(960);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect;
      setW(cr.width);
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// Build an SVG path for the stacked band (lower → upper → close)
function bandPath(lower, upper, x0, y0, w, h, maxY) {
  if (!lower.length) return "";
  const dx = w / (lower.length - 1);
  const yOf = (v) => y0 + h - (v / maxY) * h;
  let d = `M ${x0} ${yOf(lower[0])}`;
  upper.forEach((v, i) => {
    d += ` L ${(x0 + i * dx).toFixed(2)} ${yOf(v).toFixed(2)}`;
  });
  for (let i = lower.length - 1; i >= 0; i--) {
    d += ` L ${(x0 + i * dx).toFixed(2)} ${yOf(lower[i]).toFixed(2)}`;
  }
  d += " Z";
  return d;
}

function buildStackedSeries(appliances) {
  // Returns [{id, name, color, lower:[48], upper:[48]}] in stack order
  const lower = new Array(48).fill(0);
  const out = [];
  appliances.forEach((a) => {
    const upper = a.profile.map((v, i) => lower[i] + Math.max(0, v));
    out.push({ id: a.id, name: a.name, color: a.color, lower: lower.slice(), upper: upper.slice(), profile: a.profile });
    for (let i = 0; i < 48; i++) lower[i] = upper[i];
  });
  return { series: out, total: lower };
}

export default function LoadCanvas({ appliances, zone }) {
  // appliances: list of active appliances (already filtered) with profile, color, name
  const [containerRef, containerW] = useElementWidth();
  const H = 360;
  const chartW = Math.max(0, containerW - PAD.l - PAD.r);
  const chartH = H - PAD.t - PAD.b;
  const bucketPx = chartW / 47; // 48 points → 47 segments
  const [hoverBucket, setHoverBucket] = useState(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  const { series, total } = useMemo(
    () => buildStackedSeries(appliances || []),
    [appliances]
  );

  const maxY = useMemo(() => {
    const peak = Math.max(...total, 1);
    // round up to a nice number
    const niceSteps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500];
    const target = peak * 1.15;
    const mag = Math.pow(10, Math.floor(Math.log10(target)));
    const norm = target / mag;
    const step = niceSteps.find((s) => s >= norm) || 10;
    return step * mag;
  }, [total]);

  const yTicks = useMemo(() => {
    const n = 4;
    return Array.from({ length: n + 1 }, (_, i) => (maxY / n) * i);
  }, [maxY]);

  const xTicks = [0, 6, 12, 18, 24];

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - PAD.l;
    if (x < 0 || x > chartW) {
      setHoverBucket(null);
      return;
    }
    const b = Math.max(0, Math.min(47, Math.round(x / bucketPx)));
    setHoverBucket(b);
    setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };
  const onLeave = () => setHoverBucket(null);

  const totalAtHover = hoverBucket !== null ? total[hoverBucket] : null;

  return (
    <div className="relative" ref={containerRef}>
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${Math.max(containerW, 1)} ${H}`}
        preserveAspectRatio="none"
        data-testid="load-canvas-svg"
        onMouseMove={onMove}
        onMouseLeave={onLeave}
        className="block"
      >
        {/* TOU bands as ultra-faint background washes */}
        {zone && (
          <g opacity="0.55">
            {zone.peak_buckets.map(([a, b], i) => (
              <rect
                key={`peak-${i}`}
                x={PAD.l + (a / 47) * chartW}
                y={PAD.t}
                width={((b - a) / 47) * chartW}
                height={chartH}
                fill="#fee2e2"
              />
            ))}
            {zone.shoulder_buckets.map(([a, b], i) => (
              <rect
                key={`sh-${i}`}
                x={PAD.l + (a / 47) * chartW}
                y={PAD.t}
                width={((b - a) / 47) * chartW}
                height={chartH}
                fill="#fef3c7"
              />
            ))}
          </g>
        )}

        {/* Gridlines */}
        {yTicks.map((t, i) => {
          const y = PAD.t + chartH - (t / maxY) * chartH;
          return (
            <g key={`y-${i}`}>
              <line
                x1={PAD.l}
                x2={PAD.l + chartW}
                y1={y}
                y2={y}
                stroke="#e2e8f0"
                strokeWidth="0.8"
                strokeDasharray={i === 0 ? "0" : "2 3"}
              />
              <text
                x={PAD.l - 10}
                y={y + 3.5}
                textAnchor="end"
                fontSize="11"
                fill="#94a3b8"
                fontFamily="JetBrains Mono, monospace"
              >
                {fmtNumber(t, 0)}
              </text>
            </g>
          );
        })}
        {/* X ticks */}
        {xTicks.map((h) => {
          const x = PAD.l + (h / 24) * chartW;
          return (
            <g key={`x-${h}`}>
              <line
                x1={x}
                x2={x}
                y1={PAD.t}
                y2={PAD.t + chartH}
                stroke="#e2e8f0"
                strokeWidth="0.6"
                strokeDasharray="1 4"
              />
              <text
                x={x}
                y={PAD.t + chartH + 18}
                textAnchor="middle"
                fontSize="11"
                fill="#94a3b8"
                fontFamily="JetBrains Mono, monospace"
              >
                {String(h).padStart(2, "0")}:00
              </text>
            </g>
          );
        })}

        {/* Stacked bands */}
        {series.map((s) => (
          <path
            key={s.id}
            d={bandPath(s.lower, s.upper, PAD.l, PAD.t, chartW, chartH, maxY)}
            fill={s.color}
            fillOpacity="0.82"
            stroke={s.color}
            strokeOpacity="0.95"
            strokeWidth="0.8"
          />
        ))}

        {/* Hover guide */}
        {hoverBucket !== null && (
          <g pointerEvents="none">
            <line
              x1={PAD.l + (hoverBucket / 47) * chartW}
              x2={PAD.l + (hoverBucket / 47) * chartW}
              y1={PAD.t}
              y2={PAD.t + chartH}
              stroke="#0f172a"
              strokeOpacity="0.35"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
          </g>
        )}

        {/* Axis labels */}
        <text
          x={PAD.l - 8}
          y={PAD.t - 6}
          fontSize="10"
          fill="#64748b"
          fontFamily="IBM Plex Sans, sans-serif"
          fontWeight="600"
          textAnchor="end"
        >
          kW
        </text>
        <text
          x={PAD.l + chartW}
          y={H - 6}
          textAnchor="end"
          fontSize="10"
          fill="#94a3b8"
          fontFamily="IBM Plex Sans, sans-serif"
        >
          Hour of day (typical weekday)
        </text>
      </svg>

      {/* Hover tooltip */}
      {hoverBucket !== null && totalAtHover !== null && (
        <div
          data-testid="hover-tooltip"
          className="pointer-events-none absolute z-20 rounded-lg border border-line bg-white shadow-lg px-3 py-2.5 text-[11.5px] tabnum"
          style={{
            left: Math.min(hoverPos.x + 14, containerW - 220),
            top: Math.max(hoverPos.y - 10, 10),
            width: 210,
          }}
        >
          <div className="flex items-baseline justify-between mb-1.5 border-b border-line pb-1.5">
            <span className="text-ink-mute text-[10.5px] uppercase tracking-wider">
              {bucketToTime(hoverBucket)}
            </span>
            <span className="font-semibold text-ink">
              {fmtNumber(totalAtHover, 1)} kW
            </span>
          </div>
          <div className="space-y-0.5">
            {series.slice().reverse().map((s) => {
              const v = s.profile[hoverBucket];
              if (v < 0.05) return null;
              return (
                <div key={s.id} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span
                      className="inline-block h-2 w-2 rounded-sm shrink-0"
                      style={{ background: s.color }}
                    />
                    <span className="text-ink-soft truncate">{s.name}</span>
                  </div>
                  <span className="text-ink font-medium">{fmtNumber(v, 1)} kW</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
