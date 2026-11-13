"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { shortDate } from "@/lib/i18n";

import { useApp } from "./providers";
import { errorText, sum } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Xodim paneli (Marketing): kun tovari, "birga arzonroq" to'plamlari va bonus tizimi.

type Variant = { id: number; product_id: number; sku: string; name: string; price: string; old_price: string | null };
type Page<T> = { results: T[] };
const num = (v: string) => v.replace(/[^\d.]/g, "");

/** Tovar tanlash: nom, model yoki SKU bo'yicha qidiruv. */
function VariantPicker({ value, onPick, placeholder }: { value: Variant | null; onPick: (v: Variant | null) => void; placeholder: string }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Variant[]>([]);
  useEffect(() => {
    if (value || q.trim().length < 2) return setRows([]);
    const id = setTimeout(() => {
      api<Variant[]>(`/admin/marketing/variants?q=${encodeURIComponent(q.trim())}`).then(setRows).catch(() => setRows([]));
    }, 250);
    return () => clearTimeout(id);
  }, [q, value]);
  if (value) {
    return (
      <div className="flex items-center gap-2 rounded-2xl bg-brand-light px-3 py-2 text-sm">
        <span className="min-w-0 flex-1 truncate"><b>{value.name}</b> · {sum(value.price)}</span>
        <button type="button" onClick={() => onPick(null)} className="shrink-0 text-xs font-semibold text-brand">O&apos;zgartirish</button>
      </div>
    );
  }
  return (
    <div className="relative">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="w-full" />
      {rows.length ? (
        <div className="absolute inset-x-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-2xl bg-white p-1 shadow-lg ring-1 ring-line">
          {rows.map((v) => (
            <button key={v.id} type="button" onClick={() => { onPick(v); setQ(""); }}
              className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-sm hover:bg-surface">
              <span className="min-w-0 truncate">{v.name} <span className="text-xs text-zinc-400">{v.sku}</span></span>
              <span className="shrink-0 font-medium">{sum(v.price)}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function useAction() {
  const { toast } = useApp();
  return async (fn: () => Promise<unknown>, done: string, after?: () => Promise<unknown> | void) => {
    try {
      await fn();
      toast(done);
      await after?.();
      return true;
    } catch (e) {
      toast(errorText(e), "error");
      return false;
    }
  };
}

// ------------------------------------------------------------------ kun tovari
type Deal = {
  id: number; product: string; sku: string; price: string; current_price: string; base_price: string | null;
  starts_at: string; ends_at: string; state: "scheduled" | "active" | "ended" | "cancelled"; state_label: string; note: string;
};
const localInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export function Deals() {
  const act = useAction();
  const [rows, setRows] = useState<Deal[] | null>(null);
  const [variant, setVariant] = useState<Variant | null>(null);
  const [price, setPrice] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState(() => localInput(new Date(Date.now() + 24 * 3600 * 1000)));
  const load = useCallback(() => api<Page<Deal>>("/admin/marketing/deals?page_size=30").then((r) => setRows(r.results)), []);
  useEffect(() => { void load(); }, [load]);

  const create = () => act(
    () => api("/admin/marketing/deals", {
      method: "POST",
      body: { variant: variant!.id, price, starts_at: start ? new Date(start).toISOString() : null, ends_at: new Date(end).toISOString() },
    }),
    "Aksiya yaratildi",
    async () => { setVariant(null); setPrice(""); await load(); },
  );
  const when = (v: string) => shortDate(v, "uz", true);
  const tone: Record<Deal["state"], string> = {
    active: "bg-green-50 text-green-700", scheduled: "bg-amber-50 text-amber-700", ended: "bg-surface text-zinc-500", cancelled: "bg-surface text-zinc-500",
  };
  const off = variant && Number(price) > 0 ? Math.round((1 - Number(price) / Number(variant.price)) * 100) : 0;

  return (
    <Panel className="space-y-3">
      <div>
        <h2 className="font-bold">Kun tovari (vaqtli aksiya)</h2>
        <p className="text-sm text-zinc-500">Belgilangan muddatda tovar maxsus narxda sotiladi, bosh sahifada sanoq bilan chiqadi. Muddat tugagach narx o&apos;zi qaytadi.</p>
      </div>
      <VariantPicker value={variant} onPick={setVariant} placeholder="Tovarni qidiring (nom, model yoki SKU)" />
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">Aksiya narxi, so&apos;m
          <input value={price} onChange={(e) => setPrice(num(e.target.value))} inputMode="numeric" className="mt-1 w-full" />
        </label>
        <label className="block text-sm">Boshlanishi (bo&apos;sh — hozir)
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 w-full" />
        </label>
        <label className="block text-sm">Tugashi
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className="mt-1 w-full" />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={!variant || !Number(price) || !end} onClick={create}>Aksiyani boshlash</Button>
        {off > 0 ? <span className="text-sm text-zinc-500">Chegirma: <b className="text-sale">−{off}%</b></span> : null}
        {variant && Number(price) >= Number(variant.price) ? <span className="text-sm text-red-600">Narx hozirgi narxdan past bo&apos;lsin</span> : null}
      </div>
      {!rows ? <Loading /> : rows.length ? (
        <div className="divide-y divide-line rounded-2xl ring-1 ring-line">
          {rows.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-3 p-3 text-sm">
              <div className="min-w-[200px] flex-1">
                <p className="font-medium">{d.product}</p>
                <p className="text-xs text-zinc-500">{when(d.starts_at)} — {when(d.ends_at)}{d.note ? ` · ${d.note}` : ""}</p>
              </div>
              <span><b>{sum(d.price)}</b>{d.base_price ? <span className="ml-1 text-xs text-zinc-400 line-through">{sum(d.base_price)}</span> : null}</span>
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${tone[d.state]}`}>{d.state_label}</span>
              {d.state === "active" || d.state === "scheduled" ? (
                <button onClick={() => window.confirm("Aksiya bekor qilinsinmi? Narx avvalgisiga qaytadi.") && act(() => api(`/admin/marketing/deals/${d.id}`, { method: "DELETE" }), "Aksiya bekor qilindi", load)}
                  className="text-xs font-medium text-zinc-500 hover:text-red-600">Bekor qilish</button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

// ------------------------------------------------------------------ birga arzonroq
type Bundle = { id: number; product_name: string; extra_name: string; discount_percent: string; is_active: boolean };

export function BundlesAdmin() {
  const act = useAction();
  const [rows, setRows] = useState<Bundle[] | null>(null);
  const [main, setMain] = useState<Variant | null>(null);
  const [extra, setExtra] = useState<Variant | null>(null);
  const [percent, setPercent] = useState("10");
  const load = useCallback(() => api<Page<Bundle>>("/admin/marketing/bundles?page_size=100").then((r) => setRows(r.results)), []);
  useEffect(() => { void load(); }, [load]);
  const same = !!main && !!extra && main.product_id === extra.product_id;

  return (
    <Panel className="space-y-3">
      <div>
        <h2 className="font-bold">Birga arzonroq</h2>
        <p className="text-sm text-zinc-500">Asosiy tovar savatda bo&apos;lsa, qo&apos;shimcha tovarga chegirma beriladi (masalan, televizor + kronshteyn). Tovar sahifasida taklif sifatida ko&apos;rinadi.</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">Asosiy tovar<span className="mt-1 block"><VariantPicker value={main} onPick={setMain} placeholder="Masalan: televizor" /></span></label>
        <label className="block text-sm">Qo&apos;shimcha tovar (chegirma shunga)<span className="mt-1 block"><VariantPicker value={extra} onPick={setExtra} placeholder="Masalan: kronshteyn" /></span></label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="block text-sm">Chegirma, %
          <input value={percent} onChange={(e) => setPercent(num(e.target.value))} inputMode="numeric" className="mt-1 block w-28" />
        </label>
        <Button disabled={!main || !extra || same || !(Number(percent) > 0 && Number(percent) <= 90)}
          onClick={() => act(
            () => api("/admin/marketing/bundles", { method: "POST", body: { product: main!.product_id, extra: extra!.product_id, discount_percent: percent } }),
            "To'plam qo'shildi",
            async () => { setExtra(null); await load(); },
          )}>Qo&apos;shish</Button>
        {same ? <span className="text-sm text-red-600">Ikki xil tovar tanlang</span> : null}
        {extra && Number(percent) > 0 && !same ? <span className="text-sm text-zinc-500">Birga narxi: <b>{sum(Math.floor(Number(extra.price) * (1 - Number(percent) / 100)))}</b></span> : null}
      </div>
      {!rows ? <Loading /> : rows.length ? (
        <div className="divide-y divide-line rounded-2xl ring-1 ring-line">
          {rows.map((b) => (
            <div key={b.id} className={`flex flex-wrap items-center gap-3 p-3 text-sm ${b.is_active ? "" : "opacity-60"}`}>
              <p className="min-w-[220px] flex-1"><b>{b.product_name}</b> + {b.extra_name}</p>
              <span className="rounded-full bg-sale/10 px-2.5 py-0.5 text-xs font-bold text-sale">−{Number(b.discount_percent)}%</span>
              <button onClick={() => act(() => api(`/admin/marketing/bundles/${b.id}`, { method: "PATCH", body: { is_active: !b.is_active } }), b.is_active ? "O'chirildi" : "Yoqildi", load)}
                className="text-xs font-medium text-brand">{b.is_active ? "O'chirib qo'yish" : "Yoqish"}</button>
              <button onClick={() => window.confirm("To'plam o'chirilsinmi?") && act(() => api(`/admin/marketing/bundles/${b.id}`, { method: "DELETE" }), "O'chirildi", load)}
                className="text-xs font-medium text-zinc-500 hover:text-red-600">O&apos;chirish</button>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

// ------------------------------------------------------------------ bonus
type Setting = { key: string; value: string | number | null };
type Entry = { id: number; phone: string; amount: string; kind_label: string; order: string | null; note: string; created_at: string };

/** Bonus tizimi: foizlar (sozlamalar) va xaridorga qo'lda bonus qo'shish/ayirish. Faqat administrator. */
export function BonusAdmin() {
  const act = useAction();
  const [earn, setEarn] = useState("");
  const [maxPay, setMaxPay] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [rows, setRows] = useState<Entry[]>([]);
  const [f, setF] = useState({ phone: "+998 ", amount: "", note: "" });
  const load = useCallback(async () => {
    const s = await api<Setting[]>("/admin/settings");
    const get = (k: string) => s.find((x) => x.key === k)?.value;
    setEarn(get("bonus_earn_percent") == null ? "" : String(Number(get("bonus_earn_percent"))));
    setMaxPay(String(get("bonus_max_pay_percent") ?? 30));
    setLoaded(true);
    setRows((await api<Page<Entry>>("/admin/bonus?page_size=15")).results);
  }, []);
  useEffect(() => { load().catch(() => setLoaded(true)); }, [load]);
  if (!loaded) return <Loading />;
  const on = Number(earn) > 0;

  return (
    <Panel className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-bold">Bonus (keshbek)</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${on ? "bg-green-50 text-green-700" : "bg-surface text-zinc-500"}`}>{on ? "Yoqilgan" : "O'chiq"}</span>
      </div>
      <p className="text-sm text-zinc-500">Buyurtma yetkazilganda xariddan bonus yoziladi (1 bonus = 1 so&apos;m). Keyingi xaridda tovarlar summasining bir qismini bonus bilan to&apos;lash mumkin. Foiz bo&apos;sh qoldirilsa — tizim o&apos;chiq.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="block text-sm">Xariddan bonus, %
          <input value={earn} onChange={(e) => setEarn(num(e.target.value))} inputMode="decimal" placeholder="masalan 2" className="mt-1 block w-32" />
        </label>
        <label className="block text-sm">Bonus bilan to&apos;lash, ko&apos;pi bilan %
          <input value={maxPay} onChange={(e) => setMaxPay(num(e.target.value))} inputMode="numeric" className="mt-1 block w-32" />
        </label>
        <Button onClick={() => act(
          () => api("/admin/settings", { method: "PATCH", body: { bonus_earn_percent: earn === "" ? null : earn, bonus_max_pay_percent: Number(maxPay || 30) } }),
          "Bonus sozlamalari saqlandi", load,
        )}>Saqlash</Button>
      </div>
      <div className="space-y-2 rounded-2xl bg-surface p-3">
        <p className="text-sm font-semibold">Xaridorga qo&apos;lda bonus</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_140px_1fr_auto]">
          <input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="Telefon" inputMode="tel" />
          <input value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value.replace(/[^\d.-]/g, "") })} placeholder="Summa (− ayirish)" />
          <input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Izoh (sababi)" maxLength={200} />
          <Button className="!h-11" disabled={!Number(f.amount) || !f.note.trim() || f.phone.replace(/\D/g, "").length < 9}
            onClick={() => act(() => api("/admin/bonus/adjust", { method: "POST", body: f }), "Bonus yozildi", async () => { setF({ phone: "+998 ", amount: "", note: "" }); await load(); })}>Yozish</Button>
        </div>
      </div>
      {rows.length ? (
        <div className="divide-y divide-line text-sm">
          {rows.map((e) => (
            <div key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>{e.phone} · {e.kind_label}{e.order ? ` · № ${e.order}` : ""}{e.note && !e.order ? ` · ${e.note}` : ""}
                <span className="ml-2 text-xs text-zinc-400">{shortDate(e.created_at, "uz")}</span></span>
              <b className={Number(e.amount) < 0 ? "text-red-600" : "text-green-700"}>{Number(e.amount) > 0 ? "+" : "−"}{sum(Math.abs(Number(e.amount)))}</b>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}
