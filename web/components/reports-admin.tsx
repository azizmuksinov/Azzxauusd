"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { shortDate } from "@/lib/i18n";

import { errorText, sum } from "./staff";
import { Loading, Panel } from "./ui";

// Xodim paneli: sotuv hisoboti. Bitta ko'rsatkich — bitta rang (brend feruzasi); matnlar doim oddiy siyohda.

type Report = {
  days: number; from: string; to: string;
  totals: {
    orders: number; revenue: string; avg_check: string; units: number; goods: string; discounts: string; bonus_spent: string;
    delivery: string; customers: number; new_customers: number; delivered: number; cancelled: number; pickup: number; gross_profit: string | null;
  };
  daily: { date: string; orders: number; revenue: string }[];
  top_products: { variant_id: number; sku: string; name: string; qty: number; revenue: string }[];
  payment_methods: { code: string; orders: number; revenue: string }[];
  abandoned_carts: { carts: number; value: string };
};

const PAY: Record<string, string> = { payme: "Payme", click: "Click", uzum: "Uzum Bank", cash: "Naqd (eshikda / olib ketishda)", card_on_delivery: "Karta (eshikda)" };
const BAR = "#0d9488"; // brend feruzasi: bitta qator — bitta rang (oq fonda tekshirilgan)
const GRID = "rgb(214 226 226)";

/** Qisqa son: 1,2 mln / 850 ming — o'q belgilari uchun. */
function compact(n: number): string {
  if (n >= 1e9) return `${+(n / 1e9).toFixed(1)} mlrd`;
  if (n >= 1e6) return `${+(n / 1e6).toFixed(1)} mln`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} ming`;
  return String(Math.round(n));
}
/** O'q uchun "chiroyli" yuqori chegara (1, 2, 5 × 10ⁿ). */
function niceMax(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 5, 10].map((m) => m * pow).find((x) => x >= v) ?? 10 * pow;
}
const day = (iso: string) => shortDate(`${iso}T00:00:00`, "uz");

/** Kunlik savdo: ustunlar (vaqt bo'yicha o'zgarish), sichqoncha/klaviatura bilan aniq qiymat. */
function DailyChart({ rows }: { rows: Report["daily"] }) {
  const [active, setActive] = useState<number | null>(null);
  const values = rows.map((r) => Number(r.revenue));
  const top = niceMax(Math.max(...values, 0));
  const peak = values.indexOf(Math.max(...values));
  const ticks = [top, top / 2, 0];
  const labelEvery = Math.max(1, Math.ceil(rows.length / 6));
  return (
    <div className="flex gap-2">
      <div className="flex h-56 w-16 shrink-0 flex-col justify-between pb-6 text-right text-[11px] text-zinc-500">
        {ticks.map((t) => <span key={t} className="-translate-y-1/2 first:translate-y-0">{compact(t)}</span>)}
      </div>
      <div className="relative min-w-0 flex-1">
        <div className="relative h-56 pb-6">
          {/* panjara chiziqlari — ingichka, orqa fonda */}
          <div className="pointer-events-none absolute inset-x-0 bottom-6 top-0">
            {ticks.map((t, i) => <span key={t} className="absolute inset-x-0 h-px" style={{ top: `${(i / (ticks.length - 1)) * 100}%`, background: GRID }} />)}
          </div>
          <div className="absolute inset-x-0 bottom-6 top-0 flex items-end" style={{ gap: 2 }} onMouseLeave={() => setActive(null)}>
            {rows.map((r, i) => {
              const v = values[i];
              return (
                <button key={r.date} type="button" aria-label={`${day(r.date)}: ${sum(v)}, ${r.orders} ta buyurtma`}
                  onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                  className="group relative flex h-full min-w-0 flex-1 items-end justify-center outline-none">
                  {i === peak && v > 0 && active === null ? (
                    <span className="pointer-events-none absolute left-1/2 z-10 -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold text-ink" style={{ bottom: `calc(${(v / top) * 100}% + 4px)` }}>{compact(v)}</span>
                  ) : null}
                  <span className="w-full max-w-[24px] rounded-t transition-opacity group-focus-visible:ring-2 group-focus-visible:ring-ink"
                    style={{ height: `${(v / top) * 100}%`, minHeight: v > 0 ? 2 : 0, background: BAR, opacity: active === null || active === i ? 1 : 0.45 }} />
                </button>
              );
            })}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex h-5 text-[11px] text-zinc-500" style={{ gap: 2 }}>
            {rows.map((r, i) => (
              <span key={r.date} className="relative min-w-0 flex-1">
                {i % labelEvery === 0 ? <span className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap">{day(r.date)}</span> : null}
              </span>
            ))}
          </div>
        </div>
        {active !== null ? (
          // Chetdagi ustunlarda oynacha diagramma ichida qoladi (o'ng/chap chetga yopishadi).
          <div className={`pointer-events-none absolute top-0 z-20 whitespace-nowrap rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-lg ${active / rows.length > 0.75 ? "right-0" : active / rows.length < 0.25 ? "left-0" : "-translate-x-1/2"}`}
            style={active / rows.length > 0.75 || active / rows.length < 0.25 ? undefined : { left: `${((active + 0.5) / rows.length) * 100}%` }}>
            <b className="block text-sm">{sum(values[active])}</b>
            {day(rows[active].date)} · {rows[active].orders} ta buyurtma
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-3xl bg-white p-4 shadow-card">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-display text-xl font-bold tracking-tight text-ink">{value}</p>
      {note ? <p className="mt-0.5 text-xs text-zinc-500">{note}</p> : null}
    </div>
  );
}

export function ReportsTab() {
  const [days, setDays] = useState(30);
  const [r, setR] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [table, setTable] = useState(false);
  useEffect(() => {
    setR(null);
    setError("");
    api<Report>(`/admin/reports/sales?days=${days}`).then(setR).catch((e) => setError(errorText(e)));
  }, [days]);
  if (error) return <Panel><p className="text-sm text-red-600">{error}</p></Panel>;
  const t = r?.totals;
  const topMax = Math.max(1, ...(r?.top_products ?? []).map((p) => Number(p.revenue)));
  const payTotal = Math.max(1, (r?.payment_methods ?? []).reduce((a, p) => a + Number(p.revenue), 0));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {[7, 30, 90].map((d) => (
          <button key={d} onClick={() => setDays(d)} aria-pressed={days === d}
            className={`rounded-full px-4 py-2 text-sm font-medium ${days === d ? "bg-ink text-white" : "bg-white text-zinc-600 ring-1 ring-line"}`}>Oxirgi {d} kun</button>
        ))}
        {r ? <span className="ml-auto text-sm text-zinc-500">{day(r.from)} — {day(r.to)}</span> : null}
      </div>
      {!r || !t ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Savdo" value={sum(t.revenue)} note={`Tovarlar: ${sum(t.goods)}`} />
            <Tile label="Buyurtmalar" value={String(t.orders)} note={`Yetkazilgan: ${t.delivered} · bekor: ${t.cancelled}`} />
            <Tile label="O'rtacha chek" value={sum(t.avg_check)} note={`Sotilgan: ${t.units} dona`} />
            <Tile label="Xaridorlar" value={String(t.customers)} note={`Yangi: ${t.new_customers}`} />
            {t.gross_profit !== null ? <Tile label="Yalpi foyda" value={sum(t.gross_profit)} note="Tannarxi kiritilgan tovarlar bo'yicha" /> : null}
            <Tile label="Chegirmalar" value={sum(t.discounts)} note={Number(t.bonus_spent) > 0 ? `Bonus bilan: ${sum(t.bonus_spent)}` : undefined} />
            <Tile label="Olib ketish" value={String(t.pickup)} note="buyurtma" />
            <Tile label="Tashlab ketilgan savatlar" value={String(r.abandoned_carts.carts)} note={`Qiymati: ${sum(r.abandoned_carts.value)}`} />
          </div>

          <Panel className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-bold">Kunlik savdo, so&apos;m</h2>
                <p className="text-xs text-zinc-500">Bekor qilingan va qaytgan buyurtmalarsiz</p>
              </div>
              <button onClick={() => setTable((v) => !v)} className="rounded-full bg-surface px-3 py-1.5 text-xs font-medium hover:text-brand">{table ? "Diagramma" : "Jadval"}</button>
            </div>
            {table ? (
              <div className="max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-zinc-500"><tr><th className="py-1.5 font-medium">Sana</th><th className="font-medium">Buyurtmalar</th><th className="text-right font-medium">Savdo</th></tr></thead>
                  <tbody className="divide-y divide-line">
                    {[...r.daily].reverse().map((d) => <tr key={d.date}><td className="py-1.5">{day(d.date)}</td><td>{d.orders}</td><td className="text-right font-medium">{sum(d.revenue)}</td></tr>)}
                  </tbody>
                </table>
              </div>
            ) : t.orders === 0 ? <p className="py-10 text-center text-sm text-zinc-500">Bu davrda sotuv yo&apos;q</p> : <DailyChart rows={r.daily} />}
          </Panel>

          <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
            <Panel className="space-y-3">
              <h2 className="font-bold">Eng ko&apos;p sotilgan tovarlar</h2>
              {!r.top_products.length ? <p className="text-sm text-zinc-500">Ma&apos;lumot yo&apos;q</p> : r.top_products.map((p) => (
                <div key={p.variant_id} className="space-y-1" title={`${p.name}: ${sum(p.revenue)}, ${p.qty} dona`}>
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="min-w-0 truncate">{p.name}</span>
                    <span className="shrink-0 font-semibold">{sum(p.revenue)} <span className="font-normal text-zinc-500">· {p.qty} dona</span></span>
                  </div>
                  <div className="h-2 rounded-r" style={{ width: `${Math.max(2, (Number(p.revenue) / topMax) * 100)}%`, background: BAR }} />
                </div>
              ))}
            </Panel>
            <Panel className="space-y-3">
              <h2 className="font-bold">To&apos;lov usullari</h2>
              {!r.payment_methods.length ? <p className="text-sm text-zinc-500">Ma&apos;lumot yo&apos;q</p> : r.payment_methods.map((p) => {
                const share = (Number(p.revenue) / payTotal) * 100;
                return (
                  <div key={p.code} className="space-y-1" title={`${PAY[p.code] ?? p.code}: ${sum(p.revenue)}`}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span>{PAY[p.code] ?? p.code} <span className="text-zinc-500">· {p.orders} ta</span></span>
                      <span className="shrink-0 font-semibold">{Math.round(share)}%</span>
                    </div>
                    <div className="h-2 rounded-r" style={{ width: `${Math.max(2, share)}%`, background: BAR }} />
                  </div>
                );
              })}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
