"use client";

import Link from "next/link";
import { Fragment, useEffect, useState } from "react";

import { IconCard, IconChevron, IconEye, IconShield, IconTruck } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { Star8 } from "@/components/illustrations-star";
import { DealsStrip } from "@/components/loyalty";
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

// Admin banner qo'shmagan bo'lsa, kategoriya slaydlari shu ranglarda navbat bilan chiqadi (feruza oilasi + iliq urg'u).
const SLIDE_COLORS = [
  "linear-gradient(125deg, #0f766e 0%, #0d9488 45%, #06b6d4 100%)",
  "linear-gradient(125deg, #0b3b47 0%, #0e7490 55%, #22d3ee 100%)",
  "linear-gradient(125deg, #b45309 0%, #f59e0b 100%)",
  "linear-gradient(125deg, #134e4a 0%, #059669 100%)",
  "linear-gradient(125deg, #9f1239 0%, #e11d48 60%, #fb7185 100%)",
];

/** Banner ostidagi afzalliklar: bitta oq kartochkada to'rtta band. */
function Benefits() {
  const { t } = useApp();
  const items: [React.ReactNode, string, string][] = [
    [<IconTruck key="i" className="h-6 w-6" />, t("benefitDoor"), t("benefitDoorText")],
    [<IconEye key="i" className="h-6 w-6" />, t("benefitCheck"), t("benefitCheckText")],
    [<IconShield key="i" className="h-6 w-6" />, t("benefitWarranty"), t("benefitWarrantyText")],
    [<IconCard key="i" className="h-6 w-6" />, t("benefitPay"), t("benefitPayText")],
  ];
  return (
    <div className="grid grid-cols-2 gap-x-2 gap-y-4 rounded-3xl bg-white p-4 shadow-card md:p-5 lg:grid-cols-4 lg:divide-x lg:divide-line">
      {items.map(([icon, title, text]) => (
        <div key={title} className="flex items-center gap-3 lg:px-4 lg:first:pl-0 lg:last:pr-0">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-brand-light text-brand md:h-12 md:w-12">{icon}</span>
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

  if (!slides.length) return <div className="skeleton h-[280px] rounded-[32px] md:h-[400px]" />;
  const n = i % slides.length;
  const s = slides[n];
  const maxDeal = Math.max(0, ...deals.map((d) => d.discount_percent));
  const external = /^https?:/.test(s.link);
  const two = (x: number) => String(x).padStart(2, "0");

  return (
    <div className="space-y-3 md:space-y-4">
      <div className="grid gap-3 md:gap-4 lg:grid-cols-[1fr_330px]">
        <Link href={s.link || "#"} target={external ? "_blank" : undefined}
          className="group relative flex h-[280px] overflow-hidden rounded-[32px] text-white shadow-card md:h-[400px]" style={{ background: s.color }}>
          {s.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={s.image} src={s.image} alt="" className="absolute inset-0 h-full w-full animate-[fadeIn_.6s_ease-out] object-cover" />
          ) : (
            <>
              {/* koshin naqshi (o'ngdan chapga so'nadi) va sekin aylanuvchi yulduz */}
              <span className="tiles absolute inset-0 [mask-image:linear-gradient(to_left,black,transparent_75%)]" />
              <Star8 className="animate-spin-slow absolute -right-24 -top-24 h-[340px] w-[340px] text-white/10 md:h-[460px] md:w-[460px]" />
            </>
          )}
          <div key={s.key} className={`animate-fade-up relative z-10 flex flex-col justify-center gap-3 p-6 pb-12 md:gap-4 md:p-12 ${s.image ? "max-w-[62%] bg-gradient-to-r from-black/40 via-black/15 to-transparent [text-shadow:0_1px_12px_rgba(0,0,0,.35)]" : "max-w-[68%] sm:max-w-[60%]"}`}>
            <p className="font-display text-[26px] font-bold leading-[1.1] tracking-tight md:text-[46px]">{s.title}</p>
            {s.subtitle ? <p className="w-fit rounded-full bg-white/15 px-4 py-1.5 text-[15px] font-semibold backdrop-blur md:text-xl">{s.subtitle}</p> : null}
            <span className="photo mt-1 inline-flex h-12 w-fit items-center gap-2 rounded-full pl-5 pr-1.5 font-semibold text-zinc-900 shadow-lg">
              {t("heroCta")}
              <span className="grid h-9 w-9 place-items-center rounded-full bg-brand text-white transition group-hover:translate-x-0.5"><IconChevron className="h-4 w-4" /></span>
            </span>
          </div>
          {s.art && !s.image ? (
            <div key={`art-${s.key}`} className="absolute right-4 top-1/2 h-32 w-32 -translate-y-1/2 animate-[fadeIn_.6s_ease-out] overflow-hidden rounded-full bg-white/10 ring-1 ring-white/25 backdrop-blur-sm sm:h-44 sm:w-44 md:right-14 md:h-64 md:w-64 [&_div]:bg-transparent [&_svg]:h-[52%] [&_svg]:w-[52%] [&_svg]:stroke-white">
              <Illustration category={s.art} />
            </div>
          ) : null}
          <div className="absolute bottom-5 left-6 z-10 flex items-center gap-1.5 md:left-12">
            {slides.map((x, k) => (
              <button key={x.key} aria-label={x.title} onClick={(e) => { e.preventDefault(); setI(k); }}
                className={`h-1.5 rounded-full transition-all ${k === n ? "photo w-8" : "w-1.5 bg-white/40 hover:bg-white/70"}`} />
            ))}
          </div>
          <span className="absolute bottom-4 right-6 z-10 font-display text-sm font-semibold text-white/70 md:right-10">{two(n + 1)} / {two(slides.length)}</span>
        </Link>

        <div className="hidden gap-3 sm:grid sm:grid-cols-2 md:gap-4 lg:grid-cols-1">
          {maxDeal > 0 ? (
            <a href="#deals" className="group relative flex flex-col justify-between overflow-hidden rounded-[32px] bg-white p-6 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift">
              <p className="w-fit rounded-full bg-sale/10 px-3 py-1 text-sm font-semibold text-sale">{t("heroDeals")}</p>
              <div>
                <p className="font-display text-[56px] font-bold leading-none tracking-tight text-sale">−{maxDeal}%</p>
                <p className="mt-2 flex items-center justify-between text-[15px] font-semibold text-ink">
                  {t("dealsUpTo").replace("{x}", String(maxDeal))}
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink text-white transition group-hover:translate-x-0.5"><IconChevron className="h-4 w-4" /></span>
                </p>
              </div>
            </a>
          ) : null}
          <div className="relative flex flex-col justify-between overflow-hidden rounded-[32px] bg-[#0a1f24] p-6 text-white shadow-card">
            <span className="tiles absolute inset-0 opacity-70" />
            <span className="relative grid h-12 w-12 place-items-center rounded-2xl bg-white/10 text-teal-300 ring-1 ring-white/15"><IconEye className="h-6 w-6" /></span>
            <div className="relative">
              <p className="text-sm font-semibold text-teal-300">{t("benefitCheck")}</p>
              <p className="mt-1 font-display text-[22px] font-bold leading-tight">{t("benefitCheckText")}</p>
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
    hero: (
      <div className="space-y-3 md:space-y-4">
        <Hero slides={slides} deals={deals} />
        <DealsStrip />
      </div>
    ),
    categories: (
      <section>
        <div className={`no-scrollbar -mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 md:mx-0 md:grid md:grid-cols-6 md:gap-4 md:overflow-visible md:px-0 md:pb-0 ${leaves.length > 6 ? "lg:grid-cols-8" : ""}`}>
          {(tree ? leaves : Array.from({ length: 8 }, (_, i) => ({ id: -i, slug: "", name: "" }) as CategoryNode)).map((c) => (
            <Link key={c.id} href={c.slug ? `/c/${c.slug}` : "#"}
              className="group w-[104px] shrink-0 rounded-3xl bg-white p-2 shadow-card transition duration-300 hover:-translate-y-1 hover:shadow-lift md:w-auto md:p-2.5">
              <div className={`aspect-square overflow-hidden rounded-2xl ${c.slug ? "" : "skeleton"}`}>
                {c.slug ? <Illustration category={c.slug} tinted className="transition duration-500 group-hover:scale-110" /> : null}
              </div>
              <p className="mt-2 line-clamp-2 min-h-[32px] px-0.5 text-center text-[13px] font-semibold leading-4 text-ink group-hover:text-brand md:text-sm">{c.name}</p>
            </Link>
          ))}
        </div>
      </section>
    ),
    deals: deals.length > 0 ? (
      <section id="deals" className="deals-panel -mx-4 scroll-mt-44 px-4 py-6 md:mx-0 md:rounded-[32px] md:p-7">
        <div className="mb-4 flex items-center gap-3 md:mb-5">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-sale font-display text-lg font-bold text-white">%</span>
          <h2 className="text-[22px] font-extrabold tracking-tight md:text-[26px]">{title("deals") || t("deals")}</h2>
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
        <div className="no-scrollbar -mx-4 flex gap-2.5 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:overflow-visible md:px-0">
          {brands.map((b) => (
            <Link key={b.slug} href={`/search?q=${encodeURIComponent(b.name)}`}
              className="flex h-14 shrink-0 items-center justify-center rounded-full bg-white px-6 text-[15px] font-semibold text-ink shadow-card transition hover:-translate-y-0.5 hover:text-brand hover:shadow-lift">
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
    <div className="space-y-9 md:space-y-14">
      {error ? <ErrorBox message={error} /> : null}
      {sections.map(({ key }) => <Fragment key={key}>{render[key]}</Fragment>)}
    </div>
  );
}

