// Sayt matnlari (admin paneldagi "Sayt" bo'limidan boshqariladi): /api/v1/site.
import type { Lang } from "./i18n";
import { latinToCyrillic } from "./translit";

export type L = { uz: string; ru: string };
export type SectionKey = "hero" | "categories" | "deals" | "popular" | "new" | "brands" | "recent";
export type Site = {
  store_name: string;
  city: L;
  phone: string;
  email: string;
  address: L;
  working_hours: L;
  socials: { telegram: string; instagram: string; facebook: string; youtube: string };
  announcement: { enabled: boolean; text: L; link: string; color: string };
  home_sections: { key: SectionKey; enabled: boolean; title: L }[];
  footer_about: L;
  pay_methods: string;
  pages: Record<string, { title: L; body: L }>;
  /** Muddatli to'lov kalkulyatori: rejalar (oy, ustama foizi). */
  installments?: { enabled: boolean; plans: { months: number; percent: number }[]; note: L };
};

/** Ikki tilli matn → joriy tilda (ruscha bo'sh bo'lsa — o'zbekcha; kirill — lotindan o'giriladi). */
export function loc(v: L | undefined | null, lang: Lang): string {
  if (!v) return "";
  if (lang === "ru") return v.ru || v.uz || "";
  return lang === "uz_cyrl" ? latinToCyrillic(v.uz || "") : v.uz || "";
}
