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
        // Termina palette
        accent: "#4F46E5",        // indigo CTA
        "accent-hover": "#4338CA",
        forest: "#0F2A26",        // dark teal navbar
        "forest-soft": "#1B3B36",
        lime: "#C8E000",          // acid lime accent (best plan)
        "lime-soft": "#EAF291",
        mint: "#5EEAD4",          // aqua accent
        cream: "#EDE9D5",         // secondary button cream
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
