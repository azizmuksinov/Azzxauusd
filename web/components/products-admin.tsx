"use client";

import { useCallback, useEffect, useState } from "react";

import { api, apiUpload } from "@/lib/api";

import { type Draft, Review } from "./ai-cards";
import { useApp } from "./providers";
import { errorText, sum } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Tovarlar: ro'yxat, yaratish/tahrirlash (rasm, video, narx, qoldiq, xususiyatlar), havoladan AI import.

type I18n = { uz?: string; ru?: string };
type Variant = { id: number; sku: string; name_suffix: I18n; price: string; old_price: string | null; cost_price: string | null; is_active: boolean };
type AttrValue = { code: string; variant_id: number | null; value: string; raw: string | number | boolean };
type Product = {
  id: number; category: number; brand: number | null; slug: string; name: I18n; description: I18n; model_code: string;
  video_url: string; status: string; warranty_months: number; is_bulky: boolean; mxik_code: string;
  variants: Variant[]; attribute_values: AttrValue[]; image: string; stock: Record<string, number>;
};
type Category = { id: number; parent: number | null; name: I18n; attribute_ids: number[] };
type Brand = { id: number; name: string };
type Attribute = { id: number; code: string; name: I18n; data_type: string; unit: string; options: { code: string; value: I18n }[] };
type Image = { id: number; url: string; sort: number };
type StockRow = { id: number; warehouse: number; warehouse_code: string; on_hand: number; reserved: number; available: number };
type Warehouse = { id: number; name: string };
type Page<T> = { results: T[]; count?: number } | T[];
const list = <T,>(p: Page<T>): T[] => (Array.isArray(p) ? p : p.results);

const STATUS: Record<string, [string, string]> = {
  active: ["Sotuvda", "bg-green-50 text-green-800"],
  draft: ["Qoralama", "bg-amber-50 text-amber-800"],
  archived: ["Arxiv", "bg-zinc-100 text-zinc-500"],
};

export function ProductsTab() {
  const { toast } = useApp();
  const [rows, setRows] = useState<Product[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const load = useCallback(async () => {
    const p = new URLSearchParams({ page_size: "100" });
    if (q.trim()) p.set("q", q.trim());
    if (status) p.set("status", status);
    setRows(list(await api<Page<Product>>(`/admin/products?${p}`)));
  }, [q, status]);

  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  const importUrl = async () => {
    setImporting(true);
    try {
      const d = await api<Draft>("/admin/ai-cards/drafts/from-url", { method: "POST", body: { url } });
      setDraft(d);
      setUrl("");
      if (d.status !== "ready") toast(d.error || d.status_label, "error");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <Panel className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto font-bold">Havoladan kartochka</h2>
          <span className="text-xs text-zinc-500">Uzum, Ozon, Yandex Market yoki istalgan do&apos;kon — AI ikki tilda tayyorlaydi</span>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://uzum.uz/uz/product/..." className="min-w-0 flex-1" />
          <Button disabled={importing || !url.startsWith("http")} onClick={importUrl}>
            {importing ? "AI o'qimoqda… (1–2 daqiqa)" : "Kartochka yaratish"}
          </Button>
        </div>
      </Panel>

      <div className="flex flex-wrap items-center gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nomi, model yoki SKU" className="min-w-0 flex-1 sm:max-w-sm" />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Barcha holatlar</option>
          {Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <Button className="ml-auto" onClick={() => setEditing("new")}>+ Yangi tovar</Button>
      </div>

      {!rows ? <Loading /> : (
        <div className="divide-y divide-line rounded-xl border border-line bg-white">
          {rows.length === 0 ? <p className="p-6 text-center text-sm text-zinc-500">Tovar topilmadi</p> : null}
          {rows.map((p) => {
            const v = p.variants[0];
            const stock = Object.values(p.stock).reduce((a, b) => a + b, 0);
            const [label, cls] = STATUS[p.status] ?? [p.status, ""];
            return (
              <button key={p.id} onClick={() => setEditing(p.id)} className="flex w-full items-center gap-3 p-3 text-left hover:bg-surface/60">
                <span className="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-surface">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {p.image ? <img src={p.image} alt="" className="h-full w-full object-contain mix-blend-multiply" /> : null}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{p.name.uz}</span>
                  <span className="block truncate text-xs text-zinc-500">{v?.sku ?? "—"}{p.model_code ? ` · ${p.model_code}` : ""}</span>
                </span>
                <span className="hidden w-32 shrink-0 text-right text-sm sm:block">{v ? sum(v.price) : ""}</span>
                <span className={`w-16 shrink-0 text-right text-sm ${stock > 0 ? "" : "text-red-600"}`}>{stock} dona</span>
                <span className={`hidden shrink-0 rounded-md px-2 py-0.5 text-xs sm:inline ${cls}`}>{label}</span>
              </button>
            );
          })}
        </div>
      )}

      {editing !== null ? (
        <ProductEditor id={editing} onClose={() => setEditing(null)} onSaved={async (id) => { setEditing(id); await load(); }} />
      ) : null}
      {draft ? (
        <Review draft={draft} currency="" onClose={() => setDraft(null)}
          onChanged={async (d) => { setDraft(d); await load(); }} />
      ) : null}
    </div>
  );
}

function ProductEditor({ id, onClose, onSaved }: { id: number | "new"; onClose: () => void; onSaved: (id: number) => Promise<void> }) {
  const { toast } = useApp();
  const isNew = id === "new";
  const [p, setP] = useState<Product | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [attrs, setAttrs] = useState<Attribute[]>([]);
  const [images, setImages] = useState<Image[]>([]);
  const [values, setValues] = useState<Record<string, string | number | boolean | null>>({});
  const [newVariant, setNewVariant] = useState({ sku: "", price: "", old_price: "" });
  const [newBrand, setNewBrand] = useState("");
  const [busy, setBusy] = useState(false);

  const loadImages = useCallback(async (pid: number) => {
    setImages(list(await api<Page<Image>>(`/admin/product-images?product=${pid}&page_size=50`)).sort((a, b) => a.sort - b.sort));
  }, []);

  useEffect(() => {
    Promise.all([
      api<Page<Category>>("/admin/categories?page_size=200"),
      api<Page<Brand>>("/admin/brands?page_size=200"),
      api<Page<Attribute>>("/admin/attributes?page_size=200"),
    ]).then(([c, b, a]) => {
      setCats(list(c));
      setBrands(list(b));
      setAttrs(list(a));
    });
    if (isNew) {
      setP({
        id: 0, category: 0, brand: null, slug: "", name: { uz: "", ru: "" }, description: { uz: "", ru: "" }, model_code: "",
        video_url: "", status: "draft", warranty_months: 12, is_bulky: false, mxik_code: "", variants: [], attribute_values: [], image: "", stock: {},
      });
    } else {
      api<Product>(`/admin/products/${id}`).then((x) => {
        setP(x);
        setValues(Object.fromEntries(x.attribute_values.filter((a) => !a.variant_id).map((a) => [a.code, a.raw])));
      });
      loadImages(id);
    }
  }, [id, isNew, loadImages]);

  if (!p) return <Drawer onClose={onClose}><Loading /></Drawer>;
  const leafCats = cats.filter((c) => !cats.some((x) => x.parent === c.id));
  const cat = cats.find((c) => c.id === p.category);
  const catAttrs = attrs.filter((a) => cat?.attribute_ids.includes(a.id));
  const set = (patch: Partial<Product>) => setP({ ...p, ...patch });

  const save = async () => {
    setBusy(true);
    try {
      let brand = p.brand;
      if (newBrand.trim()) {
        const form = new FormData();
        form.append("name", newBrand.trim());
        form.append("slug", newBrand.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || `brand-${Date.now()}`);
        brand = (await apiUpload<Brand>("/admin/brands", form)).id;
        setNewBrand("");
      }
      const body = {
        category: p.category, brand, name: p.name, description: p.description, model_code: p.model_code,
        video_url: p.video_url, status: p.status, warranty_months: p.warranty_months, is_bulky: p.is_bulky, mxik_code: p.mxik_code,
        attributes: catAttrs.map((a) => ({ code: a.code, value: values[a.code] === "" || values[a.code] === undefined ? null : values[a.code] })),
      };
      const saved = isNew
        ? await api<Product>("/admin/products", { method: "POST", body })
        : await api<Product>(`/admin/products/${p.id}`, { method: "PATCH", body });
      if (isNew && newVariant.sku && newVariant.price) {
        await api("/admin/variants", {
          method: "POST",
          body: { product: saved.id, sku: newVariant.sku, price: newVariant.price, old_price: newVariant.old_price || null },
        });
      }
      toast("Saqlandi");
      await onSaved(saved.id);
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer onClose={onClose}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-zinc-500">{isNew ? "Yangi tovar" : `#${p.id} · ${p.slug}`}</p>
          <h3 className="text-lg font-bold">{p.name.uz || "Nomsiz tovar"}</h3>
        </div>
        <button onClick={onClose} className="text-2xl leading-none text-zinc-400 hover:text-ink">×</button>
      </div>

      <div className="space-y-6">
        <Section title="Asosiy">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Nomi (o'zbekcha)"><input value={p.name.uz ?? ""} onChange={(e) => set({ name: { ...p.name, uz: e.target.value } })} className="w-full" /></Field>
            <Field label="Nomi (ruscha)"><input value={p.name.ru ?? ""} onChange={(e) => set({ name: { ...p.name, ru: e.target.value } })} className="w-full" /></Field>
            <Field label="Kategoriya">
              <select value={p.category || ""} onChange={(e) => set({ category: Number(e.target.value) })} className="w-full">
                <option value="">— tanlang —</option>
                {leafCats.map((c) => <option key={c.id} value={c.id}>{c.name.uz}</option>)}
              </select>
            </Field>
            <Field label="Brend">
              <div className="flex gap-2">
                <select value={p.brand ?? ""} onChange={(e) => set({ brand: e.target.value ? Number(e.target.value) : null })} className="min-w-0 flex-1">
                  <option value="">—</option>
                  {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
                <input value={newBrand} onChange={(e) => setNewBrand(e.target.value)} placeholder="yoki yangi" className="w-28" />
              </div>
            </Field>
            <Field label="Model"><input value={p.model_code} onChange={(e) => set({ model_code: e.target.value })} className="w-full" /></Field>
            <Field label="Holat">
              <select value={p.status} onChange={(e) => set({ status: e.target.value })} className="w-full">
                {Object.entries(STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <Field label="Kafolat, oy"><input value={p.warranty_months} inputMode="numeric" onChange={(e) => set({ warranty_months: Number(e.target.value.replace(/\D/g, "")) || 0 })} className="w-full" /></Field>
            <Field label="MXIK kodi (sotuvga chiqarish uchun)"><input value={p.mxik_code} onChange={(e) => set({ mxik_code: e.target.value })} className="w-full" /></Field>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={p.is_bulky} onChange={(e) => set({ is_bulky: e.target.checked })} /> Yirik texnika (yuk mashinasida)
          </label>
        </Section>

        <Section title="Tavsif">
          <Field label="O'zbekcha"><textarea rows={4} value={p.description.uz ?? ""} onChange={(e) => set({ description: { ...p.description, uz: e.target.value } })} className="w-full" /></Field>
          <Field label="Ruscha"><textarea rows={4} value={p.description.ru ?? ""} onChange={(e) => set({ description: { ...p.description, ru: e.target.value } })} className="mt-2 w-full" /></Field>
        </Section>

        {catAttrs.length ? (
          <Section title="Xususiyatlar">
            <div className="grid gap-3 sm:grid-cols-2">
              {catAttrs.map((a) => (
                <Field key={a.code} label={`${a.name.uz}${a.unit ? `, ${a.unit}` : ""}`}>
                  {a.data_type === "enum" ? (
                    <select value={String(values[a.code] ?? "")} onChange={(e) => setValues({ ...values, [a.code]: e.target.value })} className="w-full">
                      <option value="">—</option>
                      {a.options.map((o) => <option key={o.code} value={o.code}>{o.value.uz}</option>)}
                    </select>
                  ) : a.data_type === "bool" ? (
                    <select value={values[a.code] === true ? "1" : values[a.code] === false ? "0" : ""}
                      onChange={(e) => setValues({ ...values, [a.code]: e.target.value === "" ? null : e.target.value === "1" })} className="w-full">
                      <option value="">—</option><option value="1">Ha</option><option value="0">Yo&apos;q</option>
                    </select>
                  ) : (
                    <input value={String(values[a.code] ?? "")} inputMode={a.data_type === "number" ? "decimal" : "text"}
                      onChange={(e) => setValues({ ...values, [a.code]: a.data_type === "number" ? (e.target.value === "" ? "" : Number(e.target.value.replace(",", "."))) : e.target.value })}
                      className="w-full" />
                  )}
                </Field>
              ))}
            </div>
          </Section>
        ) : null}

        <Section title="Video">
          <Field label="YouTube havolasi yoki .mp4 fayl manzili">
            <input value={p.video_url} onChange={(e) => set({ video_url: e.target.value })} placeholder="https://youtu.be/..." className="w-full" />
          </Field>
        </Section>

        {isNew ? (
          <Section title="Narx">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Artikul (SKU)"><input value={newVariant.sku} onChange={(e) => setNewVariant({ ...newVariant, sku: e.target.value })} className="w-full" /></Field>
              <Field label="Narx, so'm"><input value={newVariant.price} inputMode="numeric" onChange={(e) => setNewVariant({ ...newVariant, price: e.target.value.replace(/\D/g, "") })} className="w-full" /></Field>
              <Field label="Eski narx (chegirma)"><input value={newVariant.old_price} inputMode="numeric" onChange={(e) => setNewVariant({ ...newVariant, old_price: e.target.value.replace(/\D/g, "") })} className="w-full" /></Field>
            </div>
            <p className="mt-2 text-xs text-zinc-500">Saqlangandan keyin rasm, qoldiq va boshqa variantlarni qo&apos;shasiz.</p>
          </Section>
        ) : (
          <>
            <Section title="Rasmlar">
              <ImagesEditor productId={p.id} images={images} reload={() => loadImages(p.id)} />
            </Section>
            <Section title="Narx va qoldiq">
              <div className="space-y-3">
                {p.variants.map((v) => <VariantRow key={v.id} v={v} available={p.stock[String(v.id)] ?? 0} />)}
                <AddVariant productId={p.id} onAdded={() => onSaved(p.id)} />
              </div>
            </Section>
          </>
        )}

        <div className="sticky bottom-0 -mx-6 flex gap-2 border-t border-line bg-white px-6 py-4">
          <Button disabled={busy || !p.name.uz || !p.category} onClick={save}>{isNew ? "Yaratish" : "Saqlash"}</Button>
          {!isNew ? <a href={`/p/${p.slug}`} target="_blank" rel="noreferrer" className="inline-flex h-11 items-center px-3 text-sm text-brand underline">Saytda ko&apos;rish</a> : null}
        </div>
      </div>
    </Drawer>
  );
}

function ImagesEditor({ productId, images, reload }: { productId: number; images: Image[]; reload: () => Promise<void> }) {
  const { toast } = useApp();
  const [link, setLink] = useState("");
  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await reload();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= images.length) return;
    const a = images[i], b = images[j];
    run(async () => {
      await api(`/admin/product-images/${a.id}`, { method: "PATCH", body: { sort: j } });
      await api(`/admin/product-images/${b.id}`, { method: "PATCH", body: { sort: i } });
    });
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {images.map((img, i) => (
          <div key={img.id} className="group relative h-24 w-24 overflow-hidden rounded-lg border border-line bg-surface">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={img.url} alt="" className="h-full w-full object-contain mix-blend-multiply" />
            {i === 0 ? <span className="absolute left-1 top-1 rounded bg-white/90 px-1 text-[10px]">asosiy</span> : null}
            <div className="absolute inset-x-0 bottom-0 flex justify-between bg-white/90 opacity-0 transition group-hover:opacity-100">
              <button onClick={() => move(i, -1)} className="px-2 text-sm">‹</button>
              <button onClick={() => run(() => api(`/admin/product-images/${img.id}`, { method: "DELETE" }))} className="px-2 text-sm text-red-600">×</button>
              <button onClick={() => move(i, 1)} className="px-2 text-sm">›</button>
            </div>
          </div>
        ))}
        <label className="grid h-24 w-24 cursor-pointer place-items-center rounded-lg border border-dashed border-zinc-300 text-xs text-zinc-500 hover:border-brand">
          + Yuklash
          <input type="file" accept="image/*" multiple className="hidden" onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            run(async () => {
              for (const [k, file] of files.entries()) {
                const form = new FormData();
                form.append("product", String(productId));
                form.append("file", file);
                form.append("sort", String(images.length + k));
                await apiUpload("/admin/product-images", form);
              }
            });
          }} />
        </label>
      </div>
      <div className="flex gap-2">
        <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="yoki rasm havolasi https://..." className="min-w-0 flex-1" />
        <Button variant="ghost" disabled={!link.startsWith("http")} onClick={() => run(async () => {
          const form = new FormData();
          form.append("product", String(productId));
          form.append("external_url", link);
          form.append("sort", String(images.length));
          await apiUpload("/admin/product-images", form);
          setLink("");
        })}>Qo&apos;shish</Button>
      </div>
    </div>
  );
}

function VariantRow({ v, available }: { v: Variant; available: number }) {
  const { toast } = useApp();
  const [price, setPrice] = useState(String(Math.round(Number(v.price))));
  const [old, setOld] = useState(v.old_price ? String(Math.round(Number(v.old_price))) : "");
  const [stock, setStock] = useState<StockRow[] | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [wh, setWh] = useState("");
  const [qty, setQty] = useState("");
  const [avail, setAvail] = useState(available);

  const loadStock = async () => {
    const [s, w] = await Promise.all([api<Page<StockRow>>(`/admin/stock?variant=${v.id}`), api<Page<Warehouse>>("/admin/warehouses")]);
    setStock(list(s));
    setWarehouses(list(w));
    setWh((x) => x || String(list(w)[0]?.id ?? ""));
  };

  const savePrice = async () => {
    try {
      await api(`/admin/variants/${v.id}/price`, { method: "PATCH", body: { price, old_price: old || null } });
      toast("Narx yangilandi");
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const saveStock = async () => {
    try {
      await api("/admin/stock/adjustments", { method: "POST", body: { warehouse: Number(wh), variant: v.id, on_hand: Number(qty), comment: "Tovar kartochkasidan" } });
      toast("Qoldiq yangilandi");
      setQty("");
      await loadStock();
      const rows = list(await api<Page<StockRow>>(`/admin/stock?variant=${v.id}`));
      setAvail(rows.reduce((a, r) => a + r.available, 0));
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <div className="rounded-xl border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">{v.sku}{v.name_suffix?.uz ? ` · ${v.name_suffix.uz}` : ""}</p>
        <span className={`text-sm ${avail > 0 ? "" : "text-red-600"}`}>Sotuvda: {avail} dona</span>
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <Field label="Narx"><input value={price} inputMode="numeric" onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))} className="w-32" /></Field>
        <Field label="Eski narx"><input value={old} inputMode="numeric" onChange={(e) => setOld(e.target.value.replace(/\D/g, ""))} className="w-32" /></Field>
        <Button variant="ghost" onClick={savePrice}>Narxni saqlash</Button>
        {stock === null ? <Button variant="ghost" onClick={loadStock}>Qoldiq</Button> : null}
      </div>
      {stock !== null ? (
        <div className="mt-3 space-y-2 border-t border-line pt-3 text-sm">
          {stock.map((s) => <p key={s.id} className="text-zinc-600">{s.warehouse_code}: {s.on_hand} dona (band: {s.reserved})</p>)}
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Ombor">
              <select value={wh} onChange={(e) => setWh(e.target.value)}>{warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select>
            </Field>
            <Field label="Yangi qoldiq"><input value={qty} inputMode="numeric" onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))} className="w-24" /></Field>
            <Button variant="ghost" disabled={!qty || !wh} onClick={saveStock}>Saqlash</Button>
          </div>
          <p className="text-xs text-zinc-400">Tez tuzatish (inventarizatsiya). Xarid bilan kirim — back-office kirim hujjati orqali.</p>
        </div>
      ) : null}
    </div>
  );
}

function AddVariant({ productId, onAdded }: { productId: number; onAdded: () => Promise<void> }) {
  const { toast } = useApp();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ sku: "", suffix: "", price: "", old_price: "" });
  if (!open) return <button onClick={() => setOpen(true)} className="text-sm text-brand">+ Variant qo&apos;shish (rang, xotira…)</button>;
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-xl border border-dashed border-zinc-300 p-3">
      <Field label="SKU"><input value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} className="w-32" /></Field>
      <Field label="Nomi (masalan 256 GB)"><input value={f.suffix} onChange={(e) => setF({ ...f, suffix: e.target.value })} className="w-40" /></Field>
      <Field label="Narx"><input value={f.price} inputMode="numeric" onChange={(e) => setF({ ...f, price: e.target.value.replace(/\D/g, "") })} className="w-28" /></Field>
      <Button variant="ghost" disabled={!f.sku || !f.price} onClick={async () => {
        try {
          await api("/admin/variants", { method: "POST", body: { product: productId, sku: f.sku, price: f.price, name_suffix: f.suffix ? { uz: f.suffix } : {} } });
          toast("Variant qo'shildi");
          setOpen(false);
          await onAdded();
        } catch (e) {
          toast(errorText(e), "error");
        }
      }}>Qo&apos;shish</Button>
    </div>
  );
}

function Drawer({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 animate-[fadeIn_.15s_ease-out]" onClick={onClose}>
      <div className="h-full w-full max-w-3xl overflow-y-auto bg-white px-6 pt-6 animate-[slideIn_.2s_ease-out]" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">{title}</h4>
      {children}
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-zinc-600">{label}</span>
      {children}
    </label>
  );
}
