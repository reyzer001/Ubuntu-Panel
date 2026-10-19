import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#080c11",
        sidebar: "#0c1117",
        panel: "#111821",
        panel2: "#151e28",
        panel3: "#1a2430",
        line: "#24303d",
        muted: "#8794a4",
        muted2: "#5f6c7c",
        accent: "#e95420",
        ok: "#22c55e",
        bad: "#ef4444",
        warn: "#f59e0b",
        info: "#3b82f6",
        violet: "#8b5cf6",
        cyanx: "#06b6d4",
      },
      borderRadius: {
        card: "14px",
      },
    },
  },
  plugins: [],
};

export default config;
