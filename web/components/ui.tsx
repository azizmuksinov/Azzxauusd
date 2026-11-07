"use client";

import Link from "next/link";
import { useState } from "react";

import { formatMoney } from "@/lib/i18n";
import type { Card } from "@/lib/types";

import { IconCart, IconChevron, IconHeart, IconStar } from "./icons";
import { Illustration } from "./illustrations";
import { useApp } from "./providers";

/** Tovar rasmi; demo'da rasm yo'q — kategoriya illyustratsiyasi. */
export function ProductImage({ src, category, seed = 0, className = "" }: {
  src: string; category: string; seed?: number; className?: string;
}) {
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" className={`h-full w-full object-contain ${className}`} />;
  }
  return <Illustration category={category} seed={seed} className={className} />;
}

export function Price({ price, old, size = "md" }: { price: string; old?: string | null; size?: "sm" | "md" | "lg" }) {
  const { lang } = useApp();
  const cls = { sm: "text-base", md: "text-lg", lg: "text-3xl" }[size];
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className={`${cls} font-extrabold tracking-tight text-gray-900`}>{formatMoney(price, lang)}</span>
      {old ? <span className="text-sm text-gray-400 line-through">{formatMoney(old, lang)}</span> : null}
    </div>
  );
}

export function Stars({ value, count }: { value: string | number; count: number }) {
  const { t } = useApp();
  const v = Number(value);
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-gray-500">
      <IconStar className="h-3.5 w-3.5 text-amber-400" />
      <b className="font-semibold text-gray-700">{v.toFixed(1)}</b>({count} {t("reviews")})
    </span>
  );
}

export function StockBadge({ status }: { status: Card["stock_status"] }) {
  const { t } = useApp();
  const map = {
    in_stock: ["bg-emerald-50 text-emerald-700", t("inStock")],
    low: ["bg-amber-50 text-amber-700", t("low")],
    out_of_stock: ["bg-gray-100 text-gray-500", t("outOfStock")],
  } as const;
  const [cls, label] = map[status];
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}

export function HeartButton({ productId, className = "" }: { productId: number; className?: string }) {
  const { favorites, toggleFavorite } = useApp();
  const on = favorites.has(productId);
  return (
    <button
      aria-label="favorite"
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleFavorite(productId); }}
      className={`grid h-9 w-9 place-items-center rounded-full bg-white/90 shadow-sm backdrop-blur transition hover:scale-110 ${on ? "text-rose-500" : "text-gray-400 hover:text-rose-500"} ${className}`}>
      <IconHeart filled={on} className="h-5 w-5" />
    </button>
  );
}

export function ProductCard({ p }: { p: Card }) {
  const { t, addToCart, cart } = useApp();
  const [busy, setBusy] = useState(false);
  const inCart = cart?.items.some((i) => i.variant_id === p.variant_id);
  const soldOut = p.stock_status === "out_of_stock";
  return (
    <Link href={`/p/${p.slug}`}
      className="group relative flex flex-col overflow-hidden rounded-3xl bg-white p-2 ring-1 ring-gray-100 transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_30px_-12px_rgba(76,29,149,0.25)]">
      <div className="relative aspect-[4/5] overflow-hidden rounded-2xl">
        <ProductImage src={p.image} category={p.category_slug} seed={p.id} className="transition duration-300 group-hover:scale-105" />
        <div className="absolute left-2 top-2 flex flex-col gap-1">
          {p.discount_percent > 0 ? (
            <span className="rounded-lg bg-rose-500 px-2 py-0.5 text-xs font-bold text-white">−{p.discount_percent}%</span>
          ) : null}
          {p.is_bulky ? <span className="rounded-lg bg-white/90 px-2 py-0.5 text-[11px] font-medium text-gray-600">🚚 XL</span> : null}
        </div>
        <HeartButton productId={p.id} className="absolute right-2 top-2" />
      </div>
      <div className="flex flex-1 flex-col gap-1.5 px-1.5 pb-1.5 pt-3">
        <Price price={p.price} old={p.old_price} />
        <p className="line-clamp-2 min-h-[2.5rem] text-sm leading-5 text-gray-700 group-hover:text-brand">
          {p.brand ? <span className="font-semibold text-gray-900">{p.brand.name} </span> : null}
          {p.brand ? p.name.replace(new RegExp(`^${p.brand.name}\\s*`, "i"), "") : p.name}
        </p>
        <Stars value={p.rating_avg} count={p.rating_count} />
        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <StockBadge status={p.stock_status} />
          <button
            disabled={busy || soldOut}
            onClick={async (e) => {
              e.preventDefault();
              e.stopPropagation();
              setBusy(true);
              await addToCart(p.variant_id);
              setBusy(false);
            }}
            aria-label={t("addToCart")}
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl transition ${inCart ? "bg-emerald-500 text-white" : "bg-brand text-white hover:bg-brand-dark"} disabled:bg-gray-200 disabled:text-gray-400`}>
            <IconCart className="h-5 w-5" />
          </button>
        </div>
      </div>
    </Link>
  );
}

export function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{children}</div>;
}

export function CardSkeleton() {
  return (
    <div className="animate-pulse rounded-3xl bg-white p-2 ring-1 ring-gray-100">
      <div className="aspect-[4/5] rounded-2xl bg-gray-100" />
      <div className="space-y-2 p-2">
        <div className="h-5 w-2/3 rounded bg-gray-100" />
        <div className="h-4 w-full rounded bg-gray-100" />
        <div className="h-4 w-1/2 rounded bg-gray-100" />
      </div>
    </div>
  );
}

export function GridSkeleton({ n = 10 }: { n?: number }) {
  return <Grid>{Array.from({ length: n }, (_, i) => <CardSkeleton key={i} />)}</Grid>;
}

export function Loading() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-1/3 animate-pulse rounded-xl bg-gray-200/70" />
      <GridSkeleton n={5} />
    </div>
  );
}

export function SectionTitle({ title, href }: { title: string; href?: string }) {
  const { t } = useApp();
  return (
    <div className="mb-4 flex items-end justify-between">
      <h2 className="text-xl font-extrabold tracking-tight md:text-2xl">{title}</h2>
      {href ? (
        <Link href={href} className="inline-flex items-center gap-0.5 text-sm font-semibold text-brand hover:underline">
          {t("seeAll")} <IconChevron className="h-4 w-4" />
        </Link>
      ) : null}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="rounded-2xl bg-red-50 p-4 text-sm text-red-700 ring-1 ring-red-100">
      {message}
      {onRetry ? <button onClick={onRetry} className="ml-3 font-semibold underline">{t("retry")}</button> : null}
    </div>
  );
}

export function Button({
  children, onClick, disabled, variant = "primary", type = "button", className = "",
}: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "ghost" | "danger" | "dark";
  type?: "button" | "submit"; className?: string;
}) {
  const styles = {
    primary: "bg-brand text-white shadow-[0_8px_20px_-8px_rgba(109,40,217,0.7)] hover:bg-brand-dark disabled:bg-gray-300 disabled:shadow-none",
    dark: "bg-gray-900 text-white hover:bg-black disabled:bg-gray-300",
    ghost: "bg-brand-light text-brand hover:bg-violet-200 disabled:opacity-50",
    danger: "bg-white text-red-600 ring-1 ring-red-200 hover:bg-red-50 disabled:opacity-50",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-3.5 font-semibold transition active:scale-[0.98] ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-3xl bg-white p-5 ring-1 ring-gray-100 md:p-6 ${className}`}>{children}</section>;
}
