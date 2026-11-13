"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import { loc } from "@/lib/site";
import type { CategoryNode } from "@/lib/types";

import { IconBox, IconCart, IconChevron, IconClose, IconHeart, IconMenu, IconMoon, IconPhone, IconPin, IconScale, IconSearch, IconSun, IconUser } from "./icons";
import { Star8 } from "./illustrations-star";
import { useApp } from "./providers";
import { InstallButton } from "./pwa";

function SearchBox() {
  const { t } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [focus, setFocus] = useState(false);
  const [suggest, setSuggest] = useState<{ products: { slug: string; name: string }[]; categories: { slug: string; name: string }[] } | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setSuggest(null);
      return;
    }
    const id = setTimeout(() => {
      api(`/search/suggest?q=${encodeURIComponent(q)}`).then(setSuggest).catch(() => setSuggest(null));
    }, 200);
    return () => clearTimeout(id);
  }, [q]);

  const show = focus && suggest && (suggest.products.length > 0 || suggest.categories.length > 0);
  return (
    <form
      className="relative order-last flex basis-full md:order-none md:basis-auto md:flex-1"
      onSubmit={(e) => {
        e.preventDefault();
        setFocus(false);
        if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
      }}
    >
      <div className="flex h-12 w-full items-center rounded-full bg-surface pl-4 pr-1.5 ring-brand/40 transition focus-within:bg-white focus-within:ring-2">
        <IconSearch className="h-5 w-5 shrink-0 text-zinc-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder={t("searchPlaceholder")}
          className="h-full w-full !rounded-none !border-0 !bg-transparent !px-3 !py-0 !shadow-none"
        />
        <button aria-label={t("search")} className="hidden h-9 shrink-0 items-center rounded-full bg-brand px-5 text-sm font-semibold text-white transition hover:bg-brand-dark sm:inline-flex">
          {t("search")}
        </button>
      </div>
      {show ? (
        <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-3xl bg-white p-1.5 shadow-dock">
          {suggest!.categories.map((c) => (
            <Link key={c.slug} href={`/c/${c.slug}`} className="flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm hover:bg-surface">
              <span className="rounded-full bg-brand-light px-2 py-0.5 text-xs font-medium text-brand">{t("catalog")}</span>{c.name}
            </Link>
          ))}
          {suggest!.products.map((p) => (
            <Link key={p.slug} href={`/p/${p.slug}`} className="flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm hover:bg-surface">
              <IconSearch className="h-4 w-4 shrink-0 text-zinc-400" />{p.name}
            </Link>
          ))}
        </div>
      ) : null}
    </form>
  );
}

/** Sarlavhadagi dumaloq amal tugmasi (savat, sevimlilar...) — son belgisi bilan. */
function NavIcon({ href, label, children, badge }: { href: string; label: string; children: React.ReactNode; badge?: number }) {
  return (
    <Link href={href} title={label} aria-label={label}
      className="relative grid h-11 w-11 place-items-center rounded-full text-ink transition hover:bg-surface hover:text-brand">
      {children}
      {badge ? (
        <span key={badge} className="animate-pop absolute -right-0.5 -top-0.5 min-w-[20px] rounded-full bg-sale px-1 text-center text-2xs font-bold leading-5 text-white ring-2 ring-white">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}

export function isStaffPath(pathname: string): boolean {
  return pathname.startsWith("/kuryer") || pathname.startsWith("/xodim");
}

function StaffBar({ title }: { title: string }) {
  const { me, logout } = useApp();
  return (
    <header className="sticky top-0 z-40 bg-gray-900 text-white">
      <div className={`mx-auto flex items-center gap-3 px-4 py-3 ${title === "Kuryer" ? "max-w-7xl" : "max-w-[1600px]"}`}>
        <Link href={title === "Kuryer" ? "/kuryer" : "/xodim"} className="flex items-center gap-2 font-display text-[15px] font-bold tracking-tight">
          <Star8 className="h-5 w-5 text-teal-300" filled /> TexnoDo&apos;kon
        </Link>
        <div className="leading-tight">
          <p className="font-bold">{title}</p>
          <p className="text-xs text-gray-400">{me ? `${me.first_name || ""} ${me.phone}`.trim() : "TexnoDo'kon"}</p>
        </div>
        <span className="flex-1" />
        <span className="hidden rounded bg-amber-400/90 px-2 py-0.5 text-xs font-semibold text-gray-900 sm:inline">DEMO</span>
        <InstallButton scope={title === "Kuryer" ? "/kuryer" : "/xodim"} />
        {me ? <button onClick={logout} className="rounded-full bg-white/10 px-4 py-2 text-sm hover:bg-white/20">Chiqish</button> : null}
      </div>
    </header>
  );
}

export function Header() {
  const { t, lang, setLang, me, logout, cart, favorites, site, compare, theme, toggleTheme } = useApp();
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<CategoryNode[]>([]);
  const [active, setActive] = useState(0);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    api<CategoryNode[]>("/categories").then(setTree).catch(() => setTree([]));
  }, [lang]);

  // Telefonda pastga varaqlanganda yuqori qator va kategoriya yorliqlari yig'iladi — ekran tovarlarga qoladi.
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const onScroll = () => setCompact((c) => (c ? window.scrollY > 40 : window.scrollY > 220));
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (isStaffPath(pathname)) return <StaffBar title={pathname.startsWith("/kuryer") ? "Kuryer" : "Xodim paneli"} />;
  const name = site?.store_name || "TexnoDo'kon";

  return (
    <header className="sticky top-0 z-40 bg-page/85 backdrop-blur-xl">
      {site?.announcement.enabled && loc(site.announcement.text, lang) ? (
        <a href={site.announcement.link || undefined} style={{ background: site.announcement.color }}
          className="block px-4 py-2 text-center text-[13px] font-medium text-white">
          {loc(site.announcement.text, lang)}
        </a>
      ) : null}

      {/* Yuqori qator: shahar, aloqa, mavzu va til */}
      <div className={`mx-auto h-9 max-w-7xl items-center gap-4 px-4 text-[13px] text-zinc-500 md:flex ${compact ? "hidden" : "flex"}`}>
        <span className="inline-flex items-center gap-1"><IconPin className="h-4 w-4 text-brand" />{loc(site?.city, lang) || t("city")}</span>
        <span className="hidden md:inline">{t("doorDelivery")}</span>
        {site?.phone ? (
          <a href={`tel:${site.phone.replace(/[^\d+]/g, "")}`} className="hidden items-center gap-1 font-semibold text-ink sm:inline-flex">
            <IconPhone className="h-3.5 w-3.5 text-brand" />{site.phone}
          </a>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={toggleTheme} title={theme === "dark" ? t("themeLight") : t("themeDark")} aria-label={theme === "dark" ? t("themeLight") : t("themeDark")}
            className="inline-flex h-7 items-center gap-1.5 rounded-full bg-white px-2.5 text-xs font-medium text-ink shadow-card transition hover:text-brand">
            {theme === "dark" ? <IconSun className="h-4 w-4" /> : <IconMoon className="h-4 w-4" />}
            <span className="hidden sm:inline">{theme === "dark" ? t("themeLight") : t("themeDark")}</span>
          </button>
          <div className="flex h-7 items-center rounded-full bg-white p-0.5 shadow-card">
            {LANGS.map((l) => (
              <button key={l.code} onClick={() => setLang(l.code)}
                className={`h-6 rounded-full px-2 text-xs font-medium transition ${lang === l.code ? "bg-ink text-white" : "text-zinc-500 hover:text-ink"}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Asosiy "orol": logotip, katalog, qidiruv, amallar */}
      <div className={`mx-auto max-w-7xl px-2 pb-2 sm:px-4 ${compact ? "max-md:pt-2" : ""}`}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[28px] bg-white p-2 shadow-card md:flex-nowrap md:rounded-full md:pl-5">
          <Link href="/" className="flex shrink-0 items-center gap-2 pl-2 font-display text-[17px] font-bold tracking-tight text-ink md:pl-0">
            <span className="grid h-9 w-9 place-items-center rounded-2xl bg-brand text-white"><Star8 className="h-5 w-5" filled /></span>
            <span>{name}</span>
          </Link>
          <button onClick={() => setOpen((v) => !v)}
            className="hidden h-12 shrink-0 items-center gap-2 rounded-full bg-ink px-5 text-[15px] font-semibold text-white transition hover:bg-black md:inline-flex">
            {open ? <IconClose className="h-5 w-5" /> : <IconMenu className="h-5 w-5" />} {t("catalog")}
          </button>
          <Suspense fallback={<div className="order-last basis-full md:order-none md:basis-auto md:flex-1" />}>
            <SearchBox />
          </Suspense>
          <nav className="ml-auto flex shrink-0 items-center md:ml-0">
            {me ? (
              <>
                <span className="hidden md:block"><NavIcon href="/orders" label={t("orders")}><IconBox /></NavIcon></span>
                <button onClick={logout} title={t("logout")} aria-label={t("logout")}
                  className="hidden h-11 w-11 place-items-center rounded-full text-ink transition hover:bg-surface hover:text-brand md:grid">
                  <IconUser />
                </button>
              </>
            ) : (
              <span className="hidden md:block"><NavIcon href="/login" label={t("login")}><IconUser /></NavIcon></span>
            )}
            <span className="hidden md:block"><NavIcon href="/compare" label={t("compare")} badge={compare.length || undefined}><IconScale /></NavIcon></span>
            <NavIcon href="/favorites" label={t("favorites")} badge={favorites.size || undefined}><IconHeart /></NavIcon>
            <Link href="/cart" aria-label={t("cart")}
              className="relative ml-1 inline-flex h-11 items-center gap-2 rounded-full bg-brand px-3.5 font-semibold text-white transition hover:bg-brand-dark md:h-12 md:px-5">
              <IconCart className="h-5 w-5" />
              <span className="hidden text-[15px] lg:inline">{t("cart")}</span>
              {cart?.items_count ? (
                <span key={cart.items_count} className="animate-pop min-w-[22px] rounded-full bg-white px-1.5 text-center text-xs font-bold leading-[22px] text-brand">{cart.items_count}</span>
              ) : null}
            </Link>
          </nav>
        </div>
      </div>

      {/* Kategoriya yorliqlari */}
      {tree.length > 0 ? (
        <div className={`no-scrollbar mx-auto max-w-7xl gap-1.5 overflow-x-auto px-4 pb-2.5 text-sm md:flex ${compact ? "hidden" : "flex"}`}>
          {tree.flatMap((r) => r.children).map((c) => (
            <Link key={c.id} href={`/c/${c.slug}`}
              className={`shrink-0 rounded-full px-3.5 py-1.5 font-medium transition ${pathname === `/c/${c.slug}` ? "bg-brand text-white" : "bg-white/80 text-zinc-600 hover:bg-white hover:text-brand"}`}>
              {c.name}
            </Link>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="absolute inset-x-0 top-full px-4">
          <div className="mx-auto grid max-w-7xl grid-cols-[260px_1fr] gap-8 rounded-[32px] bg-white p-6 shadow-dock">
            <ul className="space-y-1 border-r border-line pr-4">
              {tree.map((root, i) => (
                <li key={root.id}>
                  <button onMouseEnter={() => setActive(i)} onClick={() => setActive(i)}
                    className={`flex w-full items-center justify-between rounded-2xl px-4 py-3 text-left text-[15px] font-medium transition ${active === i ? "bg-brand text-white" : "hover:bg-surface"}`}>
                    {root.name} <IconChevron className="h-4 w-4 opacity-60" />
                  </button>
                </li>
              ))}
            </ul>
            <div>
              {tree[active] ? (
                <>
                  <Link href={`/c/${tree[active].slug}`} className="font-display text-lg font-bold hover:text-brand">{tree[active].name}</Link>
                  <ul className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-3">
                    {tree[active].children.map((c) => (
                      <li key={c.id}>
                        <Link href={`/c/${c.slug}`} className="block rounded-2xl bg-surface px-4 py-3 text-[15px] font-medium text-zinc-700 transition hover:bg-brand-light hover:text-brand">{c.name}</Link>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}
