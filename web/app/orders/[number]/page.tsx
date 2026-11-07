"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { Button, ErrorBox, Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { type Key, formatMoney, statusLabel } from "@/lib/i18n";
import type { Order } from "@/lib/types";

export default function OrderPage() {
  const { number } = useParams<{ number: string }>();
  const { t, lang, me } = useApp();
  const [o, setO] = useState<Order | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Order>(`/orders/${number}`).then(setO).catch((e) => setError(e.message));
  }, [number]);
  useEffect(() => {
    if (me) load();
  }, [me, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setMsg("");
    try {
      await fn();
      load();
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorBox message={error} />;
  if (!o) return <Loading />;
  const due = Number(o.amount_to_pay_online);
  const online = ["payme", "click", "uzum"];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{t("orderNumber")} № {o.number}</h1>
          <span className="rounded-md bg-surface px-2.5 py-1 text-sm font-medium">{statusLabel(lang, o.status)}</span>
        </div>
        <section className="divide-y rounded-xl bg-white border border-line">
          {o.items.map((i) => (
            <div key={i.id} className="flex justify-between gap-4 p-4 text-sm">
              <span>{i.name}{i.variant_name ? ` · ${i.variant_name}` : ""} × {i.qty}</span>
              <span className="font-semibold">{formatMoney(i.line_total, lang)}</span>
            </div>
          ))}
        </section>
        <section className="rounded-xl border border-line bg-white p-4 text-sm">
          <h2 className="mb-2 font-semibold">{t("address")}</h2>
          <p>{o.address_snapshot.street}, {o.address_snapshot.house}{o.address_snapshot.apartment ? `, ${o.address_snapshot.apartment}` : ""} · {t("floor")}: {o.address_snapshot.floor ?? "—"}</p>
          <p className="text-zinc-500">{o.recipient_name}, {o.recipient_phone} · {t("delivery")}: {o.delivery_eta_min}–{o.delivery_eta_max} {t("deliveryDays")}</p>
        </section>
        <section className="rounded-xl border border-line bg-white p-4 text-sm">
          <h2 className="mb-2 font-semibold">{t("history")}</h2>
          <ol className="space-y-1">
            {o.history.map((h, idx) => (
              <li key={idx}>
                <span className="text-zinc-400">{new Date(h.created_at).toLocaleString(lang === "ru" ? "ru-RU" : "uz-UZ")}</span> — {statusLabel(lang, h.to_status)}
              </li>
            ))}
          </ol>
        </section>
      </div>
      <aside className="h-fit space-y-3 rounded-xl bg-white p-5 border border-line">
        <div className="flex justify-between text-sm"><span>{t("subtotal")}</span><span>{formatMoney(o.subtotal, lang)}</span></div>
        <div className="flex justify-between text-sm"><span>{t("delivery")}</span><span>{formatMoney(o.delivery_fee, lang)}</span></div>
        <div className="flex justify-between border-t pt-3 text-lg font-bold"><span>{t("total")}</span><span>{formatMoney(o.total, lang)}</span></div>
        <div className="flex justify-between text-sm"><span>{t("payment")}</span><span>{t(o.payment_method as Key)}</span></div>
        {Number(o.paid_amount) > 0 ? <div className="flex justify-between text-sm text-green-700"><span>{t("paid")}</span><span>{formatMoney(o.paid_amount, lang)}</span></div> : null}
        {Number(o.refund_due) > 0 ? <div className="flex justify-between text-sm font-medium text-amber-700"><span>{t("refundDue")}</span><span>{formatMoney(o.refund_due, lang)}</span></div> : null}
        {Number(o.refunded_amount) > 0 ? <div className="flex justify-between text-sm"><span>{t("refunded")}</span><span>{formatMoney(o.refunded_amount, lang)}</span></div> : null}
        {Number(o.cod_amount) > 0 && !["delivered", "returned", "cancelled"].includes(o.status) ? <div className="flex justify-between text-sm"><span>{t("atDoor")}</span><span>{formatMoney(Number(o.cod_amount), lang)}</span></div> : null}
        {o.status === "created" && due > 0 ? (
          <div className="space-y-2 rounded-lg bg-surface p-3">
            <p className="text-sm">{t("payOnline")}: <b>{formatMoney(due, lang)}</b></p>
            {o.payment_deadline ? <p className="text-xs text-zinc-500">{t("deadline")}: {new Date(o.payment_deadline).toLocaleTimeString()}</p> : null}
            <Button className="w-full" disabled={busy} onClick={() => act(() => api(`/orders/${o.number}/demo-pay`, { method: "POST" }))}>
              {t("payDemo")}
            </Button>
            {online.includes(o.payment_method) ? (
              <Button variant="ghost" className="w-full" disabled={busy}
                onClick={() => act(async () => {
                  const r = await api<{ payment_url: string }>(`/orders/${o.number}/pay`, { method: "POST", body: { provider: o.payment_method, return_url: window.location.href } });
                  window.location.href = r.payment_url;
                })}>
                {t(o.payment_method as Key)} {t("payVia")}
              </Button>
            ) : null}
          </div>
        ) : null}
        {o.can_cancel ? (
          <Button variant="danger" className="w-full" disabled={busy}
            onClick={() => {
              const reason = window.prompt(t("cancelReason"));
              if (reason) act(() => api(`/orders/${o.number}/cancel`, { method: "POST", body: { reason } }));
            }}>
            {t("cancel")}
          </Button>
        ) : null}
        {msg ? <p className="text-sm text-red-600">{msg}</p> : null}
      </aside>
    </div>
  );
}
