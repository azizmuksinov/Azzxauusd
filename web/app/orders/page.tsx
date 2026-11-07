"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney, statusLabel } from "@/lib/i18n";
import type { OrderListItem, Page } from "@/lib/types";

export default function OrdersPage() {
  const { t, lang, me, ready } = useApp();
  const router = useRouter();
  const [orders, setOrders] = useState<OrderListItem[] | null>(null);

  useEffect(() => {
    if (ready && !me) router.replace("/login?next=/orders");
    if (me) api<Page<OrderListItem>>("/orders").then((p) => setOrders(p.results));
  }, [ready, me, router]);

  if (!orders) return <Loading />;
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-extrabold tracking-tight">{t("orders")}</h1>
      {orders.length === 0 ? <p className="rounded-[2rem] bg-white p-10 text-center text-gray-500 ring-1 ring-gray-100">{t("noOrders")}</p> : null}
      {orders.map((o) => (
        <Link key={o.number} href={`/orders/${o.number}`} className="flex items-center justify-between rounded-3xl bg-white p-4 ring-1 ring-gray-100 hover:ring-1 hover:ring-brand">
          <div>
            <p className="font-semibold">{t("orderNumber")} № {o.number}</p>
            <p className="text-sm text-gray-500">{new Date(o.created_at).toLocaleString(lang === "ru" ? "ru-RU" : "uz-UZ")} · {o.items_count} {t("items")}</p>
          </div>
          <div className="text-right">
            <p className="font-bold">{formatMoney(o.total, lang)}</p>
            <span className="rounded-full bg-brand-light px-2 py-0.5 text-xs text-brand">{statusLabel(lang, o.status)}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}
