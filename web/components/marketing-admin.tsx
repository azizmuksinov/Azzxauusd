"use client";

import { useCallback, useEffect, useState } from "react";

import { api, apiUpload } from "@/lib/api";

import { useApp } from "./providers";
import { errorText } from "./staff";
import { Button, Loading, Panel } from "./ui";

type I18n = { uz?: string; ru?: string };
type Banner = { id: number; title: I18n; subtitle: I18n; url: string; image_url: string; link: string; color: string; sort: number; is_active: boolean };
type Opt = { id: number; name: I18n | string; parent?: number | null };
type Page<T> = { results: T[] } | T[];
const list = <T,>(p: Page<T>): T[] => (Array.isArray(p) ? p : p.results);
const nm = (n: I18n | string) => (typeof n === "string" ? n : n.uz ?? "");

export function MarketingTab() {
  return (
    <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr] [&>*]:min-w-0">
      <Banners />
      <Discounts />
    </div>
  );
}

function Banners() {
  const { toast } = useApp();
  const [rows, setRows] = useState<Banner[] | null>(null);
  const [f, setF] = useState({ title_uz: "", title_ru: "", sub_uz: "", sub_ru: "", link: "", color: "#5b21b6", image_url: "" });
  const [file, setFile] = useState<File | null>(null);
  const load = useCallback(async () => setRows(list(await api<Page<Banner>>("/admin/marketing/banners"))), []);
  useEffect(() => {
    load();
  }, [load]);

  const create = async () => {
    try {
      const form = new FormData();
      form.append("title", JSON.stringify({ uz: f.title_uz, ru: f.title_ru }));
      form.append("subtitle", JSON.stringify({ uz: f.sub_uz, ru: f.sub_ru }));
      form.append("link", f.link);
      form.append("color", f.color);
      form.append("sort", String(rows?.length ?? 0));
      form.append("is_active", "true"); // multipart'da yuborilmagan belgi "false" deb o'qiladi
      if (f.image_url) form.append("image_url", f.image_url);
      if (file) form.append("image", file);
      await apiUpload("/admin/marketing/banners", form);
      toast("Banner qo'shildi");
      setF({ ...f, title_uz: "", title_ru: "", sub_uz: "", sub_ru: "", image_url: "" });
      setFile(null);
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <Panel className="space-y-4">
      <h2 className="font-bold">Bosh sahifa bannerlari</h2>
      {!rows ? <Loading /> : rows.length === 0 ? <p className="text-sm text-zinc-500">Banner yo&apos;q — bosh sahifada kategoriyalar va narxlardan avtomatik banner chiqadi.</p> : null}
      <div className="space-y-2">
        {rows?.map((b) => (
          <div key={b.id} className="flex items-center gap-3 rounded-xl border border-line p-2">
            <span className="grid h-14 w-24 shrink-0 place-items-center overflow-hidden rounded-lg text-xs text-white" style={{ background: b.color }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {b.url ? <img src={b.url} alt="" className="h-full w-full object-cover" /> : nm(b.title).slice(0, 12)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{nm(b.title)}</p>
              <p className="truncate text-xs text-zinc-500">{b.link || "havolasiz"}</p>
            </div>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={b.is_active} onChange={async (e) => {
                await api(`/admin/marketing/banners/${b.id}`, { method: "PATCH", body: { is_active: e.target.checked } });
                await load();
              }} /> faol
            </label>
            <button className="px-2 text-red-600" onClick={async () => {
              await api(`/admin/marketing/banners/${b.id}`, { method: "DELETE" });
              await load();
            }}>×</button>
          </div>
        ))}
      </div>
      <div className="space-y-2 rounded-xl border border-dashed border-zinc-300 p-3">
        <p className="text-sm font-medium">Yangi banner</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <input placeholder="Sarlavha (uz)" value={f.title_uz} onChange={(e) => setF({ ...f, title_uz: e.target.value })} />
          <input placeholder="Sarlavha (ru)" value={f.title_ru} onChange={(e) => setF({ ...f, title_ru: e.target.value })} />
          <input placeholder="Matn (uz)" value={f.sub_uz} onChange={(e) => setF({ ...f, sub_uz: e.target.value })} />
          <input placeholder="Matn (ru)" value={f.sub_ru} onChange={(e) => setF({ ...f, sub_ru: e.target.value })} />
          <input placeholder="Havola: /c/smartfonlar" value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} />
          <label className="flex items-center gap-2 text-sm">Fon rangi
            <input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="h-10 w-16 !p-1" />
          </label>
          <input placeholder="Rasm havolasi (ixtiyoriy)" value={f.image_url} onChange={(e) => setF({ ...f, image_url: e.target.value })} />
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
        </div>
        <Button disabled={!f.title_uz} onClick={create}>Qo&apos;shish</Button>
      </div>
    </Panel>
  );
}

function Discounts() {
  const { toast } = useApp();
  const [cats, setCats] = useState<Opt[]>([]);
  const [brands, setBrands] = useState<Opt[]>([]);
  const [f, setF] = useState({ category: "", brand: "", percent: "10" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Page<Opt>>("/admin/categories?page_size=200").then((c) => setCats(list(c)));
    api<Page<Opt>>("/admin/brands?page_size=200").then((b) => setBrands(list(b)));
  }, []);

  const run = async (action: "apply" | "remove") => {
    setBusy(true);
    try {
      const r = await api<{ variants: number }>("/admin/marketing/discount", {
        method: "POST",
        body: { action, percent: Number(f.percent), category: f.category ? Number(f.category) : null, brand: f.brand ? Number(f.brand) : null },
      });
      toast(action === "apply" ? `Chegirma qo'yildi: ${r.variants} ta tovar` : `Chegirma olindi: ${r.variants} ta tovar`);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel className="h-fit space-y-3">
      <h2 className="font-bold">Ommaviy chegirma</h2>
      <p className="text-xs text-zinc-500">Eski narx — asl narx, yangi narx foiz bo&apos;yicha (1000 so&apos;mgacha yaxlitlanadi). Takroriy chegirma asl narxdan hisoblanadi.</p>
      <label className="block text-sm">Kategoriya
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="mt-1 w-full">
          <option value="">— barchasi emas —</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.parent ? "— " : ""}{nm(c.name)}</option>)}
        </select>
      </label>
      <label className="block text-sm">Brend
        <select value={f.brand} onChange={(e) => setF({ ...f, brand: e.target.value })} className="mt-1 w-full">
          <option value="">—</option>
          {brands.map((b) => <option key={b.id} value={b.id}>{nm(b.name)}</option>)}
        </select>
      </label>
      <label className="block text-sm">Chegirma, %
        <input value={f.percent} inputMode="numeric" onChange={(e) => setF({ ...f, percent: e.target.value.replace(/\D/g, "") })} className="mt-1 w-full" />
      </label>
      <div className="flex gap-2">
        <Button disabled={busy || (!f.category && !f.brand) || !f.percent} onClick={() => run("apply")}>Qo&apos;llash</Button>
        <Button variant="ghost" disabled={busy || (!f.category && !f.brand)} onClick={() => run("remove")}>Chegirmani olish</Button>
      </div>
    </Panel>
  );
}
