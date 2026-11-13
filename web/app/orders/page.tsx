"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { Loading, useTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { Star8 } from "@/components/illustrations-star";
import { formatMoney, statusLabel } from "@/lib/i18n";
import type { OrderListItem, Page } from "@/lib/types";

type Bonus = { enabled: boolean; balance: string; earn_percent: string; max_pay_percent: number; history: { id: number; amount: string; kind: string; kind_label: string; order: string | null; created_at: string }[] };

/** Bonus balansi va oxirgi yozuvlar (tizim yoqilgan bo'lsa). */
function BonusCard() {
  const { t, lang } = useApp();
  const [b, setB] = useState<Bonus | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api<Bonus>("/me/bonus").then(setB).catch(() => setB(null));
  }, []);
  if (!b?.enabled) return null;
  return (
    <div className="rounded-3xl bg-white p-4 border border-line">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-2xl bg-amber-100 text-amber-700"><Star8 className="h-5 w-5" filled /></span>
        <div className="flex-1">
          <p className="text-sm text-zinc-500">{t("bonusBalance")}</p>
          <p className="font-display text-xl font-bold">{formatMoney(b.balance, lang)}</p>
        </div>
        {b.history.length ? <button onClick={() => setOpen((v) => !v)} className="text-sm font-semibold text-brand">{t("bonusHistory")}</button> : null}
      </div>
      <p className="mt-2 text-xs text-zinc-500">{t("bonusRule").replace("{p}", String(b.max_pay_percent))}</p>
      {open ? (
        <ul className="mt-3 divide-y divide-line text-sm">
          {b.history.map((h) => (
            <li key={h.id} className="flex justify-between gap-3 py-2">
              <span>{h.kind === "earn" ? t("bonusEarned") : h.kind === "spend" ? t("bonusSpent") : h.kind_label}{h.order ? ` · № ${h.order}` : ""}<span className="block text-xs text-zinc-400">{new Date(h.created_at).toLocaleDateString(lang === "ru" ? "ru-RU" : "uz-UZ")}</span></span>
              <b className={Number(h.amount) < 0 ? "text-red-600" : "text-green-700"}>{Number(h.amount) > 0 ? "+" : "−"}{formatMoney(Math.abs(Number(h.amount)), lang)}</b>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default function OrdersPage() {
  const { t, lang, me, ready } = useApp();
  const router = useRouter();
  const [orders, setOrders] = useState<OrderListItem[] | null>(null);
  useTitle(t("orders"));

  useEffect(() => {
    if (ready && !me) router.replace("/login?next=/orders");
    if (me) api<Page<OrderListItem>>("/orders").then((p) => setOrders(p.results));
  }, [ready, me, router]);

  if (!orders) return <Loading />;
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold tracking-tight">{t("orders")}</h1>
      <BonusCard />
      {orders.length === 0 ? <p className="rounded-2xl bg-white p-10 text-center text-zinc-500 border border-line">{t("noOrders")}</p> : null}
      {orders.map((o) => (
        <Link key={o.number} href={`/orders/${o.number}`} className="flex items-center justify-between rounded-3xl bg-white p-4 border border-line hover:ring-1 hover:ring-brand">
          <div>
            <p className="font-semibold">{t("orderNumber")} № {o.number}</p>
            <p className="text-sm text-zinc-500">{new Date(o.created_at).toLocaleString(lang === "ru" ? "ru-RU" : "uz-UZ")} · {o.items_count} {t("items")}</p>
          </div>
          <div className="text-right">
            <p className="font-bold">{formatMoney(o.total, lang)}</p>
            <span className="rounded-full bg-brand-light px-2 py-0.5 text-xs text-brand">{statusLabel(lang, o.status, o.is_pickup)}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
