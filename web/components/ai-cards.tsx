"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, apiUpload } from "@/lib/api";
import type { CategoryNode } from "@/lib/types";

import { useApp } from "./providers";
import { errorText, sum } from "./staff";
import { IconChevron, IconSearch } from "./icons";
import { Button, Loading, Panel } from "./ui";

// Ta'minotchi faylidan AI (Groq) yordamida tovar kartochkalari: yuklash → to'ldirish → tekshirish → nashr.

type Batch = {
  id: number; file_name: string; columns: Record<string, string>; rows_total: number; currency: string;
  usd_rate: string | null; markup_percent: string | null; counts: Record<string, number>; created_at: string;
};
type DraftRow = {
  id: number; row_number: number; query: string; supplier_sku: string; purchase_price: string | null; qty: number | null;
  status: string; status_label: string; name: string; product_slug: string | null;
  image?: string; category?: string; cost_uzs?: string | null; suggested_price?: string | null;
  quality?: Quality | null;
};
type Quality = { score: number; issues: { code: string; label: string }[] };
/** Sifat bahosi rangi: 85+ yashil, 60+ sariq, pasti qizil. */
const qualityCls = (score: number) =>
  score >= 85 ? "bg-green-50 text-green-800" : score >= 60 ? "bg-amber-50 text-amber-800" : "bg-red-50 text-red-700";
const GOOD_SCORE = 85;
type Preview = {
  rows_total: number; columns: Record<string, string>; currency: string; with_price: number;
  price_min: string | null; price_max: string | null; usd_rate: string | null;
  sample: { sheet?: string; row: number; name: string; sku: string; price: string | null; qty: number | null }[];
  sheets?: { name: string; rows: number; with_price?: number; columns: Record<string, string> }[];
  max_rows?: number;
};
type PublishResult = { published: { id: number; name: string; price: string }[]; failed: { id: number; name: string; reason: string }[] };
type Result = {
  found?: boolean; confidence?: number | null; brand: string; model_code: string; category_slug: string;
  name: { uz: string; ru: string }; description: { uz: string; ru: string };
  warranty_months: number | null; weight_kg: number | null; is_bulky: boolean;
  attributes: Record<string, string | number | boolean>; images: string[]; sources?: { uri: string; title: string }[];
  specs?: Spec[];
  new_category?: { name: { uz: string; ru: string }; parent_slug: string } | null;
  image_report?: ImageReport | null;
};
/** Rasmlar qanday tanlangani: nechta nomzod, nechta rad etildi, AI qaysilarini ko'rib tasdiqladi. */
type ImageReport = {
  candidates?: number; rejected?: number; ai_removed?: number; unconfirmed?: number; vision?: string;
  vision_error?: string; seen?: Record<string, string>; colour_dropped?: number; colour_other?: number; info_dropped?: number;
};
type L = { uz: string; ru: string };
type Spec = { group: L; name: L; value: L };
type Market = { count: number; min?: number; max?: number; median?: number; suggested?: number; sources: { url: string; title: string; price: number }[] };
export type Draft = DraftRow & { raw: Record<string, string>; result: Result; warnings: string[]; error: string; model_used: string; cost_uzs?: string | null };
type AiProvider = {
  name: string; label: string; model: string; search: boolean; configured: boolean; missing: string;
  used_today: number; daily_cap: number | null; tokens_today?: number; cost_today_usd?: number | null;
};
type CheckRow = {
  name: string; label: string; configured: boolean; missing: string; ok?: boolean; error?: string; seconds?: number;
  served_model?: string; limits?: Record<string, string>; account?: Record<string, unknown>;
};
type Usage = {
  provider: string; model: string; search: boolean; used_today: number; daily_limit: number | null; usd_rate: string | null;
  providers: AiProvider[]; cost_today_usd?: number; daily_budget_usd?: string | null;
};
type Page<T> = { results: T[] } | T[];
const list = <T,>(p: Page<T>): T[] => (Array.isArray(p) ? p : p.results);

const STATUS_CLS: Record<string, string> = {
  pending: "bg-zinc-100 text-zinc-600",
  ready: "bg-amber-50 text-amber-800",
  not_found: "bg-zinc-100 text-zinc-500",
  failed: "bg-red-50 text-red-700",
  approved: "bg-green-50 text-green-800",
  rejected: "bg-zinc-100 text-zinc-400",
  duplicate: "bg-sky-50 text-sky-800",
};

/** Fayldagi narx: valyuta aniq bo'lsa ko'rsatiladi, aks holda faqat son. */
function supplierPrice(v: string | null, currency: string): string {
  if (!v) return "";
  if (currency === "UZS") return sum(v);
  const n = Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
  return currency === "USD" ? "$" + n : n;
}

const COLUMN_LABELS: Record<string, string> = { name: "Nomi", sku: "Artikul", price: "Xarid narxi", qty: "Soni", brand: "Brend" };

export function AiCardsTab() {
  const { toast } = useApp();
  const [batches, setBatches] = useState<Batch[] | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [rows, setRows] = useState<DraftRow[]>([]);
  const [open, setOpen] = useState<Draft | null>(null);
  const [zoom, setZoom] = useState<{ images: string[]; index: number } | null>(null);
  const [running, setRunning] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [limit, setLimit] = useState("");
  const stop = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Usage>("/admin/ai-cards/settings").then((u) => {
      setUsage(u);
      setLimit(u.daily_limit === null ? "" : String(u.daily_limit));
      setRate(u.usd_rate ? String(Math.round(Number(u.usd_rate))) : "");
    }).catch(() => setUsage(null));
  }, []);

  const [rate, setRate] = useState("");
  const [check, setCheck] = useState<CheckRow[] | null>(null);
  const [checking, setChecking] = useState(false);
  const runCheck = async () => {
    setChecking(true);
    try {
      const r = await api<{ providers: CheckRow[]; usage: Usage }>("/admin/ai-cards/check", { method: "POST" });
      setCheck(r.providers);
      setUsage(r.usage);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setChecking(false);
    }
  };
  const saveRate = async () => {
    try {
      const u = await api<Usage>("/admin/ai-cards/settings", { method: "PATCH", body: { usd_rate: rate === "" ? null : rate } });
      setUsage(u);
      toast(u.usd_rate ? `Kurs: 1 $ = ${Math.round(Number(u.usd_rate))} so'm` : "Kurs olib tashlandi");
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("all");
  const [publishing, setPublishing] = useState(false);
  const [result, setResult] = useState<PublishResult | null>(null);
  const [bs, setBs] = useState({ usd_rate: "", markup: "" });
  useEffect(() => {
    setBs({
      usd_rate: batch?.usd_rate ? String(Math.round(Number(batch.usd_rate))) : "",
      markup: batch?.markup_percent ? String(Number(batch.markup_percent)) : "",
    });
    setSelected(new Set());
    setResult(null);
  }, [batch?.id, batch?.usd_rate, batch?.markup_percent]);

  const saveBatchSettings = async () => {
    if (!batch) return;
    try {
      const b = await api<Batch>(`/admin/ai-cards/batches/${batch.id}/settings`, {
        method: "PATCH",
        body: { usd_rate: bs.usd_rate ? bs.usd_rate : null, markup_percent: bs.markup !== "" ? bs.markup : null },
      });
      setBatch(b);
      await loadRows(b);
      toast("Narxlar qayta hisoblandi");
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const publishSelected = async () => {
    if (!batch || !selected.size) return;
    if (!window.confirm(`${selected.size} ta tovar saytga chiqarilsinmi? Narx — foyda foizi bo'yicha.`)) return;
    setPublishing(true);
    try {
      const r = await api<PublishResult>(`/admin/ai-cards/batches/${batch.id}/publish`, { method: "POST", body: { ids: [...selected], publish: true } });
      setResult(r);
      setSelected(new Set());
      toast(`E'lon qilindi: ${r.published.length} ta${r.failed.length ? `, ${r.failed.length} tasi o'tmadi` : ""}`, r.failed.length && !r.published.length ? "error" : "ok");
      await loadRows(batch);
      await loadBatches();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setPublishing(false);
    }
  };

  const setCurrency = async (currency: string) => {
    if (!batch) return;
    try {
      setBatch(await api<Batch>(`/admin/ai-cards/batches/${batch.id}/currency`, { method: "POST", body: { currency } }));
      await loadBatches();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const [budget, setBudget] = useState("");
  useEffect(() => {
    if (usage) setBudget(usage.daily_budget_usd ? String(Number(usage.daily_budget_usd)) : "");
  }, [usage?.daily_budget_usd]); // eslint-disable-line react-hooks/exhaustive-deps
  const saveBudget = async () => {
    try {
      const u = await api<Usage>("/admin/ai-cards/settings", { method: "PATCH", body: { daily_budget_usd: budget === "" ? null : budget } });
      setUsage(u);
      toast(u.daily_budget_usd ? `Kunlik chegara: $${Number(u.daily_budget_usd)}` : "Chegara olib tashlandi");
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const saveLimit = async () => {
    try {
      const u = await api<Usage>("/admin/ai-cards/settings", { method: "PATCH", body: { daily_limit: limit === "" ? null : Number(limit) } });
      setUsage(u);
      toast(u.daily_limit === null ? "Kunlik limit olib tashlandi" : `Kunlik limit: ${u.daily_limit}`);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const loadBatches = useCallback(async () => {
    const b = list(await api<Page<Batch>>("/admin/ai-cards/batches"));
    setBatches(b);
    return b;
  }, []);
  const loadRows = useCallback(async (b: Batch) => {
    setRows(list(await api<Page<DraftRow>>(`/admin/ai-cards/drafts?batch=${b.id}&page_size=500`)));
    setBatch(await api<Batch>(`/admin/ai-cards/batches/${b.id}`));
  }, []);

  useEffect(() => {
    loadBatches().then((b) => b[0] && loadRows(b[0]));
  }, [loadBatches, loadRows]);

  const [preview, setPreview] = useState<Preview | null>(null);
  const [opts, setOpts] = useState({ currency: "", usd_rate: "", markup: "" });
  // Yuklanmaydigan (belgisi olib tashlangan) varaqlar; sukut bo'yicha hammasi yuklanadi.
  const [sheetsOff, setSheetsOff] = useState<Set<string>>(new Set());
  const multiSheet = (preview?.sheets?.length ?? 1) > 1;
  const pickedRows = preview
    ? multiSheet ? preview.sheets!.filter((s) => !sheetsOff.has(s.name)).reduce((n, s) => n + s.rows, 0) : preview.rows_total
    : 0;
  const tooMany = !!preview?.max_rows && pickedRows > preview.max_rows;

  const onPick = async () => {
    const file = fileRef.current?.files?.[0];
    setPreview(null);
    if (!file) return;
    try {
      const data = new FormData();
      data.append("file", file);
      const p = await apiUpload<Preview>("/admin/ai-cards/batches/preview", data);
      setPreview(p);
      setSheetsOff(new Set());
      setOpts((o) => ({ ...o, currency: p.currency, usd_rate: o.usd_rate || (p.usd_rate ? String(Math.round(Number(p.usd_rate))) : "") }));
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      if (opts.currency) form.append("currency", opts.currency);
      if (opts.currency === "USD" && opts.usd_rate) form.append("usd_rate", opts.usd_rate);
      if (opts.markup !== "") form.append("markup_percent", opts.markup);
      if (preview?.sheets && sheetsOff.size) {
        form.append("sheets", JSON.stringify(preview.sheets.filter((s) => !sheetsOff.has(s.name)).map((s) => s.name)));
      }
      const b = await apiUpload<Batch>("/admin/ai-cards/batches", form);
      toast(`${b.rows_total} ta tovar topildi`);
      if (fileRef.current) fileRef.current.value = "";
      setPreview(null);
      await loadBatches();
      await loadRows(b);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setUploading(false);
    }
  };

  const [categorizing, setCategorizing] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [fixInfo, setFixInfo] = useState("");
  const fixAll = async () => {
    if (!batch) return;
    setFixing(true);
    let total = 0;
    try {
      for (;;) {
        const r = await api<{ fixed: { id: number; actions: string[] }[]; remaining: number; usage: Usage }>(
          `/admin/ai-cards/batches/${batch.id}/autofix`, { method: "POST" });
        setUsage(r.usage);
        total += r.fixed.length;
        setFixInfo(`${total} ta, qoldi ${r.remaining}`);
        if (!r.fixed.length || r.remaining === 0) break;
      }
      toast(total ? `Avto-tuzatish: ${total} ta kartochka tekshirildi` : "Tuzatiladigan kartochka yo'q");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setFixing(false);
      setFixInfo("");
      await loadRows(batch);
    }
  };
  const categorize = async (onlyMissing: boolean) => {
    if (!batch) return;
    setCategorizing(true);
    try {
      const r = await api<{ total: number; matched: number; new: number; unchanged: number; usage: Usage }>(
        `/admin/ai-cards/batches/${batch.id}/categorize`, { method: "POST", body: { only_missing: onlyMissing } });
      setUsage(r.usage);
      toast(r.total ? `Kategoriya: ${r.matched} ta mavjudiga, ${r.new} ta yangi taklif, ${r.unchanged} ta aniqlanmadi` : "Kategoriyasiz kartochka yo'q");
      await loadRows(batch);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setCategorizing(false);
    }
  };

  const exportBatch = async () => {
    if (!batch) return;
    try {
      const data = await api(`/admin/ai-cards/batches/${batch.id}/export`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: "application/json" }));
      a.download = `${batch.file_name.replace(/\.[^.]+$/, "")}-ai-zaxira.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const importBackup = async (file: File) => {
    try {
      const form = new FormData();
      form.append("file", file);
      const b = await apiUpload<Batch>("/admin/ai-cards/batches/import", form);
      toast(`Zaxiradan tiklandi: ${b.rows_total} ta qator (AI so'rovi sarflanmadi)`);
      await loadBatches();
      await loadRows(b);
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  const run = async () => {
    if (!batch) return;
    setRunning(true);
    stop.current = false;
    try {
      for (;;) {
        const r = await api<{ draft: DraftRow | null; remaining: number; usage: Usage }>(`/admin/ai-cards/batches/${batch.id}/process`, { method: "POST" });
        setUsage(r.usage);
        if (r.draft) setRows((rs) => rs.map((x) => (x.id === r.draft!.id ? r.draft! : x)));
        if (!r.draft || r.remaining === 0 || stop.current) break;
      }
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setRunning(false);
      await loadRows(batch);
      await loadBatches();
    }
  };

  if (!batches) return <Loading />;
  const pending = rows.filter((r) => r.status === "pending").length;
  const done = rows.length - pending;

  return (
    <div className="grid gap-5 lg:grid-cols-[300px_1fr] [&>*]:min-w-0">
      <div className="space-y-4">
        <Panel>
          <h2 className="font-bold">Ta&apos;minotchi fayli</h2>
          <p className="mt-1 text-xs text-zinc-500">Excel (.xlsx). Barcha varaqlar o&apos;qiladi; nomi, artikul, xarid narxi va soni ustunlari avtomatik aniqlanadi.</p>
          <input ref={fileRef} type="file" accept=".xlsx" onChange={onPick} className="mt-3 w-full text-sm" />
          {preview ? (
            <div className="mt-3 space-y-3 rounded-xl bg-surface p-3 text-sm">
              <p><b>{preview.rows_total}</b> ta tovar topildi{preview.with_price ? `, ${preview.with_price} tasida narx bor` : ", narx ustuni yo'q"}.</p>
              {/* Varaqlar va tanilgan ustunlar: nom noto'g'ri ustundan olinsa — shu yerda ko'rinadi. */}
              {multiSheet ? (
                <p className="text-xs text-zinc-600">
                  Faylda {preview.sheets!.length} ta varaq bor — keraklilarini belgilang ({pickedRows} ta tovar tanlandi):
                </p>
              ) : null}
              <ul className="space-y-1 text-xs text-zinc-600">
                {(preview.sheets ?? [{ name: "", rows: preview.rows_total, columns: preview.columns }]).map((sh) => (
                  <li key={sh.name || "1"} className={`rounded-lg bg-white px-2 py-1.5 ${sheetsOff.has(sh.name) ? "opacity-50" : ""}`}>
                    {multiSheet ? (
                      <label className="mr-1 inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink">
                        <input type="checkbox" checked={!sheetsOff.has(sh.name)}
                          onChange={() => setSheetsOff((old) => { const next = new Set(old); if (next.has(sh.name)) next.delete(sh.name); else next.add(sh.name); return next; })} />
                        <b>{sh.name}: {sh.rows} ta ·</b>
                      </label>
                    ) : null}
                    nom — «{sh.columns.name}»
                    {sh.columns.sku ? `, artikul — «${sh.columns.sku}»` : ""}
                    {sh.columns.price ? `, narx — «${sh.columns.price}»` : ""}
                    {sh.columns.qty ? `, soni — «${sh.columns.qty}»` : ""}
                  </li>
                ))}
              </ul>
              {preview.with_price ? (
                <>
                  <label className="block">Narx valyutasi
                    <select value={opts.currency} onChange={(e) => setOpts({ ...opts, currency: e.target.value })} className="mt-1 w-full">
                      <option value="">— tanlang —</option>
                      <option value="USD">Dollar ($)</option>
                      <option value="UZS">So&apos;m</option>
                    </select>
                    <span className={`mt-1 block text-xs ${preview.currency ? "text-zinc-500" : "text-amber-700"}`}>
                      {preview.currency ? `Fayldan aniqlandi: ${preview.currency === "USD" ? "dollar" : "so'm"}` : "Faylda valyuta belgisi yo'q — tanlang"}
                      {preview.price_min ? ` · narxlar ${Number(preview.price_min).toLocaleString("ru-RU")} – ${Number(preview.price_max).toLocaleString("ru-RU")}` : ""}
                    </span>
                  </label>
                  {opts.currency === "USD" ? (
                    <label className="block">Kurs: 1 $ = ? so&apos;m
                      <input value={opts.usd_rate} inputMode="numeric" onChange={(e) => setOpts({ ...opts, usd_rate: e.target.value.replace(/[^\d.]/g, "") })} placeholder="12800" className="mt-1 w-full" />
                    </label>
                  ) : null}
                  <label className="block">Foyda, % (barcha tovarga)
                    <input value={opts.markup} inputMode="decimal" onChange={(e) => setOpts({ ...opts, markup: e.target.value.replace(/[^\d.]/g, "") })} placeholder="masalan 25" className="mt-1 w-full" />
                    <span className="mt-1 block text-xs text-zinc-500">Sotuv narxi = tannarx × (1 + foyda %), 1 000 so&apos;mgacha yaxlitlanadi. Keyin o&apos;zgartirsa bo&apos;ladi.</span>
                  </label>
                </>
              ) : null}
              <div className="max-h-40 overflow-auto text-xs">
                {preview.sample.map((x) => (
                  <p key={`${x.sheet ?? ""}-${x.row}`} className="flex gap-2 border-b border-line py-1 last:border-0">
                    <span className="min-w-0 flex-1 truncate">{x.sheet ? <span className="text-zinc-400">{x.sheet}: </span> : null}{x.name}</span>
                    {x.price ? <span className="shrink-0 text-zinc-500">{opts.currency === "USD" ? "$" : ""}{Number(x.price).toLocaleString("ru-RU")}</span> : null}
                  </p>
                ))}
              </div>
            </div>
          ) : null}
          {tooMany ? (
            <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
              Bir yuklashda ko&apos;pi bilan {preview!.max_rows} ta tovar bo&apos;lishi mumkin — ba&apos;zi varaqlar belgisini olib, bo&apos;lib yuklang.
            </p>
          ) : null}
          <Button className="mt-3 w-full" disabled={uploading || !preview || pickedRows === 0 || tooMany || (preview.with_price > 0 && (!opts.currency || (opts.currency === "USD" && !opts.usd_rate)))} onClick={upload}>
            {uploading ? "Yuklanmoqda…" : preview ? `Yuklash (${pickedRows} ta)` : "Faylni tanlang"}
          </Button>
          <label className="mt-3 block cursor-pointer text-center text-xs text-brand underline">
            Zaxiradan tiklash (.json)
            <input type="file" accept=".json,application/json" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importBackup(f); e.target.value = ""; }} />
          </label>
        </Panel>
        {usage ? (
          <Panel>
            <h2 className="font-bold">AI</h2>
            <p className="mt-1 text-xs text-zinc-500">Tartib bo&apos;yicha: birinchi ulangani ishlaydi, kvota tugasa yoki xato bo&apos;lsa — keyingisi.</p>
            <ol className="mt-2 space-y-1">
              {usage.providers.map((p, i) => (
                <li key={p.name} className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${p.configured ? "bg-surface" : "text-zinc-400"}`}>
                  <span className={`h-2 w-2 shrink-0 rounded-full ${p.configured ? "bg-green-500" : "bg-zinc-300"}`} />
                  <span className="min-w-0 flex-1 truncate" title={p.model}>
                    {p.label}{p.search ? " 🔎" : ""}{p.configured ? "" : ` — ${p.missing} yo'q`}
                  </span>
                  <span className="shrink-0 text-xs text-zinc-500">
                    {p.configured ? `${p.used_today}${p.daily_cap ? `/${p.daily_cap}` : ""}` : ""}
                    {p.configured && p.tokens_today ? ` · ${(p.tokens_today / 1000).toFixed(p.tokens_today < 10000 ? 1 : 0)}k token` : ""}
                    {p.cost_today_usd ? ` · $${p.cost_today_usd.toFixed(3)}` : ""}
                  </span>
                  <button aria-label="yuqoriga" disabled={i === 0} className="px-1 disabled:opacity-30"
                    onClick={async () => {
                      const names = usage.providers.map((x) => x.name);
                      [names[i - 1], names[i]] = [names[i], names[i - 1]];
                      try {
                        setUsage(await api<Usage>("/admin/ai-cards/settings", { method: "PATCH", body: { provider_order: names } }));
                      } catch (e) {
                        toast(errorText(e), "error");
                      }
                    }}>↑</button>
                </li>
              ))}
            </ol>
            <p className="mt-1 text-xs text-zinc-400">
              Raqam — bugungi so&apos;rovlar / kunlik chegara (bepul limitdan oshmaslik uchun; to&apos;lsa keyingisiga o&apos;tiladi).
              Barcha ishni avval Groq bajaradi: kartochka yozish, havoladan nusxa, kategoriya va rasm tanlash. Limiti tugasa —
              tiklanguncha zaxiralar (Cerebras, OpenRouter...). Internet qidiruvini tizimning o&apos;zi bepul qiladi (DuckDuckGo/Bing +
              sahifani o&apos;qish), topilgan ma&apos;lumot 7 kun saqlanadi. 🔎 — internetdan o&apos;zi qidiradi.
              Rasmlar: avval &quot;aynan shu modelnikimi&quot; deb saralanadi (model kodi, sahifa nomi, rasm tavsifi), keyin AI rasmning o&apos;ziga qarab
              tekshiradi — boshqa tovar, aksessuar yoki banner rasmi olinmaydi. Kalitlar Space sozlamalarida (Secrets).
            </p>
            <Button variant="ghost" className="mt-2 w-full" disabled={checking} onClick={runCheck}>
              {checking ? "Tekshirilmoqda…" : "Xizmatlarni tekshirish (har biriga 1 so'rov)"}
            </Button>
            {check ? (
              <ul className="mt-2 space-y-1 text-xs">
                {check.filter((c) => c.configured).map((c) => (
                  <li key={c.name} className={`rounded-lg p-2 ${c.ok ? "bg-green-50 text-green-900" : "bg-red-50 text-red-800"}`}>
                    <b>{c.label}</b>: {c.ok ? `ishlaydi, ${c.seconds} s` : c.error}
                    {c.name === "vision" && c.ok && c.served_model ? <span className="block text-zinc-600">model: {c.served_model}</span> : null}
                    {c.limits && Object.keys(c.limits).length ? (
                      <span className="block text-zinc-600">
                        {Object.entries(c.limits).filter(([k]) => /limit|remaining/.test(k)).map(([k, v]) => `${k.replace("x-ratelimit-", "")}: ${v}`).join(" · ")}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="mt-2 text-sm">
              Bugun: <b>{usage.used_today}</b>{usage.daily_limit !== null ? ` / ${usage.daily_limit}` : ""} ta so&apos;rov
            </p>
            <div className="mt-2 flex gap-2">
              <input value={limit} onChange={(e) => setLimit(e.target.value.replace(/\D/g, ""))} inputMode="numeric"
                placeholder="cheklovsiz" className="w-full min-w-0" aria-label="Kunlik limit" />
              <Button variant="ghost" className="shrink-0" onClick={saveLimit}>Saqlash</Button>
            </div>
            <p className="mt-1 text-xs text-zinc-400">Kunlik limit — bepul limitdan oshmaslik uchun. Bo&apos;sh — cheklovsiz.</p>
            <p className="mt-3 text-sm">
              Groq xarajati bugun: <b>${(usage.cost_today_usd ?? 0).toFixed(3)}</b>
              {usage.daily_budget_usd ? ` / $${Number(usage.daily_budget_usd)}` : ""}
            </p>
            <div className="mt-1 flex gap-2">
              <input value={budget} onChange={(e) => setBudget(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal"
                placeholder="chegara yo'q" className="w-full min-w-0" aria-label="Kunlik xarajat chegarasi, $" />
              <Button variant="ghost" className="shrink-0" onClick={saveBudget}>Saqlash</Button>
            </div>
            <p className="mt-1 text-xs text-zinc-400">
              Kunlik chegara ($). Yetganda Groq to&apos;xtaydi, bepul zaxiralar (Cerebras va h.k.) ishlaydi.
              Bepul tarifda haqiqiy to&apos;lov yo&apos;q — raqam pullik tarifda qancha bo&apos;lishini ko&apos;rsatadi.
            </p>
            <p className="mt-3 text-sm">Dollar kursi (1 $ = ? so&apos;m)</p>
            <div className="mt-1 flex gap-2">
              <input value={rate} onChange={(e) => setRate(e.target.value.replace(/\D/g, ""))} inputMode="numeric"
                placeholder="kiritilmagan" className="w-full min-w-0" aria-label="Dollar kursi" />
              <Button variant="ghost" className="shrink-0" onClick={saveRate}>Saqlash</Button>
            </div>
            <p className="mt-1 text-xs text-zinc-400">Ta&apos;minotchi narxi dollarda bo&apos;lsa, tannarx shu kurs bo&apos;yicha so&apos;mga o&apos;giriladi.</p>
          </Panel>
        ) : null}
        <div className="space-y-2">
          {batches.map((b) => (
            <button key={b.id} onClick={() => loadRows(b)}
              className={`w-full rounded-xl border p-3 text-left text-sm ${batch?.id === b.id ? "border-ink" : "border-line hover:border-zinc-400"}`}>
              <p className="truncate font-medium">{b.file_name}</p>
              <p className="text-xs text-zinc-500">
                {b.rows_total} ta · tayyor {b.counts.ready ?? 0} · nashr {b.counts.approved ?? 0}
              </p>
            </button>
          ))}
        </div>
      </div>

      <div>
        {!batch ? (
          <Panel><p className="text-sm text-zinc-500">Ta&apos;minotchi faylini yuklang — har bir qator uchun tizim internetdan ma&apos;lumot topadi, AI (Groq) kartochka tayyorlaydi. Kartochka siz tekshirib nashr qilmaguncha saytda chiqmaydi.</p></Panel>
        ) : (
          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-bold">{batch.file_name}</h2>
                <p className="text-xs text-zinc-500">
                  Narx valyutasi:{" "}
                  <select value={batch.currency} onChange={(e) => setCurrency(e.target.value)} className="!px-2 !py-0.5 text-xs">
                    <option value="">aniqlanmadi</option>
                    <option value="UZS">so&apos;m</option>
                    <option value="USD">dollar</option>
                  </select>{" "}·{" "}
                  Ustunlar: {Object.entries(batch.columns).map(([k, v]) => `${COLUMN_LABELS[k] ?? k} — «${v}»`).join(", ")}
                </p>
                <div className="mt-2 flex flex-wrap items-end gap-2 text-xs">
                  {batch.currency === "USD" ? (
                    <label>Kurs (1 $ = so&apos;m)
                      <input value={bs.usd_rate} inputMode="numeric" onChange={(e) => setBs({ ...bs, usd_rate: e.target.value.replace(/[^\d.]/g, "") })} placeholder={usage?.usd_rate ? String(Math.round(Number(usage.usd_rate))) : "12800"} className="mt-0.5 block w-28 !py-1 text-sm" />
                    </label>
                  ) : null}
                  <label>Foyda, %
                    <input value={bs.markup} inputMode="decimal" onChange={(e) => setBs({ ...bs, markup: e.target.value.replace(/[^\d.]/g, "") })} placeholder="25" className="mt-0.5 block w-20 !py-1 text-sm" />
                  </label>
                  <Button variant="ghost" onClick={saveBatchSettings}>Narxlarni hisoblash</Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" onClick={exportBatch}>Zaxira (JSON)</Button>
                <Button variant="ghost" disabled={running || fixing} onClick={fixAll}>
                  {fixing ? `Tuzatilmoqda… ${fixInfo}` : "Hammasini avto-tuzatish"}
                </Button>
                <Button variant="ghost" disabled={running || categorizing} onClick={() => categorize(true)}>
                  {categorizing ? "AI kategoriyalarni aniqlamoqda…" : "Kategoriyalarni AI aniqlasin"}
                </Button>
                {!running && (batch.counts.failed ?? 0) > 0 ? (
                  <Button variant="ghost" onClick={async () => {
                    try {
                      await api(`/admin/ai-cards/batches/${batch.id}/retry-failed`, { method: "POST" });
                      await loadRows(batch);
                      await loadBatches();
                    } catch (e) {
                      toast(errorText(e), "error");
                    }
                  }}>
                    Xatolarni qayta navbatga ({batch.counts.failed})
                  </Button>
                ) : null}
                {running ? (
                  <Button variant="ghost" onClick={() => { stop.current = true; }}>To&apos;xtatish</Button>
                ) : (
                  <Button disabled={pending === 0} onClick={run}>AI bilan to&apos;ldirish ({pending})</Button>
                )}
              </div>
            </div>
            {running || (done > 0 && pending > 0) ? (
              <div className="mt-3">
                <div className="h-1.5 overflow-hidden rounded-full bg-surface">
                  <div className="h-full bg-brand transition-all" style={{ width: `${(done / Math.max(rows.length, 1)) * 100}%` }} />
                </div>
                <p className="mt-1 text-xs text-zinc-500">{done} / {rows.length}{running ? " — qidirilmoqda va yozilmoqda…" : ""}</p>
              </div>
            ) : null}
            {(() => {
              const FILTERS: [string, string][] = [["all", "Hammasi"], ["ready", "Tayyor"], ["pending", "Navbatda"], ["not_found", "Topilmadi"], ["failed", "Xato"], ["duplicate", "Katalogda bor"], ["approved", "E'lon qilingan"]];
              const shown = rows.filter((r) => filter === "all" || r.status === filter);
              const selectable = shown.filter((r) => r.status === "ready");
              const allOn = selectable.length > 0 && selectable.every((r) => selected.has(r.id));
              const toggle = (id: number) => setSelected((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n; });
              return (
                <>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    {FILTERS.map(([k, l]) => {
                      const n = k === "all" ? rows.length : rows.filter((r) => r.status === k).length;
                      return n || k === "all" ? (
                        <button key={k} onClick={() => setFilter(k)} className={`rounded-full px-3 py-1 text-xs ${filter === k ? "bg-ink text-white" : "bg-surface text-zinc-600"}`}>{l} {n}</button>
                      ) : null;
                    })}
                  </div>
                  <div className="sticky top-14 z-10 mt-3 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-white/95 px-3 py-2 text-sm backdrop-blur">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={allOn} disabled={!selectable.length}
                        onChange={() => setSelected((cur) => { const n = new Set(cur); selectable.forEach((r) => (allOn ? n.delete(r.id) : n.add(r.id))); return n; })} />
                      Hammasini belgilash ({selectable.length} ta tayyor)
                    </label>
                    <button
                      disabled={!selectable.some((r) => (r.quality?.score ?? 0) >= GOOD_SCORE)}
                      onClick={() => setSelected(new Set(selectable.filter((r) => (r.quality?.score ?? 0) >= GOOD_SCORE && r.suggested_price).map((r) => r.id)))}
                      className="text-brand underline disabled:text-zinc-400 disabled:no-underline"
                      title={`Sifati ${GOOD_SCORE}% dan yuqori va narxi hisoblangan kartochkalar`}>
                      Faqat sifatlilarini ({selectable.filter((r) => (r.quality?.score ?? 0) >= GOOD_SCORE && r.suggested_price).length})
                    </button>
                    <span className="text-zinc-500">Belgilangan: {selected.size}</span>
                    <Button className="ml-auto" disabled={!selected.size || publishing} onClick={publishSelected}>
                      {publishing ? "E'lon qilinmoqda…" : `Belgilanganlarni e'lon qilish (${selected.size})`}
                    </Button>
                  </div>
                  {result?.failed.length ? (
                    <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                      <p className="font-medium">E&apos;lon qilinmadi ({result.failed.length}):</p>
                      <ul className="mt-1 space-y-0.5">{result.failed.map((f) => <li key={f.id}>{f.name} — {f.reason}</li>)}</ul>
                    </div>
                  ) : null}
                  <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
                    {shown.map((r) => (
                      <div key={r.id} className={`relative flex flex-col overflow-hidden rounded-xl border bg-white transition ${selected.has(r.id) ? "border-brand ring-2 ring-brand/30" : "border-line hover:shadow-md"}`}>
                        {r.status === "ready" ? (
                          <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)}
                            className="absolute left-2 top-2 z-10 h-5 w-5 cursor-pointer" aria-label="Belgilash" />
                        ) : null}
                        <span className={`absolute right-2 top-2 z-10 rounded-md px-1.5 py-0.5 text-[11px] ${STATUS_CLS[r.status] ?? ""}`}>{r.status_label}</span>
                        {r.quality && r.status === "ready" ? (
                          <span title={r.quality.issues.map((i) => i.label).join("\n") || "Kamchilik topilmadi"}
                            className={`absolute right-2 top-8 z-10 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${qualityCls(r.quality.score)}`}>
                            Sifat {r.quality.score}%
                          </span>
                        ) : null}
                        {r.image ? (
                          <span className="pointer-events-none absolute inset-x-0 top-0 z-10 block aspect-square">
                            <button title="Rasmni kattalashtirish" aria-label="Rasmni kattalashtirish"
                              onClick={async () => {
                                const first = r.image!;
                                setZoom({ images: [first], index: 0 });
                                // Asosiy rasm darhol ochiladi; kartochkaning qolgan rasmlari yuklangach qo'shiladi.
                                const d = await api<Draft>(`/admin/ai-cards/drafts/${r.id}`).catch(() => null);
                                const all = d?.result?.images ?? [];
                                if (all.length > 1) setZoom((z) => (z && z.images.length === 1 && z.images[0] === first ? { images: all, index: Math.max(0, all.indexOf(first)) } : z));
                              }}
                              className="pointer-events-auto absolute bottom-2 right-2 grid h-8 w-8 place-items-center rounded-full bg-white/95 text-zinc-600 shadow ring-1 ring-black/10 transition hover:bg-brand hover:text-white">
                              <IconSearch className="h-4 w-4" />
                            </button>
                          </span>
                        ) : null}
                        <button disabled={r.status === "pending"} onClick={async () => setOpen(await api<Draft>(`/admin/ai-cards/drafts/${r.id}`))}
                          className="flex flex-1 flex-col text-left disabled:cursor-default">
                          <span className="block aspect-square w-full bg-white p-3">
                            {r.image ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={r.image} alt="" className="h-full w-full object-contain" loading="lazy" />
                            ) : (
                              <span className="flex h-full items-center justify-center text-xs text-zinc-400">{r.status === "pending" ? "Navbatda" : "Rasm yo'q"}</span>
                            )}
                          </span>
                          <span className="flex flex-1 flex-col gap-1 border-t border-line p-2.5">
                            <span className="line-clamp-2 min-h-[2.5rem] text-[13px] font-medium leading-5">{r.name || r.query}</span>
                            {r.status === "ready" || r.status === "approved" ? (
                              <span className={`truncate text-[11px] ${r.category ? (r.category.startsWith("+") ? "text-brand" : "text-zinc-500") : "text-red-600"}`}>
                                {r.category ? (r.category.startsWith("+") ? `Yangi kategoriya: ${r.category.slice(2)}` : r.category) : "Kategoriya yo'q"}
                              </span>
                            ) : null}
                            <span className="mt-auto flex items-end justify-between gap-1 text-[12px]">
                              <span className="text-zinc-400">{r.cost_uzs ? `tannarx ${sum(r.cost_uzs)}` : r.purchase_price ? supplierPrice(r.purchase_price, batch.currency) : ""}</span>
                              {r.suggested_price ? <b className="text-[13px]">{sum(r.suggested_price)}</b> : null}
                            </span>
                          </span>
                        </button>
                      </div>
                    ))}
                  </div>
                </>
              );
            })()}
          </Panel>
        )}
      </div>

      {open ? (
        <Review draft={open} currency={batch?.currency ?? ""} onClose={() => setOpen(null)}
          onChanged={async (d) => {
            if (d) setOpen(d);
            else setOpen(null);
            if (batch) await loadRows(batch);
            await loadBatches();
          }} />
      ) : null}
      {zoom ? (
        <Lightbox images={zoom.images} index={zoom.index} onIndex={(index) => setZoom((z) => (z ? { ...z, index } : z))} onClose={() => setZoom(null)} />
      ) : null}
    </div>
  );
}

/** Rasmni to'liq ekranda ko'rish: oldingi/keyingi, klaviatura (← → Esc), rasm o'lchami va manbasi. */
export function Lightbox({ images, index, onIndex, onClose, actions, seen }: {
  images: string[]; index: number; onIndex: (i: number) => void; onClose: () => void;
  actions?: (url: string, i: number) => React.ReactNode;
  /** AI ko'rib tasdiqlagan rasmlar: havola → rasmda nima ko'ringani. */
  seen?: Record<string, string>;
}) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const n = images.length;
  const i = Math.min(index, n - 1);
  const url = images[i];
  useEffect(() => setSize(null), [url]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight" && n > 1) onIndex((i + 1) % n);
      if (e.key === "ArrowLeft" && n > 1) onIndex((i - 1 + n) % n);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [i, n, onClose, onIndex]);
  if (!url) return null;
  let host = "";
  try { host = new URL(url, window.location.href).hostname.replace(/^www\./, ""); } catch { /* nisbiy manzil */ }
  const small = size ? Math.min(size.w, size.h) < 600 : false;
  const arrow = "absolute top-1/2 grid h-11 w-11 -translate-y-1/2 place-items-center rounded-full bg-black/55 text-white shadow-lg ring-1 ring-white/40 transition hover:bg-black/80";
  return (
    <div className="fixed inset-0 z-[70] !m-0 flex animate-[fadeIn_.15s_ease-out] flex-col bg-black/90" onClick={onClose}>
      <div className="flex items-center gap-3 px-4 py-3 text-sm text-white" onClick={(e) => e.stopPropagation()}>
        <span className="shrink-0 whitespace-nowrap font-medium">{i + 1} / {n}</span>
        {size ? (
          <span className={`shrink-0 whitespace-nowrap rounded-md px-2 py-0.5 text-xs ${small ? "bg-amber-400 text-black" : "bg-white/15"}`}>
            {size.w} × {size.h} px{small ? " · kichik" : ""}
          </span>
        ) : null}
        {seen && seen[url] !== undefined ? (
          <span title={seen[url]} className="shrink-0 whitespace-nowrap rounded-md bg-green-500 px-2 py-0.5 text-xs font-medium text-white">✓ AI ko&apos;rib tasdiqlagan</span>
        ) : null}
        {host ? <span className="hidden truncate text-white/60 sm:inline">{host}</span> : null}
        <span className="flex-1" />
        <a href={url} target="_blank" rel="noreferrer" className="shrink-0 whitespace-nowrap rounded-lg bg-white/15 px-3 py-1.5 hover:bg-white/30">Asl rasm<span className="hidden sm:inline">ni ochish</span></a>
        <button onClick={onClose} aria-label="Yopish" className="grid h-9 w-9 place-items-center rounded-full bg-white/15 text-2xl leading-none hover:bg-white/30">×</button>
      </div>
      <div className="relative min-h-0 flex-1 px-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={url} src={url} alt="" referrerPolicy="no-referrer" onClick={(e) => e.stopPropagation()}
          onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          className="mx-auto h-full max-w-full rounded-lg bg-white object-contain" />
        {n > 1 ? (
          <>
            <button aria-label="Oldingi" onClick={(e) => { e.stopPropagation(); onIndex((i - 1 + n) % n); }} className={`${arrow} left-3`}>
              <IconChevron className="h-6 w-6 rotate-180" />
            </button>
            <button aria-label="Keyingi" onClick={(e) => { e.stopPropagation(); onIndex((i + 1) % n); }} className={`${arrow} right-3`}>
              <IconChevron className="h-6 w-6" />
            </button>
          </>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2 px-4 py-3" onClick={(e) => e.stopPropagation()}>
        {n > 1 ? images.map((u, k) => (
          <button key={u} onClick={() => onIndex(k)} aria-label={`Rasm ${k + 1}`}
            className={`h-14 w-14 shrink-0 overflow-hidden rounded-lg bg-white ring-2 transition ${k === i ? "ring-brand" : "opacity-60 ring-transparent hover:opacity-100"}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={u} alt="" referrerPolicy="no-referrer" className="h-full w-full object-contain" />
          </button>
        )) : null}
        {actions ? <span className="flex gap-2 sm:ml-4">{actions(url, i)}</span> : null}
      </div>
    </div>
  );
}

export function Review({ draft, currency, onClose, onChanged }: { draft: Draft; currency: string; onClose: () => void; onChanged: (d: Draft | null) => Promise<void> }) {
  const { toast } = useApp();
  const [r, setR] = useState<Result>(draft.result);
  const [cats, setCats] = useState<{ slug: string; name: string }[]>([]);
  const [price, setPrice] = useState(draft.suggested_price ? String(Math.round(Number(draft.suggested_price))) : "");
  const [sku, setSku] = useState(draft.supplier_sku);
  const [publish, setPublish] = useState(true);
  const [zoom, setZoom] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const editable = draft.status === "ready";

  const [roots, setRoots] = useState<{ id: number; slug: string; name: string }[]>([]);
  const [market, setMarket] = useState<Market | null>(null);
  const [marketBusy, setMarketBusy] = useState(false);
  const loadMarket = async () => {
    setMarketBusy(true);
    try {
      const q = [r.brand, r.model_code].filter(Boolean).join(" ") || draft.query;
      setMarket(await api<Market>("/admin/ai-cards/market-price", { method: "POST", body: { query: q } }));
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setMarketBusy(false);
    }
  };
  const [newCat, setNewCat] = useState<{ uz: string; ru: string; parent: string } | null>(null);

  useEffect(() => setR(draft.result), [draft]);
  useEffect(() => setMarket(null), [draft.id]);
  const loadCats = () =>
    api<CategoryNode[]>("/categories").then((tree) => {
      setCats(tree.flatMap((root) => (root.children.length ? root.children : [root])).map((c) => ({ slug: c.slug, name: c.name })));
      setRoots(tree.map((c) => ({ id: c.id, slug: c.slug, name: c.name })));
    });
  useEffect(() => {
    loadCats();
  }, []);

  const createCategory = async () => {
    if (!newCat?.uz.trim()) return;
    setBusy(true);
    try {
      const c = await api<{ slug: string }>("/admin/categories", {
        method: "POST",
        body: {
          name: { uz: newCat.uz.trim(), ru: newCat.ru.trim() },
          parent: newCat.parent ? Number(newCat.parent) : null,
          is_active: true,
        },
      });
      await loadCats();
      setR({ ...r, category_slug: c.slug, attributes: {} });
      setNewCat(null);
      toast("Kategoriya yaratildi");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };

  const act = async (fn: () => Promise<Draft | null>, ok: string) => {
    setBusy(true);
    try {
      const d = await fn();
      toast(ok);
      await onChanged(d);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const save = () =>
    api<Draft>(`/admin/ai-cards/drafts/${draft.id}`, {
      method: "PATCH",
      body: {
        brand: r.brand, model_code: r.model_code, category_slug: r.category_slug, name: r.name, description: r.description,
        warranty_months: r.warranty_months, weight_kg: r.weight_kg, is_bulky: r.is_bulky, images: r.images, specs: r.specs ?? [],
        new_category: r.category_slug ? null : r.new_category ?? null,
        attributes: Object.fromEntries(Object.keys(draft.result.attributes ?? {}).map((k) => [k, k in r.attributes ? r.attributes[k] : null])),
      },
    });

  const field = (label: string, value: string, set: (v: string) => void, area = false) => (
    <label className="block text-sm">{label}
      {area ? (
        <textarea value={value} onChange={(e) => set(e.target.value)} disabled={!editable} rows={Math.min(14, Math.max(5, Math.ceil(value.length / 90)))} className="mt-1 w-full" />
      ) : (
        <input value={value} onChange={(e) => set(e.target.value)} disabled={!editable} className="mt-1 w-full" />
      )}
    </label>
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-zinc-500">{draft.raw?.Varaq ? `${draft.raw.Varaq} · ` : ""}Qator {draft.row_number} · {draft.query}</p>
            <h3 className="text-lg font-bold">{r.name?.uz || draft.query}</h3>
            <p className="text-xs text-zinc-400">{draft.status_label}{draft.model_used ? ` · ${draft.model_used}` : ""}{r.confidence != null ? ` · ishonch ${Math.round(r.confidence * 100)}%` : ""}</p>
          </div>
          <button onClick={onClose} className="text-2xl leading-none text-zinc-400 hover:text-ink">×</button>
        </div>

        {draft.error ? (
          <p className={`mb-3 rounded-lg p-3 text-sm ${draft.status === "duplicate" ? "bg-sky-50 text-sky-900" : "bg-red-50 text-red-700"}`}>
            {draft.error}
            {draft.status === "duplicate" && draft.product_slug ? (
              <> <a href={`/p/${draft.product_slug}`} target="_blank" rel="noreferrer" className="font-medium underline">Tovarni ochish</a></>
            ) : null}
          </p>
        ) : null}
        {draft.quality && draft.status === "ready" ? (
          <div className="mb-3 rounded-lg border border-line p-3 text-sm">
            <div className="flex items-center gap-2">
              <span className={`rounded-md px-2 py-0.5 font-semibold ${qualityCls(draft.quality.score)}`}>Sifat {draft.quality.score}%</span>
              <span className="text-zinc-500">
                {draft.quality.issues.length ? "Nashrdan oldin tekshiring:" : "Kamchilik topilmadi — nashrga tayyor."}
              </span>
            </div>
            {draft.quality.issues.length ? (
              <ul className="mt-2 grid gap-x-4 gap-y-0.5 text-[13px] text-zinc-700 sm:grid-cols-2">
                {draft.quality.issues.map((i) => <li key={i.code}>• {i.label}</li>)}
              </ul>
            ) : null}
          </div>
        ) : null}
        {draft.warnings.length ? (
          <ul className="mb-4 space-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            {draft.warnings.map((w, i) => <li key={i}>• {w}</li>)}
          </ul>
        ) : null}

        {draft.status === "ready" || draft.status === "approved" ? (
          <div className="space-y-4">
            {r.images.length ? (
              <div className="flex flex-wrap gap-2">
                {r.images.map((u, k) => (
                  <div key={u} className={`group relative h-28 w-28 overflow-hidden rounded-xl border bg-white ${k === 0 ? "border-brand" : "border-line"}`}>
                    <button onClick={() => setZoom(k)} title="Kattalashtirish" className="block h-full w-full cursor-zoom-in">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={u} alt="" className="h-full w-full object-contain" referrerPolicy="no-referrer" />
                      <span className="pointer-events-none absolute bottom-1 right-1 grid h-6 w-6 place-items-center rounded-full bg-white/95 text-zinc-600 shadow ring-1 ring-black/10">
                        <IconSearch className="h-3.5 w-3.5" />
                      </span>
                    </button>
                    {k === 0 ? <span className="pointer-events-none absolute left-1 top-1 rounded bg-brand px-1.5 text-[10px] font-semibold leading-4 text-white">Asosiy</span> : null}
                    {r.image_report?.seen?.[u] !== undefined ? (
                      <span title={`AI ko'rib tasdiqlagan: ${r.image_report.seen[u]}`}
                        className="pointer-events-none absolute bottom-1 left-1 grid h-5 w-5 place-items-center rounded-full bg-green-500 text-[11px] font-bold text-white shadow">✓</span>
                    ) : null}
                    {editable ? (
                      <button onClick={() => setR({ ...r, images: r.images.filter((x) => x !== u) })}
                        className="absolute right-1 top-1 grid h-6 w-6 place-items-center rounded-full bg-white/90 text-sm">×</button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-zinc-500">Rasm topilmadi — nashrdan keyin admin panelda yuklang.</p>}
            {r.image_report?.candidates ? (
              <p className="-mt-2 text-xs text-zinc-500">
                Rasm tekshiruvi: {r.image_report.candidates} ta nomzoddan {r.image_report.rejected ?? 0} tasi boshqa tovar yoki begona sahifaniki deb olinmadi
                {r.image_report.vision
                  ? `; AI rasmlarni ko'rib chiqdi${r.image_report.ai_removed ? ` va ${r.image_report.ai_removed} tasini rad etdi` : ""}${r.image_report.unconfirmed ? `, ${r.image_report.unconfirmed} tasini tasdiqlamadi` : ""}. ✓ — AI tasdiqlagan rasm.`
                  : `; AI rasmlarni ko'ra olmadi${r.image_report.vision_error ? ` (${r.image_report.vision_error})` : ""}${r.image_report.unconfirmed ? ` — dalilsiz ${r.image_report.unconfirmed} ta rasm olinmadi` : ""}. «Avto-tuzatish» keyinroq qayta tekshiradi.`}
                {r.image_report.colour_dropped ? ` Boshqa rangdagi ${r.image_report.colour_dropped} ta surat olinmadi.` : ""}
                {r.image_report.colour_other ? ` Diqqat: ${r.image_report.colour_other} ta surat boshqa rangdagi variantga o'xshaydi — tekshirib ko'ring.` : ""}
                {" "}Eng sifatli toza surat birinchi qo'yilgan; nashrda suratlar kvadrat qilib tekislanadi.
              </p>
            ) : null}
            {zoom !== null && r.images.length ? (
              <Lightbox images={r.images} index={zoom} onIndex={setZoom} onClose={() => setZoom(null)} seen={r.image_report?.seen}
                actions={editable ? (url, k) => (
                  <>
                    {k > 0 ? (
                      <button onClick={() => { setR({ ...r, images: [url, ...r.images.filter((x) => x !== url)] }); setZoom(0); }}
                        className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-ink hover:bg-zinc-100">Asosiy rasm qilish</button>
                    ) : null}
                    <button onClick={() => {
                        const rest = r.images.filter((x) => x !== url);
                        setR({ ...r, images: rest });
                        setZoom(rest.length ? Math.min(k, rest.length - 1) : null);
                      }}
                      className="rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700">Rasmni olib tashlash</button>
                  </>
                ) : undefined} />
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              {field("Nomi (o'zbekcha)", r.name.uz, (v) => setR({ ...r, name: { ...r.name, uz: v } }))}
              {field("Nomi (ruscha)", r.name.ru, (v) => setR({ ...r, name: { ...r.name, ru: v } }))}
              {field("Brend", r.brand, (v) => setR({ ...r, brand: v }))}
              {field("Model", r.model_code, (v) => setR({ ...r, model_code: v }))}
              <label className="block text-sm">Kategoriya
                <select value={r.category_slug} onChange={(e) => {
                    if (e.target.value === "__new") return setNewCat({ uz: "", ru: "", parent: "" });
                    setR({ ...r, category_slug: e.target.value, attributes: e.target.value === draft.result.category_slug ? r.attributes : {} });
                  }}
                  disabled={!editable} className="mt-1 w-full">
                  <option value="">— tanlang —</option>
                  {cats.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
                  <option value="__new">+ Yangi kategoriya…</option>
                </select>
              </label>
              {r.new_category && !r.category_slug && !newCat ? (
                <div className="rounded-xl border border-brand/30 bg-brand/5 p-3 text-sm">
                  <p><b>AI taklifi:</b> yangi kategoriya «{r.new_category.name.uz}» / «{r.new_category.name.ru}»
                    {r.new_category.parent_slug ? ` — «${roots.find((x) => x.slug === r.new_category!.parent_slug)?.name ?? r.new_category.parent_slug}» bo'limida` : ""}.
                  </p>
                  <p className="mt-1 text-xs text-zinc-500">Nashr qilinganda avtomatik yaratiladi. Boshqasini xohlasangiz — ro&apos;yxatdan tanlang.</p>
                  {editable ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button disabled={busy} onClick={() => act(async () => {
                        await save();
                        const d = await api<Draft>(`/admin/ai-cards/drafts/${draft.id}/create-category`, { method: "POST" });
                        await loadCats();
                        return d;
                      }, "Kategoriya qo'shildi va tanlandi")}>Qo&apos;shish</Button>
                      <Button variant="ghost" onClick={() => setNewCat({ uz: r.new_category!.name.uz, ru: r.new_category!.name.ru, parent: String(roots.find((x) => x.slug === r.new_category!.parent_slug)?.id ?? "") })}>Nomini o&apos;zgartirib yaratish</Button>
                      <Button variant="ghost" onClick={() => setR({ ...r, new_category: null })}>Taklifni olib tashlash</Button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {newCat && (
                <div className="space-y-2 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-sm">
                  <div className="font-medium">Yangi kategoriya</div>
                  <input placeholder="Nomi (o'zbekcha), masalan: Gaz plitalar" value={newCat.uz}
                    onChange={(e) => setNewCat({ ...newCat, uz: e.target.value })} className="w-full" />
                  <input placeholder="Nomi (ruscha), masalan: Газовые плиты" value={newCat.ru}
                    onChange={(e) => setNewCat({ ...newCat, ru: e.target.value })} className="w-full" />
                  <select value={newCat.parent} onChange={(e) => setNewCat({ ...newCat, parent: e.target.value })} className="w-full">
                    <option value="">Bo&apos;lim: yuqori daraja</option>
                    {roots.map((c) => <option key={c.id} value={c.id}>Bo&apos;lim: {c.name}</option>)}
                  </select>
                  <div className="flex gap-2">
                    <Button disabled={busy || !newCat.uz.trim()} onClick={createCategory}>Yaratish</Button>
                    <Button variant="ghost" onClick={() => setNewCat(null)}>Bekor qilish</Button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                {field("Kafolat, oy", r.warranty_months ? String(r.warranty_months) : "", (v) => setR({ ...r, warranty_months: v ? Number(v.replace(/\D/g, "")) : null }))}
                {field("Og'irlik, kg", r.weight_kg ? String(r.weight_kg) : "", (v) => setR({ ...r, weight_kg: v ? Number(v.replace(",", ".")) || null : null }))}
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={r.is_bulky} disabled={!editable} onChange={(e) => setR({ ...r, is_bulky: e.target.checked })} />
              Yirik texnika (yuk mashinasida yetkaziladi)
            </label>
            {field("Tavsif (o'zbekcha)", r.description.uz, (v) => setR({ ...r, description: { ...r.description, uz: v } }), true)}
            {field("Tavsif (ruscha)", r.description.ru, (v) => setR({ ...r, description: { ...r.description, ru: v } }), true)}

            {Object.keys(r.attributes).length ? (
              <div>
                <p className="mb-1 text-sm font-medium">Xususiyatlar</p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(r.attributes).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 rounded-md bg-surface px-2 py-1 text-xs">
                      {k}: <b>{String(v)}</b>
                      {editable ? (
                        <button onClick={() => { const a = { ...r.attributes }; delete a[k]; setR({ ...r, attributes: a }); }} className="ml-1 text-zinc-400 hover:text-ink">×</button>
                      ) : null}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {r.specs?.length ? (
              <details open className="text-sm">
                <summary className="cursor-pointer font-medium">Texnik xususiyatlar ({r.specs.length})</summary>
                <table className="mt-2 w-full text-[13px]">
                  <tbody>
                    {r.specs.map((s, i) => (
                      <tr key={i} className="border-b border-line align-top">
                        <td className="py-1 pr-2 text-zinc-400">{s.group.uz}</td>
                        <td className="py-1 pr-2 text-zinc-600">{s.name.uz}</td>
                        <td className="py-1 pr-2 font-medium">{s.value.uz}</td>
                        <td className="py-1 text-right">
                          {editable ? (
                            <button title="O'chirish" onClick={() => setR({ ...r, specs: r.specs!.filter((_, j) => j !== i) })} className="text-zinc-400 hover:text-red-600">×</button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ) : null}

            {r.sources?.length ? (
              <details className="text-sm">
                <summary className="cursor-pointer text-zinc-500">Manbalar ({r.sources.length})</summary>
                <ul className="mt-1 space-y-0.5">
                  {r.sources.map((s) => <li key={s.uri}><a href={s.uri} target="_blank" rel="noreferrer" className="text-brand underline">{s.title || s.uri}</a></li>)}
                </ul>
              </details>
            ) : null}

            {editable ? (
              <div className="space-y-3 rounded-xl border border-line p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">Sotuv narxi, so&apos;m
                    <input value={price} onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} inputMode="numeric" className="mt-1 w-full" />
                    {draft.purchase_price ? (
                      <span className="text-xs text-zinc-400">
                        Xarid narxi: {supplierPrice(draft.purchase_price, currency)}
                        {draft.cost_uzs
                          ? currency === "USD" ? ` ≈ ${sum(draft.cost_uzs)} (tannarx)` : ""
                          : " — tannarx yozilmaydi (valyuta yoki kurs yo'q)"}
                      </span>
                    ) : null}
                  </label>
                  <div className="sm:col-span-2">
                    <Button variant="ghost" disabled={marketBusy} onClick={loadMarket}>
                      {marketBusy ? "Do'konlar narxi olinmoqda…" : "Bozor narxini aniqlash"}
                    </Button>
                    {market ? (
                      market.count ? (
                        <div className="mt-2 rounded-lg bg-surface p-3 text-sm">
                          <div className="flex flex-wrap gap-x-5 gap-y-1">
                            <span>Eng past: <b>{sum(market.min!)}</b></span>
                            <span>O&apos;rtacha: <b>{sum(market.median!)}</b></span>
                            <span>Eng yuqori: <b>{sum(market.max!)}</b></span>
                            <button className="text-brand underline" onClick={() => setPrice(String(market.suggested))}>
                              {sum(market.suggested!)} ni qo&apos;yish
                            </button>
                          </div>
                          <ul className="mt-2 space-y-0.5 text-xs text-zinc-500">
                            {market.sources.map((s) => (
                              <li key={s.url}>
                                <a href={s.url} target="_blank" rel="noreferrer" className="underline">{new URL(s.url).hostname.replace("www.", "")}</a>
                                {" — "}{sum(s.price)}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <p className="mt-2 text-xs text-zinc-500">O&apos;zbekiston do&apos;konlarida bu model narxi topilmadi.</p>
                      )
                    ) : null}
                  </div>
                  <label className="block text-sm">Artikul (SKU)
                    <input value={sku} onChange={(e) => setSku(e.target.value)} className="mt-1 w-full" />
                  </label>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} /> Darhol saytga chiqarish
                </label>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={busy || !price} onClick={() => act(async () => {
                    await save();
                    return api<Draft>(`/admin/ai-cards/drafts/${draft.id}/approve`, { method: "POST", body: { price, sku, publish } });
                  }, publish ? "Nashr qilindi" : "Katalogga qoralama sifatida qo'shildi")}>
                    {publish ? "Nashr qilish" : "Katalogga qo'shish"}
                  </Button>
                  <Button variant="ghost" disabled={busy} onClick={() => act(save, "Saqlandi")}>Saqlash</Button>
                  <Button variant="ghost" disabled={busy} onClick={() => act(async () => {
                    await save();
                    return api<Draft>(`/admin/ai-cards/drafts/${draft.id}/autofix`, { method: "POST" });
                  }, "Avto-tuzatish tugadi")}>Avto-tuzatish</Button>
                  <Button variant="ghost" disabled={busy} onClick={() => act(() => api<Draft>(`/admin/ai-cards/drafts/${draft.id}/regenerate`, { method: "POST" }), "Qayta yaratildi")}>Qayta yaratish</Button>
                  <Button variant="danger" disabled={busy} onClick={() => act(() => api<Draft>(`/admin/ai-cards/drafts/${draft.id}/reject`, { method: "POST" }), "Rad etildi")}>Rad etish</Button>
                </div>
              </div>
            ) : draft.product_slug ? (
              <a href={`/p/${draft.product_slug}`} target="_blank" rel="noreferrer" className="inline-block text-sm text-brand underline">Saytda ko&apos;rish</a>
            ) : null}
          </div>
        ) : (
          <div className="flex gap-2">
            {draft.status !== "rejected" ? (
              <Button disabled={busy} onClick={() => act(() => api<Draft>(`/admin/ai-cards/drafts/${draft.id}/regenerate`, { method: "POST" }), "Qayta yaratildi")}>Qayta yaratish</Button>
            ) : null}
            {draft.status === "failed" ? (
              <Button variant="ghost" disabled={busy} onClick={() => act(() => api<Draft>(`/admin/ai-cards/drafts/${draft.id}/autofix`, { method: "POST" }), "Avto-tuzatish tugadi")}>Avto-tuzatish</Button>
            ) : null}
            {["not_found", "failed"].includes(draft.status) ? (
              <Button variant="danger" disabled={busy} onClick={() => act(() => api<Draft>(`/admin/ai-cards/drafts/${draft.id}/reject`, { method: "POST" }), "Rad etildi")}>Rad etish</Button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
