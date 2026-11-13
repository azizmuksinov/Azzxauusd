"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { CompareButton } from "@/components/compare";
import { IconEye, IconMinus, IconPlus, IconShare, IconShield, IconTruck } from "@/components/icons";
import { Star8 } from "@/components/illustrations-star";
import { Gallery, RecentlyViewed, Reviews, rememberViewed } from "@/components/product-extras";
import { Installments, LeadButton } from "@/components/buy-extras";
import { useApp } from "@/components/providers";
import { Button, ErrorBox, Grid, HeartButton, Price, ProductCard, SectionTitle, Stars, StockBadge, useTitle } from "@/components/ui";
import { formatMoney } from "@/lib/i18n";
import { api } from "@/lib/api";
import type { Card, ProductDetail } from "@/lib/types";

function ProductSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_400px]">
      <div className="skeleton aspect-square rounded-[28px] lg:aspect-auto lg:h-[500px]" />
      <div className="space-y-4">
        <div className="skeleton h-8 w-3/4 rounded-full" />
        <div className="skeleton h-72 rounded-[28px]" />
      </div>
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { t, lang, addToCart, cart, toast } = useApp();
  const [p, setP] = useState<ProductDetail | null>(null);
  const [similar, setSimilar] = useState<Card[]>([]);
  const [variantId, setVariantId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [tab, setTab] = useState<"specs" | "desc">("specs");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Telefonda asosiy "Savatga" tugmasi ekrandan chiqib ketsa — pastda xarid qatori ko'rinadi.
  const buyRef = useRef<HTMLDivElement>(null);
  const [buyVisible, setBuyVisible] = useState(true);
  useTitle(p?.name);
  useEffect(() => {
    const el = buyRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setBuyVisible(e.isIntersecting), { threshold: 0.2 });
    io.observe(el);
    return () => io.disconnect();
  }, [p?.id]);

  useEffect(() => {
    setError("");
    api<ProductDetail>(`/products/${slug}`)
      .then((d) => {
        setP(d);
        const { description: _d, attributes: _a, variants: _v, images: _i, category: _c, ...card } = d;
        rememberViewed({ ...card, image: d.images[0]?.url ?? "", category_slug: d.category.at(-1)?.slug ?? "" } as Card);
        setVariantId((v) => (v && d.variants.some((x) => x.id === v) ? v : (d.variants.find((x) => x.stock_status !== "out_of_stock") ?? d.variants[0])?.id ?? null));
      })
      .catch((e) => setError(e.message));
    api<Card[]>(`/products/${slug}/similar`).then(setSimilar).catch(() => setSimilar([]));
  }, [slug, lang]);

  const variant = useMemo(() => p?.variants.find((v) => v.id === variantId) ?? null, [p, variantId]);
  if (error) return <ErrorBox message={error} />;
  if (!p || !variant) return <ProductSkeleton />;

  const category = p.category.at(-1)?.slug ?? "";
  const inCart = cart?.items.find((i) => i.variant_id === variant.id);
  const soldOut = variant.stock_status === "out_of_stock";
  const add = async (thenCheckout = false) => {
    setBusy(true);
    const ok = await addToCart(variant.id, qty);
    setBusy(false);
    if (ok && thenCheckout) router.push("/cart");
  };
  const share = async () => {
    const data = { title: p.name, url: window.location.href };
    try {
      if (navigator.share) return await navigator.share(data);
      await navigator.clipboard.writeText(data.url);
      toast(t("linkCopied"));
    } catch {
      /* foydalanuvchi ulashishni bekor qildi */
    }
  };

  return (
    <div className="space-y-6 md:space-y-10">
      <nav className="no-scrollbar -mx-4 flex items-center gap-1.5 overflow-x-auto whitespace-nowrap px-4 text-[13px] text-zinc-500 md:mx-0 md:px-0">
        <Link href="/" className="hover:text-brand">{t("shopName")}</Link>
        {p.category.map((c) => (
          <span key={c.slug} className="flex items-center gap-1.5"><span className="text-zinc-300">/</span><Link href={`/c/${c.slug}`} className="hover:text-brand">{c.name}</Link></span>
        ))}
      </nav>

      <div className="grid gap-x-8 gap-y-6 lg:grid-cols-[1fr_400px] lg:grid-rows-[auto_1fr]">
        <div className="min-w-0 lg:col-start-1 lg:row-start-1">
          <Gallery images={p.images} video={p.video_url} category={category}>
            <HeartButton productId={p.id} className="absolute right-3 top-3 h-11 w-11 rounded-full bg-white/90 shadow-card ring-1 ring-black/5" />
            <CompareButton productId={p.id} className="absolute right-3 top-[64px] !h-11 !w-11 rounded-full bg-white/90 shadow-card ring-1 ring-black/5" />
            {variant.old_price ? (
              <span className="absolute left-4 top-4 rounded-full bg-sale px-3 py-1 text-sm font-bold text-white">
                −{Math.round((1 - Number(variant.price) / Number(variant.old_price)) * 100)}%
              </span>
            ) : null}
          </Gallery>
        </div>

        <section className="min-w-0 self-start rounded-[28px] bg-white p-4 shadow-card md:p-6 lg:col-start-1 lg:row-start-2">
          <div className="mb-5 inline-flex rounded-full bg-surface p-1">
            {(["specs", "desc"] as const).map((k) => (
              <button key={k} onClick={() => setTab(k)}
                className={`h-10 rounded-full px-5 text-[15px] font-semibold transition ${tab === k ? "bg-brand text-white" : "text-zinc-500 hover:text-ink"}`}>
                {k === "specs" ? t("specs") : t("description")}
              </button>
            ))}
          </div>
          {tab === "specs" ? (
            <div className="grid gap-x-8 gap-y-6 md:grid-cols-2">
              {p.attributes.map((g) => (
                <div key={g.group}>
                  {g.group ? <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold"><Star8 className="h-4 w-4 text-brand" filled />{g.group}</h3> : null}
                  <dl className="text-sm">
                    {g.items.map((i) => (
                      <div key={i.code} className="flex items-start justify-between gap-4 rounded-xl px-3 py-2 odd:bg-surface/70">
                        <dt className="text-zinc-500">{i.name}</dt>
                        <dd className="text-right font-medium">{i.value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
              {p.model_code ? <p className="px-3 text-sm text-zinc-500">{t("model")}: <b className="text-ink">{p.model_code}</b></p> : null}
            </div>
          ) : (
            <p className="max-w-3xl whitespace-pre-line leading-7 text-zinc-700">{p.description || "—"}</p>
          )}
        </section>

        <aside className="row-start-2 space-y-4 lg:sticky lg:top-44 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start">
          <div className="rounded-[28px] bg-white p-5 shadow-card md:p-6">
            <div className="flex items-center gap-2">
              {p.brand ? <Link href={`/search?q=${encodeURIComponent(p.brand.name)}`} className="inline-flex rounded-full bg-brand-light px-3 py-1 text-[13px] font-semibold text-brand transition hover:bg-brand hover:text-white">{p.brand.name}</Link> : null}
              <StockBadge status={variant.stock_status} />
              <button onClick={share} aria-label={t("share")} title={t("share")}
                className="ml-auto grid h-10 w-10 place-items-center rounded-full bg-surface text-zinc-500 transition hover:bg-brand-light hover:text-brand">
                <IconShare className="h-[18px] w-[18px]" />
              </button>
            </div>
            <h1 className="mt-3 text-[22px] font-bold leading-snug tracking-tight md:text-2xl">{p.name}</h1>
            <a href="#sharhlar" className="mt-2 inline-flex hover:opacity-80"><Stars value={p.rating_avg} count={p.rating_count} /></a>

            <div className="mt-5 space-y-5 border-t border-line pt-5">
              <Price price={variant.price} old={variant.old_price} size="lg" />
              <Installments price={variant.price} />
              {p.variants.length > 1 ? (
                <div>
                  <p className="mb-2 text-sm text-zinc-500">{t("variant")}</p>
                  <div className="flex flex-wrap gap-2">
                    {p.variants.map((v) => (
                      <button key={v.id} onClick={() => { setVariantId(v.id); setQty(1); }}
                        className={`rounded-full border-2 px-4 py-2 text-sm font-medium transition ${v.id === variant.id ? "border-brand bg-brand-light text-brand" : "border-line hover:border-zinc-400"} ${v.stock_status === "out_of_stock" ? "text-zinc-400 line-through" : ""}`}>
                        {v.name_suffix || v.sku}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              <div ref={buyRef} className="flex items-center gap-2.5">
                <div className="flex h-12 items-center rounded-full bg-surface px-1">
                  <button onClick={() => setQty((q) => Math.max(1, q - 1))} className="grid h-10 w-10 place-items-center rounded-full text-zinc-500 transition hover:bg-white hover:text-ink" aria-label="-"><IconMinus className="h-4 w-4" /></button>
                  <span className="w-7 text-center font-semibold">{qty}</span>
                  <button onClick={() => setQty((q) => q + 1)} className="grid h-10 w-10 place-items-center rounded-full text-zinc-500 transition hover:bg-white hover:text-ink" aria-label="+"><IconPlus className="h-4 w-4" /></button>
                </div>
                <Button onClick={() => add(false)} disabled={busy || soldOut} className="flex-1">
                  {inCart ? `${t("inCart")} · ${inCart.qty}` : t("addToCart")}
                </Button>
              </div>
              <Button variant="ghost" onClick={() => add(true)} disabled={busy || soldOut} className="w-full">{t("buyNow")}</Button>
              {/* Tovar bor — telefon qoldirib tez buyurtma; tugagan — kelganda xabar berish. */}
              <LeadButton kind={soldOut ? "stock" : "quick"} variantId={variant.id} qty={qty} />
            </div>
          </div>

          <div className="divide-y divide-line rounded-[28px] bg-white px-5 text-sm shadow-card">
            {[
              [IconTruck, t("delivery"), p.is_bulky ? `${t("bulky")}. ${t("deliveryInfo")}` : t("deliveryInfo")],
              [IconEye, t("benefitCheck"), t("checkAtDoor")],
              [IconShield, t("warranty"), `${p.warranty_months} ${t("months")} · ${t("benefitWarrantyText")}`],
            ].map(([Icon, title, text]) => {
              const I = Icon as typeof IconTruck;
              return (
                <div key={title as string} className="flex gap-3.5 py-4">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-brand-light text-brand"><I className="h-5 w-5" /></span>
                  <div className="min-w-0"><p className="font-semibold">{title as string}</p><p className="mt-0.5 text-zinc-500">{text as string}</p></div>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      <div id="sharhlar" className="scroll-mt-40"><Reviews slug={p.slug} /></div>

      {similar.length > 0 ? (
        <section>
          <SectionTitle title={t("similar")} />
          <Grid>{similar.map((s) => <ProductCard key={s.id} p={s} />)}</Grid>
        </section>
      ) : null}
      <RecentlyViewed exclude={p.id} />

      {/* Telefon: pastki menyu ustida doim ko'rinadigan narx va "Savatga" */}
      {!buyVisible ? (
        <div className="fixed inset-x-3 bottom-[calc(86px+env(safe-area-inset-bottom))] z-30 flex animate-fade-up items-center gap-3 rounded-[24px] bg-white/95 py-2 pl-4 pr-2 shadow-dock ring-1 ring-black/5 backdrop-blur-xl md:hidden">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-zinc-500">{p.name}</p>
            <p className={`text-lg font-bold leading-6 ${variant.old_price ? "text-sale" : ""}`}>{formatMoney(variant.price, lang)}</p>
          </div>
          <Button onClick={() => add(false)} disabled={busy || soldOut} className="shrink-0 px-6">
            {soldOut ? t("outOfStock") : inCart ? `${t("inCart")} · ${inCart.qty}` : t("addToCart")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
