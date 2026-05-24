import React, { useState, useMemo } from 'react';
import { fmtNumber } from '../lib/api';

// Fixed appliance order (bottom→top of stack)
export const APPLIANCE_LAYERS = [
  { key: 'Fridges', color: '#3a6a5d' },
  { key: 'Espresso', color: '#d4a843' },
  { key: 'Ovens', color: '#c44d3a' },
  { key: 'HVAC', color: '#5b4bff' },
  { key: 'Lighting', color: '#c4e94a' },
  { key: 'Dishwasher', color: '#1a504a' },
  { key: 'Hot Water', color: '#8a6cf5' },
  { key: 'Misc', color: '#a89280' },
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

const TOU_BANDS = [
  { start: 30, end: 42, color: 'rgba(196,77,58,0.07)' },     // peak
  { start: 14, end: 30, color: 'rgba(212,168,67,0.07)' },    // shoulder
  { start: 42, end: 44, color: 'rgba(212,168,67,0.07)' },    // shoulder evening
];

export default function StackedAreaChart({
  applianceCurves,
  scales,
  height = 240,
  baseline = null,
  overlay = null,
  showTooltip = true,
  testId = 'stacked-area-chart',
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

  const polygons = useMemo(() => {
    const polys = [];
    const baseStack = new Array(48).fill(0);
    for (const layer of layers) {
      const topStack = baseStack.map((v, i) => v + (layer.scaled[i] || 0));
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers, maxVal]);

  const buildLinePath = (arr) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`).join(' ');

  const yTicks = 4;
  const yTickStep = maxVal / yTicks;

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
        data-testid={testId}
      >
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

        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const val = yTickStep * i;
          const y = yPos(val);
          return (
            <g key={i}>
              <line x1={padL} y1={y} x2={padL + cW} y2={y} stroke="#e0dbc9" strokeWidth={1} />
              <text x={padL - 6} y={y + 4} textAnchor="end" fontSize={10} fill="#7a8a87">
                {fmtNumber(val, 1)}
              </text>
            </g>
          );
        })}

        {polygons.map((p) => (
          <polygon
            key={p.key}
            points={p.points}
            fill={p.color}
            fillOpacity={0.82}
            stroke={p.color}
            strokeWidth={0.5}
            strokeOpacity={0.6}
          />
        ))}

        {baseline && (
          <path d={buildLinePath(baseline)} fill="none" stroke="#0d2e2a" strokeWidth={1.5} strokeDasharray="4 3" opacity={0.55} />
        )}

        {overlay && (
          <path d={buildLinePath(overlay)} fill="none" stroke="#5b4bff" strokeWidth={2.4} strokeLinecap="round" />
        )}

        {X_LABELS.map(({ bucket, label }) => (
          <text key={bucket} x={xPos(bucket)} y={padT + cH + 18} textAnchor="middle" fontSize={10} fill="#3a4d4a">
            {label}
          </text>
        ))}

        <text x={12} y={padT + cH / 2} textAnchor="middle" fontSize={10} fill="#3a4d4a"
          transform={`rotate(-90, 12, ${padT + cH / 2})`}>
          kW
        </text>

        {hoverBucket != null && (
          <line
            x1={xPos(hoverBucket)} y1={padT}
            x2={xPos(hoverBucket)} y2={padT + cH}
            stroke="#5b4bff" strokeWidth={1} strokeDasharray="2 2" opacity={0.7}
          />
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
