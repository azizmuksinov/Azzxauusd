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
        page: v("page"),
        card: v("card"),
        accent: v("accent"),
      },
      fontFamily: {
        // Sarlavha va logotip uchun keng, xarakterli shrift; matn uchun kirillni yaxshi ko'rsatadigan shrift.
        display: ['"Unbounded Variable"', '"Golos Text Variable"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgb(10 31 36 / 0.04), 0 10px 28px -16px rgb(10 31 36 / 0.16)",
        lift: "0 2px 4px rgb(10 31 36 / 0.05), 0 22px 44px -18px rgb(13 148 136 / 0.38)",
        dock: "0 12px 40px -10px rgb(10 31 36 / 0.35)",
      },
      fontSize: { "2xs": ["11px", "14px"] },
    },
  },
  plugins: [],
} satisfies Config;
