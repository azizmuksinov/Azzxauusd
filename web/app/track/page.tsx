"use client";

import { useState } from "react";

import { useApp } from "@/components/providers";
import { Button, useTitle } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatMoney, shortDate, statusLabel } from "@/lib/i18n";

type Tracked = {
  number: string; status: string; payment_status: string; total: string; is_pickup: boolean;
  pickup: { name: string; address: string; landmark: string; hours: string; phone: string } | null;
  delivery_eta_min: number; delivery_eta_max: number;
  items: { name: string; qty: number }[]; history: { status: string; at: string }[]; created_at: string;
};

// Xaridor ko'radigan asosiy bosqichlar (oraliq holatlar eng yaqin bosqichga birlashtiriladi).
const STEPS: [string, string[]][] = [
  ["created", ["created"]],
  ["cod_confirmed", ["paid", "cod_confirmed"]],
  ["picking", ["picking"]],
  ["packed", ["packed"]],
  ["out_for_delivery", ["handed_to_courier", "in_transit", "out_for_delivery"]],
  ["delivered", ["delivered"]],
];
const FAILED = ["cancelled", "refused_at_door", "returned"];

/** Buyurtmani tizimga kirmasdan kuzatish: raqam + telefon. */
export default function TrackPage() {
  const { t, lang, me } = useApp();
  useTitle(t("trackTitle"));
  const [number, setNumber] = useState("");
  const [phone, setPhone] = useState(me?.phone ?? "+998 ");
  const [o, setO] = useState<Tracked | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const find = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setO(null);
    try {
      setO(await api<Tracked>("/orders/track", { method: "POST", body: { number: number.trim(), phone }, auth: false }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  };
  const when = (v: string) => shortDate(v, lang, true);
  const steps = o ? STEPS.filter(([key]) => !(o.is_pickup && key === "out_for_delivery")) : [];
  const reached = o ? steps.reduce((acc, [, codes], i) => (codes.includes(o.status) ? i : acc), 0) : 0;
  const failed = o ? FAILED.includes(o.status) : false;

  return (
    <div className="mx-auto max-w-xl space-y-5 py-2 md:py-6">
      <form onSubmit={find} className="space-y-4 rounded-[32px] bg-white p-6 shadow-card md:p-8">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">{t("trackTitle")}</h1>
          <p className="mt-1 text-sm text-zinc-500">{t("trackHint")}</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">{t("trackNumber")}
            <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="26-0000123" autoFocus className="mt-1 w-full text-lg" />
          </label>
          <label className="block">{t("phone")}
            <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" className="mt-1 w-full text-lg" />
          </label>
        </div>
        {error ? <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        <Button type="submit" disabled={busy || !number.trim() || phone.replace(/\D/g, "").length < 9} className="w-full">{t("trackFind")}</Button>
      </form>

      {o ? (
        <div className="animate-fade-up space-y-4 rounded-[32px] bg-white p-6 shadow-card md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-lg font-bold">{t("orderNumber")} № {o.number}</p>
            <span className={`rounded-full px-3 py-1 text-sm font-semibold ${failed ? "bg-red-50 text-red-700" : "bg-brand-light text-brand"}`}>{statusLabel(lang, o.status, o.is_pickup)}</span>
          </div>
          {!failed ? (
            <ol className="space-y-0">
              {steps.map(([key], i) => {
                const done = i <= reached;
                const at = o.history.find((h) => STEPS.find(([k]) => k === key)![1].includes(h.status))?.at;
                return (
                  <li key={key} className="flex gap-3">
                    <span className="flex flex-col items-center">
                      <span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${done ? "bg-brand text-white" : "bg-surface text-zinc-400"}`}>{done ? "✓" : i + 1}</span>
                      {i < steps.length - 1 ? <span className={`w-0.5 flex-1 ${i < reached ? "bg-brand" : "bg-line"}`} style={{ minHeight: 18 }} /> : null}
                    </span>
                    <span className={`pb-3 text-sm ${done ? "font-semibold text-ink" : "text-zinc-400"}`}>
                      {statusLabel(lang, key, o.is_pickup)}
                      {done && at ? <span className="ml-2 font-normal text-zinc-400">{when(at)}</span> : null}
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : null}
          {o.pickup ? (
            <div className="rounded-2xl bg-surface p-4 text-sm">
              <p className="font-semibold">{t("pickupPoint")}: {o.pickup.name}</p>
              <p>{o.pickup.address}{o.pickup.landmark ? ` · ${o.pickup.landmark}` : ""}</p>
              <p className="text-zinc-500">{[o.pickup.hours ? `${t("workHours")}: ${o.pickup.hours}` : "", o.pickup.phone].filter(Boolean).join(" · ")}</p>
            </div>
          ) : !failed && o.status !== "delivered" ? (
            <p className="text-sm text-zinc-500">{t("delivery")}: {o.delivery_eta_min}–{o.delivery_eta_max} {t("deliveryDays")}</p>
          ) : null}
          <ul className="divide-y divide-line text-sm">
            {o.items.map((i, k) => <li key={k} className="flex justify-between gap-3 py-2"><span>{i.name}</span><span className="shrink-0 text-zinc-500">× {i.qty}</span></li>)}
          </ul>
          <div className="flex justify-between border-t border-line pt-3 font-bold"><span>{t("total")}</span><span>{formatMoney(o.total, lang)}</span></div>
        </div>
      ) : null}
    </div>
  );
}
