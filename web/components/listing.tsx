"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Card, Facets, Page } from "@/lib/types";

import { useApp } from "./providers";
import { ErrorBox, Grid, GridSkeleton, ProductCard } from "./ui";

const PAGE_SIZE = 20;

/** Tovarlar ro'yxati: filtrlar URL'da saqlanadi (ulashish va "orqaga" uchun). */
export function Listing({ category, query }: { category?: string; query?: string }) {
  const { t, lang } = useApp();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [data, setData] = useState<Page<Card> | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [error, setError] = useState("");

  const qs = params.toString();
  useEffect(() => {
    const p = new URLSearchParams(qs);
    if (category) p.set("category", category);
    if (query) p.set("q", query);
    p.set("page_size", String(PAGE_SIZE));
    setError("");
    setData(null);
    api<Page<Card>>(`${query ? "/search" : "/products"}?${p}`).then(setData).catch((e) => setError(e.message));
    if (category) {
      const f = new URLSearchParams(qs);
      f.delete("page");
      f.delete("sort");
      api<Facets>(`/categories/${category}/filters?${f}`).then(setFacets).catch(() => setFacets(null));
    }
  }, [qs, category, query, lang]);

  const update = (changes: Record<string, string | null>) => {
    const p = new URLSearchParams(qs);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") p.delete(k);
      else p.set(k, v);
    }
    if (!("page" in changes)) p.delete("page");
    router.push(`${pathname}?${p}`);
  };
  const toggleList = (key: string, value: string) => {
    const current = (params.get(key) ?? "").split(",").filter(Boolean);
    const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    update({ [key]: next.join(",") || null });
  };

  const page = Number(params.get("page") ?? 1);
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-6 md:flex-row">
      {category ? (
        <aside className="w-full shrink-0 space-y-5 rounded-3xl bg-white p-4 ring-1 ring-gray-100 md:w-64">
          <div className="flex items-center justify-between">
            <h3 className="font-bold">{t("filters")}</h3>
            <button onClick={() => router.push(pathname)} className="text-sm text-brand">{t("reset")}</button>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={params.get("in_stock") === "true"}
              onChange={(e) => update({ in_stock: e.target.checked ? "true" : null })} />
            {t("onlyInStock")}
          </label>
          {facets?.price.min ? (
            <PriceFilter key={qs} min={facets.price.min} max={facets.price.max!} onApply={(lo, hi) => update({ price_min: lo, price_max: hi })}
              initial={[params.get("price_min") ?? "", params.get("price_max") ?? ""]} />
          ) : null}
          {facets && facets.brands.length > 0 ? (
            <div>
              <h4 className="mb-2 font-semibold">{t("brands")}</h4>
              {facets.brands.map((b) => (
                <label key={b.slug} className="flex items-center gap-2 py-0.5">
                  <input type="checkbox" checked={(params.get("brand") ?? "").split(",").includes(b.slug)}
                    onChange={() => toggleList("brand", b.slug)} />
                  {b.name} <span className="text-gray-400">({b.count})</span>
                </label>
              ))}
            </div>
          ) : null}
          {facets?.attributes.map((a) => {
            const key = `f[${a.code}]`;
            if (a.type === "enum") {
              return (
                <div key={a.code}>
                  <h4 className="mb-2 font-semibold">{a.name}</h4>
                  {a.options!.map((o) => (
                    <label key={o.code} className="flex items-center gap-2 py-0.5">
                      <input type="checkbox" checked={(params.get(key) ?? "").split(",").includes(o.code)}
                        onChange={() => toggleList(key, o.code)} />
                      {o.name} <span className="text-gray-400">({o.count})</span>
                    </label>
                  ))}
                </div>
              );
            }
            if (a.type === "bool") {
              return (
                <label key={a.code} className="flex items-center gap-2">
                  <input type="checkbox" checked={params.get(key) === "true"}
                    onChange={(e) => update({ [key]: e.target.checked ? "true" : null })} />
                  {a.name}
                </label>
              );
            }
            const [lo, hi] = (params.get(key) ?? "..").split("..");
            return (
              <div key={a.code}>
                <h4 className="mb-2 font-semibold">{a.name}{a.unit ? `, ${a.unit}` : ""}</h4>
                <div className="flex gap-2">
                  <select value={lo} onChange={(e) => update({ [key]: e.target.value || hi ? `${e.target.value}..${hi}` : null })} className="w-1/2">
                    <option value="">{Number(a.min)}</option>
                    {numberSteps(a.min!, a.max!).map((v) => <option key={v} value={v}>{t("from")} {v}</option>)}
                  </select>
                  <select value={hi} onChange={(e) => update({ [key]: lo || e.target.value ? `${lo}..${e.target.value}` : null })} className="w-1/2">
                    <option value="">{Number(a.max)}</option>
                    {numberSteps(a.min!, a.max!).map((v) => <option key={v} value={v}>{t("to")} {v}</option>)}
                  </select>
                </div>
              </div>
            );
          })}
        </aside>
      ) : null}

      <section className="flex-1 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-gray-500">{data ? `${t("found")}: ${data.count} ${t("items")}` : ""}</span>
          <select value={params.get("sort") ?? ""} onChange={(e) => update({ sort: e.target.value || null })} className="py-2">
            {query ? <option value="">—</option> : null}
            <option value={query ? "popular" : ""}>{t("sortPopular")}</option>
            <option value="new">{t("sortNew")}</option>
            <option value="price_asc">{t("sortPriceAsc")}</option>
            <option value="price_desc">{t("sortPriceDesc")}</option>
            <option value="rating">{t("sortRating")}</option>
          </select>
        </div>
        {error ? <ErrorBox message={error} /> : !data ? <GridSkeleton n={8} /> : data.results.length === 0 ? (
          <div className="rounded-[2rem] bg-white py-16 text-center ring-1 ring-gray-100 text-gray-500">{t("nothingFound")}</div>
        ) : (
          <>
            <Grid>{data.results.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
            {pages > 1 ? (
              <div className="flex justify-center gap-2">
                <button disabled={page <= 1} onClick={() => update({ page: String(page - 1) })} className="rounded-lg bg-white px-4 py-2 disabled:opacity-40">{t("prev")}</button>
                <span className="px-3 py-2 text-sm">{page} / {pages}</span>
                <button disabled={page >= pages} onClick={() => update({ page: String(page + 1) })} className="rounded-lg bg-white px-4 py-2 disabled:opacity-40">{t("next")}</button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}

function numberSteps(min: string, max: string): string[] {
  const lo = Number(min);
  const hi = Number(max);
  if (!(hi > lo)) return [];
  const step = (hi - lo) / 4;
  return Array.from({ length: 5 }, (_, i) => String(Math.round((lo + step * i) * 10) / 10));
}

function PriceFilter({ min, max, initial, onApply }: {
  min: string; max: string; initial: [string, string]; onApply: (lo: string | null, hi: string | null) => void;
}) {
  const { t } = useApp();
  const [lo, setLo] = useState(initial[0]);
  const [hi, setHi] = useState(initial[1]);
  return (
    <div>
      <h4 className="mb-2 font-semibold">{t("price")}</h4>
      <div className="flex gap-2">
        <input inputMode="numeric" placeholder={String(Math.floor(Number(min)))} value={lo} onChange={(e) => setLo(e.target.value.replace(/\D/g, ""))} className="w-1/2" />
        <input inputMode="numeric" placeholder={String(Math.ceil(Number(max)))} value={hi} onChange={(e) => setHi(e.target.value.replace(/\D/g, ""))} className="w-1/2" />
      </div>
      <button onClick={() => onApply(lo || null, hi || null)} className="mt-2 w-full rounded-lg bg-brand-light py-2 text-sm font-semibold text-brand">{t("apply")}</button>
    </div>
  );
}
