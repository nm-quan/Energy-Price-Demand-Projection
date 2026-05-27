import React, { useState, useMemo } from 'react';
import { fmtNumber } from '../lib/api';

/**
 * Render a load curve at HOURLY resolution.
 * Input is the original 48 half-hourly buckets — we average pairs into 24 hourly kW values.
 *
 * Optional props:
 *  - baseline (48 numbers): drawn as a dashed line under the main curve (for "before")
 *  - overlay  (48 numbers): drawn as a violet solid line on top
 *  - filled   (boolean):    fill area under `series` (default true)
 */
export function toHourly(series) {
  if (!series || series.length === 0) return [];
  const out = [];
  for (let h = 0; h < 24; h++) {
    const a = series[h * 2] ?? 0;
    const b = series[h * 2 + 1] ?? a;
    out.push((a + b) / 2);
  }
  return out;
}

const X_LABELS = [
  { hour: 0, label: '12a' },
  { hour: 6, label: '6a' },
  { hour: 12, label: '12p' },
  { hour: 18, label: '6p' },
  { hour: 23, label: '11p' },
];

const TOU_BANDS = [
  { start: 15, end: 21, color: 'rgba(196,77,58,0.08)', label: 'peak' },
  { start: 7, end: 15, color: 'rgba(212,168,67,0.07)' },
  { start: 21, end: 22, color: 'rgba(212,168,67,0.07)' },
];

export default function HourlyLineChart({
  series,
  baseline = null,
  overlay = null,
  height = 220,
  fill = true,
  primaryColor = '#0d2e2a',
  overlayColor = '#5b4bff',
  testId = 'hourly-line-chart',
  showTooltip = true,
}) {
  const [hoverHour, setHoverHour] = useState(null);

  const svgW = 760;
  const svgH = height;
  const padL = 44, padR = 16, padT = 16, padB = 28;
  const cW = svgW - padL - padR;
  const cH = svgH - padT - padB;

  const main = useMemo(() => toHourly(series || []), [series]);
  const base = useMemo(() => (baseline ? toHourly(baseline) : null), [baseline]);
  const over = useMemo(() => (overlay ? toHourly(overlay) : null), [overlay]);

  const maxVal = useMemo(() => {
    let m = 0;
    [main, base, over].forEach((arr) => {
      if (arr) {
        for (const v of arr) if (v > m) m = v;
      }
    });
    return (m || 1) * 1.10;
  }, [main, base, over]);

  const xPos = (h) => padL + (h / 23) * cW;
  const yPos = (v) => padT + cH - (v / maxVal) * cH;

  const linePath = (arr) =>
    arr.map((v, i) => `${i === 0 ? 'M' : 'L'}${xPos(i).toFixed(1)},${yPos(v).toFixed(1)}`).join(' ');

  const areaPath = (arr) =>
    `${linePath(arr)} L${xPos(arr.length - 1).toFixed(1)},${yPos(0).toFixed(1)} L${xPos(0).toFixed(1)},${yPos(0).toFixed(1)} Z`;

  const yTicks = 4;
  const yTickStep = maxVal / yTicks;

  const handleMove = (e) => {
    if (!showTooltip) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * svgW;
    const ratio = (x - padL) / cW;
    const h = Math.max(0, Math.min(23, Math.round(ratio * 23)));
    setHoverHour(h);
  };

  return (
    <div style={{ width: '100%' }}>
      <svg
        viewBox={`0 0 ${svgW} ${svgH}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: 'auto' }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverHour(null)}
        data-testid={testId}
      >
        {TOU_BANDS.map((band, idx) => (
          <rect
            key={idx}
            x={xPos(band.start)}
            y={padT}
            width={xPos(Math.min(band.end, 23)) - xPos(band.start)}
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

        {fill && main.length > 0 && (
          <path d={areaPath(main)} fill={primaryColor} fillOpacity={0.10} />
        )}
        {main.length > 0 && (
          <path d={linePath(main)} fill="none" stroke={primaryColor} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
        )}

        {base && (
          <path d={linePath(base)} fill="none" stroke="#0d2e2a" strokeWidth={1.4} strokeDasharray="4 3" opacity={0.55} />
        )}

        {over && (
          <path d={linePath(over)} fill="none" stroke={overlayColor} strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
        )}

        {X_LABELS.map(({ hour, label }) => (
          <text key={hour} x={xPos(hour)} y={padT + cH + 18} textAnchor="middle" fontSize={10} fill="#3a4d4a">
            {label}
          </text>
        ))}

        <text x={12} y={padT + cH / 2} textAnchor="middle" fontSize={10} fill="#3a4d4a"
              transform={`rotate(-90, 12, ${padT + cH / 2})`}>
          kW
        </text>

        {hoverHour != null && main[hoverHour] != null && (
          <>
            <line
              x1={xPos(hoverHour)} y1={padT}
              x2={xPos(hoverHour)} y2={padT + cH}
              stroke="#5b4bff" strokeWidth={1} strokeDasharray="2 2" opacity={0.6}
            />
            <circle cx={xPos(hoverHour)} cy={yPos(main[hoverHour])} r={3.5} fill={primaryColor} />
            {over && (
              <circle cx={xPos(hoverHour)} cy={yPos(over[hoverHour])} r={3.5} fill={overlayColor} />
            )}
          </>
        )}
      </svg>

      {hoverHour != null && main[hoverHour] != null && (
        <div className="mt-1 text-[11px] text-forest-900 tabnum text-right pr-2" data-testid="chart-hover-info">
          {String(hoverHour).padStart(2, '0')}:00 ·
          <span className="font-semibold ml-1">{fmtNumber(main[hoverHour], 2)} kW</span>
          {over && (
            <span className="ml-3" style={{ color: overlayColor }}>
              after: <span className="font-semibold">{fmtNumber(over[hoverHour], 2)} kW</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}
