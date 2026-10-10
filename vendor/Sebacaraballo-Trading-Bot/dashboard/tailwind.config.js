/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        surface: "#12121a",
        "surface-hover": "#1a1a26",
        border: "#1e1e2e",
        primary: "#6366f1",
        bullish: "#22c55e",
        bearish: "#ef4444",
        neutral: "#94a3b8",
        "text-primary": "#f1f5f9",
        "text-muted": "#64748b",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
