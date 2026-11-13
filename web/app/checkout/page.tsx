"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AddressForm } from "@/components/address-form";
import { IconBox, IconTruck } from "@/components/icons";
import { savePromo, savedPromo } from "@/components/promo";
import { useApp } from "@/components/providers";
import { Button, ErrorBox, Loading, useTitle } from "@/components/ui";
import { ApiError, api, uuid } from "@/lib/api";
import { type Key, formatMoney } from "@/lib/i18n";
import type { Address, Order, PickupPoint, Quote, Summary } from "@/lib/types";

type Mode = "delivery" | "pickup";
const CARD = "space-y-3 rounded-3xl bg-white p-5 border border-line";
const CHOICE = "flex cursor-pointer items-start gap-3 rounded-2xl p-4 ring-2 ring-gray-100 transition has-[:checked]:bg-brand-light/40 has-[:checked]:ring-brand";

export default function CheckoutPage() {
  const { t, lang, me, ready, cart, reloadCart } = useApp();
  useTitle(t("checkout"));
  const router = useRouter();
  const [addresses, setAddresses] = useState<Address[] | null>(null);
  const [addressId, setAddressId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [points, setPoints] = useState<PickupPoint[]>([]);
  const [pointId, setPointId] = useState<number | null>(null);
  const [mode, setMode] = useState<Mode>("delivery");
  const [name, setName] = useState("");
  const [useBonus, setUseBonus] = useState(false);
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
    setName(me.first_name || "");
    api<Address[]>("/me/addresses").then((list) => {
      setAddresses(list);
      setAddressId(list[0]?.id ?? null);
      setAdding(list.length === 0);
    });
    api<PickupPoint[]>("/pickup-points", { auth: false }).then((list) => {
      setPoints(list);
      setPointId(list[0]?.id ?? null);
    }).catch(() => setPoints([]));
  }, [me]);

  // Yakuniy summa: manzil (yetkazish narxi bilan) yoki olib ketish punkti bo'yicha.
  const calc = useCallback(async (m: Mode, id: number, bonus: boolean) => {
    setError("");
    setSummary(null);
    try {
      let body: Record<string, unknown>;
      if (m === "pickup") {
        setQuote(null);
        body = { pickup_point_id: id, use_bonus: bonus };
      } else {
        const q = await api<Quote>("/checkout/delivery-options", { method: "POST", body: { address_id: id } });
        setQuote(q);
        body = { address_id: id, quote_id: q.quote_id, use_bonus: bonus };
      }
      // Savatda kiritilgan promokod shu yerda qo'llanadi; yaroqsiz bo'lib qolgan bo'lsa — usiz hisoblanadi.
      let s: Summary;
      try {
        s = await api<Summary>("/checkout/summary", { method: "POST", body: { ...body, promo_code: savedPromo() } });
        setPromoNote("");
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "promo_invalid")) throw e;
        savePromo("");
        setPromoNote(e.message);
        s = await api<Summary>("/checkout/summary", { method: "POST", body });
      }
      setSummary(s);
      setMethod((cur) => (s.payment_methods.some((o) => o.code === cur && o.available) ? cur : s.payment_methods.find((o) => o.available)?.code || ""));
    } catch (e) {
      setQuote(null);
      setError(e instanceof ApiError ? (e.code === "delivery_unavailable" ? t("deliveryUnavailable") : e.message) : t("error"));
    }
  }, [t]);

  const target = mode === "pickup" ? pointId : addressId;
  useEffect(() => {
    if (target && cart?.items.length) calc(mode, target, useBonus);
  }, [mode, target, useBonus, calc, cart?.items.length, lang]);

  if (!ready || !me || addresses === null) return <Loading />;
  if (!cart || cart.items.length === 0) return <ErrorBox message={t("cartEmpty")} />;

  const place = async () => {
    if (!target || !summary) return;
    setBusy(true);
    setError("");
    try {
      const where = mode === "pickup"
        ? { pickup_point_id: pointId, recipient_name: name }
        : { address_id: addressId, quote_id: quote?.quote_id };
      const o = await api<Order>("/orders", {
        method: "POST",
        headers: { "Idempotency-Key": idemKey },
        body: { ...where, payment_method: method, comment, promo_code: summary.promo_code ?? "", use_bonus: useBonus },
      });
      savePromo("");
      await reloadCart();
      router.push(`/orders/${o.number}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("error"));
      if (e instanceof ApiError && ["quote_expired", "bonus_changed"].includes(e.code)) calc(mode, target, useBonus);
    } finally {
      setBusy(false);
    }
  };

  const option = summary?.payment_methods.find((o) => o.code === method);
  const pickup = mode === "pickup";
  const bundle = Number(summary?.bundle_discount ?? cart.bundle_discount);
  const promo = summary ? Number(summary.discount_total) - Number(summary.bundle_discount) : 0;
  const bonus = summary?.bonus;
  const payLabel = (code: string) => (pickup && code === "cash" ? t("pickupPay") : t(code as Key));

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="space-y-6">
        <h1 className="text-[26px] font-extrabold tracking-tight">{t("checkout")}</h1>

        {points.length > 0 ? (
          <section className={CARD}>
            <h2 className="font-bold">{t("receiveMethod")}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {([["delivery", IconTruck, t("byCourier"), ""], ["pickup", IconBox, t("byPickup"), t("free")]] as const).map(([m, Icon, label, note]) => (
                <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
                  className={`flex items-center gap-3 rounded-2xl p-4 text-left ring-2 transition ${mode === m ? "bg-brand-light/40 ring-brand" : "ring-gray-100 hover:ring-line"}`}>
                  <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${mode === m ? "bg-brand text-white" : "bg-surface text-zinc-500"}`}><Icon className="h-5 w-5" /></span>
                  <span className="font-semibold">{label}{note ? <span className="block text-sm font-medium text-brand">{note}</span> : null}</span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        {pickup ? (
          <section className={CARD}>
            <h2 className="font-bold">{t("pickupPoint")}</h2>
            {points.map((p) => (
              <label key={p.id} className={CHOICE}>
                <input type="radio" name="point" checked={pointId === p.id} onChange={() => setPointId(p.id)} className="mt-1" />
                <span className="text-sm">
                  <b>{p.name}</b>
                  <span className="block">{p.address}{p.landmark ? ` · ${p.landmark}` : ""}</span>
                  <span className="block text-zinc-500">{[p.hours ? `${t("workHours")}: ${p.hours}` : "", p.phone].filter(Boolean).join(" · ")}</span>
                </span>
              </label>
            ))}
            <label className="block">{t("recipient")}
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={128} className="mt-1 block w-full sm:max-w-sm" />
            </label>
            <p className="text-sm text-zinc-500">{me.phone}</p>
          </section>
        ) : (
          <section className={CARD}>
            <h2 className="font-bold">{t("address")}</h2>
            {addresses.map((a) => (
              <label key={a.id} className={CHOICE}>
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
        )}

        {summary ? (
          <section className={CARD}>
            <h2 className="font-bold">{t("payment")}</h2>
            {summary.payment_methods.map((o) => (
              <label key={o.code} className={`${CHOICE} ${o.available ? "" : "!cursor-default opacity-50"}`}>
                <input type="radio" name="pay" disabled={!o.available} checked={method === o.code} onChange={() => setMethod(o.code)} className="mt-1" />
                <span className="text-sm">
                  <b>{payLabel(o.code)}</b>
                  {Number(o.required_prepayment) > 0 && Number(o.required_prepayment) < Number(summary.total) ? (
                    <span className="block text-zinc-500">{t("prepay")}: {formatMoney(o.required_prepayment, lang)} · {pickup ? t("atPickup") : t("atDoor")}: {formatMoney(Number(summary.total) - Number(o.required_prepayment), lang)}</span>
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
          <span>{pickup ? t("byPickup") : `${t("delivery")}${quote ? ` (${quote.eta_days_min}–${quote.eta_days_max} ${t("deliveryDays")})` : ""}`}</span>
          <span>{pickup ? t("free") : quote ? formatMoney(quote.delivery_price, lang) : "—"}</span>
        </div>
        {bundle > 0 ? (
          <div className="flex justify-between text-sm text-sale"><span>{t("bundleDiscount")}</span><span>−{formatMoney(bundle, lang)}</span></div>
        ) : null}
        {promo > 0 ? (
          <div className="flex justify-between text-sm text-sale">
            <span>{t("promoDiscount")} ({summary?.promo_code})</span><span>−{formatMoney(promo, lang)}</span>
          </div>
        ) : null}
        {promoNote ? <p className="text-xs text-amber-700">{t("promoDropped")}: {promoNote}</p> : null}
        {bonus?.enabled && Number(bonus.balance) > 0 ? (
          <label className="flex cursor-pointer items-start gap-2.5 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">
            <input type="checkbox" checked={useBonus} onChange={(e) => setUseBonus(e.target.checked)} className="mt-0.5" />
            <span>
              <b>{t("payWithBonus")}</b>
              <span className="block text-xs">{t("bonusBalance")}: {formatMoney(bonus.balance, lang)} · −{formatMoney(useBonus ? summary!.bonus_spent : bonus.usable, lang)}</span>
            </span>
          </label>
        ) : null}
        {summary && Number(summary.bonus_spent) > 0 ? (
          <div className="flex justify-between text-sm text-amber-700"><span>{t("bonusSpent")}</span><span>−{formatMoney(summary.bonus_spent, lang)}</span></div>
        ) : null}
        <div className="flex justify-between border-t border-line pt-3 text-lg font-bold"><span>{t("total")}</span><span>{summary ? formatMoney(summary.total, lang) : "—"}</span></div>
        {bonus?.enabled && Number(bonus.will_earn) > 0 ? (
          <p className="text-xs text-zinc-500">{t("bonusWillEarn")}: <b className="text-amber-700">+{formatMoney(bonus.will_earn, lang)}</b></p>
        ) : null}
        {option && Number(option.required_prepayment) > 0 ? (
          <p className="rounded-2xl bg-brand-light p-3 text-sm text-brand">{t("payOnline")}: <b>{formatMoney(option.required_prepayment, lang)}</b></p>
        ) : null}
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <Button className="w-full" disabled={busy || !summary || !method} onClick={place}>{t("placeOrder")}</Button>
      </aside>
    </div>
  );
}
