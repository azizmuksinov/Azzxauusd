"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useApp } from "@/components/providers";
import { Button, ErrorBox, Grid, Loading, Price, ProductCard, ProductImage, StockBadge } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { Card, ProductDetail } from "@/lib/types";

export default function ProductPage() {
  const { slug } = useParams<{ slug: string }>();
  const { t, lang, reloadCart } = useApp();
  const [p, setP] = useState<ProductDetail | null>(null);
  const [similar, setSimilar] = useState<Card[]>([]);
  const [variantId, setVariantId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError("");
    api<ProductDetail>(`/products/${slug}`)
      .then((d) => {
        setP(d);
        setVariantId((v) => v ?? (d.variants.find((x) => x.stock_status !== "out_of_stock") ?? d.variants[0])?.id ?? null);
      })
      .catch((e) => setError(e.message));
    api<Card[]>(`/products/${slug}/similar`).then(setSimilar).catch(() => setSimilar([]));
  }, [slug, lang]);

  const variant = useMemo(() => p?.variants.find((v) => v.id === variantId) ?? null, [p, variantId]);

  if (error) return <ErrorBox message={error} />;
  if (!p || !variant) return <Loading />;

  const add = async () => {
    setBusy(true);
    setMsg("");
    try {
      await api("/cart/items", { method: "POST", body: { variant_id: variant.id, qty: 1 } });
      await reloadCart();
      setMsg(t("added"));
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-10">
      <nav className="text-sm text-gray-500">
        <Link href="/" className="hover:text-brand">⌂</Link>
        {p.category.map((c) => (
          <span key={c.slug}> / <Link href={`/c/${c.slug}`} className="hover:text-brand">{c.name}</Link></span>
        ))}
      </nav>
      <div className="grid gap-8 md:grid-cols-2">
        <div className="aspect-square overflow-hidden rounded-3xl bg-white shadow-sm">
          <ProductImage src={p.images[0]?.url ?? ""} category={p.category.at(-1)?.slug ?? ""} className="text-9xl" />
        </div>
        <div className="space-y-5">
          <div>
            {p.brand ? <Link href={`/search?q=${p.brand.name}`} className="text-sm font-semibold text-brand">{p.brand.name}</Link> : null}
            <h1 className="mt-1 text-2xl font-bold">{p.name}</h1>
            {p.model_code ? <p className="text-sm text-gray-400">{p.model_code}</p> : null}
          </div>
          {p.variants.length > 1 ? (
            <div>
              <p className="mb-2 text-sm text-gray-500">{t("variant")}</p>
              <div className="flex flex-wrap gap-2">
                {p.variants.map((v) => (
                  <button key={v.id} onClick={() => setVariantId(v.id)}
                    className={`rounded-xl px-4 py-2 text-sm ring-1 ${v.id === variant.id ? "bg-brand-light font-semibold text-brand ring-brand" : "bg-white ring-gray-200"} ${v.stock_status === "out_of_stock" ? "opacity-50" : ""}`}>
                    {v.name_suffix || v.sku}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="rounded-2xl bg-white p-5 shadow-sm">
            <Price price={variant.price} old={variant.old_price} size="lg" />
            {variant.discount_percent > 0 ? <span className="mt-1 inline-block rounded bg-red-50 px-2 text-sm text-red-600">−{variant.discount_percent}%</span> : null}
            <div className="mt-3"><StockBadge status={variant.stock_status} /></div>
            <Button onClick={add} disabled={busy || variant.stock_status === "out_of_stock"} className="mt-4 w-full">
              {t("addToCart")}
            </Button>
            {msg ? (
              <p className="mt-2 text-sm text-brand">
                {msg} · <Link href="/cart" className="underline">{t("cart")}</Link>
              </p>
            ) : null}
          </div>
          <ul className="space-y-1 text-sm text-gray-600">
            <li>🛡 {t("warranty")}: {p.warranty_months} {t("months")}</li>
            <li>📦 {t("doorCheck")}</li>
            {p.is_bulky ? <li>🚚 {t("bulky")}</li> : null}
          </ul>
        </div>
      </div>

      {p.attributes.length > 0 ? (
        <section className="rounded-2xl bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-xl font-bold">{t("specs")}</h2>
          <div className="grid gap-6 md:grid-cols-2">
            {p.attributes.map((g) => (
              <div key={g.group}>
                {g.group ? <h3 className="mb-2 font-semibold">{g.group}</h3> : null}
                <dl className="divide-y text-sm">
                  {g.items.map((i) => (
                    <div key={i.code} className="flex justify-between gap-4 py-2">
                      <dt className="text-gray-500">{i.name}</dt>
                      <dd className="text-right font-medium">{i.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
          {p.description ? <p className="mt-6 text-sm text-gray-600">{p.description}</p> : null}
        </section>
      ) : null}

      {similar.length > 0 ? (
        <section>
          <h2 className="mb-4 text-xl font-bold">{t("similar")}</h2>
          <Grid>{similar.map((s) => <ProductCard key={s.id} p={s} />)}</Grid>
        </section>
      ) : null}
    </div>
  );
}
