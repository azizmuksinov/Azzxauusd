"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PromoBox, usePromo } from "@/components/promo";
import { useApp } from "@/components/providers";
import { Button, Loading, Price, ProductImage, useTitle } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";

export default function CartPage() {
  const { t, lang, cart, ready, reloadCart, me } = useApp();
  useTitle(t("cart"));
  const router = useRouter();
  const [error, setError] = useState("");
  const promo = usePromo(cart?.items.length ? cart.subtotal : undefined);

  if (!ready) return <Loading />;
  if (!cart || cart.items.length === 0) {
    return (
      <div className="rounded-2xl bg-white py-16 text-center border border-line">
        <p className="text-5xl">🛒</p>
        <p className="mt-3 text-lg">{t("cartEmpty")}</p>
        <Link href="/" className="mt-4 inline-block font-semibold text-brand">{t("goShopping")}</Link>
      </div>
    );
  }

  const change = async (id: number, qty: number) => {
    setError("");
    try {
      if (qty <= 0) await api(`/cart/items/${id}`, { method: "DELETE" });
      else await api(`/cart/items/${id}`, { method: "PATCH", body: { qty } });
      await reloadCart();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("error"));
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <section className="space-y-3">
        <h1 className="text-2xl font-bold tracking-tight">{t("cart")}</h1>
        {error ? <p className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        {cart.items.map((i) => (
          <div key={i.id} className="flex gap-4 rounded-xl bg-white p-4 border border-line">
            <Link href={`/p/${i.product.slug}`} className="h-28 w-28 shrink-0 overflow-hidden rounded-2xl">
              <ProductImage src={i.image} category={i.product.category_slug} seed={i.product.id} />
            </Link>
            <div className="flex flex-1 flex-col gap-1">
              <Link href={`/p/${i.product.slug}`} className="font-medium hover:text-brand">
                {i.product.name} {i.name_suffix ? <span className="text-zinc-500">· {i.name_suffix}</span> : null}
              </Link>
              <Price price={i.unit_price} old={i.old_price} />
              {i.problem ? (
                <span className="text-sm text-red-600">
                  {i.problem === "unavailable" ? t("problemUnavailable") : `${t("problemStock")} (${i.max_qty})`}
                </span>
              ) : null}
              <div className="mt-auto flex items-center gap-3">
                <div className="flex items-center rounded-2xl bg-surface">
                  <button onClick={() => change(i.id, i.qty - 1)} className="px-3 py-1 text-lg">−</button>
                  <span className="w-8 text-center">{i.qty}</span>
                  <button onClick={() => change(i.id, i.qty + 1)} disabled={i.qty >= i.max_qty} className="px-3 py-1 text-lg disabled:opacity-30">+</button>
                </div>
                <button onClick={() => change(i.id, 0)} className="text-sm text-zinc-400 hover:text-red-600">{t("remove")}</button>
              </div>
            </div>
            <div className="hidden text-right font-bold sm:block">{formatMoney(i.line_total, lang)}</div>
          </div>
        ))}
      </section>
      <aside className="h-fit space-y-4 rounded-xl bg-white p-5 border border-line lg:sticky lg:top-28">
        <div className="flex justify-between text-sm">
          <span>{t("subtotal")} ({cart.items_count})</span>
          <span>{formatMoney(cart.subtotal, lang)}</span>
        </div>
        <PromoBox promo={promo} />
        {promo.discount > 0 ? (
          <div className="flex justify-between text-sm text-sale">
            <span>{t("promoDiscount")}</span>
            <span>−{formatMoney(promo.discount, lang)}</span>
          </div>
        ) : null}
        <div className="flex justify-between text-lg font-bold">
          <span>{t("total")}</span>
          <span>{formatMoney(Number(cart.subtotal) - promo.discount, lang)}</span>
        </div>
        <p className="text-xs text-zinc-500">+ {t("delivery")}</p>
        <Button className="w-full" disabled={!cart.can_checkout}
          onClick={() => router.push(me ? "/checkout" : "/login?next=/checkout")}>
          {t("checkout")}
        </Button>
      </aside>
    </div>
  );
}
