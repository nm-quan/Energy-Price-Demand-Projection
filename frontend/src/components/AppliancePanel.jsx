import React from 'react';
import { APPLIANCE_LAYERS } from './StackedAreaChart';

/**
 * AppliancePanel — toggle chips with scale sliders (0–200%).
 *
 * Props:
 *  - scales: { [name]: number }
 *  - enabled: { [name]: boolean }
 *  - lastScales: { [name]: number }
 *  - onScaleChange(name, value)
 *  - onToggle(name)
 */
export default function AppliancePanel({ scales, enabled, onScaleChange, onToggle }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="appliance-panel">
      {APPLIANCE_LAYERS.map(({ key, color }) => {
        const isOn = enabled[key];
        const scale = scales[key] ?? 1;
        return (
          <div
            key={key}
            data-testid={`appliance-chip-${key}`}
            className={`border rounded-lg p-2.5 transition-colors ${
              isOn ? 'border-forest-300 bg-white' : 'border-slate-200 bg-slate-50 opacity-60'
            }`}
          >
            <button
              type="button"
              onClick={() => onToggle(key)}
              data-testid={`appliance-toggle-${key}`}
              className="flex items-center gap-2 w-full text-left"
            >
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-xs font-medium text-forest-900 truncate">{key}</span>
              <span className="ml-auto text-xs text-slate-500 tabnum">
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
              className="w-full mt-2 accent-lime-500 disabled:opacity-40"
            />
          </div>
        );
      })}
    </div>
  );
}
