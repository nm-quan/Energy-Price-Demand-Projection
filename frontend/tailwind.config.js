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
        // Termina palette (per Change 2 spec)
        forest: {
          DEFAULT: "#14532d",
          50: "#f0fdf4",
          100: "#dcfce7",
          200: "#bbf7d0",
          300: "#86efac",
          400: "#4ade80",
          500: "#22c55e",
          600: "#16a34a",
          700: "#15803d",
          800: "#166534",
          900: "#14532d",
          950: "#0a2918",
        },
        lime: {
          DEFAULT: "#84cc16",
          50: "#f7fee7",
          100: "#ecfccb",
          200: "#d9f99d",
          300: "#bef264",
          400: "#a3e635",
          500: "#84cc16",
          600: "#65a30d",
          700: "#4d7c0f",
          800: "#3f6212",
          900: "#365314",
        },
        mint: {
          DEFAULT: "#f0fdf4",
          50: "#f0fdf4",
          100: "#dcfce7",
        },
        cream: "#EDE9D5",
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
