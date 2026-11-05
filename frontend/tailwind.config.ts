import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["var(--font-sans)", "system-ui", "sans-serif"], mono: ["var(--font-mono)", "ui-monospace", "monospace"] },
      colors: {
        ink: { DEFAULT: "#0B1726", 2: "#3B4757", 3: "#6B7685" },
        line: "#E4E7EC", canvas: "#F5F6F8",
        brand: { DEFAULT: "#1F3B73", soft: "#E8EDF7" },
      },
    },
  },
  plugins: [],
};
export default config;
