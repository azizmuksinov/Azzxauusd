"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { Button, ErrorBox, Loading, Price, ProductImage, StockBadge, useTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card } from "@/lib/types";

type Row = { code: string; name: string; group: string; values: (string | null)[]; is_different: boolean };
type Data = { products: Card[]; attributes: Row[] };

/** Tovarlarni yonma-yon solishtirish: narx, holat va barcha xususiyatlar; farqlari ajratib ko'rsatiladi. */
export default function ComparePage() {
  const { t, lang, compare, toggleCompare, clearCompare, addToCart, cart } = useApp();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [onlyDiff, setOnlyDiff] = useState(false);
  useTitle(t("compare"));

  const ids = compare.join(",");
  useEffect(() => {
    setError("");
    if (!ids) return setData({ products: [], attributes: [] });
    api<Data>(`/compare?products=${ids}`).then(setData).catch((e) => setError(e.message));
  }, [ids, lang]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading />;
  if (data.products.length === 0) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-line bg-white p-10 text-center">
        <h1 className="text-xl font-bold">{t("compareEmpty")}</h1>
        <p className="mt-2 text-sm text-zinc-500">{t("compareHint")}</p>
        <Link href="/catalog" className="mt-5 inline-flex h-12 items-center rounded-full bg-brand px-6 font-semibold text-white">{t("catalog")}</Link>
      </div>
    );
  }

  const rows = data.attributes.filter((r) => !onlyDiff || r.is_different);
  const groups: [string, Row[]][] = [];
  for (const r of rows) {
    const g = groups.find(([name]) => name === (r.group || ""));
    if (g) g[1].push(r);
    else groups.push([r.group || "", [r]]);
  }
  const n = data.products.length;
  // Telefonda: tor nom ustuni va ixcham tovar ustunlari (yon tomonga suriladi); kompyuterda — keng.
  const cols = {
    "--cols-m": `92px repeat(${n}, minmax(0, 1fr))`,
    "--cols-d": `180px repeat(${n}, minmax(0, 260px))`,
  } as React.CSSProperties;
  const grid = "grid gap-x-3 [grid-template-columns:var(--cols-m)] md:gap-x-4 md:[grid-template-columns:var(--cols-d)]";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="mr-auto text-2xl font-bold tracking-tight">{t("compare")}</h1>
        {n > 1 ? (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} /> {t("onlyDiff")}
          </label>
        ) : null}
        <button onClick={clearCompare} className="text-sm text-zinc-500 hover:text-ink">{t("clearAll")}</button>
      </div>

      <div className="-mx-4 overflow-x-auto px-4">
        <div className="rounded-3xl border border-line bg-white md:!min-w-0" style={{ ...cols, minWidth: 92 + n * 140 }}>
          <div className={`${grid} border-b border-line p-3 md:p-4`}>
            <div />
            {data.products.map((p) => {
              const inCart = cart?.items.some((i) => i.variant_id === p.variant_id);
              return (
                <div key={p.id} className="flex flex-col">
                  <div className="relative">
                    <Link href={`/p/${p.slug}`} className="block aspect-square overflow-hidden rounded-lg border border-line bg-white">
                      <ProductImage src={p.image} category={p.category_slug} seed={p.id} />
                    </Link>
                    <button onClick={() => toggleCompare(p.id)} aria-label={t("remove")}
                      className="absolute right-1 top-1 grid h-7 w-7 place-items-center rounded-full bg-white/90 text-zinc-500 shadow hover:text-ink">×</button>
                  </div>
                  <Link href={`/p/${p.slug}`} className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 hover:text-brand">{p.name}</Link>
                  <div className="mt-1"><Price price={p.price} old={p.old_price} size="sm" /></div>
                  <div className="mt-1 min-h-[18px]"><StockBadge status={p.stock_status} /></div>
                  <Button className="mt-2 !h-9 w-full text-sm" disabled={p.stock_status === "out_of_stock"} onClick={() => addToCart(p.variant_id)}>
                    {p.stock_status === "out_of_stock" ? t("outOfStock") : inCart ? t("inCart") : t("addToCart")}
                  </Button>
                </div>
              );
            })}
          </div>

          {rows.length === 0 ? <p className="p-6 text-center text-sm text-zinc-500">—</p> : null}
          {groups.map(([group, items]) => (
            <div key={group}>
              {group ? <p className="bg-surface px-3 py-2 text-sm font-semibold md:px-4">{group}</p> : null}
              {items.map((r) => (
                <div key={r.code} className={`${grid} border-b border-line px-3 py-2.5 text-[13px] last:border-0 md:px-4 md:text-sm ${r.is_different && n > 1 ? "bg-brand/[0.04]" : ""}`}>
                  <div className="break-words text-zinc-500">{r.name}</div>
                  {r.values.map((v, i) => <div key={i} className={`break-words ${r.is_different && n > 1 ? "font-medium" : ""}`}>{v ?? "—"}</div>)}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
