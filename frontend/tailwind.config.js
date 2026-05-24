/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        // Termina-inspired palette
        forest: {
          DEFAULT: "#0d2e2a",
          50: "#e6f1ee",
          100: "#c7e0d9",
          200: "#9cc6bb",
          300: "#6daa9a",
          400: "#45897a",
          500: "#2a6a5d",
          600: "#1a504a",
          700: "#123e3a",
          800: "#0d2e2a",
          900: "#091e1c",
          950: "#051310",
        },
        lime: {
          DEFAULT: "#c4e94a",
          50: "#f5fbe0",
          100: "#ebf6c1",
          200: "#dcef8e",
          300: "#cde75c",
          400: "#c4e94a",
          500: "#a8d426",
          600: "#86ab1e",
          700: "#647f19",
          800: "#475a15",
          900: "#2e3b10",
        },
        violet: {
          DEFAULT: "#5b4bff",
          50: "#eeebff",
          100: "#ddd8ff",
          200: "#bcb2ff",
          300: "#9b8dff",
          400: "#7a67ff",
          500: "#5b4bff",
          600: "#4937e8",
          700: "#3727b8",
          800: "#261b85",
          900: "#181159",
        },
        cream: {
          DEFAULT: "#f5f1e8",
          50: "#fdfcf8",
          100: "#f9f6ed",
          200: "#f5f1e8",
          300: "#ece5d3",
          400: "#dcd2b8",
        },
        ink: {
          DEFAULT: "#0d2e2a",
          soft: "#3a4d4a",
          mute: "#7a8a87",
        },
        line: "#e0dbc9",
      },
      fontFamily: {
        // Distinctive serif headline + grotesk body
        display: ['"Fraunces"', '"Recoleta"', "Georgia", "ui-serif", "serif"],
        sans: ['"Inter Tight"', '"DM Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      letterSpacing: {
        tightish: "-0.018em",
        tightest: "-0.04em",
      },
      boxShadow: {
        card: "0 1px 0 rgba(13,46,42,0.04), 0 8px 24px -12px rgba(13,46,42,0.08)",
        glow: "0 0 0 4px rgba(91,75,255,0.18)",
      },
    },
  },
  plugins: [],
};
