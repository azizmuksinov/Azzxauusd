"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { IconEye, IconMinus, IconPlus, IconShield, IconTruck } from "@/components/icons";
import { Gallery, RecentlyViewed, Reviews, rememberViewed } from "@/components/product-extras";
import { useApp } from "@/components/providers";
import { Button, ErrorBox, Grid, HeartButton, Panel, Price, ProductCard, Stars, StockBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card, ProductDetail } from "@/lib/types";

function ProductSkeleton() {
  return (
    <div className="grid animate-pulse gap-8 lg:grid-cols-[1fr_400px]">
      <div className="aspect-square rounded-2xl bg-surface" />
      <div className="space-y-4">
        <div className="h-8 w-3/4 rounded bg-surface" />
        <div className="h-40 rounded-xl bg-surface" />
      </div>
    </div>
  );
}

export default function ProductPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const { t, lang, addToCart, cart } = useApp();
  const [p, setP] = useState<ProductDetail | null>(null);
  const [similar, setSimilar] = useState<Card[]>([]);
  const [variantId, setVariantId] = useState<number | null>(null);
  const [qty, setQty] = useState(1);
  const [tab, setTab] = useState<"specs" | "desc">("specs");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="space-y-12">
      <nav className="flex flex-wrap items-center gap-1 text-[13px] text-zinc-500">
        <Link href="/" className="hover:text-ink">{t("shopName")}</Link>
        {p.category.map((c) => (
          <span key={c.slug} className="flex items-center gap-1">/ <Link href={`/c/${c.slug}`} className="hover:text-ink">{c.name}</Link></span>
        ))}
      </nav>

      <div className="grid gap-10 lg:grid-cols-[1fr_380px]">
        <div className="space-y-10">
          <Gallery images={p.images} video={p.video_url} category={category}>
            <HeartButton productId={p.id} className="absolute right-3 top-3 h-10 w-10" />
          </Gallery>

          <section>
            <div className="mb-5 flex gap-6 border-b border-line">
              {(["specs", "desc"] as const).map((k) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`-mb-px border-b-2 pb-2.5 text-[15px] font-medium transition ${tab === k ? "border-ink text-ink" : "border-transparent text-zinc-500 hover:text-ink"}`}>
                  {k === "specs" ? t("specs") : t("description")}
                </button>
              ))}
            </div>
            {tab === "specs" ? (
              <div className="grid gap-6 md:grid-cols-2">
                {p.attributes.map((g) => (
                  <div key={g.group}>
                    {g.group ? <h3 className="mb-2 text-[15px] font-semibold">{g.group}</h3> : null}
                    <dl className="text-sm">
                      {g.items.map((i) => (
                        <div key={i.code} className="flex items-end gap-2 py-1.5">
                          <dt className="shrink-0 text-zinc-500">{i.name}</dt>
                          <span className="mb-1 flex-1 border-b border-dotted border-zinc-300" />
                          <dd className="text-right">{i.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
                {p.model_code ? <p className="text-sm text-zinc-500">{t("model")}: <b>{p.model_code}</b></p> : null}
              </div>
            ) : (
              <p className="max-w-3xl whitespace-pre-line leading-7 text-zinc-700">{p.description || "—"}</p>
            )}
          </section>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-40 lg:self-start">
          <div>
            {p.brand ? <Link href={`/search?q=${encodeURIComponent(p.brand.name)}`} className="text-sm text-zinc-500 hover:text-ink">{p.brand.name}</Link> : null}
            <h1 className="mt-1 text-2xl font-bold leading-tight tracking-tight">{p.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3"><Stars value={p.rating_avg} count={p.rating_count} /><StockBadge status={variant.stock_status} /></div>
          </div>

          <Panel className="space-y-5">
            <Price price={variant.price} old={variant.old_price} size="lg" />
            {p.variants.length > 1 ? (
              <div>
                <p className="mb-2 text-sm text-zinc-500">{t("variant")}</p>
                <div className="flex flex-wrap gap-2">
                  {p.variants.map((v) => (
                    <button key={v.id} onClick={() => { setVariantId(v.id); setQty(1); }}
                      className={`rounded-lg border px-3.5 py-2 text-sm transition ${v.id === variant.id ? "border-ink" : "border-line hover:border-zinc-400"} ${v.stock_status === "out_of_stock" ? "text-zinc-400" : ""}`}>
                      {v.name_suffix || v.sku}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="flex items-center gap-3">
              <div className="flex h-11 items-center rounded-lg border border-line">
                <button onClick={() => setQty((q) => Math.max(1, q - 1))} className="grid h-full w-10 place-items-center text-zinc-500" aria-label="-"><IconMinus className="h-4 w-4" /></button>
                <span className="w-7 text-center font-medium">{qty}</span>
                <button onClick={() => setQty((q) => q + 1)} className="grid h-full w-10 place-items-center text-zinc-500" aria-label="+"><IconPlus className="h-4 w-4" /></button>
              </div>
              <Button onClick={() => add(false)} disabled={busy || soldOut} className="flex-1">
                {inCart ? `${t("inCart")} · ${inCart.qty}` : t("addToCart")}
              </Button>
            </div>
            <Button variant="ghost" onClick={() => add(true)} disabled={busy || soldOut} className="w-full">{t("buyNow")}</Button>
          </Panel>

          <div className="space-y-4 px-1 text-sm">
            {[
              [IconTruck, t("delivery"), p.is_bulky ? `${t("bulky")}. ${t("deliveryInfo")}` : t("deliveryInfo")],
              [IconEye, t("benefitCheck"), t("checkAtDoor")],
              [IconShield, t("warranty"), `${p.warranty_months} ${t("months")} · ${t("benefitWarrantyText")}`],
            ].map(([Icon, title, text]) => {
              const I = Icon as typeof IconTruck;
              return (
                <div key={title as string} className="flex gap-3">
                  <I className="mt-0.5 h-5 w-5 shrink-0 text-zinc-400" />
                  <div><p className="font-medium">{title as string}</p><p className="text-zinc-500">{text as string}</p></div>
                </div>
              );
            })}
          </div>
        </aside>
      </div>

      <Reviews slug={p.slug} />

      {similar.length > 0 ? (
        <section>
          <h2 className="mb-4 text-xl font-bold tracking-tight md:text-[22px]">{t("similar")}</h2>
          <Grid>{similar.map((s) => <ProductCard key={s.id} p={s} />)}</Grid>
        </section>
      ) : null}
      <RecentlyViewed exclude={p.id} />
    </div>
  );
}
