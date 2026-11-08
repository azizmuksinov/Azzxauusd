"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, apiUpload } from "@/lib/api";
import type { CategoryNode } from "@/lib/types";

import { useApp } from "./providers";
import { errorText, sum } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Ta'minotchi faylidan Gemini yordamida tovar kartochkalari: yuklash → to'ldirish → tekshirish → nashr.

type Batch = { id: number; file_name: string; columns: Record<string, string>; rows_total: number; currency: string; counts: Record<string, number>; created_at: string };
type DraftRow = { id: number; row_number: number; query: string; supplier_sku: string; purchase_price: string | null; qty: number | null; status: string; status_label: string; name: string; product_slug: string | null };
type Result = {
  found?: boolean; confidence?: number | null; brand: string; model_code: string; category_slug: string;
  name: { uz: string; ru: string }; description: { uz: string; ru: string };
  warranty_months: number | null; weight_kg: number | null; is_bulky: boolean;
  attributes: Record<string, string | number | boolean>; images: string[]; sources?: { uri: string; title: string }[];
  specs?: Spec[];
  new_category?: { name: { uz: string; ru: string }; parent_slug: string } | null;
};
type L = { uz: string; ru: string };
type Spec = { group: L; name: L; value: L };
type Market = { count: number; min?: number; max?: number; median?: number; suggested?: number; sources: { url: string; title: string; price: number }[] };
export type Draft = DraftRow & { raw: Record<string, string>; result: Result; warnings: string[]; error: string; model_used: string; cost_uzs?: string | null };
type AiProvider = {
  name: string; label: string; model: string; search: boolean; configured: boolean; missing: string;
  used_today: number; daily_cap: number | null;
};
type CheckRow = {
  name: string; label: string; configured: boolean; missing: string; ok?: boolean; error?: string; seconds?: number;
  served_model?: string; limits?: Record<string, string>; account?: Record<string, unknown>;
};
type Usage = {
  provider: string; model: string; search: boolean; used_today: number; daily_limit: number | null; usd_rate: string | null;
  providers: AiProvider[];
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

  const setCurrency = async (currency: string) => {
    if (!batch) return;
    try {
      setBatch(await api<Batch>(`/admin/ai-cards/batches/${batch.id}/currency`, { method: "POST", body: { currency } }));
      await loadBatches();
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
    setRows(list(await api<Page<DraftRow>>(`/admin/ai-cards/drafts?batch=${b.id}&page_size=200`)));
    setBatch(await api<Batch>(`/admin/ai-cards/batches/${b.id}`));
  }, []);

  useEffect(() => {
    loadBatches().then((b) => b[0] && loadRows(b[0]));
  }, [loadBatches, loadRows]);

  const upload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const b = await apiUpload<Batch>("/admin/ai-cards/batches", form);
      toast(`${b.rows_total} ta tovar topildi`);
      if (fileRef.current) fileRef.current.value = "";
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
    <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
      <div className="space-y-4">
        <Panel>
          <h2 className="font-bold">Ta&apos;minotchi fayli</h2>
          <p className="mt-1 text-xs text-zinc-500">Excel (.xlsx). Nomi, artikul, xarid narxi va soni ustunlari avtomatik aniqlanadi.</p>
          <input ref={fileRef} type="file" accept=".xlsx" className="mt-3 w-full text-sm" />
          <Button className="mt-3 w-full" disabled={uploading} onClick={upload}>{uploading ? "Yuklanmoqda…" : "Yuklash"}</Button>
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
              Excel kartochkalar — avval bepul xizmatlar (yuklama teng bo&apos;linadi), havoladan ham avval bepul xizmatlar (Gemini — zaxira, sekin),
              rasm — avval AI&apos;siz qidiruv. 🔎 — internetdan o&apos;zi qidiradi. Qolganlari uchun qidiruvni tizimning o&apos;zi qiladi
              (DuckDuckGo/Bing + sahifani o&apos;qish), AI faqat kartochkani yozadi. Kalitlar Space sozlamalarida (Secrets).
            </p>
            <Button variant="ghost" className="mt-2 w-full" disabled={checking} onClick={runCheck}>
              {checking ? "Tekshirilmoqda…" : "Xizmatlarni tekshirish (har biriga 1 so'rov)"}
            </Button>
            {check ? (
              <ul className="mt-2 space-y-1 text-xs">
                {check.filter((c) => c.configured).map((c) => (
                  <li key={c.name} className={`rounded-lg p-2 ${c.ok ? "bg-green-50 text-green-900" : "bg-red-50 text-red-800"}`}>
                    <b>{c.label}</b>: {c.ok ? `ishlaydi, ${c.seconds} s` : c.error}
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
          <Panel><p className="text-sm text-zinc-500">Ta&apos;minotchi faylini yuklang — har bir qator uchun Gemini internetdan ma&apos;lumot topib, kartochka tayyorlaydi. Kartochka siz tekshirib nashr qilmaguncha saytda chiqmaydi.</p></Panel>
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
                  <Button disabled={pending === 0} onClick={run}>Gemini bilan to&apos;ldirish ({pending})</Button>
                )}
              </div>
            </div>
            {running || (done > 0 && pending > 0) ? (
              <div className="mt-3">
                <div className="h-1.5 overflow-hidden rounded-full bg-surface">
                  <div className="h-full bg-brand transition-all" style={{ width: `${(done / Math.max(rows.length, 1)) * 100}%` }} />
                </div>
                <p className="mt-1 text-xs text-zinc-500">{done} / {rows.length}{running ? " — Gemini qidirmoqda…" : ""}</p>
              </div>
            ) : null}
            <div className="mt-4 divide-y divide-line">
              {rows.map((r) => (
                <button key={r.id} disabled={r.status === "pending"}
                  onClick={async () => setOpen(await api<Draft>(`/admin/ai-cards/drafts/${r.id}`))}
                  className="flex w-full items-center gap-3 py-2.5 text-left text-sm hover:bg-surface/60 disabled:cursor-default">
                  <span className="w-8 shrink-0 text-xs text-zinc-400">{r.row_number}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{r.name || r.query}</span>
                    {r.name ? <span className="block truncate text-xs text-zinc-400">{r.query}</span> : null}
                  </span>
                  {r.purchase_price ? <span className="hidden shrink-0 text-xs text-zinc-500 sm:inline">{supplierPrice(r.purchase_price, batch.currency)}</span> : null}
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs ${STATUS_CLS[r.status] ?? ""}`}>{r.status_label}</span>
                </button>
              ))}
            </div>
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
    </div>
  );
}

export function Review({ draft, currency, onClose, onChanged }: { draft: Draft; currency: string; onClose: () => void; onChanged: (d: Draft | null) => Promise<void> }) {
  const { toast } = useApp();
  const [r, setR] = useState<Result>(draft.result);
  const [cats, setCats] = useState<{ slug: string; name: string }[]>([]);
  const [price, setPrice] = useState("");
  const [sku, setSku] = useState(draft.supplier_sku);
  const [publish, setPublish] = useState(true);
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
            <p className="text-xs text-zinc-500">Qator {draft.row_number} · {draft.query}</p>
            <h3 className="text-lg font-bold">{r.name?.uz || draft.query}</h3>
            <p className="text-xs text-zinc-400">{draft.status_label}{draft.model_used ? ` · ${draft.model_used}` : ""}{r.confidence != null ? ` · ishonch ${Math.round(r.confidence * 100)}%` : ""}</p>
          </div>
          <button onClick={onClose} className="text-2xl leading-none text-zinc-400 hover:text-ink">×</button>
        </div>

        {draft.error ? <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{draft.error}</p> : null}
        {draft.warnings.length ? (
          <ul className="mb-4 space-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            {draft.warnings.map((w, i) => <li key={i}>• {w}</li>)}
          </ul>
        ) : null}

        {draft.status === "ready" || draft.status === "approved" ? (
          <div className="space-y-4">
            {r.images.length ? (
              <div className="flex flex-wrap gap-2">
                {r.images.map((u) => (
                  <div key={u} className="relative h-24 w-24 overflow-hidden rounded-lg border border-line bg-surface">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={u} alt="" className="h-full w-full object-contain" referrerPolicy="no-referrer" />
                    {editable ? (
                      <button onClick={() => setR({ ...r, images: r.images.filter((x) => x !== u) })}
                        className="absolute right-1 top-1 grid h-6 w-6 place-items-center rounded-full bg-white/90 text-sm">×</button>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-zinc-500">Rasm topilmadi — nashrdan keyin admin panelda yuklang.</p>}

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
