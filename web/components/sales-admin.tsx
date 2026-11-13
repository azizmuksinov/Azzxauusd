"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Site } from "@/lib/site";

import { useApp } from "./providers";
import { errorText, sum } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Xodim paneli: promokodlar, muddatli to'lov rejalari va mijoz murojaatlari (tez buyurtma, "kelganda xabar").

type Promo = {
  id: number; code: string; kind: "percent" | "amount"; value: string; min_subtotal: string; max_discount: string | null;
  usage_limit: number | null; once_per_customer: boolean; ends_at: string | null; is_active: boolean; note: string; used: number;
};
const num = (v: string) => v.replace(/[^\d.]/g, "");

export function PromoCodes() {
  const { toast } = useApp();
  const [rows, setRows] = useState<Promo[] | null>(null);
  const [f, setF] = useState({ code: "", kind: "percent", value: "", min_subtotal: "", max_discount: "", usage_limit: "", ends_at: "" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api<{ results: Promo[] }>("/admin/marketing/promos?page_size=100").then((r) => setRows(r.results)), []);
  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    setBusy(true);
    try {
      await api("/admin/marketing/promos", {
        method: "POST",
        body: {
          code: f.code, kind: f.kind, value: f.value, min_subtotal: f.min_subtotal || "0",
          max_discount: f.kind === "percent" && f.max_discount ? f.max_discount : null,
          usage_limit: f.usage_limit ? Number(f.usage_limit) : null,
          ends_at: f.ends_at ? new Date(`${f.ends_at}T23:59:59`).toISOString() : null,
        },
      });
      setF({ code: "", kind: f.kind, value: "", min_subtotal: "", max_discount: "", usage_limit: "", ends_at: "" });
      toast("Promokod yaratildi");
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const patch = async (id: number, body: Record<string, unknown>) => {
    try {
      await api(`/admin/marketing/promos/${id}`, { method: "PATCH", body });
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const remove = async (p: Promo) => {
    if (!window.confirm(`«${p.code}» promokodi o'chirilsinmi?`)) return;
    try {
      await api(`/admin/marketing/promos/${p.id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <Panel className="space-y-4">
      <div>
        <h2 className="font-bold">Promokodlar</h2>
        <p className="mt-1 text-xs text-zinc-500">Chegirma faqat tovarlar summasiga beriladi (yetkazish narxiga emas). Mijoz kodni savatda kiritadi.</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-sm">Kod
          <input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} placeholder="BAHOR10" maxLength={32} className="mt-1 w-full uppercase" />
        </label>
        <label className="block text-sm">Turi
          <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} className="mt-1 w-full">
            <option value="percent">Foiz (%)</option>
            <option value="amount">Summa (so&apos;m)</option>
          </select>
        </label>
        <label className="block text-sm">{f.kind === "percent" ? "Chegirma, %" : "Chegirma, so'm"}
          <input value={f.value} inputMode="decimal" onChange={(e) => setF({ ...f, value: num(e.target.value) })} className="mt-1 w-full" />
        </label>
        <label className="block text-sm">Eng kam xarid, so&apos;m
          <input value={f.min_subtotal} inputMode="numeric" onChange={(e) => setF({ ...f, min_subtotal: num(e.target.value) })} placeholder="cheklovsiz" className="mt-1 w-full" />
        </label>
        {f.kind === "percent" ? (
          <label className="block text-sm">Eng ko&apos;p chegirma, so&apos;m
            <input value={f.max_discount} inputMode="numeric" onChange={(e) => setF({ ...f, max_discount: num(e.target.value) })} placeholder="cheklovsiz" className="mt-1 w-full" />
          </label>
        ) : null}
        <label className="block text-sm">Necha marta ishlatiladi
          <input value={f.usage_limit} inputMode="numeric" onChange={(e) => setF({ ...f, usage_limit: e.target.value.replace(/\D/g, "") })} placeholder="cheklovsiz" className="mt-1 w-full" />
        </label>
        <label className="block text-sm">Amal qilish muddati (shu kungacha)
          <input type="date" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} className="mt-1 w-full" />
        </label>
      </div>
      <Button disabled={busy || !f.code.trim() || !f.value} onClick={create}>Promokod yaratish</Button>

      {rows === null ? <Loading /> : rows.length === 0 ? <p className="text-sm text-zinc-500">Hali promokod yo&apos;q.</p> : (
        <ul className="divide-y divide-line border-t border-line text-sm">
          {rows.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <b className={p.is_active ? "" : "text-zinc-400 line-through"}>{p.code}</b>
              <span>{p.kind === "percent" ? `${Number(p.value)}%` : sum(p.value)}</span>
              <span className="text-xs text-zinc-500">
                ishlatildi: {p.used}{p.usage_limit ? ` / ${p.usage_limit}` : ""}
                {Number(p.min_subtotal) ? ` · ${sum(p.min_subtotal)} dan` : ""}
                {p.max_discount ? ` · ko'pi ${sum(p.max_discount)}` : ""}
                {p.ends_at ? ` · ${new Date(p.ends_at).toLocaleDateString("ru-RU")} gacha` : ""}
              </span>
              <span className="ml-auto flex gap-2">
                <button onClick={() => patch(p.id, { is_active: !p.is_active })} className="text-brand underline">{p.is_active ? "O'chirib qo'yish" : "Yoqish"}</button>
                <button onClick={() => remove(p)} className="text-red-600 underline">O&apos;chirish</button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** Muddatli to'lov kalkulyatori sozlamasi: oy va ustama foizi. Tovar sahifasida oylik to'lov ko'rsatiladi. */
export function InstallmentSettings() {
  const { toast, reloadSite } = useApp();
  const [cfg, setCfg] = useState<NonNullable<Site["installments"]> | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<Site>("/admin/site").then((s) => setCfg(s.installments ?? { enabled: false, plans: [], note: { uz: "", ru: "" } })); }, []);
  if (!cfg) return <Panel><Loading /></Panel>;
  const setPlan = (i: number, key: "months" | "percent", v: string) =>
    setCfg({ ...cfg, plans: cfg.plans.map((p, k) => (k === i ? { ...p, [key]: Number(v.replace(/[^\d.]/g, "")) || 0 } : p)) });
  const save = async () => {
    setBusy(true);
    try {
      const s = await api<Site>("/admin/site", { method: "PUT", body: { installments: cfg } });
      setCfg(s.installments ?? cfg);
      await reloadSite();
      toast("Saqlandi");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="space-y-3">
      <div>
        <h2 className="font-bold">Muddatli to&apos;lov kalkulyatori</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Tovar sahifasida «oyiga … so&apos;m» ko&apos;rsatiladi. Bu faqat hisob-kitob: rasmiylashtirishni operator yoki hamkor bank bajaradi.
        </p>
      </div>
      <label className="flex items-center gap-2 text-sm text-ink">
        <input type="checkbox" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} /> Saytda ko&apos;rsatish
      </label>
      <div className="space-y-2">
        {cfg.plans.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <input value={p.months || ""} inputMode="numeric" onChange={(e) => setPlan(i, "months", e.target.value)} className="w-20" aria-label="Oy" />
            <span>oy, ustama</span>
            <input value={String(p.percent)} inputMode="decimal" onChange={(e) => setPlan(i, "percent", e.target.value)} className="w-20" aria-label="Ustama foizi" />
            <span>%</span>
            <button onClick={() => setCfg({ ...cfg, plans: cfg.plans.filter((_, k) => k !== i) })} className="ml-auto text-red-600 underline">olib tashlash</button>
          </div>
        ))}
        <button onClick={() => setCfg({ ...cfg, plans: [...cfg.plans, { months: 0, percent: 0 }] })} className="text-sm text-brand underline">+ reja qo&apos;shish</button>
      </div>
      <label className="block text-sm">Izoh (o&apos;zbekcha)
        <input value={cfg.note.uz} onChange={(e) => setCfg({ ...cfg, note: { ...cfg.note, uz: e.target.value } })} placeholder="Masalan: Uzum Nasiya orqali" className="mt-1 w-full" />
      </label>
      <label className="block text-sm">Izoh (ruscha)
        <input value={cfg.note.ru} onChange={(e) => setCfg({ ...cfg, note: { ...cfg.note, ru: e.target.value } })} className="mt-1 w-full" />
      </label>
      <Button disabled={busy} onClick={save}>Saqlash</Button>
    </Panel>
  );
}

// --- Murojaatlar ---
type Lead = {
  id: number; product: string; product_slug: string; sku: string; phone: string; name: string; status: string; status_label: string;
  available: number; created_at: string; qty?: number; price?: string; comment?: string;
};
const when = (v: string) => new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

function LeadList({ kind }: { kind: "quick-orders" | "stock-requests" }) {
  const { toast } = useApp();
  const [rows, setRows] = useState<Lead[] | null>(null);
  const [all, setAll] = useState(false);
  const load = useCallback(
    () => api<{ results: Lead[] }>(`/admin/${kind}?page_size=100${all ? "" : "&status=new"}`).then((r) => setRows(r.results)).catch(() => setRows([])),
    [kind, all],
  );
  useEffect(() => {
    void load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);
  const set = async (id: number, status: string) => {
    try {
      await api(`/admin/${kind}/${id}/status`, { method: "POST", body: { status } });
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const quick = kind === "quick-orders";
  return (
    <Panel className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto font-bold">{quick ? "1 bosishda xarid — qo'ng'iroq qilish kerak" : "Kelganda xabar bering"}</h2>
        <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> hammasini ko&apos;rsatish</label>
      </div>
      {rows === null ? <Loading /> : rows.length === 0 ? (
        <p className="py-4 text-center text-sm text-zinc-500">{quick ? "Yangi tez buyurtma yo'q." : "Kutilayotgan so'rov yo'q."}</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <div className="min-w-0 flex-1 basis-56">
                <a href={`/p/${r.product_slug}`} target="_blank" rel="noreferrer" className="font-medium hover:text-brand">{r.product}</a>
                <p className="text-xs text-zinc-500">
                  {quick ? `${r.qty} dona · ${sum(r.price ?? "0")} · ` : ""}
                  {r.available > 0 ? <span className="font-semibold text-green-700">omborda {r.available} ta</span> : <span className="text-red-600">omborda yo&apos;q</span>}
                  {" · "}{when(r.created_at)}
                </p>
              </div>
              <div className="text-right">
                <a href={`tel:${r.phone}`} className="font-semibold text-brand">{r.phone}</a>
                <p className="text-xs text-zinc-500">{r.name || "—"}</p>
              </div>
              {r.status === "new" ? (
                <span className="flex gap-2">
                  <Button className="!h-9 !px-3 text-sm" onClick={() => set(r.id, quick ? "done" : "notified")}>{quick ? "Bog'landim" : "Xabar berdim"}</Button>
                  <Button variant="ghost" className="!h-9 !px-3 text-sm" onClick={() => set(r.id, "cancelled")}>Bekor</Button>
                </span>
              ) : <span className="rounded bg-surface px-2 py-1 text-xs text-zinc-500">{r.status_label}</span>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export function LeadsTab() {
  return (
    <div className="space-y-5">
      <LeadList kind="quick-orders" />
      <LeadList kind="stock-requests" />
    </div>
  );
}
