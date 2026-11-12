import type { Config } from "tailwindcss";

// Ranglar CSS o'zgaruvchilaridan olinadi (globals.css): yorug' va qora mavzu bitta sinflar bilan ishlaydi.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: v("brand"), dark: v("brand-dark"), light: v("brand-light") },
        ink: v("ink"),
        surface: v("surface"),
        line: v("line"),
        sale: v("sale"),
      },
      fontSize: { "2xs": ["11px", "14px"] },
    },
  },
  plugins: [],
} satisfies Config;
