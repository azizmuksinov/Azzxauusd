"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { IconCart, IconEye, IconMinus, IconPlus, IconShield, IconTruck } from "@/components/icons";
import { useApp } from "@/components/providers";
import { Button, ErrorBox, Grid, HeartButton, Panel, Price, ProductCard, ProductImage, Stars, StockBadge } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card, ProductDetail } from "@/lib/types";

function ProductSkeleton() {
  return (
    <div className="grid animate-pulse gap-8 lg:grid-cols-[1fr_400px]">
      <div className="aspect-square rounded-[2rem] bg-gray-200/70" />
      <div className="space-y-4">
        <div className="h-8 w-3/4 rounded-xl bg-gray-200/70" />
        <div className="h-40 rounded-3xl bg-gray-200/70" />
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
    <div className="space-y-10">
      <nav className="flex flex-wrap items-center gap-1 text-sm text-gray-500">
        <Link href="/" className="hover:text-brand">{t("shopName")}</Link>
        {p.category.map((c) => (
          <span key={c.slug} className="flex items-center gap-1">/ <Link href={`/c/${c.slug}`} className="hover:text-brand">{c.name}</Link></span>
        ))}
      </nav>

      <div className="grid gap-8 lg:grid-cols-[1fr_400px]">
        <div className="space-y-6">
          <div className="relative aspect-square overflow-hidden rounded-[2rem] ring-1 ring-gray-100 md:aspect-[4/3]">
            <ProductImage src={p.images[0]?.url ?? ""} category={category} seed={p.id} />
            {variant.discount_percent > 0 ? (
              <span className="absolute left-4 top-4 rounded-xl bg-rose-500 px-3 py-1 text-sm font-bold text-white">−{variant.discount_percent}%</span>
            ) : null}
            <HeartButton productId={p.id} className="absolute right-4 top-4 h-11 w-11" />
          </div>

          <Panel>
            <div className="mb-5 flex gap-2">
              {(["specs", "desc"] as const).map((k) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`rounded-2xl px-4 py-2 text-sm font-bold transition ${tab === k ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
                  {k === "specs" ? t("specs") : t("description")}
                </button>
              ))}
            </div>
            {tab === "specs" ? (
              <div className="grid gap-6 md:grid-cols-2">
                {p.attributes.map((g) => (
                  <div key={g.group}>
                    {g.group ? <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-gray-400">{g.group}</h3> : null}
                    <dl className="text-sm">
                      {g.items.map((i) => (
                        <div key={i.code} className="flex items-end gap-2 py-1.5">
                          <dt className="shrink-0 text-gray-500">{i.name}</dt>
                          <span className="mb-1 flex-1 border-b border-dotted border-gray-300" />
                          <dd className="text-right font-semibold">{i.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
                {p.model_code ? <p className="text-sm text-gray-500">{t("model")}: <b>{p.model_code}</b></p> : null}
              </div>
            ) : (
              <p className="leading-7 text-gray-700">{p.description || "—"}</p>
            )}
          </Panel>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-40 lg:self-start">
          <div>
            {p.brand ? <Link href={`/search?q=${encodeURIComponent(p.brand.name)}`} className="text-sm font-bold text-brand">{p.brand.name}</Link> : null}
            <h1 className="mt-1 text-2xl font-extrabold leading-tight md:text-3xl">{p.name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-3"><Stars value={p.rating_avg} count={p.rating_count} /><StockBadge status={variant.stock_status} /></div>
          </div>

          <Panel className="space-y-5">
            <Price price={variant.price} old={variant.old_price} size="lg" />
            {p.variants.length > 1 ? (
              <div>
                <p className="mb-2 text-sm font-semibold text-gray-500">{t("variant")}</p>
                <div className="flex flex-wrap gap-2">
                  {p.variants.map((v) => (
                    <button key={v.id} onClick={() => { setVariantId(v.id); setQty(1); }}
                      className={`rounded-2xl px-4 py-2.5 text-sm font-semibold ring-2 transition ${v.id === variant.id ? "bg-brand-light text-brand ring-brand" : "bg-white ring-gray-100 hover:ring-gray-300"} ${v.stock_status === "out_of_stock" ? "opacity-40" : ""}`}>
                      {v.name_suffix || v.sku}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="flex items-center gap-3">
              <div className="flex items-center rounded-2xl bg-gray-100">
                <button onClick={() => setQty((q) => Math.max(1, q - 1))} className="grid h-12 w-11 place-items-center" aria-label="-"><IconMinus className="h-5 w-5" /></button>
                <span className="w-8 text-center font-bold">{qty}</span>
                <button onClick={() => setQty((q) => q + 1)} className="grid h-12 w-11 place-items-center" aria-label="+"><IconPlus className="h-5 w-5" /></button>
              </div>
              <Button onClick={() => add(false)} disabled={busy || soldOut} className="flex-1">
                <IconCart className="h-5 w-5" /> {inCart ? `${t("inCart")} · ${inCart.qty}` : t("addToCart")}
              </Button>
            </div>
            <Button variant="dark" onClick={() => add(true)} disabled={busy || soldOut} className="w-full">{t("buyNow")}</Button>
          </Panel>

          <Panel className="space-y-4 text-sm">
            {[
              [IconTruck, t("delivery"), p.is_bulky ? `${t("bulky")}. ${t("deliveryInfo")}` : t("deliveryInfo")],
              [IconEye, t("benefitCheck"), t("checkAtDoor")],
              [IconShield, t("warranty"), `${p.warranty_months} ${t("months")} · ${t("benefitWarrantyText")}`],
            ].map(([Icon, title, text]) => {
              const I = Icon as typeof IconTruck;
              return (
                <div key={title as string} className="flex gap-3">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-brand-light text-brand"><I className="h-5 w-5" /></span>
                  <div><p className="font-bold">{title as string}</p><p className="text-gray-500">{text as string}</p></div>
                </div>
              );
            })}
          </Panel>
        </aside>
      </div>

      {similar.length > 0 ? (
        <section>
          <h2 className="mb-4 text-xl font-extrabold md:text-2xl">{t("similar")}</h2>
          <Grid>{similar.map((s) => <ProductCard key={s.id} p={s} />)}</Grid>
        </section>
      ) : null}
    </div>
  );
}
