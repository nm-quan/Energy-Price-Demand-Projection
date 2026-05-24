import React from 'react';
import { APPLIANCE_LAYERS } from './StackedAreaChart';

/**
 * Compact 4-column appliance grid (8 chips × 1 row on wide, 2 rows on narrow).
 * No internal scrolling — fits within the parent. Sliders are full-width pills.
 */
export default function AppliancePanel({ scales, enabled, onScaleChange, onToggle }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2" data-testid="appliance-panel">
      {APPLIANCE_LAYERS.map(({ key, color }) => {
        const isOn = enabled[key];
        const scale = scales[key] ?? 1;
        return (
          <div
            key={key}
            data-testid={`appliance-chip-${key}`}
            className={`border rounded-xl p-2.5 transition-colors ${
              isOn ? 'border-forest-200 bg-cream-50' : 'border-line bg-cream-200 opacity-60'
            }`}
          >
            <button
              type="button"
              onClick={() => onToggle(key)}
              data-testid={`appliance-toggle-${key}`}
              className="flex items-center gap-2 w-full text-left"
            >
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
              <span className="text-[11px] font-semibold text-forest-900 truncate flex-1">{key}</span>
              <span className="text-[10px] text-ink-mute tabnum">
                {isOn ? `${Math.round(scale * 100)}%` : 'off'}
              </span>
            </button>
            <input
              type="range"
              min={0}
              max={200}
              step={5}
              value={isOn ? Math.round(scale * 100) : 0}
              onChange={(e) => onScaleChange(key, parseInt(e.target.value, 10) / 100)}
              disabled={!isOn}
              data-testid={`appliance-slider-${key}`}
              className="w-full mt-1.5 disabled:opacity-40"
            />
          </div>
        );
      })}
    </div>
  );
}
