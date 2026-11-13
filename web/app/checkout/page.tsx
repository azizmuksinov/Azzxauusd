"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AddressForm } from "@/components/address-form";
import { useApp } from "@/components/providers";
import { Button, ErrorBox, Loading, useTitle } from "@/components/ui";
import { ApiError, api, uuid } from "@/lib/api";
import { savePromo, savedPromo } from "@/components/promo";
import { type Key, formatMoney } from "@/lib/i18n";
import type { Address, Order, Quote, Summary } from "@/lib/types";

export default function CheckoutPage() {
  const { t, lang, me, ready, cart, reloadCart } = useApp();
  useTitle(t("checkout"));
  const router = useRouter();
  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [addressId, setAddressId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [method, setMethod] = useState("");
  const [comment, setComment] = useState("");
  const [promoNote, setPromoNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [idemKey] = useState(uuid);

  useEffect(() => {
    if (ready && !me) router.replace("/login?next=/checkout");
  }, [ready, me, router]);

  useEffect(() => {
    if (!me) return;
    api<Address[]>("/me/addresses").then((list) => {
      setAddresses(list);
      setAddressId(list[0]?.id ?? null);
      setAdding(list.length === 0);
    });
  }, [me]);

  const calc = useCallback(async (id: number) => {
    setError("");
    setQuote(null);
    setSummary(null);
    try {
      const q = await api<Quote>("/checkout/delivery-options", { method: "POST", body: { address_id: id } });
      setQuote(q);
      // Savatda kiritilgan promokod shu yerda qo'llanadi; yaroqsiz bo'lib qolgan bo'lsa — usiz hisoblanadi.
      const body = { address_id: id, quote_id: q.quote_id };
      let s: Summary;
      const code = savedPromo();
      try {
        s = await api<Summary>("/checkout/summary", { method: "POST", body: { ...body, promo_code: code } });
        setPromoNote("");
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "promo_invalid")) throw e;
        savePromo("");
        setPromoNote(e.message);
        s = await api<Summary>("/checkout/summary", { method: "POST", body });
      }
      setSummary(s);
      setMethod((m) => m || s.payment_methods.find((o) => o.available)?.code || "");
    } catch (e) {
      setError(e instanceof ApiError ? (e.code === "delivery_unavailable" ? t("deliveryUnavailable") : e.message) : t("error"));
    }
  }, [t]);

  useEffect(() => {
    if (addressId && cart?.items.length) calc(addressId);
  }, [addressId, calc, cart?.items.length, lang]);

  if (!ready || !me || addresses === null) return <Loading />;
  if (!cart || cart.items.length === 0) return <ErrorBox message={t("cartEmpty")} />;

  const place = async () => {
    if (!quote || !addressId) return;
    setBusy(true);
    setError("");
    try {
      const o = await api<Order>("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": idemKey },
        body: { address_id: addressId, quote_id: quote.quote_id, payment_method: method, comment, promo_code: summary?.promo_code ?? "" },
      });
      savePromo("");
      await reloadCart();
      router.push(`/orders/${o.number}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("error"));
      if (e instanceof ApiError && e.code === "quote_expired") calc(addressId);
    } finally {
      setBusy(false);
    }
  };

  const option = summary?.payment_methods.find((o) => o.code === method);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">{t("checkout")}</h1>
        <section className="space-y-3 rounded-3xl bg-white p-5 border border-line">
          <h2 className="font-bold">{t("address")}</h2>
          {addresses.map((a) => (
            <label key={a.id} className="flex cursor-pointer items-start gap-3 rounded-2xl p-4 ring-2 ring-gray-100 transition has-[:checked]:bg-brand-light/40 has-[:checked]:ring-brand">
              <input type="radio" name="addr" checked={addressId === a.id} onChange={() => setAddressId(a.id)} className="mt-1" />
              <span className="text-sm">
                {a.street}, {a.house}{a.apartment ? `, ${a.apartment}` : ""} · {t("floor")}: {a.floor ?? "—"}
                <br /><span className="text-zinc-500">{a.recipient_name}, {a.recipient_phone}</span>
              </span>
            </label>
          ))}
          {adding ? (
            <AddressForm defaultPhone={me.phone} onSaved={(a) => { setAddresses((l) => [a, ...(l ?? [])]); setAddressId(a.id); setAdding(false); }} />
          ) : (
            <button onClick={() => setAdding(true)} className="text-sm font-semibold text-brand">+ {t("newAddress")}</button>
          )}
        </section>

        {summary ? (
          <section className="space-y-3 rounded-3xl bg-white p-5 border border-line">
            <h2 className="font-bold">{t("payment")}</h2>
            {summary.payment_methods.map((o) => (
              <label key={o.code} className={`flex items-start gap-3 rounded-2xl p-4 ring-2 ring-gray-100 transition has-[:checked]:bg-brand-light/40 has-[:checked]:ring-brand ${o.available ? "cursor-pointer" : "opacity-50"}`}>
                <input type="radio" name="pay" disabled={!o.available} checked={method === o.code} onChange={() => setMethod(o.code)} className="mt-1" />
                <span className="text-sm">
                  <b>{t(o.code as Key)}</b>
                  {Number(o.required_prepayment) > 0 && Number(o.required_prepayment) < Number(summary.total) ? (
                    <span className="block text-zinc-500">{t("prepay")}: {formatMoney(o.required_prepayment, lang)} · {t("atDoor")}: {formatMoney(Number(summary.total) - Number(o.required_prepayment), lang)}</span>
                  ) : null}
                </span>
              </label>
            ))}
            <label className="block">{t("comment")}
              <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} className="mt-1 w-full" />
            </label>
          </section>
        ) : null}
      </div>

      <aside className="h-fit space-y-3 rounded-3xl bg-white p-5 border border-line lg:sticky lg:top-44">
        <div className="flex justify-between text-sm"><span>{t("subtotal")}</span><span>{formatMoney(cart.subtotal, lang)}</span></div>
        <div className="flex justify-between text-sm">
          <span>{t("delivery")}{quote ? ` (${quote.eta_days_min}–${quote.eta_days_max} ${t("deliveryDays")})` : ""}</span>
          <span>{quote ? formatMoney(quote.delivery_price, lang) : "—"}</span>
        </div>
        {summary && Number(summary.discount_total) > 0 ? (
          <div className="flex justify-between text-sm text-sale">
            <span>{t("promoDiscount")} ({summary.promo_code})</span><span>−{formatMoney(summary.discount_total, lang)}</span>
          </div>
        ) : null}
        {promoNote ? <p className="text-xs text-amber-700">{t("promoDropped")}: {promoNote}</p> : null}
        <div className="flex justify-between border-t border-line pt-3 text-lg font-bold"><span>{t("total")}</span><span>{summary ? formatMoney(summary.total, lang) : "—"}</span></div>
        {option && Number(option.required_prepayment) > 0 ? (
          <p className="rounded-2xl bg-brand-light p-3 text-sm text-brand">{t("payOnline")}: <b>{formatMoney(option.required_prepayment, lang)}</b></p>
        ) : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <Button className="w-full" disabled={busy || !summary || !method} onClick={place}>{t("placeOrder")}</Button>
      </aside>
    </div>
  );
}
