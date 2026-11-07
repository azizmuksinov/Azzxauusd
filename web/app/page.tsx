"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconChevron } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { useApp } from "@/components/providers";
import { ErrorBox, Grid, GridSkeleton, ProductCard, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";
import type { Card, CategoryNode, Page } from "@/lib/types";

type Row = { slug: string; name: string; items: Card[]; minPrice: number };

/** Banner: kategoriya va undagi eng arzon narx (ma'lumotlardan). */
function Hero({ slides, deals }: { slides: Row[]; deals: Card[] }) {
  const { t, lang } = useApp();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return;
    const id = setInterval(() => setI((x) => (x + 1) % slides.length), 6000);
    return () => clearInterval(id);
  }, [slides.length]);

  if (!slides.length) return <div className="h-[260px] animate-pulse rounded-2xl bg-surface md:h-[320px]" />;
  const s = slides[i % slides.length];
  const maxDeal = Math.max(0, ...deals.map((d) => d.discount_percent));

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_340px]">
      <Link href={`/c/${s.slug}`} className="relative flex h-[260px] overflow-hidden rounded-2xl bg-brand text-white md:h-[320px]">
        <div className="relative z-10 flex flex-col justify-center gap-3 p-7 md:p-12">
          <p className="text-3xl font-extrabold leading-tight tracking-tight md:text-5xl">{s.name}</p>
          <p className="text-lg text-white/80 md:text-2xl">{t("fromPrice").replace("{x}", formatMoney(s.minPrice, lang))}</p>
          <span className="mt-2 inline-flex h-11 w-fit items-center gap-1 rounded-lg bg-white px-5 font-medium text-brand">
            {t("heroCta")} <IconChevron className="h-4 w-4" />
          </span>
        </div>
        <div className="absolute -right-10 bottom-0 top-0 hidden w-[46%] opacity-90 sm:block [&_div]:bg-transparent [&_svg]:stroke-white/40">
          <Illustration category={s.slug} />
        </div>
        <div className="absolute bottom-4 left-7 z-10 flex gap-1.5 md:left-12">
          {slides.map((x, k) => (
            <button key={x.slug} aria-label={x.name} onClick={(e) => { e.preventDefault(); setI(k); }}
              className={`h-1.5 rounded-full transition-all ${k === i % slides.length ? "w-6 bg-white" : "w-1.5 bg-white/40"}`} />
          ))}
        </div>
      </Link>
      <div className="hidden gap-3 sm:grid sm:grid-cols-2 lg:grid-cols-1">
        {maxDeal > 0 ? (
          <a href="#deals" className="flex flex-col justify-between rounded-2xl bg-[#fdecea] p-6">
            <p className="text-sm font-medium text-sale">{t("heroDeals")}</p>
            <p className="text-2xl font-extrabold leading-tight tracking-tight text-ink">{t("dealsUpTo").replace("{x}", String(maxDeal))}</p>
          </a>
        ) : null}
        <div className="flex flex-col justify-between rounded-2xl bg-surface p-6">
          <p className="text-sm font-medium text-zinc-500">{t("benefitCheck")}</p>
          <p className="text-2xl font-extrabold leading-tight tracking-tight text-ink">{t("benefitCheckText")}</p>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  const { t, lang } = useApp();
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  const [popular, setPopular] = useState<Card[] | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    Promise.all([api<CategoryNode[]>("/categories"), api<Page<Card>>("/products?sort=popular&page_size=20")])
      .then(async ([c, p]) => {
        setTree(c);
        setPopular(p.results);
        const leaves = c.flatMap((r) => (r.children.length ? r.children : [r]));
        const lists = await Promise.all(
          leaves.map((leaf) => api<Page<Card>>(`/products?category=${leaf.slug}&sort=price_asc&page_size=5`)),
        );
        setRows(
          leaves
            .map((leaf, i) => ({
              slug: leaf.slug,
              name: leaf.name,
              items: lists[i].results,
              minPrice: Math.min(...lists[i].results.map((x) => Number(x.price))),
            }))
            .filter((r) => r.items.length > 0),
        );
      })
      .catch((e) => setError(e.message));
  }, [lang]);

  const leaves = tree?.flatMap((r) => (r.children.length ? r.children : [r])) ?? [];
  const deals = (popular ?? []).filter((p) => p.discount_percent > 0).sort((a, b) => b.discount_percent - a.discount_percent);

  return (
    <div className="space-y-12">
      <Hero slides={rows} deals={deals} />
      {error ? <ErrorBox message={error} /> : null}

      <section>
        <div className="no-scrollbar -mx-4 flex gap-4 overflow-x-auto px-4 md:mx-0 md:grid md:grid-cols-6 md:overflow-visible md:px-0">
          {(tree ? leaves : Array.from({ length: 6 }, (_, i) => ({ id: -i, slug: "", name: "" }) as CategoryNode)).map((c) => (
            <Link key={c.id} href={c.slug ? `/c/${c.slug}` : "#"} className="group w-28 shrink-0 md:w-auto">
              <div className="aspect-square overflow-hidden rounded-xl bg-surface transition group-hover:bg-zinc-200/70">
                {c.slug ? <Illustration category={c.slug} className="!bg-transparent" /> : null}
              </div>
              <p className="mt-2 text-center text-sm text-zinc-700 group-hover:text-ink">{c.name}</p>
            </Link>
          ))}
        </div>
      </section>

      {deals.length > 0 ? (
        <section id="deals" className="scroll-mt-40">
          <SectionTitle title={t("deals")} />
          <Grid>{deals.slice(0, 5).map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
        </section>
      ) : null}

      <section>
        <SectionTitle title={t("popular")} />
        {popular ? <Grid>{popular.slice(0, 10).map((p) => <ProductCard key={p.id} p={p} />)}</Grid> : <GridSkeleton />}
      </section>

    </div>
  );
}
