import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "rgb(var(--border) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-strong": "rgb(var(--accent-strong) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        "ok-soft": "rgb(var(--ok-soft) / <alpha-value>)",
        warn: "rgb(var(--warn) / <alpha-value>)",
        "warn-soft": "rgb(var(--warn-soft) / <alpha-value>)",
        risk: "rgb(var(--risk) / <alpha-value>)",
        "risk-soft": "rgb(var(--risk-soft) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
        "info-soft": "rgb(var(--info-soft) / <alpha-value>)",
        app: "rgb(var(--app) / <alpha-value>)"
      },
      boxShadow: {
        soft: "0 10px 30px rgb(15 23 42 / 0.08)"
      }
    }
  },
  plugins: []
};

export default config;
