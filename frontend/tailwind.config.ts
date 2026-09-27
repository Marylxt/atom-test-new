import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#06080F",
          900: "#0A0E18",
          800: "#0F1524",
          700: "#151C2E",
          600: "#1D2539",
          500: "#2A3348",
        },
        brand: {
          300: "#9DBAFF",
          400: "#6E9BFF",
          500: "#4F7FFF",
          600: "#3A63DB",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseRing: {
          "0%": { boxShadow: "0 0 0 0 rgba(79,127,255,0.45)" },
          "70%": { boxShadow: "0 0 0 10px rgba(79,127,255,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(79,127,255,0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-in": "fadeIn .28s ease-out both",
        "pulse-ring": "pulseRing 1.8s ease-out infinite",
        shimmer: "shimmer 1.8s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
