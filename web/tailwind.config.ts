import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#7c3aed", dark: "#6d28d9", light: "#f3edff" },
        ink: "#18181b",
        surface: "#f4f4f5",
        line: "#e4e4e7",
        sale: "#e11d48",
      },
      fontSize: { "2xs": ["11px", "14px"] },
    },
  },
  plugins: [],
} satisfies Config;
