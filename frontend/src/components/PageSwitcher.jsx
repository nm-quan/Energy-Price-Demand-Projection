import React, { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

const PAGES = [
  { id: "dashboard", label: "Load Dashboard", hint: "Stacked appliance load + plans" },
  { id: "scenarios", label: "Scenario Builder", hint: "Chat with Claude · profile extraction" },
];

export default function PageSwitcher({ page, onNavigate }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const active = PAGES.find((p) => p.id === page) || PAGES[0];

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        data-testid="page-switcher-btn"
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 rounded-md border border-white/15 bg-white/[0.04] px-3 py-2 text-left transition hover:border-white/30 hover:bg-white/[0.08]"
      >
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] font-semibold text-mint/70">
            Page
          </div>
          <div className="text-[13px] font-semibold text-white truncate">
            {active.label}
          </div>
        </div>
        <ChevronDown
          size={14}
          strokeWidth={2.5}
          className={`shrink-0 text-white/60 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div
          data-testid="page-switcher-menu"
          className="absolute left-0 right-0 z-30 mt-1 rounded-md border border-white/10 bg-forest-soft shadow-xl overflow-hidden"
        >
          {PAGES.map((p) => (
            <button
              key={p.id}
              type="button"
              data-testid={`page-switcher-item-${p.id}`}
              onClick={() => {
                onNavigate(p.id);
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-2 transition ${
                p.id === page
                  ? "bg-white/10 text-white"
                  : "text-white/80 hover:bg-white/[0.06] hover:text-white"
              }`}
            >
              <div className="text-[13px] font-semibold">{p.label}</div>
              <div className="text-[10.5px] text-white/50">{p.hint}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
