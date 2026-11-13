"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";
import type { Card } from "@/lib/types";

import { IconChevron, IconPlus } from "./icons";
import { Star8 } from "./illustrations-star";
import { useApp } from "./providers";
import { Button, ProductImage, SectionTitle } from "./ui";

// ------------------------------------------------------------------ bonus
export type BonusInfo = { enabled: boolean; earn_percent: string; max_pay_percent: number };
let bonusCache: Promise<BonusInfo> | null = null;

/** Bonus shartlari (bir marta so'raladi): tizim o'chiq bo'lsa — hech narsa ko'rsatilmaydi. */
export function useBonusInfo(): BonusInfo | null {
  const [info, setInfo] = useState<BonusInfo | null>(null);
  useEffect(() => {
    bonusCache ??= api<BonusInfo>("/bonus", { auth: false });
    bonusCache.then(setInfo).catch(() => { bonusCache = null; });
  }, []);
  return info?.enabled ? info : null;
}

/** Tovar sahifasi: "+N bonus" — shu xariddan qaytadigan bonus. */
export function BonusHint({ price }: { price: string | number }) {
  const { t, lang } = useApp();
  const info = useBonusInfo();
  if (!info) return null;
  const amount = Math.floor((Number(price) * Number(info.earn_percent)) / 100);
  if (amount <= 0) return null;
  return (
    <p className="flex items-center gap-2 rounded-2xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
      <Star8 className="h-4 w-4 shrink-0 text-accent" filled />
      <span><b>+{formatMoney(amount, lang).replace(/\s\S+$/, "")}</b> {t("bonusEarnHint").replace("{p}", String(Number(info.earn_percent)))}</span>
    </p>
  );
}

// ------------------------------------------------------------------ birga arzonroq
type Offer = { id: number; discount_percent: string; bundle_price: string; save: string; product: Card };

/** Tovar sahifasi: shu tovar bilan birga olinsa arzonroq bo'ladigan tovarlar. */
export function Bundles({ slug, variantId }: { slug: string; variantId: number }) {
  const { t, lang, addToCart, cart } = useApp();
  const [offers, setOffers] = useState<Offer[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  useEffect(() => {
    api<Offer[]>(`/products/${slug}/bundles`, { auth: false }).then(setOffers).catch(() => setOffers([]));
  }, [slug, lang]);
  if (!offers.length) return null;
  const inCart = (id: number) => cart?.items.some((i) => i.variant_id === id);
  return (
    <section className="rounded-[28px] bg-white p-4 shadow-card md:p-6">
      <div className="mb-4 flex items-center gap-2.5">
        <span className="grid h-10 w-10 place-items-center rounded-2xl bg-sale/10 font-display text-sm font-bold text-sale">%</span>
        <div>
          <h2 className="text-lg font-extrabold tracking-tight md:text-xl">{t("bundleTitle")}</h2>
          <p className="text-sm text-zinc-500">{t("bundleWith")}</p>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {offers.map((o) => {
          const both = inCart(variantId) && inCart(o.product.variant_id);
          return (
            <div key={o.id} className="flex items-center gap-3 rounded-2xl bg-surface p-3">
              <IconPlus className="h-5 w-5 shrink-0 text-zinc-400" />
              <Link href={`/p/${o.product.slug}`} className="h-20 w-20 shrink-0 overflow-hidden rounded-2xl">
                <ProductImage src={o.product.image} category={o.product.category_slug} seed={o.product.id} />
              </Link>
              <div className="min-w-0 flex-1">
                <Link href={`/p/${o.product.slug}`} className="line-clamp-2 text-sm font-medium leading-5 hover:text-brand">{o.product.name}</Link>
                <p className="mt-1 flex flex-wrap items-baseline gap-x-2">
                  <b className="text-sale">{formatMoney(o.bundle_price, lang)}</b>
                  <span className="text-xs text-zinc-400 line-through">{formatMoney(o.product.price, lang)}</span>
                  <span className="rounded-full bg-sale px-1.5 text-[11px] font-bold leading-[18px] text-white">−{Number(o.discount_percent)}%</span>
                </p>
              </div>
              <button disabled={busy === o.id || both}
                onClick={async () => {
                  setBusy(o.id);
                  // Asosiy tovar savatda bo'lmasa — ikkalasi qo'shiladi (chegirma faqat birga bo'lganda ishlaydi).
                  if (!inCart(variantId)) await addToCart(variantId);
                  if (!inCart(o.product.variant_id)) await addToCart(o.product.variant_id);
                  setBusy(null);
                }}
                className={`h-10 shrink-0 rounded-full px-4 text-sm font-semibold transition ${both ? "bg-brand-light text-brand" : "bg-brand text-white hover:bg-brand-dark"}`}>
                {both ? t("inCart") : t("bundleAdd")}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ kun tovari
type Deal = { id: number; ends_at: string; product: Card };

function useNow(tick = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), tick);
    return () => clearInterval(id);
  }, [tick]);
  return now;
}

/** Tugashigacha sanoq: kun (bo'lsa) va soat:daqiqa:soniya. */
export function Countdown({ until, onEnd }: { until: string; onEnd?: () => void }) {
  const { t } = useApp();
  const now = useNow();
  const left = Math.max(0, Math.floor((new Date(until).getTime() - now) / 1000));
  useEffect(() => {
    if (left === 0) onEnd?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [left === 0]);
  const two = (n: number) => String(n).padStart(2, "0");
  const days = Math.floor(left / 86400);
  const cells = [two(Math.floor((left % 86400) / 3600)), two(Math.floor((left % 3600) / 60)), two(left % 60)];
  return (
    <span className="inline-flex items-center gap-1 font-display text-sm font-bold tabular-nums" aria-label={t("dealEnds")}>
      {days > 0 ? <span className="mr-1 rounded-lg bg-white/20 px-2 py-1">{days} {t("dealDays")}</span> : null}
      {cells.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="min-w-[32px] rounded-lg bg-white/20 px-1.5 py-1 text-center">{c}</span>
          {i < 2 ? <span className="opacity-70">:</span> : null}
        </span>
      ))}
    </span>
  );
}

/** Bosh sahifa: hozir davom etayotgan vaqtli aksiyalar (bo'lmasa — hech narsa ko'rsatilmaydi). */
export function DealsStrip() {
  const { t, lang, addToCart, cart } = useApp();
  const [deals, setDeals] = useState<Deal[]>([]);
  const load = () => api<Deal[]>("/deals", { auth: false }).then(setDeals).catch(() => setDeals([]));
  useEffect(() => {
    load();
  }, [lang]);
  if (!deals.length) return null;
  return (
    <section className={`grid gap-3 md:gap-4 ${deals.length > 1 ? "lg:grid-cols-2" : ""}`}>
      {deals.slice(0, 4).map((d) => {
        const p = d.product;
        const inCart = cart?.items.some((i) => i.variant_id === p.variant_id);
        return (
          <div key={d.id} className="relative flex flex-col overflow-hidden rounded-[32px] text-white shadow-card sm:flex-row"
            style={{ background: "linear-gradient(125deg, #9f1239 0%, #e11d48 55%, #f59e0b 130%)" }}>
            <span className="tiles pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_left,black,transparent_70%)]" />
            <Link href={`/p/${p.slug}`} className="relative m-3 mb-0 aspect-[16/10] shrink-0 overflow-hidden rounded-3xl sm:m-4 sm:mr-0 sm:aspect-square sm:w-44 md:w-52">
              <ProductImage src={p.image} category={p.category_slug} seed={p.id} />
              {p.discount_percent > 0 ? <span className="absolute left-2 top-2 rounded-full bg-sale px-2.5 text-sm font-bold leading-7 text-white shadow">−{p.discount_percent}%</span> : null}
            </Link>
            <div className="relative flex min-w-0 flex-1 flex-col gap-3 p-5 md:p-6">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="rounded-full bg-white/20 px-3 py-1 text-sm font-semibold backdrop-blur">{t("dealTitle")}</span>
                <Countdown until={d.ends_at} onEnd={load} />
              </div>
              <Link href={`/p/${p.slug}`} className="line-clamp-2 font-display text-lg font-bold leading-snug md:text-[22px]">{p.name}</Link>
              <div className="mt-auto flex flex-wrap items-end justify-between gap-3">
                <div>
                  {p.old_price ? <p className="text-sm text-white/70 line-through">{formatMoney(p.old_price, lang)}</p> : null}
                  <p className="font-display text-2xl font-bold md:text-[28px]">{formatMoney(p.price, lang)}</p>
                </div>
                <button onClick={() => addToCart(p.variant_id)} disabled={p.stock_status === "out_of_stock"}
                  className="photo inline-flex h-12 items-center gap-2 rounded-full pl-5 pr-1.5 font-semibold text-zinc-900 shadow-lg transition active:scale-95 disabled:opacity-60">
                  {p.stock_status === "out_of_stock" ? t("outOfStock") : inCart ? t("inCart") : t("addToCart")}
                  <span className="grid h-9 w-9 place-items-center rounded-full bg-sale text-white"><IconChevron className="h-4 w-4" /></span>
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </section>
  );
}

// ------------------------------------------------------------------ savol-javob
type Question = { id: number; author: string; text: string; answer: string; answered_at: string | null; status: string; created_at: string };

/** Tovar sahifasi: savol-javob. Savol xodim javob bergach hammaga ko'rinadi. */
export function Questions({ slug }: { slug: string }) {
  const { t, lang, me, toast } = useApp();
  const [rows, setRows] = useState<Question[] | null>(null);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api<Question[]>(`/products/${slug}/questions`).then(setRows).catch(() => setRows([]));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, me?.id]);
  if (!rows) return null;
  const date = (v: string) => new Date(v).toLocaleDateString(lang === "ru" ? "ru-RU" : "uz-UZ");
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/products/${slug}/questions`, { method: "POST", body: { text, name } });
      toast(t("qaSent"));
      setText("");
      setOpen(false);
      await load();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t("error"), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <section id="savollar" className="scroll-mt-40">
      <SectionTitle title={t("qaTitle")} />
      <div className="space-y-3">
        {rows.length === 0 && !open ? <p className="rounded-3xl bg-white p-5 text-sm text-zinc-500 shadow-card">{t("qaEmpty")}</p> : null}
        {rows.map((q) => (
          <article key={q.id} className="rounded-3xl bg-white p-5 shadow-card">
            <p className="text-xs text-zinc-400">{q.author} · {date(q.created_at)}</p>
            <p className="mt-1 font-medium">{q.text}</p>
            {q.answer ? (
              <div className="mt-3 rounded-2xl bg-brand-light p-3.5 text-sm">
                <p className="mb-1 text-xs font-semibold text-brand">{t("qaAnswer")}</p>
                <p className="whitespace-pre-line text-ink">{q.answer}</p>
              </div>
            ) : <p className="mt-2 text-xs font-medium text-amber-700">{t("qaPending")}</p>}
          </article>
        ))}
        {open ? (
          <form onSubmit={send} className="animate-fade-up space-y-3 rounded-3xl bg-white p-5 shadow-card">
            {!me ? <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("qaName")} maxLength={80} className="w-full sm:max-w-xs" /> : null}
            <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={t("qaPlaceholder")} rows={3} maxLength={1000} autoFocus className="w-full" />
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || text.trim().length < 5}>{t("send")}</Button>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>{t("back")}</Button>
            </div>
          </form>
        ) : <Button variant="ghost" onClick={() => setOpen(true)}>{t("qaAsk")}</Button>}
      </div>
    </section>
  );
}
