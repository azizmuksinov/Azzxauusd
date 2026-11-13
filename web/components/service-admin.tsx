"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { shortDate } from "@/lib/i18n";

import { useApp } from "./providers";
import { StatusBadge, errorText, sum } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Xodim paneli: tovar bo'yicha savollar va olib ketish (punktlar, buyurtmani topshirish).

type Page<T> = { results: T[] };

// ------------------------------------------------------------------ savollar
type Question = {
  id: number; author: string; phone: string; text: string; answer: string; status: "new" | "answered" | "hidden";
  product: string; product_slug: string; created_at: string;
};

export function QuestionsTab({ onChange }: { onChange?: () => void }) {
  const { toast } = useApp();
  const [filter, setFilter] = useState<"new" | "answered" | "hidden">("new");
  const [rows, setRows] = useState<Question[] | null>(null);
  const [draft, setDraft] = useState<Record<number, string>>({});
  const load = useCallback(async () => {
    setRows(null);
    setRows((await api<Page<Question>>(`/admin/questions?status=${filter}&page_size=100`)).results);
  }, [filter]);
  useEffect(() => { void load(); }, [load]);
  const patch = async (q: Question, body: Record<string, unknown>, done: string) => {
    try {
      await api(`/admin/questions/${q.id}`, { method: "PATCH", body });
      toast(done);
      await load();
      onChange?.();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const tabs: [typeof filter, string][] = [["new", "Javob kutmoqda"], ["answered", "Javob berilgan"], ["hidden", "Yashirilgan"]];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {tabs.map(([k, l]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`rounded-full px-4 py-2 text-sm font-medium ${filter === k ? "bg-ink text-white" : "bg-white text-zinc-600 ring-1 ring-line"}`}>{l}</button>
        ))}
      </div>
      <p className="text-sm text-zinc-500">Savol saytda faqat javob berilgandan keyin ko&apos;rinadi. Reklama yoki haqoratni yashiring.</p>
      {!rows ? <Loading /> : rows.length === 0 ? <Panel><p className="text-sm text-zinc-500">Bo&apos;sh</p></Panel> : rows.map((q) => {
        const text = draft[q.id] ?? q.answer;
        return (
          <Panel key={q.id} className="space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <a href={`/p/${q.product_slug}`} target="_blank" rel="noreferrer" className="text-sm font-semibold text-brand">{q.product} ↗</a>
                <p className="text-xs text-zinc-500">{q.author}{q.phone ? ` · ${q.phone}` : ""} · {shortDate(q.created_at, "uz", true)}</p>
              </div>
              {q.status !== "hidden"
                ? <button onClick={() => patch(q, { status: "hidden" }, "Yashirildi")} className="text-xs font-medium text-zinc-500 hover:text-red-600">Yashirish</button>
                : <button onClick={() => patch(q, { status: q.answer ? "answered" : "new" }, "Qaytarildi")} className="text-xs font-medium text-brand">Qaytarish</button>}
            </div>
            <p className="font-medium">{q.text}</p>
            <textarea value={text} onChange={(e) => setDraft({ ...draft, [q.id]: e.target.value })} rows={3} maxLength={3000} placeholder="Javobingiz (saytda hammaga ko'rinadi)" className="w-full" />
            <Button disabled={!text.trim() || text === q.answer} onClick={() => patch(q, { answer: text }, "Javob saqlandi")}>{q.answer ? "Javobni yangilash" : "Javob berish"}</Button>
          </Panel>
        );
      })}
    </div>
  );
}

// ------------------------------------------------------------------ olib ketish
type Order = { number: string; status: string; total: string; paid_amount: string; items_count: number; recipient_name: string; recipient_phone: string; payment_method: string };
type Till = { id: number; name: string; kind: string };
type Point = { id: number; name: string; address: string; landmark: string; hours: string; phone: string; is_active: boolean };
const EMPTY_POINT = { name: "", address: "", landmark: "", hours: "", phone: "" };

export function PickupTab({ canManage }: { canManage: boolean }) {
  const { toast } = useApp();
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [tills, setTills] = useState<Till[]>([]);
  const [till, setTill] = useState<number | null>(null);
  const [points, setPoints] = useState<Point[]>([]);
  const [f, setF] = useState(EMPTY_POINT);
  const load = useCallback(async () => {
    const [o, t] = await Promise.all([
      api<Page<Order>>("/admin/orders?pickup=1&status=paid,cod_confirmed,picking,packed&page_size=100"),
      api<Till[]>("/admin/orders/pickup-tills").catch(() => [] as Till[]),
    ]);
    setOrders(o.results);
    setTills(t);
    setTill((cur) => cur ?? t.find((x) => x.kind === "cash")?.id ?? t[0]?.id ?? null);
    if (canManage) setPoints(await api<Point[]>("/admin/pickup-points"));
  }, [canManage]);
  useEffect(() => { load().catch(() => setOrders([])); }, [load]);
  const run = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      toast(done);
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  if (!orders) return <Loading />;
  const ready = orders.filter((o) => o.status === "packed");
  const waiting = orders.filter((o) => o.status !== "packed");

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel className="space-y-3">
        <h2 className="font-bold">Olib ketishga tayyor <span className="text-gray-400">({ready.length})</span></h2>
        {ready.some((o) => Number(o.total) > Number(o.paid_amount)) ? (
          tills.length ? (
            <label className="block text-sm">To&apos;lov tushadigan kassa
              <select value={till ?? ""} onChange={(e) => setTill(Number(e.target.value))} className="mt-1 w-full">
                {tills.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
          ) : <p className="rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">Joyida to&apos;lov olish uchun avval kassa (hisob) yarating — moliya bo&apos;limi.</p>
        ) : null}
        {!ready.length ? <p className="text-sm text-gray-500">Bo&apos;sh</p> : null}
        {ready.map((o) => {
          const due = Math.max(0, Number(o.total) - Number(o.paid_amount));
          return (
            <div key={o.number} className="space-y-2 rounded-2xl p-3 ring-1 ring-gray-100">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-semibold">{o.number} <span className="text-xs text-gray-500">· {o.items_count} dona</span></p>
                  <p className="text-xs text-gray-500">{[o.recipient_name, o.recipient_phone].filter((x, i, a) => x && a.indexOf(x) === i).join(" · ")}</p>
                </div>
                <p className="text-right text-sm">{due > 0 ? <>Olinadi: <b>{sum(due)}</b></> : <span className="font-medium text-green-700">To&apos;langan</span>}</p>
              </div>
              <Button className="!h-10 w-full text-sm" disabled={due > 0 && !till}
                onClick={() => window.confirm(due > 0 ? `${sum(due)} olindi va tovar topshirildimi?` : "Tovar xaridorga topshirildimi?")
                  && run(() => api(`/admin/orders/${o.number}/hand-over`, { method: "POST", body: due > 0 ? { account: till } : {} }), "Buyurtma topshirildi")}>
                {due > 0 ? "To'lov olindi — topshirish" : "Topshirish"}
              </Button>
            </div>
          );
        })}
        {waiting.length ? (
          <div className="border-t border-line pt-3">
            <p className="mb-2 text-sm font-semibold">Hali tayyor emas ({waiting.length}) — «Yig&apos;ish» bo&apos;limida qadoqlanadi</p>
            <ul className="space-y-1.5 text-sm">
              {waiting.map((o) => <li key={o.number} className="flex items-center justify-between gap-2"><span>{o.number} · {o.recipient_name}</span><StatusBadge status={o.status} /></li>)}
            </ul>
          </div>
        ) : null}
      </Panel>

      {canManage ? (
        <Panel className="space-y-3">
          <h2 className="font-bold">Olib ketish punktlari</h2>
          <p className="text-sm text-zinc-500">Kamida bitta faol punkt bo&apos;lsa, rasmiylashtirishda «O&apos;zim olib ketaman» (bepul) tanlovi chiqadi.</p>
          {points.map((p) => (
            <div key={p.id} className={`flex flex-wrap items-center gap-3 rounded-2xl p-3 ring-1 ring-gray-100 ${p.is_active ? "" : "opacity-60"}`}>
              <div className="min-w-[180px] flex-1 text-sm">
                <p className="font-semibold">{p.name}</p>
                <p className="text-xs text-gray-500">{[p.address, p.landmark, p.hours, p.phone].filter(Boolean).join(" · ")}</p>
              </div>
              <button onClick={() => run(() => api(`/admin/pickup-points/${p.id}`, { method: "PATCH", body: { is_active: !p.is_active } }), p.is_active ? "O'chirildi" : "Yoqildi")}
                className="text-xs font-medium text-brand">{p.is_active ? "O'chirib qo'yish" : "Yoqish"}</button>
            </div>
          ))}
          <div className="grid gap-2 sm:grid-cols-2">
            <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Nomi (masalan: Chilonzor do'koni)" />
            <input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} placeholder="Manzil" />
            <input value={f.landmark} onChange={(e) => setF({ ...f, landmark: e.target.value })} placeholder="Mo'ljal" />
            <input value={f.hours} onChange={(e) => setF({ ...f, hours: e.target.value })} placeholder="Ish vaqti (9:00–20:00)" />
            <input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="Telefon" />
            <Button className="!h-11" disabled={!f.name.trim() || !f.address.trim()}
              onClick={() => run(async () => { await api("/admin/pickup-points", { method: "POST", body: f }); setF(EMPTY_POINT); }, "Punkt qo'shildi")}>Punkt qo&apos;shish</Button>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
