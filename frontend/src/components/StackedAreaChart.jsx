import React, { useState, useMemo } from 'react';
import { fmtNumber } from '../lib/api';

// Fixed appliance order (bottom→top of stack) with colors per Change 2 spec
export const APPLIANCE_LAYERS = [
  { key: 'Fridges', color: '#64748b' },
  { key: 'Espresso', color: '#f97316' },
  { key: 'Ovens', color: '#ef4444' },
  { key: 'HVAC', color: '#0ea5e9' },
  { key: 'Lighting', color: '#eab308' },
  { key: 'Dishwasher', color: '#22c55e' },
  { key: 'Hot Water', color: '#a855f7' },
  { key: 'Misc', color: '#ec4899' },
];

const X_LABELS = [
  { bucket: 0, label: '12am' },
  { bucket: 8, label: '4am' },
  { bucket: 16, label: '8am' },
  { bucket: 24, label: '12pm' },
  { bucket: 32, label: '4pm' },
  { bucket: 40, label: '8pm' },
  { bucket: 47, label: '12am' },
];

// TOU band overlays — per Change 2 spec
const TOU_BANDS = [
  { start: 30, end: 42, color: 'rgba(239,68,68,0.08)', label: 'Peak' },
  { start: 14, end: 30, color: 'rgba(245,158,11,0.08)', label: 'Shoulder' },
  { start: 42, end: 44, color: 'rgba(245,158,11,0.08)', label: 'Shoulder' },
];

/**
 * StackedAreaChart
 * Renders an 8-appliance stacked area chart on top of TOU band overlays.
 *
 * Props:
 *  - applianceCurves: { [name]: number[48] }
 *  - scales: { [name]: number }   (0..2)
 *  - height: number
 *  - baseline?: number[48]        (optional fade outline for compare mode)
 *  - overlay?: number[48]         (optimised curve, drawn on top as a line)
 */
export default function StackedAreaChart({
  applianceCurves,
  scales,
  height = 240,
  baseline = null,
  overlay = null,
  showTooltip = true,
}) {
  const [hoverBucket, setHoverBucket] = useState(null);

  const svgW = 760;
  const svgH = height;
  const padL = 48, padR = 16, padT = 12, padB = 28;
  const cW = svgW - padL - padR;
  const cH = svgH - padT - padB;

  const layers = useMemo(() => {
    return APPLIANCE_LAYERS.map(({ key, color }) => {
      const curve = applianceCurves?.[key] || [];
      const scale = scales?.[key] ?? 1.0;
      const scaled = curve.map((v) => (v || 0) * scale);
      return { key, color, scaled };
    });
  }, [applianceCurves, scales]);

  // Cumulative stack values for each bucket
  const stackedTotals = useMemo(() => {
    const totals = [];
    for (let b = 0; b < 48; b++) {
      let sum = 0;
      for (const l of layers) sum += l.scaled[b] || 0;
      totals.push(sum);
    }
    return totals;
  }, [layers]);

  const maxVal = useMemo(() => {
    const overlayMax = overlay ? Math.max(...overlay) : 0;
    const baselineMax = baseline ? Math.max(...baseline) : 0;
    const stackMax = Math.max(...stackedTotals);
    return Math.max(stackMax, overlayMax, baselineMax) * 1.10 || 1;
  }, [stackedTotals, overlay, baseline]);

  const xPos = (b) => padL + (b / 47) * cW;
  const yPos = (v) => padT + cH - (v / maxVal) * cH;

  // Build polygon for each layer (stacked from bottom to top)
  const polygons = useMemo(() => {
    const polys = [];
    const baseStack = new Array(48).fill(0);
    for (const layer of layers) {
      const topStack = baseStack.map((v, i) => v + (layer.scaled[i] || 0));
      // Polygon: across the top, then back across the bottom
      const topPath = topStack
        .map((v, i) => `${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`)
        .join(' ');
      const bottomPath = [...baseStack]
        .map((v, i) => `${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`)
        .reverse()
        .join(' ');
      polys.push({ key: layer.key, color: layer.color, points: `${topPath} ${bottomPath}` });
      for (let i = 0; i < 48; i++) baseStack[i] = topStack[i];
    }
    return polys;
  }, [layers]);

  const buildLinePath = (arr) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`).join(' ');

  const yTicks = 4;
  const yTickStep = maxVal / yTicks;

  // Hover handling
  const handleMove = (e) => {
    if (!showTooltip) return;
    const svgRect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - svgRect.left) / svgRect.width) * svgW;
    const ratio = (x - padL) / cW;
    const b = Math.max(0, Math.min(47, Math.round(ratio * 47)));
    setHoverBucket(b);
  };

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: 'auto' }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverBucket(null)}
        data-testid="stacked-area-chart"
      >
        {/* TOU band overlays (drawn FIRST, behind everything) */}
        {TOU_BANDS.map((band, idx) => (
          <rect
            key={idx}
            x={xPos(band.start)}
            y={padT}
            width={xPos(Math.min(band.end, 47)) - xPos(band.start)}
            height={cH}
            fill={band.color}
          />
        ))}

        {/* Y-axis grid lines */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const val = yTickStep * i;
          const y = yPos(val);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={padL + cW} y2={y} stroke="#e2e8f0" strokeWidth={1} />
              <text x={padL - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#94a3b8">
                {fmtNumber(val, 1)}
              </text>
            </g>
          );
        })}

        {/* Stacked area polygons */}
        {polygons.map((p) => (
          <polygon
            key={p.key}
            points={p.points}
            fill={p.color}
            fillOpacity={0.78}
            stroke={p.color}
            strokeWidth={0.5}
            strokeOpacity={0.4}
          />
        ))}

        {/* Baseline outline (dashed) */}
        {baseline && (
          <path d={buildLinePath(baseline)} fill="none" stroke="#0F2A26" strokeWidth={1.5} strokeDasharray="4 3" opacity={0.55} />
        )}

        {/* Overlay (optimised) curve */}
        {overlay && (
          <path d={buildLinePath(overlay)} fill="none" stroke="#14532d" strokeWidth={2.2} strokeLinecap="round" />
        )}

        {/* X-axis labels */}
        {X_LABELS.map(({ bucket, label }) => (
          <text key={bucket} x={xPos(bucket)} y={padT + cH + 18} textAnchor="middle" fontSize={10} fill="#475569">
            {label}
          </text>
        ))}

        {/* Y-axis label */}
        <text x={12} y={padT + cH / 2} textAnchor="middle" fontSize={10} fill="#475569"
          transform={`rotate(-90, 12, ${padT + cH / 2})`}>
          kW
        </text>

        {/* Hover tooltip line */}
        {hoverBucket != null && (
          <g>
            <line
              x1={xPos(hoverBucket)}
              y1={padT}
              x2={xPos(hoverBucket)}
              y2={padT + cH}
              stroke="#14532d"
              strokeWidth={1}
              strokeDasharray="2 2"
              opacity={0.6}
            />
          </g>
        )}
      </svg>

      {hoverBucket != null && stackedTotals[hoverBucket] != null && (
        <div className="mt-2 text-xs text-forest-900 tabnum text-right pr-4" data-testid="chart-hover-info">
          {String(Math.floor(hoverBucket / 2)).padStart(2, '0')}:
          {((hoverBucket % 2) * 30).toString().padStart(2, '0')} ·
          <span className="font-semibold ml-1">{fmtNumber(stackedTotals[hoverBucket], 2)} kW</span>
        </div>
      )}
    </div>
  );
}
