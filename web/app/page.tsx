"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { IconCard, IconChevron, IconEye, IconShield, IconTruck } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { RecentlyViewed } from "@/components/product-extras";
import { useApp } from "@/components/providers";
import { ErrorBox, Grid, GridSkeleton, ProductCard, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";
import { loc } from "@/lib/site";
import type { Card, CategoryNode, Page } from "@/lib/types";

type Row = { slug: string; name: string; items: Card[]; minPrice: number };

type Slide = { key: string; title: string; subtitle: string; link: string; color: string; image?: string; art?: string };
type Banner = { id: number; title: string; subtitle: string; image: string; link: string; color: string };

// Admin banner qo'shmagan bo'lsa, kategoriya slaydlari shu ranglarda navbat bilan chiqadi.
const SLIDE_COLORS = [
  "linear-gradient(120deg, #7c3aed 0%, #c026d3 100%)",
  "linear-gradient(120deg, #2563eb 0%, #06b6d4 100%)",
  "linear-gradient(120deg, #f97316 0%, #e11d48 100%)",
  "linear-gradient(120deg, #059669 0%, #14b8a6 100%)",
  "linear-gradient(120deg, #4f46e5 0%, #7c3aed 100%)",
];

/** Banner ostidagi afzalliklar qatori. */
function Benefits() {
  const { t } = useApp();
  const items: [React.ReactNode, string, string, string][] = [
    [<IconTruck key="i" className="h-6 w-6" />, t("benefitDoor"), t("benefitDoorText"), "bg-violet-100 text-violet-700"],
    [<IconEye key="i" className="h-6 w-6" />, t("benefitCheck"), t("benefitCheckText"), "bg-emerald-100 text-emerald-700"],
    [<IconShield key="i" className="h-6 w-6" />, t("benefitWarranty"), t("benefitWarrantyText"), "bg-sky-100 text-sky-700"],
    [<IconCard key="i" className="h-6 w-6" />, t("benefitPay"), t("benefitPayText"), "bg-amber-100 text-amber-700"],
  ];
  return (
    <div className="grid grid-cols-2 gap-2.5 md:gap-3 lg:grid-cols-4">
      {items.map(([icon, title, text, cls]) => (
        <div key={title} className="flex items-center gap-2.5 rounded-2xl border border-line bg-white p-2.5 md:gap-3 md:p-4">
          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl md:h-11 md:w-11 ${cls}`}>{icon}</span>
          <div className="min-w-0 leading-tight">
            <p className="text-[13px] font-semibold text-ink md:text-[15px]">{title}</p>
            <p className="mt-0.5 hidden text-[13px] text-zinc-500 sm:block">{text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

/** Banner: admin bannerlari, bo'lmasa — kategoriya va undagi eng arzon narx (ma'lumotlardan). */
function Hero({ slides, deals }: { slides: Slide[]; deals: Card[] }) {
  const { t } = useApp();
  const [i, setI] = useState(0);
  useEffect(() => {
    if (slides.length < 2) return;
    const id = setInterval(() => setI((x) => (x + 1) % slides.length), 6000);
    return () => clearInterval(id);
  }, [slides.length]);

  if (!slides.length) return <div className="skeleton h-[240px] rounded-3xl md:h-[340px]" />;
  const s = slides[i % slides.length];
  const maxDeal = Math.max(0, ...deals.map((d) => d.discount_percent));
  const external = /^https?:/.test(s.link);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <Link href={s.link || "#"} target={external ? "_blank" : undefined}
          className="group relative flex h-[240px] overflow-hidden rounded-3xl text-white md:h-[340px]" style={{ background: s.color }}>
          {s.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={s.image} src={s.image} alt="" className="absolute inset-0 h-full w-full animate-[fadeIn_.6s_ease-out] object-cover" />
          ) : (
            <>
              <span className="absolute -right-16 -top-24 h-72 w-72 rounded-full bg-white/10" />
              <span className="absolute -bottom-28 right-24 h-64 w-64 rounded-full bg-white/10" />
              <span className="absolute -bottom-10 -left-10 h-32 w-32 rounded-full bg-black/5" />
            </>
          )}
          <div key={s.key} className={`animate-fade-up relative z-10 flex flex-col justify-center gap-2.5 p-6 pb-10 md:gap-3 md:p-12 ${s.image ? "max-w-[62%] bg-gradient-to-r from-black/35 via-black/15 to-transparent [text-shadow:0_1px_12px_rgba(0,0,0,.35)]" : "max-w-[78%] sm:max-w-[60%]"}`}>
            <p className="text-[28px] font-extrabold leading-tight tracking-tight md:text-5xl">{s.title}</p>
            {s.subtitle ? <p className="text-base text-white/90 md:text-2xl">{s.subtitle}</p> : null}
            <span className="mt-1.5 inline-flex h-11 w-fit items-center gap-1 photo rounded-full pl-5 pr-3.5 font-semibold text-zinc-900 shadow-lg transition group-hover:gap-2">
              {t("heroCta")} <IconChevron className="h-4 w-4" />
            </span>
          </div>
          {s.art && !s.image ? (
            <div key={`art-${s.key}`} className="absolute -right-6 bottom-0 top-0 w-[44%] animate-[fadeIn_.6s_ease-out] sm:w-[40%] [&_div]:bg-transparent [&_svg]:h-[62%] [&_svg]:w-[62%] [&_svg]:stroke-white/70">
              <Illustration category={s.art} />
            </div>
          ) : null}
          <div className="absolute bottom-4 left-6 z-10 flex gap-1.5 md:left-12">
            {slides.map((x, k) => (
              <button key={x.key} aria-label={x.title} onClick={(e) => { e.preventDefault(); setI(k); }}
                className={`h-1.5 rounded-full transition-all ${k === i % slides.length ? "photo w-7" : "w-1.5 bg-white/40"}`} />
            ))}
          </div>
        </Link>
        <div className="hidden gap-3 sm:grid sm:grid-cols-2 lg:grid-cols-1">
          {maxDeal > 0 ? (
            <a href="#deals" className="relative flex flex-col justify-between overflow-hidden rounded-3xl bg-gradient-to-br from-rose-500 to-orange-400 p-6 text-white transition hover:-translate-y-0.5 hover:shadow-lg">
              <span className="absolute -right-3 -top-5 select-none text-[120px] font-black leading-none text-white/20">%</span>
              <p className="relative w-fit rounded-full bg-white/20 px-3 py-1 text-sm font-semibold">{t("heroDeals")}</p>
              <p className="relative text-2xl font-extrabold leading-tight tracking-tight">{t("dealsUpTo").replace("{x}", String(maxDeal))}</p>
            </a>
          ) : null}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-3xl bg-brand-light p-6">
            <span className="grid h-11 w-11 place-items-center rounded-xl bg-white text-brand shadow-sm"><IconEye className="h-6 w-6" /></span>
            <div>
              <p className="text-sm font-semibold text-brand">{t("benefitCheck")}</p>
              <p className="mt-1 text-2xl font-extrabold leading-tight tracking-tight text-ink">{t("benefitCheckText")}</p>
            </div>
          </div>
        </div>
      </div>
      <Benefits />
    </div>
  );
}

/** Telefonda bo'lim uzun bo'lib ketmasin: 6 ta tovar; kattaroq ekranda — hammasi. */
function MobileLimit({ i, children }: { i: number; children: React.ReactNode }) {
  return <div className={i >= 6 ? "hidden sm:contents" : "contents"}>{children}</div>;
}

export default function Home() {
  const { t, lang, site } = useApp();
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  const [popular, setPopular] = useState<Card[] | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [banners, setBanners] = useState<Banner[]>([]);
  const [fresh, setFresh] = useState<Card[] | null>(null);
  const [brands, setBrands] = useState<{ slug: string; name: string; logo: string }[]>([]);

  useEffect(() => {
    api<Banner[]>("/banners").then(setBanners).catch(() => setBanners([]));
    api<Page<Card>>("/products?sort=new&page_size=10").then((r) => setFresh(r.results)).catch(() => setFresh([]));
    api<{ slug: string; name: string; logo: string }[] | Page<{ slug: string; name: string; logo: string }>>("/brands?page_size=40")
      .then((r) => setBrands(Array.isArray(r) ? r : r.results))
      .catch(() => setBrands([]));
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
    ...(banners.length ? [] : rows.map((r, i) => ({
      key: r.slug, title: r.name, subtitle: t("fromPrice").replace("{x}", formatMoney(r.minPrice, lang)), link: `/c/${r.slug}`, color: SLIDE_COLORS[i % SLIDE_COLORS.length], art: r.slug,
    }))),
  ];
  const deals = (popular ?? []).filter((p) => p.discount_percent > 0).sort((a, b) => b.discount_percent - a.discount_percent);

  // Bo'limlar tartibi, ko'rinishi va sarlavhalari — admin paneldagi "Sayt" bo'limidan.
  const sections = site?.home_sections.filter((x) => x.enabled) ??
    (["hero", "categories", "deals", "popular", "new", "brands", "recent"] as const).map((key) => ({ key, enabled: true, title: { uz: "", ru: "" } }));
  const title = (key: string) => loc(site?.home_sections.find((x) => x.key === key)?.title, lang);
  const render: Record<string, React.ReactNode> = {
    hero: <Hero slides={slides} deals={deals} />,
    categories: (
      <section>
        <div className={`no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 md:mx-0 md:grid md:grid-cols-6 md:gap-4 md:overflow-visible md:px-0 ${leaves.length > 6 ? "lg:grid-cols-8" : ""}`}>
          {(tree ? leaves : Array.from({ length: 8 }, (_, i) => ({ id: -i, slug: "", name: "" }) as CategoryNode)).map((c) => (
            <Link key={c.id} href={c.slug ? `/c/${c.slug}` : "#"} className="group w-[88px] shrink-0 md:w-auto">
              <div className={`aspect-square overflow-hidden rounded-3xl transition duration-300 group-hover:-translate-y-1 group-hover:shadow-lg ${c.slug ? "" : "skeleton"}`}>
                {c.slug ? <Illustration category={c.slug} tinted className="transition duration-300 group-hover:scale-110" /> : null}
              </div>
              <p className="mt-2 line-clamp-2 text-center text-[13px] font-medium leading-4 text-zinc-700 group-hover:text-brand md:text-sm">{c.name}</p>
            </Link>
          ))}
        </div>
      </section>
    ),
    deals: deals.length > 0 ? (
      <section id="deals" className="deals-panel scroll-mt-40 -mx-4 bg-gradient-to-br from-rose-50 via-orange-50 to-amber-50 px-4 py-5 md:mx-0 md:rounded-3xl md:p-6">
        <div className="mb-4 flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-sale text-lg font-black text-white">%</span>
          <h2 className="text-xl font-extrabold tracking-tight md:text-2xl">{title("deals") || t("deals")}</h2>
        </div>
        <Grid>
          {deals.slice(0, 6).map((p, i) => (
            <div key={p.id} className={i === 5 ? "contents sm:hidden lg:contents xl:hidden" : "contents"}><ProductCard p={p} /></div>
          ))}
        </Grid>
      </section>
    ) : null,
    popular: (
      <section>
        <SectionTitle title={title("popular") || t("popular")} />
        {popular ? <Grid>{popular.slice(0, 10).map((p, i) => <MobileLimit key={p.id} i={i}><ProductCard p={p} /></MobileLimit>)}</Grid> : <GridSkeleton />}
      </section>
    ),
    new: fresh && fresh.length > 0 ? (
      <section>
        <SectionTitle title={title("new") || t("newest")} href="/catalog" />
        <Grid>{fresh.slice(0, 10).map((p, i) => <MobileLimit key={p.id} i={i}><ProductCard p={p} /></MobileLimit>)}</Grid>
      </section>
    ) : null,
    brands: brands.length > 1 ? (
      <section>
        <SectionTitle title={title("brands") || t("allBrands")} />
        <div className="no-scrollbar -mx-4 flex gap-2.5 overflow-x-auto px-4 md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
          {brands.map((b) => (
            <Link key={b.slug} href={`/search?q=${encodeURIComponent(b.name)}`}
              className="flex h-14 shrink-0 items-center justify-center rounded-2xl border border-line bg-white px-5 text-[15px] font-semibold text-zinc-700 transition hover:-translate-y-0.5 hover:border-brand hover:text-brand hover:shadow-md">
              {b.logo ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={b.logo} alt={b.name} className="max-h-8 max-w-[96px] object-contain" />
              ) : b.name}
            </Link>
          ))}
        </div>
      </section>
    ) : null,
    recent: <RecentlyViewed />,
  };

  return (
    <div className="space-y-10 md:space-y-12">
      {error ? <ErrorBox message={error} /> : null}
      {sections.map(({ key }) => <Fragment key={key}>{render[key]}</Fragment>)}
    </div>
  );
}

