"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { formatMoney } from "@/lib/i18n";
import type { Card } from "@/lib/types";

import { IconCart, IconCheck, IconChevron, IconHeart, IconStar } from "./icons";
import { Star8 } from "./illustrations-star";
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
  // Surat ochilmasa (o'chirilgan yoki manba ishlamayapti) — siniq belgi o'rniga kategoriya belgisi.
  const [failed, setFailed] = useState("");
  if (src && failed !== src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" onError={() => setFailed(src)} className={`photo h-full w-full object-contain ${className}`} />;
  }
  return <Illustration category={category} seed={seed} className={className} />;
}

export function Price({ price, old, size = "md", badge = true }: {
  price: string; old?: string | null; size?: "sm" | "md" | "lg"; badge?: boolean;
}) {
  const { lang } = useApp();
  const cls = { sm: "text-[15px]", md: "text-[15px] leading-5 md:text-[17px] md:leading-6", lg: "text-[30px] leading-9" }[size];
  const discount = old ? Math.round((1 - Number(price) / Number(old)) * 100) : 0;
  return (
    <div>
      {old ? (
        <div className="flex items-center gap-1.5 whitespace-nowrap text-[12px] leading-4 md:text-[13px]">
          <span className="text-zinc-400 line-through">{formatMoney(old, lang)}</span>
          {badge && discount > 0 ? <span className="rounded-full bg-sale px-1.5 text-[11px] font-bold leading-[18px] text-white">−{discount}%</span> : null}
        </div>
      ) : null}
      <span className={`${cls} whitespace-nowrap font-extrabold tracking-tight ${old ? "text-sale" : "text-ink"}`}>{formatMoney(price, lang)}</span>
    </div>
  );
}

export function Stars({ value, count }: { value: string | number; count: number }) {
  const v = Number(value);
  if (!count) return null;
  return (
    <span className="inline-flex items-center gap-1 text-[13px] text-zinc-500">
      <IconStar className="h-3.5 w-3.5 text-accent" />
      <span className="font-medium text-zinc-700">{v.toFixed(1)}</span>
      <span>({count})</span>
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
      className={`grid h-9 w-9 place-items-center transition ${on ? "text-sale" : "text-zinc-400 hover:text-zinc-700"} ${className}`}>
      <IconHeart filled={on} className="h-5 w-5" />
    </button>
  );
}

/** Tovar kartochkasi: oq "koshin" — surat, brend, nom, pastda narx va dumaloq savat tugmasi. */
export function ProductCard({ p }: { p: Card }) {
  const { t, addToCart, cart } = useApp();
  const [busy, setBusy] = useState(false);
  const inCart = cart?.items.some((i) => i.variant_id === p.variant_id);
  const soldOut = p.stock_status === "out_of_stock";
  const name = p.brand ? p.name.replace(new RegExp(`^${p.brand.name}\\s*`, "i"), "") : p.name;
  const label = soldOut ? t("outOfStock") : inCart ? t("inCart") : t("addToCart");
  const cartButton = (cls: string) => (
    <button
      key={inCart ? "in" : "out"}
      disabled={busy || soldOut}
      aria-label={label}
      title={label}
      onClick={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        setBusy(true);
        await addToCart(p.variant_id);
        setBusy(false);
      }}
      className={`h-11 w-11 shrink-0 place-items-center rounded-full transition active:scale-90 disabled:cursor-not-allowed disabled:bg-surface disabled:text-zinc-400 ${inCart ? "animate-pop bg-brand-light text-brand" : "bg-brand text-white hover:bg-brand-dark"} ${cls}`}>
      {inCart ? <IconCheck className="h-5 w-5" /> : <IconCart className="h-5 w-5" />}
    </button>
  );
  return (
    <Link href={`/p/${p.slug}`}
      className="group relative flex flex-col rounded-[22px] bg-white p-2 shadow-card transition duration-300 hover:-translate-y-1 hover:shadow-lift md:p-2.5">
      <div className="relative aspect-square overflow-hidden rounded-2xl">
        <ProductImage src={p.image} category={p.category_slug} seed={p.id}
          className={`transition duration-500 group-hover:scale-[1.05] ${soldOut ? "opacity-50" : ""}`} />
        {p.discount_percent > 0 ? (
          <span className="absolute left-2 top-2 rounded-full bg-sale px-2 text-xs font-bold leading-6 text-white shadow-sm">
            −{p.discount_percent}%
          </span>
        ) : null}
        <div className="absolute right-1.5 top-1.5 flex flex-col gap-1.5">
          <HeartButton productId={p.id} className="rounded-full bg-white/90 shadow-sm ring-1 ring-black/5" />
          <CompareButton productId={p.id} className="rounded-full bg-white/90 shadow-sm ring-1 ring-black/5 md:opacity-0 md:transition md:group-hover:opacity-100 md:aria-pressed:opacity-100" />
        </div>
        {/* Telefonda "Savatga" surat burchagida turadi — narx to'liq sig'adi. */}
        {cartButton("absolute bottom-1.5 right-1.5 grid shadow-md ring-2 ring-white md:hidden")}
      </div>
      <div className="flex flex-1 flex-col px-1.5 pb-1 pt-3">
        {p.brand ? <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-brand">{p.brand.name}</span> : null}
        <p className="mt-0.5 line-clamp-2 min-h-[40px] text-sm font-medium leading-5 text-ink">{name}</p>
        <div className="mt-1 flex min-h-[18px] items-center gap-2">
          <Stars value={p.rating_avg} count={p.rating_count} />
          <StockBadge status={p.stock_status} />
        </div>
        <div className="mt-auto flex items-end justify-between gap-2 pt-2">
          <div className="min-w-0"><Price price={p.price} old={p.old_price} badge={false} /></div>
          {cartButton("hidden md:grid")}
        </div>
      </div>
    </Link>
  );
}

/** `narrow` — yonida filtrlar ustuni bor ro'yxat uchun (ustunlar kamroq, kartochka siqilmaydi). */
export function Grid({ children, narrow = false }: { children: React.ReactNode; narrow?: boolean }) {
  const cols = narrow ? "sm:grid-cols-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" : "sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5";
  return <div className={`grid-stagger grid grid-cols-2 gap-2.5 md:gap-4 ${cols}`}>{children}</div>;
}

export function CardSkeleton() {
  return (
    <div className="rounded-[22px] bg-white p-2 shadow-card md:p-2.5">
      <div className="skeleton aspect-square rounded-2xl" />
      <div className="space-y-2 px-1.5 pb-1 pt-3">
        <div className="skeleton h-3 w-1/3 rounded" />
        <div className="skeleton h-4 w-full rounded" />
        <div className="flex items-end justify-between pt-3">
          <div className="skeleton h-6 w-1/2 rounded" />
          <div className="skeleton h-11 w-11 rounded-full" />
        </div>
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
      <div className="skeleton h-8 w-1/4 rounded-full" />
      <GridSkeleton n={5} />
    </div>
  );
}

/** Bo'lim sarlavhasi: brend yulduzchasi + nom; o'ngda "Hammasi" havolasi. */
export function SectionTitle({ title, href }: { title: string; href?: string }) {
  const { t } = useApp();
  return (
    <div className="mb-4 flex items-center justify-between gap-4 md:mb-5">
      <h2 className="flex items-center gap-2.5 text-[22px] font-extrabold tracking-tight md:text-[26px]">
        <Star8 className="h-5 w-5 shrink-0 text-brand md:h-6 md:w-6" filled />
        {title}
      </h2>
      {href ? (
        <Link href={href} className="group inline-flex h-9 shrink-0 items-center gap-0.5 rounded-full bg-white pl-4 pr-2.5 text-sm font-semibold text-ink shadow-card transition hover:text-brand">
          {t("seeAll")} <IconChevron className="h-4 w-4 transition group-hover:translate-x-0.5" />
        </Link>
      ) : null}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useApp();
  return (
    <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
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
      className={`inline-flex h-12 items-center justify-center gap-2 rounded-full px-6 text-[15px] font-semibold transition active:scale-[0.98] ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`rounded-3xl bg-white p-5 shadow-card ${className}`}>{children}</section>;
}
