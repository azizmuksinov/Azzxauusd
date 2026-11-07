"use client";

import Link from "next/link";

import { formatMoney } from "@/lib/i18n";
import type { Card } from "@/lib/types";

import { useApp } from "./providers";

const ICONS: [RegExp, string][] = [
  [/smartfon|telefon/, "📱"],
  [/televizor/, "📺"],
  [/noutbuk/, "💻"],
  [/muzlatkich/, "🧊"],
  [/kir-yuvish/, "🫧"],
  [/konditsioner/, "❄️"],
  [/maishiy/, "🏠"],
  [/elektronika/, "🔌"],
];

export function categoryIcon(slug: string): string {
  return ICONS.find(([re]) => re.test(slug))?.[1] ?? "📦";
}

/** Rasm bo'lmasa — kategoriya belgisi (demo tovarlarda rasm yo'q). */
export function ProductImage({ src, category, className = "" }: { src: string; category: string; className?: string }) {
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" className={`h-full w-full object-contain ${className}`} />;
  }
  const icon = categoryIcon(category);
  return (
    <div className={`flex h-full w-full items-center justify-center bg-gradient-to-br from-brand-light to-white text-6xl ${className}`}>
      {icon}
    </div>
  );
}

export function Price({ price, old, size = "md" }: { price: string; old?: string | null; size?: "md" | "lg" }) {
  const { lang } = useApp();
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className={size === "lg" ? "text-3xl font-bold" : "text-lg font-bold"}>{formatMoney(price, lang)}</span>
      {old ? <span className="text-sm text-gray-400 line-through">{formatMoney(old, lang)}</span> : null}
    </div>
  );
}

export function StockBadge({ status }: { status: Card["stock_status"] }) {
  const { t } = useApp();
  const map = {
    in_stock: ["bg-green-50 text-green-700", t("inStock")],
    low: ["bg-amber-50 text-amber-700", t("low")],
    out_of_stock: ["bg-gray-100 text-gray-500", t("outOfStock")],
  } as const;
  const [cls, label] = map[status];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}

export function ProductCard({ p }: { p: Card }) {
  return (
    <Link href={`/p/${p.slug}`} className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-gray-100 transition hover:shadow-md">
      <div className="relative aspect-square">
        <ProductImage src={p.image} category={p.category_slug} />
        {p.discount_percent > 0 ? (
          <span className="absolute left-2 top-2 rounded-lg bg-red-500 px-2 py-0.5 text-xs font-semibold text-white">
            −{p.discount_percent}%
          </span>
        ) : null}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <Price price={p.price} old={p.old_price} />
        <p className="line-clamp-2 text-sm text-gray-700 group-hover:text-brand">{p.name}</p>
        <div className="mt-auto pt-1">
          <StockBadge status={p.stock_status} />
        </div>
      </div>
    </Link>
  );
}

export function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{children}</div>;
}

export function Loading() {
  const { t } = useApp();
  return <div className="py-16 text-center text-gray-400">{t("loading")}</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="rounded-xl bg-red-50 p-4 text-sm text-red-700">
      {message}
      {onRetry ? (
        <button onClick={onRetry} className="ml-3 underline">
          {t("retry")}
        </button>
      ) : null}
    </div>
  );
}

export function Button({
  children, onClick, disabled, variant = "primary", type = "button", className = "",
}: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "ghost" | "danger";
  type?: "button" | "submit"; className?: string;
}) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-dark disabled:bg-gray-300",
    ghost: "bg-brand-light text-brand hover:bg-violet-200 disabled:opacity-50",
    danger: "bg-white text-red-600 ring-1 ring-red-200 hover:bg-red-50 disabled:opacity-50",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`rounded-xl px-5 py-3 font-semibold transition ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}
