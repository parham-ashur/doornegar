import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        persian: ["Vazirmatn", "Tahoma", "sans-serif"],
        latin: ["IBM Plex Sans", "system-ui", "sans-serif"],
      },
      colors: {
        // Source alignment colors
        state: {
          DEFAULT: "#dc2626", // red-600
          light: "#fecaca",   // red-200
          dark: "#991b1b",    // red-800
        },
        "semi-state": {
          DEFAULT: "#d97706", // amber-600
          light: "#fde68a",   // amber-200
          dark: "#92400e",    // amber-800
        },
        independent: {
          DEFAULT: "#059669", // emerald-600
          light: "#a7f3d0",   // emerald-200
          dark: "#065f46",    // emerald-800
        },
        diaspora: {
          DEFAULT: "#2563eb", // blue-600
          light: "#bfdbfe",   // blue-200
          dark: "#1e40af",    // blue-800
        },
        // Bias spectrum
        "pro-regime": "#dc2626",
        reformist: "#eab308",
        neutral: "#6b7280",
        opposition: "#2563eb",
      },
    },
  },
  plugins: [require("tailwindcss-rtl")],
};

export default config;
