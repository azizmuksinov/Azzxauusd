import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#5b21b6", dark: "#4c1d95", light: "#f3f0fb" },
        ink: "#18181b",
        surface: "#f4f4f5",
        line: "#e4e4e7",
        sale: "#dc2626",
      },
      fontSize: { "2xs": ["11px", "14px"] },
    },
  },
  plugins: [],
} satisfies Config;
