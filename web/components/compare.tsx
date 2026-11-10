"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { IconScale } from "./icons";
import { useApp } from "./providers";

// Solishtirish: kartochkadagi tugma va ekran chetidagi "Solishtirish (N)" yorlig'i.

export function CompareButton({ productId, className = "" }: { productId: number; className?: string }) {
  const { compare, toggleCompare, t } = useApp();
  const on = compare.includes(productId);
  return (
    <button
      aria-label={t("compareAdd")}
      title={t("compareAdd")}
      aria-pressed={on}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleCompare(productId); }}
      className={`grid h-8 w-8 place-items-center transition ${on ? "text-brand" : "text-zinc-400 hover:text-zinc-700"} ${className}`}>
      <IconScale className="h-5 w-5" />
    </button>
  );
}

/** Tanlangan tovarlar bo'lsa — solishtirish sahifasiga olib boradigan suzuvchi tugma. */
export function CompareBar() {
  const { compare, t } = useApp();
  const pathname = usePathname();
  if (!compare.length || pathname === "/compare" || pathname.startsWith("/kuryer") || pathname.startsWith("/xodim")) return null;
  // Telefonda pastki menyu (va tovar sahifasida xarid qatori) ustida turadi.
  const mobileBottom = pathname.startsWith("/p/") ? "bottom-[136px]" : "bottom-[72px]";
  return (
    <Link href="/compare"
      className={`animate-pop fixed right-3 z-30 flex items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-lg hover:bg-black md:bottom-6 md:right-6 ${mobileBottom}`}>
      <IconScale className="h-5 w-5" />
      {t("compare")}
      <span className="rounded-full bg-white px-1.5 text-xs font-semibold text-ink">{compare.length}</span>
    </Link>
  );
}
