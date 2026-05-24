/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        "ink-soft": "#334155",
        "ink-mute": "#64748b",
        line: "#e2e8f0",
        canvas: "#ffffff",
        surface: "#f8fafc",
        accent: "#1e40af",
        // Multi-color palette for the load-curve story
        c_orig: "#1e40af",   // original demand
        c_mod: "#ea580c",    // modelled demand
        c_price: "#7c3aed",  // RRP overlay
        band_peak: "#fecaca",
        band_shoulder: "#fde68a",
        band_off: "#bbf7d0",
        feas_easy: "#16a34a",
        feas_med: "#f59e0b",
        feas_hard: "#dc2626",
      },
      fontFamily: {
        sans: [
          "IBM Plex Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      letterSpacing: {
        tightish: "-0.012em",
      },
    },
  },
  plugins: [],
};
