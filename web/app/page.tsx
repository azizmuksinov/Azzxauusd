"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconCard, IconChevron, IconEye, IconShield, IconTruck } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { useApp } from "@/components/providers";
import { ErrorBox, Grid, GridSkeleton, ProductCard, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { Key } from "@/lib/i18n";
import type { Brand, Card, CategoryNode, Page } from "@/lib/types";

const SLIDES: { title: Key; text: Key; href: string; from: string; to: string; art: string }[] = [
  { title: "heroTitle1", text: "heroText1", href: "/c/maishiy-texnika", from: "from-violet-700", to: "to-fuchsia-500", art: "muzlatkichlar" },
  { title: "heroTitle2", text: "heroText2", href: "/c/elektronika", from: "from-indigo-700", to: "to-sky-500", art: "smartfonlar" },
  { title: "heroTitle3", text: "heroText3", href: "/c/televizorlar", from: "from-emerald-700", to: "to-teal-400", art: "televizorlar" },
];

const TILE_BG = ["bg-violet-50", "bg-sky-50", "bg-emerald-50", "bg-orange-50", "bg-pink-50", "bg-indigo-50"];

function Hero() {
  const { t } = useApp();
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI((x) => (x + 1) % SLIDES.length), 5000);
    return () => clearInterval(id);
  }, []);
  const s = SLIDES[i];
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className={`relative overflow-hidden rounded-[2rem] bg-gradient-to-br ${s.from} ${s.to} p-8 text-white transition-colors duration-700 md:p-12`}>
        <div className="relative z-10 max-w-md">
          <span className="rounded-full bg-white/20 px-3 py-1 text-xs font-semibold backdrop-blur">{t("doorDelivery")}</span>
          <h1 className="mt-4 text-3xl font-black leading-tight md:text-5xl">{t(s.title)}</h1>
          <p className="mt-3 text-white/85 md:text-lg">{t(s.text)}</p>
          <Link href={s.href} className="mt-6 inline-flex items-center gap-1 rounded-2xl bg-white px-6 py-3 font-bold text-gray-900 shadow-lg transition hover:scale-[1.03]">
            {t("heroCta")} <IconChevron className="h-5 w-5" />
          </Link>
        </div>
        <div className="pointer-events-none absolute -bottom-6 -right-6 hidden h-80 w-80 opacity-95 sm:block md:h-96 md:w-96">
          <div className="h-full w-full overflow-hidden rounded-[3rem] rotate-6 shadow-2xl ring-8 ring-white/10">
            <Illustration category={s.art} seed={i} />
          </div>
        </div>
        <div className="absolute bottom-5 left-8 z-10 flex gap-2 md:left-12">
          {SLIDES.map((_, k) => (
            <button key={k} aria-label={`slide ${k + 1}`} onClick={() => setI(k)}
              className={`h-2 rounded-full transition-all ${k === i ? "w-8 bg-white" : "w-2 bg-white/50"}`} />
          ))}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
        <Link href="/c/konditsionerlar" className="group relative overflow-hidden rounded-[2rem] bg-sky-100 p-6">
          <p className="relative z-10 max-w-[60%] text-lg font-extrabold leading-tight text-sky-950">{t("benefitCheck")}</p>
          <p className="relative z-10 mt-1 max-w-[60%] text-sm text-sky-800">{t("benefitCheckText")}</p>
          <div className="absolute -bottom-4 -right-4 h-36 w-36 overflow-hidden rounded-3xl transition group-hover:scale-105"><Illustration category="konditsionerlar" seed={1} /></div>
        </Link>
        <Link href="/c/noutbuklar" className="group relative overflow-hidden rounded-[2rem] bg-amber-100 p-6">
          <p className="relative z-10 max-w-[60%] text-lg font-extrabold leading-tight text-amber-950">{t("benefitWarranty")}</p>
          <p className="relative z-10 mt-1 max-w-[60%] text-sm text-amber-800">{t("benefitWarrantyText")}</p>
          <div className="absolute -bottom-4 -right-4 h-36 w-36 overflow-hidden rounded-3xl transition group-hover:scale-105"><Illustration category="noutbuklar" seed={3} /></div>
        </Link>
      </div>
    </div>
  );
}

function Benefits() {
  const { t } = useApp();
  const items = [
    [IconTruck, "benefitDoor", "benefitDoorText"],
    [IconEye, "benefitCheck", "benefitCheckText"],
    [IconShield, "benefitWarranty", "benefitWarrantyText"],
    [IconCard, "benefitPay", "benefitPayText"],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {items.map(([Icon, title, text]) => (
        <div key={title} className="flex items-center gap-3 rounded-3xl bg-white p-4 ring-1 ring-gray-100">
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-brand-light text-brand"><Icon /></span>
          <div>
            <p className="text-sm font-bold leading-tight">{t(title)}</p>
            <p className="text-xs text-gray-500">{t(text)}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const { t, lang } = useApp();
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  const [popular, setPopular] = useState<Card[] | null>(null);
  const [rows, setRows] = useState<{ slug: string; name: string; items: Card[] }[] | null>(null);
  const [brands, setBrands] = useState<Brand[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    Promise.all([
      api<CategoryNode[]>("/categories"),
      api<Page<Card>>("/products?sort=popular&page_size=20"),
      api<Brand[]>("/brands"),
    ])
      .then(async ([c, p, b]) => {
        setTree(c);
        setPopular(p.results);
        setBrands(b);
        // Har bir asosiy kategoriya uchun alohida qator (eng arzonidan).
        const lists = await Promise.all(
          c.map((root) => api<Page<Card>>(`/products?category=${root.slug}&sort=price_asc&page_size=5`)),
        );
        setRows(c.map((root, i) => ({ slug: root.slug, name: root.name, items: lists[i].results })));
      })
      .catch((e) => setError(e.message));
  }, [lang]);

  const leaves = tree?.flatMap((r) => (r.children.length ? r.children : [r])) ?? [];
  const deals = (popular ?? []).filter((p) => p.discount_percent > 0).sort((a, b) => b.discount_percent - a.discount_percent);

  return (
    <div className="space-y-12">
      <Hero />
      <Benefits />
      {error ? <ErrorBox message={error} /> : null}

      <section>
        <SectionTitle title={t("categories")} />
        <div className="no-scrollbar -mx-4 flex gap-3 overflow-x-auto px-4 md:mx-0 md:grid md:grid-cols-6 md:overflow-visible md:px-0">
          {(tree ? leaves : Array.from({ length: 6 }, (_, i) => ({ id: -i, slug: "", name: "" } as CategoryNode))).map((c, i) => (
            <Link key={c.id} href={c.slug ? `/c/${c.slug}` : "#"}
              className={`group w-36 shrink-0 overflow-hidden rounded-3xl ${TILE_BG[i % TILE_BG.length]} p-3 transition hover:-translate-y-0.5 hover:shadow-md md:w-auto`}>
              <p className="min-h-[2.5rem] text-sm font-bold leading-tight text-gray-800">{c.name}</p>
              <div className="mt-1 aspect-square overflow-hidden rounded-2xl">
                {c.slug ? <Illustration category={c.slug} seed={i} className="transition duration-300 group-hover:scale-110" /> : <div className="h-full animate-pulse bg-white/60" />}
              </div>
            </Link>
          ))}
        </div>
      </section>

      {deals.length > 0 ? (
        <section className="rounded-[2rem] bg-gradient-to-br from-rose-50 to-orange-50 p-5 md:p-6">
          <SectionTitle title={`🔥 ${t("deals")}`} />
          <Grid>{deals.slice(0, 5).map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
        </section>
      ) : null}

      <section>
        <SectionTitle title={t("popular")} />
        {popular ? <Grid>{popular.slice(0, 10).map((p) => <ProductCard key={p.id} p={p} />)}</Grid> : <GridSkeleton />}
      </section>

      {brands.length > 0 ? (
        <section>
          <SectionTitle title={t("brandsTitle")} />
          <div className="no-scrollbar flex gap-3 overflow-x-auto">
            {brands.map((b) => (
              <Link key={b.slug} href={`/search?q=${encodeURIComponent(b.name)}`}
                className="grid h-20 min-w-[9rem] place-items-center rounded-3xl bg-white px-6 text-lg font-black tracking-tight text-gray-800 ring-1 ring-gray-100 transition hover:text-brand hover:ring-brand">
                {b.name}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {(rows ?? []).filter((r) => r.items.length > 0).map((r) => (
        <section key={r.slug}>
          <SectionTitle title={r.name} href={`/c/${r.slug}`} />
          <Grid>{r.items.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
        </section>
      ))}
    </div>
  );
}
