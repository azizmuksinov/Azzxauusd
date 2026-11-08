"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconChevron } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { RecentlyViewed } from "@/components/product-extras";
import { useApp } from "@/components/providers";
import { ErrorBox, Grid, GridSkeleton, ProductCard, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";
import type { Card, CategoryNode, Page } from "@/lib/types";

type Row = { slug: string; name: string; items: Card[]; minPrice: number };

type Slide = { key: string; title: string; subtitle: string; link: string; color: string; image?: string; art?: string };
type Banner = { id: number; title: string; subtitle: string; image: string; link: string; color: string };

/** Banner: admin bannerlari, bo'lmasa — kategoriya va undagi eng arzon narx (ma'lumotlardan). */
function Hero({ slides, deals }: { slides: Slide[]; deals: Card[] }) {
  const { t } = useApp();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return;
    const id = setInterval(() => setI((x) => (x + 1) % slides.length), 6000);
    return () => clearInterval(id);
  }, [slides.length]);

  if (!slides.length) return <div className="skeleton h-[260px] rounded-2xl md:h-[320px]" />;
  const s = slides[i % slides.length];
  const maxDeal = Math.max(0, ...deals.map((d) => d.discount_percent));
  const external = /^https?:/.test(s.link);

  return (
    <div className="grid gap-3 lg:grid-cols-[1fr_340px]">
      <Link href={s.link || "#"} target={external ? "_blank" : undefined}
        className="relative flex h-[260px] overflow-hidden rounded-2xl text-white transition-colors duration-700 md:h-[320px]" style={{ background: s.color }}>
        {s.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={s.image} src={s.image} alt="" className="absolute inset-0 h-full w-full animate-[fadeIn_.6s_ease-out] object-cover" />
        ) : null}
        <div key={s.key} className={`animate-fade-up relative z-10 flex flex-col justify-center gap-3 p-7 md:p-12 ${s.image ? "bg-gradient-to-r from-black/50 to-transparent" : ""}`}>
          <p className="text-3xl font-extrabold leading-tight tracking-tight md:text-5xl">{s.title}</p>
          {s.subtitle ? <p className="text-lg text-white/85 md:text-2xl">{s.subtitle}</p> : null}
          <span className="mt-2 inline-flex h-11 w-fit items-center gap-1 rounded-lg bg-white px-5 font-medium text-ink">
            {t("heroCta")} <IconChevron className="h-4 w-4" />
          </span>
        </div>
        {s.art && !s.image ? (
          <div key={`art-${s.key}`} className="absolute -right-10 bottom-0 top-0 hidden w-[46%] animate-[fadeIn_.6s_ease-out] opacity-90 sm:block [&_div]:bg-transparent [&_svg]:stroke-white/40">
            <Illustration category={s.art} />
          </div>
        ) : null}
        <div className="absolute bottom-4 left-7 z-10 flex gap-1.5 md:left-12">
          {slides.map((x, k) => (
            <button key={x.key} aria-label={x.title} onClick={(e) => { e.preventDefault(); setI(k); }}
              className={`h-1.5 rounded-full transition-all ${k === i % slides.length ? "w-6 bg-white" : "w-1.5 bg-white/40"}`} />
          ))}
        </div>
      </Link>
      <div className="hidden gap-3 sm:grid sm:grid-cols-2 lg:grid-cols-1">
        {maxDeal > 0 ? (
          <a href="#deals" className="flex flex-col justify-between rounded-2xl bg-[#fdecea] p-6 transition hover:-translate-y-0.5">
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
  const [banners, setBanners] = useState<Banner[]>([]);

  useEffect(() => {
    api<Banner[]>("/banners").then(setBanners).catch(() => setBanners([]));
  }, [lang]);

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
  const slides: Slide[] = [
    ...banners.map((b) => ({ key: `b${b.id}`, title: b.title, subtitle: b.subtitle, link: b.link, color: b.color, image: b.image || undefined })),
    ...(banners.length ? [] : rows.map((r) => ({
      key: r.slug, title: r.name, subtitle: t("fromPrice").replace("{x}", formatMoney(r.minPrice, lang)), link: `/c/${r.slug}`, color: "#5b21b6", art: r.slug,
    }))),
  ];
  const deals = (popular ?? []).filter((p) => p.discount_percent > 0).sort((a, b) => b.discount_percent - a.discount_percent);

  return (
    <div className="space-y-12">
      <Hero slides={slides} deals={deals} />
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


      <RecentlyViewed />
    </div>
  );
}
