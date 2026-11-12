"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { formatMoney } from "@/lib/i18n";
import type { Card } from "@/lib/types";

import { IconCart, IconCheck, IconChevron, IconHeart, IconStar } from "./icons";
import { Illustration } from "./illustrations";
import { CompareButton } from "./compare";
import { useApp } from "./providers";

/** Brauzer yorlig'idagi sarlavha: "<sahifa> — <do'kon nomi>" (har sahifaning o'z nomi). */
export function useTitle(title?: string | null) {
  const { site } = useApp();
  const shop = site?.store_name || "TexnoDo'kon";
  useEffect(() => {
    if (!title) return;
    const full = `${title} — ${shop}`;
    const apply = () => {
      if (document.title !== full) document.title = full;
    };
    apply();
    // Next sahifa ichidagi o'tishlarda (filtr, sahifalash) umumiy sarlavhani qayta qo'yadi — qaytarib turamiz.
    const mo = new MutationObserver(apply);
    mo.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => mo.disconnect();
  }, [title, shop]);
}

/** Tovar rasmi; rasm yuklanmagan bo'lsa — neytral belgi. */
export function ProductImage({ src, category, seed = 0, className = "" }: {
  src: string; category: string; seed?: number; className?: string;
}) {
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" className={`photo h-full w-full object-contain ${className}`} />;
  }
  return <Illustration category={category} seed={seed} className={className} />;
}

export function Price({ price, old, size = "md", badge = true }: {
  price: string; old?: string | null; size?: "sm" | "md" | "lg"; badge?: boolean;
}) {
  const { lang } = useApp();
  const cls = { sm: "text-[15px]", md: "text-lg", lg: "text-[28px] leading-9" }[size];
  const discount = old ? Math.round((1 - Number(price) / Number(old)) * 100) : 0;
  return (
    <div>
      <span className={`${cls} font-bold tracking-tight ${old ? "text-sale" : "text-ink"}`}>{formatMoney(price, lang)}</span>
      {old ? (
        <div className="flex items-center gap-1.5 text-[13px]">
          <span className="text-zinc-400 line-through">{formatMoney(old, lang)}</span>
          {badge && discount > 0 ? <span className="rounded-md bg-sale px-1.5 text-xs font-bold leading-5 text-white">−{discount}%</span> : null}
        </div>
      ) : null}
    </div>
  );
}

export function Stars({ value, count }: { value: string | number; count: number }) {
  const v = Number(value);
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[13px] text-zinc-500">
      <IconStar className="h-3.5 w-3.5 text-amber-400" />
      <span className="text-zinc-700">{v.toFixed(1)}</span>
      <span>· {count}</span>
    </span>
  );
}

/** Faqat muhim holatlar ko'rsatiladi: "oz qoldi" va "tugagan". */
export function StockBadge({ status }: { status: Card["stock_status"] }) {
  const { t } = useApp();
  if (status === "in_stock") return null;
  return (
    <span className={`text-[13px] ${status === "low" ? "text-amber-700" : "text-zinc-400"}`}>
      {status === "low" ? t("low") : t("outOfStock")}
    </span>
  );
}

export function HeartButton({ productId, className = "" }: { productId: number; className?: string }) {
  const { favorites, toggleFavorite, t } = useApp();
  const on = favorites.has(productId);
  return (
    <button
      aria-label={t("favorites")}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleFavorite(productId); }}
      className={`grid h-8 w-8 place-items-center transition ${on ? "text-sale" : "text-zinc-400 hover:text-zinc-700"} ${className}`}>
      <IconHeart filled={on} className="h-[22px] w-[22px]" />
    </button>
  );
}

export function ProductCard({ p }: { p: Card }) {
  const { t, addToCart, cart } = useApp();
  const [busy, setBusy] = useState(false);
  const inCart = cart?.items.some((i) => i.variant_id === p.variant_id);
  const soldOut = p.stock_status === "out_of_stock";
  const name = p.brand ? p.name.replace(new RegExp(`^${p.brand.name}\\s*`, "i"), "") : p.name;
  return (
    <Link href={`/p/${p.slug}`}
      className="group flex flex-col rounded-2xl border border-line bg-white p-2 transition duration-300 hover:-translate-y-0.5 hover:border-transparent hover:shadow-[0_12px_32px_-12px_rgba(76,29,149,0.35)] md:p-2.5">
      <div className="relative aspect-square overflow-hidden rounded-xl bg-white">
        <ProductImage src={p.image} category={p.category_slug} seed={p.id}
          className={`transition duration-300 group-hover:scale-[1.04] ${soldOut ? "opacity-50" : ""}`} />
        {p.discount_percent > 0 ? (
          <span className="absolute left-1.5 top-1.5 rounded-full bg-sale px-2 text-xs font-bold leading-6 text-white shadow-sm">
            −{p.discount_percent}%
          </span>
        ) : null}
        <HeartButton productId={p.id} className="absolute right-1 top-1 rounded-full bg-white/90 shadow-sm ring-1 ring-black/5" />
        <CompareButton productId={p.id} className="absolute right-1 top-10 rounded-full bg-white/90 shadow-sm ring-1 ring-black/5" />
      </div>
      <div className="flex flex-1 flex-col px-1 pb-1 pt-2.5">
        <Price price={p.price} old={p.old_price} badge={false} />
        <p className="mt-1 line-clamp-2 text-sm leading-5 text-zinc-800">
          {p.brand ? <span className="font-medium">{p.brand.name} </span> : null}{name}
        </p>
        <div className="mb-2.5 mt-1 flex min-h-[18px] items-center gap-2">
          <Stars value={p.rating_avg} count={p.rating_count} />
          <StockBadge status={p.stock_status} />
        </div>
        <button
          key={inCart ? "in" : "out"}
          disabled={busy || soldOut}
          onClick={async (e) => {
            e.preventDefault();
            e.stopPropagation();
            setBusy(true);
            await addToCart(p.variant_id);
            setBusy(false);
          }}
          className={`mt-auto inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-xl text-sm font-semibold transition active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-surface disabled:text-zinc-400 ${inCart ? "animate-pop bg-brand-light text-brand" : "bg-brand text-white shadow-[0_6px_16px_-8px_rgba(124,58,237,0.9)] hover:bg-brand-dark"}`}>
          {soldOut ? null : inCart ? <IconCheck className="h-4 w-4" /> : <IconCart className="h-4 w-4" />}
          {soldOut ? t("outOfStock") : inCart ? t("inCart") : t("addToCart")}
        </button>
      </div>
    </Link>
  );
}

export function Grid({ children }: { children: React.ReactNode }) {
  return <div className="grid-stagger grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:gap-4 lg:grid-cols-4 xl:grid-cols-5">{children}</div>;
}

export function CardSkeleton() {
  return (
    <div className="rounded-2xl border border-line p-2 md:p-2.5">
      <div className="skeleton aspect-square rounded-xl" />
      <div className="space-y-2 px-1 pb-1 pt-3">
        <div className="skeleton h-5 w-1/2 rounded" />
        <div className="skeleton h-4 w-full rounded" />
        <div className="skeleton h-10 w-full rounded-xl" />
      </div>
    </div>
  );
}

export function GridSkeleton({ n = 10 }: { n?: number }) {
  return <Grid>{Array.from({ length: n }, (_, i) => <CardSkeleton key={i} />)}</Grid>;
}

export function Loading() {
  return (
    <div className="space-y-5">
      <div className="h-7 w-1/4 animate-pulse rounded bg-surface" />
      <GridSkeleton n={5} />
    </div>
  );
}

export function SectionTitle({ title, href }: { title: string; href?: string }) {
  const { t } = useApp();
  return (
    <div className="mb-4 flex items-center justify-between gap-4">
      <h2 className="text-xl font-extrabold tracking-tight md:text-2xl">{title}</h2>
      {href ? (
        <Link href={href} className="inline-flex h-8 shrink-0 items-center rounded-full bg-brand-light pl-3.5 pr-2 text-sm font-medium text-brand transition hover:bg-violet-200/70">
          {t("seeAll")} <IconChevron className="h-4 w-4" />
        </Link>
      ) : null}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      {message}
      {onRetry ? <button onClick={onRetry} className="ml-3 font-medium underline">{t("retry")}</button> : null}
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
    primary: "bg-brand text-white hover:bg-brand-dark disabled:bg-zinc-200 disabled:text-zinc-400",
    dark: "bg-ink text-white hover:bg-black disabled:bg-zinc-200 disabled:text-zinc-400",
    ghost: "bg-surface text-ink hover:bg-zinc-200 disabled:opacity-50",
    danger: "border border-red-200 bg-white text-red-600 hover:bg-red-50 disabled:opacity-50",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex h-11 items-center justify-center gap-2 rounded-xl px-5 text-[15px] font-semibold transition ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-white p-5 ${className}`}>{children}</section>;
}
