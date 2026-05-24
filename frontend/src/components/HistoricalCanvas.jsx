import React, { useEffect, useMemo, useRef, useState } from "react";
import { fmtNumber } from "../lib/api";

const PAD = { l: 56, r: 16, t: 16, b: 38 };

function useElementWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(960);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => setW(entries[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function fmtTickLabel(iso, grain) {
  const d = new Date(iso);
  if (grain === "halfhour") {
    return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
  }
  if (grain === "daily") {
    return `${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
  }
  if (grain === "weekly") {
    return `${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
  }
  return iso.slice(0, 10);
}

function fmtTooltipDate(iso, grain) {
  const d = new Date(iso);
  const opts = grain === "halfhour"
    ? { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }
    : { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" };
  return d.toLocaleString("en-AU", opts);
}

export default function HistoricalCanvas({ data }) {
  const [containerRef, containerW] = useElementWidth();
  const H = 360;
  const chartW = Math.max(0, containerW - PAD.l - PAD.r);
  const chartH = H - PAD.t - PAD.b;
  const [hoverIdx, setHoverIdx] = useState(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  const points = data?.points || [];
  const grain = data?.grain || "halfhour";
  const n = points.length;

  const maxY = useMemo(() => {
    if (!n) return 10;
    const peak = Math.max(...points.map((p) => p.kw_peak || p.kw_avg || 0), 1);
    const niceSteps = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000];
    const target = peak * 1.15;
    const mag = Math.pow(10, Math.floor(Math.log10(target)));
    const norm = target / mag;
    const step = niceSteps.find((s) => s >= norm) || 10;
    return step * mag;
  }, [points, n]);

  const yTicks = useMemo(() => {
    const tickN = 4;
    return Array.from({ length: tickN + 1 }, (_, i) => (maxY / tickN) * i);
  }, [maxY]);

  const xTickIndices = useMemo(() => {
    if (n <= 6) return points.map((_, i) => i);
    const stride = Math.max(1, Math.floor(n / 6));
    const out = [];
    for (let i = 0; i < n; i += stride) out.push(i);
    if (out[out.length - 1] !== n - 1) out.push(n - 1);
    return out;
  }, [points, n]);

  const xOf = (i) => PAD.l + (i / Math.max(n - 1, 1)) * chartW;
  const yOf = (v) => PAD.t + chartH - (v / maxY) * chartH;

  const avgPath = useMemo(() => {
    if (!n) return "";
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${xOf(i).toFixed(2)} ${yOf(p.kw_avg).toFixed(2)}`).join(" ");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, n, maxY, chartW, chartH]);

  const peakPath = useMemo(() => {
    if (!n) return "";
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${xOf(i).toFixed(2)} ${yOf(p.kw_peak).toFixed(2)}`).join(" ");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, n, maxY, chartW, chartH]);

  const onMove = (e) => {
    if (!n) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - PAD.l;
    if (x < 0 || x > chartW) { setHoverIdx(null); return; }
    const idx = Math.max(0, Math.min(n - 1, Math.round((x / chartW) * (n - 1))));
    setHoverIdx(idx);
    setHoverPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const hp = hoverIdx !== null ? points[hoverIdx] : null;

  return (
    <div className="relative" ref={containerRef}>
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${Math.max(containerW, 1)} ${H}`}
        preserveAspectRatio="none"
        data-testid="historical-canvas-svg"
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIdx(null)}
        className="block"
      >
        {/* Gridlines */}
        {yTicks.map((t, i) => {
          const y = yOf(t);
          return (
            <g key={i}>
              <line x1={PAD.l} x2={PAD.l + chartW} y1={y} y2={y}
                stroke="#e2e8f0" strokeWidth="0.8"
                strokeDasharray={i === 0 ? "0" : "2 3"} />
              <text x={PAD.l - 10} y={y + 3.5} textAnchor="end"
                fontSize="11" fill="#94a3b8" fontFamily="JetBrains Mono, monospace">
                {fmtNumber(t, 0)}
              </text>
            </g>
          );
        })}

        {/* X ticks */}
        {xTickIndices.map((i) => (
          <g key={i}>
            <line x1={xOf(i)} x2={xOf(i)} y1={PAD.t} y2={PAD.t + chartH}
              stroke="#e2e8f0" strokeWidth="0.6" strokeDasharray="1 4" />
            <text x={xOf(i)} y={PAD.t + chartH + 18} textAnchor="middle"
              fontSize="10.5" fill="#94a3b8" fontFamily="JetBrains Mono, monospace">
              {fmtTickLabel(points[i].ts, grain)}
            </text>
          </g>
        ))}

        {/* Peak (lighter line) */}
        <path d={peakPath} fill="none" stroke="#5EEAD4" strokeWidth="1.4"
          strokeOpacity="0.5" strokeLinejoin="round" strokeLinecap="round" />
        {/* Average (main line) */}
        <path d={avgPath} fill="none" stroke="#4F46E5" strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" />

        {/* Hover marker */}
        {hp !== null && (
          <g pointerEvents="none">
            <line x1={xOf(hoverIdx)} x2={xOf(hoverIdx)} y1={PAD.t} y2={PAD.t + chartH}
              stroke="#0f172a" strokeOpacity="0.35" strokeWidth="1" strokeDasharray="2 2" />
            <circle cx={xOf(hoverIdx)} cy={yOf(hp.kw_avg)} r="3.5"
              fill="#4F46E5" stroke="#fff" strokeWidth="1.5" />
          </g>
        )}

        {/* Axis labels */}
        <text x={PAD.l - 8} y={PAD.t - 6} fontSize="10" fill="#64748b"
          fontFamily="IBM Plex Sans, sans-serif" fontWeight="600" textAnchor="end">kW</text>
      </svg>

      {/* Legend */}
      <div className="absolute right-3 top-2 flex items-center gap-3 text-[10.5px] text-ink-mute">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-4 h-[2px]" style={{ background: "#4F46E5" }} />
          Avg kW
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block w-4 h-[2px]" style={{ background: "#5EEAD4", opacity: 0.7 }} />
          Peak kW
        </span>
      </div>

      {/* Tooltip */}
      {hp !== null && (
        <div
          data-testid="historical-tooltip"
          className="pointer-events-none absolute z-20 rounded-lg border border-line bg-white shadow-lg px-3 py-2.5 text-[11.5px] tabnum"
          style={{
            left: Math.min(hoverPos.x + 14, containerW - 210),
            top: Math.max(hoverPos.y - 10, 10),
            width: 200,
          }}
        >
          <div className="text-ink-mute text-[10.5px] uppercase tracking-wider border-b border-line pb-1.5 mb-1.5">
            {fmtTooltipDate(hp.ts, grain)}
          </div>
          <div className="flex justify-between"><span className="text-ink-soft">Avg</span><span className="font-semibold text-ink">{fmtNumber(hp.kw_avg, 2)} kW</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Peak</span><span className="font-semibold text-ink">{fmtNumber(hp.kw_peak, 2)} kW</span></div>
          <div className="flex justify-between"><span className="text-ink-soft">Energy</span><span className="font-semibold text-ink">{fmtNumber(hp.kwh, 1)} kWh</span></div>
        </div>
      )}
    </div>
  );
}
