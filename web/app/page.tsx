"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { ErrorBox, Grid, Loading, ProductCard, categoryIcon } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card, CategoryNode, Page } from "@/lib/types";

export default function Home() {
  const { t, lang } = useApp();
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  const [popular, setPopular] = useState<Card[] | null>(null);
  const [fresh, setFresh] = useState<Card[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    Promise.all([
      api<CategoryNode[]>("/categories"),
      api<Page<Card>>("/products?sort=popular&page_size=10"),
      api<Page<Card>>("/products?sort=new&page_size=5"),
    ])
      .then(([c, p, n]) => {
        setTree(c);
        setPopular(p.results);
        setFresh(n.results);
      })
      .catch((e) => setError(e.message));
  }, [lang]);

  if (error) return <ErrorBox message={error} />;
  if (!tree || !popular || !fresh) return <Loading />;
  const leaves = tree.flatMap((r) => (r.children.length ? r.children : [r]));

  return (
    <div className="space-y-10">
      <section className="rounded-3xl bg-gradient-to-r from-brand to-violet-500 p-8 text-white">
        <h1 className="text-3xl font-extrabold md:text-4xl">{t("shopName")}</h1>
        <p className="mt-2 max-w-xl text-violet-100">{t("doorCheck")} · {t("delivery")} 🚚</p>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t("categories")}</h2>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          {leaves.map((c) => (
            <Link key={c.id} href={`/c/${c.slug}`}
              className="flex flex-col items-center gap-2 rounded-2xl bg-white p-4 text-center shadow-sm ring-1 ring-gray-100 hover:ring-brand">
              <span className="text-4xl">{categoryIcon(c.slug)}</span>
              <span className="text-sm font-medium">{c.name}</span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t("popular")}</h2>
        <Grid>{popular.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t("newest")}</h2>
        <Grid>{fresh.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
      </section>
    </div>
  );
}
