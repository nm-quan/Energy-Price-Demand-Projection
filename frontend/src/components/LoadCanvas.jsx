import React, { useEffect, useMemo, useRef, useState } from "react";
import { DndContext, useDraggable, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { restrictToHorizontalAxis } from "@dnd-kit/modifiers";
import { GripVertical } from "lucide-react";
import { bucketToTime, fmtNumber } from "../lib/api";

const PAD = { l: 52, r: 52, t: 18, b: 30 };

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

function buildAreaPath(shape, x0, y0, w, h, maxY) {
  if (!shape.length) return "";
  const dx = w / (shape.length - 1);
  let d = `M ${x0} ${y0 + h}`;
  shape.forEach((v, i) => {
    const x = x0 + i * dx;
    const y = y0 + h - (v / maxY) * h;
    d += ` L ${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  d += ` L ${(x0 + w).toFixed(2)} ${(y0 + h).toFixed(2)} Z`;
  return d;
}

function buildLinePath(values, x0, y0, w, h, maxY) {
  if (!values.length) return "";
  const dx = w / (values.length - 1);
  return values
    .map((v, i) => {
      const x = x0 + i * dx;
      const y = y0 + h - (v / maxY) * h;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function assignLanes(assets) {
  // Sort by start, greedy lane assignment.
  const byStart = [...assets].sort((a, b) => a.current_start - b.current_start);
  const laneEnds = []; // index = lane, value = bucket where lane is free
  const lanes = {};
  byStart.forEach((a) => {
    let lane = laneEnds.findIndex((end) => end <= a.current_start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(0);
    }
    laneEnds[lane] = a.current_start + a.duration;
    lanes[a.id] = lane;
  });
  return { lanes, count: Math.max(1, laneEnds.length) };
}

function DraggableBlock({ asset, lane, laneHeight, chartH, bucketPx, maxY }) {
  const blockW = Math.max(28, asset.duration * bucketPx);
  const blockH = Math.max(28, laneHeight - 4);
  const leftPx = asset.current_start * bucketPx;
  const topPx = 4 + lane * laneHeight;

  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: asset.id,
    data: { asset },
  });

  const x = transform ? transform.x : 0;
  const color = asset.feasibility === "easy"
    ? "#16a34a"
    : asset.feasibility === "medium"
    ? "#f59e0b"
    : "#dc2626";

  return (
    <div
      ref={setNodeRef}
      data-testid={`shift-block-${asset.id}`}
      {...listeners}
      {...attributes}
      className="absolute draggable-handle select-none rounded-md border shadow-sm transition-shadow"
      style={{
        left: leftPx + x,
        top: topPx,
        width: blockW,
        height: blockH,
        background: `${color}1a`,
        borderColor: color,
        boxShadow: isDragging ? "0 6px 16px rgba(15,23,42,0.18)" : undefined,
        zIndex: isDragging ? 30 : 5,
      }}
      title={`${asset.label} · ${asset.power} kW · ${asset.duration * 30} min`}
    >
      <div className="flex h-full items-center gap-1 px-1.5 overflow-hidden">
        <GripVertical size={11} style={{ color }} strokeWidth={2.5} />
        <div className="min-w-0">
          <div className="truncate text-[10.5px] font-semibold leading-tight" style={{ color: "#0f172a" }}>
            {asset.label}
          </div>
          <div className="truncate text-[9.5px] tabnum" style={{ color: "#475569" }}>
            {bucketToTime(asset.current_start)}–{bucketToTime(asset.current_start + asset.duration)} · {asset.power} kW
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoadCanvas({
  shape,
  baseline,
  zone,
  spot,
  activeAssets,
  onAssetMove,
  onAssetRemove,
}) {
  const [containerRef, containerW] = useElementWidth();
  const H = 320;
  const chartW = Math.max(0, containerW - PAD.l - PAD.r);
  const chartH = H - PAD.t - PAD.b;
  const bucketPx = chartW / 48;

  const maxY = useMemo(() => {
    const peakShape = Math.max(...shape, ...baseline, 1);
    return Math.ceil(peakShape * 1.25);
  }, [shape, baseline]);

  const spotMax = useMemo(
    () => Math.max(...(spot?.rrp_mwh || [1])) * 1.1,
    [spot]
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } })
  );

  const onDragEnd = (ev) => {
    const asset = ev.active?.data?.current?.asset;
    if (!asset) return;
    const deltaBuckets = Math.round(ev.delta.x / bucketPx);
    if (deltaBuckets === 0) return;
    let newStart = asset.current_start + deltaBuckets;
    newStart = Math.max(0, Math.min(48 - asset.duration, newStart));
    onAssetMove(asset.id, newStart);
  };

  // TOU band rectangles
  const bands = useMemo(() => {
    if (!zone) return [];
    const out = [];
    const add = (ranges, fill, label) => {
      ranges.forEach(([a, b]) => {
        out.push({
          x: PAD.l + a * bucketPx,
          w: (b - a) * bucketPx,
          fill,
          label,
        });
      });
    };
    add(zone.peak_buckets, "#fecaca", "peak");
    add(zone.shoulder_buckets, "#fde68a", "shoulder");
    return out;
  }, [zone, bucketPx]);

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const ticks = [];
    const step = maxY / 4;
    for (let i = 0; i <= 4; i++) ticks.push(Math.round(step * i * 10) / 10);
    return ticks;
  }, [maxY]);

  const xTicks = [0, 6, 12, 18, 24];

  const baselinePath = buildAreaPath(baseline, PAD.l, PAD.t, chartW, chartH, maxY);
  const shapePath = buildAreaPath(shape, PAD.l, PAD.t, chartW, chartH, maxY);
  const spotPath = spot
    ? buildLinePath(spot.rrp_mwh, PAD.l, PAD.t, chartW, chartH, spotMax)
    : "";

  return (
    <div className="rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between px-5 pt-4 pb-2">
        <div>
          <div className="eyebrow">Load curve · typical weekday</div>
          <h3 className="mt-0.5 text-[15px] font-semibold tracking-tightish text-ink">
            Drag shiftable blocks horizontally — the curve and retailer deals update live
          </h3>
        </div>
        <div className="hidden md:flex items-center gap-3.5 text-[11px] text-ink-mute">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-2 rounded-sm bg-band_peak" /> Peak window
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-2 rounded-sm bg-band_shoulder" /> Shoulder
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-2 rounded-sm bg-band_off" /> Off-peak
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block w-3 h-[2px] rounded-sm" style={{ background: "#7c3aed" }} /> NEM spot ($/MWh)
          </span>
        </div>
      </div>

      <div ref={containerRef} className="relative px-2 pb-2">
        <svg
          width="100%"
          height={H}
          viewBox={`0 0 ${Math.max(containerW, 1)} ${H}`}
          preserveAspectRatio="none"
          data-testid="load-canvas-svg"
        >
          {/* Off-peak baseline fill */}
          <rect
            x={PAD.l}
            y={PAD.t}
            width={chartW}
            height={chartH}
            fill="#bbf7d0"
            fillOpacity="0.35"
          />
          {/* TOU bands */}
          {bands.map((b, i) => (
            <rect
              key={`${b.label}-${i}`}
              x={b.x}
              y={PAD.t}
              width={b.w}
              height={chartH}
              fill={b.fill}
              fillOpacity="0.55"
            />
          ))}
          {/* Gridlines */}
          {yTicks.map((t, i) => {
            const y = PAD.t + chartH - (t / maxY) * chartH;
            return (
              <g key={i}>
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
                  x={PAD.l - 8}
                  y={y + 3.5}
                  textAnchor="end"
                  fontSize="10.5"
                  fill="#64748b"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {t}
                </text>
              </g>
            );
          })}
          {/* X ticks */}
          {xTicks.map((h) => {
            const x = PAD.l + (h / 24) * chartW;
            return (
              <g key={h}>
                <line
                  x1={x}
                  x2={x}
                  y1={PAD.t}
                  y2={PAD.t + chartH}
                  stroke="#e2e8f0"
                  strokeWidth="0.6"
                  strokeDasharray="1 3"
                />
                <text
                  x={x}
                  y={PAD.t + chartH + 16}
                  textAnchor="middle"
                  fontSize="10.5"
                  fill="#64748b"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {String(h).padStart(2, "0")}:00
                </text>
              </g>
            );
          })}
          {/* Baseline (ghost) */}
          <path
            d={baselinePath}
            fill="#1e40af"
            fillOpacity="0.06"
            stroke="#1e40af"
            strokeOpacity="0.35"
            strokeWidth="1.2"
            strokeDasharray="3 3"
          />
          {/* Shifted shape */}
          <path
            d={shapePath}
            fill="url(#shapeFill)"
            stroke="#ea580c"
            strokeWidth="1.8"
          />
          <defs>
            <linearGradient id="shapeFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ea580c" stopOpacity="0.30" />
              <stop offset="100%" stopColor="#ea580c" stopOpacity="0.05" />
            </linearGradient>
          </defs>
          {/* Spot price */}
          {spot && (
            <>
              <path
                d={spotPath}
                fill="none"
                stroke="#7c3aed"
                strokeWidth="1.4"
                strokeOpacity="0.85"
              />
              {/* secondary y-axis labels */}
              {[0, 0.5, 1].map((p, i) => {
                const v = Math.round(spotMax * p);
                const y = PAD.t + chartH - p * chartH;
                return (
                  <text
                    key={i}
                    x={PAD.l + chartW + 8}
                    y={y + 3.5}
                    fontSize="10.5"
                    fill="#7c3aed"
                    fontFamily="JetBrains Mono, monospace"
                  >
                    {v}
                  </text>
                );
              })}
              <text
                x={PAD.l + chartW + 8}
                y={PAD.t - 4}
                fontSize="9"
                fill="#7c3aed"
                fontFamily="IBM Plex Sans, sans-serif"
                fontWeight="600"
              >
                $/MWh
              </text>
            </>
          )}
          {/* Y axis label */}
          <text
            x={12}
            y={PAD.t - 4}
            fontSize="9"
            fill="#64748b"
            fontFamily="IBM Plex Sans, sans-serif"
            fontWeight="600"
          >
            kW
          </text>
        </svg>

          <DndContext
            sensors={sensors}
            modifiers={[restrictToHorizontalAxis]}
            onDragEnd={onDragEnd}
          >
            {(() => {
              const { lanes, count } = assignLanes(activeAssets);
              const laneAreaH = Math.min(chartH * 0.55, count * 34 + 6);
              const laneHeight = (laneAreaH - 6) / Math.max(count, 1);
              return (
                <div
                  className="absolute"
                  style={{
                    left: PAD.l,
                    top: PAD.t,
                    width: chartW,
                    height: laneAreaH,
                    pointerEvents: "none",
                  }}
                >
                  <div className="relative w-full h-full" style={{ pointerEvents: "auto" }}>
                    {activeAssets.map((a) => (
                      <DraggableBlock
                        key={a.id}
                        asset={a}
                        lane={lanes[a.id] || 0}
                        laneHeight={laneHeight}
                        chartH={chartH}
                        bucketPx={bucketPx}
                        maxY={maxY}
                      />
                    ))}
                  </div>
                </div>
              );
            })()}
          </DndContext>
      </div>
    </div>
  );
}
