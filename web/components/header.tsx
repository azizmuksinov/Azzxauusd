"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import { loc } from "@/lib/site";
import type { CategoryNode } from "@/lib/types";

import { IconBox, IconCart, IconChevron, IconClose, IconHeart, IconMenu, IconPin, IconScale, IconSearch, IconUser } from "./icons";
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
      <div className="flex h-11 w-full items-center rounded-lg border-2 border-brand bg-white">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder={t("searchPlaceholder")}
          className="h-full w-full !rounded-none !border-0 !bg-transparent !px-3 !py-0"
        />
        <button aria-label={t("search")} className="grid h-full w-12 shrink-0 place-items-center bg-brand text-white hover:bg-brand-dark">
          <IconSearch className="h-5 w-5" />
        </button>
      </div>
      {show ? (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 overflow-hidden rounded-lg border border-line bg-white py-1 shadow-lg">
          {suggest!.categories.map((c) => (
            <Link key={c.slug} href={`/c/${c.slug}`} className="flex items-center gap-3 px-4 py-2 text-sm hover:bg-gray-50">
              <span className="text-zinc-400">{t("catalog")}:</span>{c.name}
            </Link>
          ))}
          {suggest!.products.map((p) => (
            <Link key={p.slug} href={`/p/${p.slug}`} className="flex items-center gap-3 px-4 py-2 text-sm hover:bg-gray-50">
              <IconSearch className="h-4 w-4 text-gray-400" />{p.name}
            </Link>
          ))}
        </div>
      ) : null}
    </form>
  );
}

function NavIcon({ href, label, children, badge }: { href: string; label: string; children: React.ReactNode; badge?: number }) {
  return (
    <Link href={href} className="relative flex flex-col items-center gap-0.5 px-2 py-1 text-xs text-zinc-600 hover:text-ink sm:px-3">
      {children}
      <span className="hidden sm:block">{label}</span>
      {badge ? (
        <span key={badge} className="animate-pop absolute -top-1 right-0 min-w-[18px] rounded-full bg-brand px-1 text-center text-2xs font-semibold leading-[18px] text-white sm:right-2">
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
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
        <Link href={title === "Kuryer" ? "/kuryer" : "/xodim"} className="text-lg font-extrabold tracking-tight">TexnoDo&apos;kon</Link>
        <div className="leading-tight">
          <p className="font-bold">{title}</p>
          <p className="text-xs text-gray-400">{me ? `${me.first_name || ""} ${me.phone}`.trim() : "TexnoDo'kon"}</p>
        </div>
        <span className="flex-1" />
        <span className="hidden rounded bg-amber-400/90 px-2 py-0.5 text-xs font-semibold text-gray-900 sm:inline">DEMO</span>
        <InstallButton scope={title === "Kuryer" ? "/kuryer" : "/xodim"} />
        {me ? <button onClick={logout} className="rounded-xl bg-white/10 px-3 py-2 text-sm hover:bg-white/20">Chiqish</button> : null}
      </div>
    </header>
  );
}

export function Header() {
  const { t, lang, setLang, me, logout, cart, favorites, site, compare } = useApp();
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<CategoryNode[]>([]);
  const [active, setActive] = useState(0);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    api<CategoryNode[]>("/categories").then(setTree).catch(() => setTree([]));
  }, [lang]);

  if (isStaffPath(pathname)) return <StaffBar title={pathname.startsWith("/kuryer") ? "Kuryer" : "Xodim paneli"} />;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-white">
      {site?.announcement.enabled && loc(site.announcement.text, lang) ? (
        <a href={site.announcement.link || undefined} style={{ background: site.announcement.color }}
          className="block px-4 py-2 text-center text-[13px] font-medium text-white">
          {loc(site.announcement.text, lang)}
        </a>
      ) : null}
      <div className="border-b border-line text-[13px] text-zinc-500">
        <div className="mx-auto flex h-9 max-w-7xl items-center gap-5 px-4">
          <span className="inline-flex items-center gap-1"><IconPin className="h-4 w-4" />{loc(site?.city, lang) || t("city")}</span>
          <span className="hidden md:inline">{t("doorDelivery")}</span>
          {site?.phone ? <a href={`tel:${site.phone.replace(/[^\d+]/g, "")}`} className="hidden font-medium text-ink sm:inline">{site.phone}</a> : null}
          <div className="ml-auto flex gap-3">
            {LANGS.map((l) => (
              <button key={l.code} onClick={() => setLang(l.code)}
                className={lang === l.code ? "font-medium text-ink" : "hover:text-ink"}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
        <Link href="/" className="shrink-0 text-[22px] font-extrabold tracking-tight text-brand">
          TexnoDo&apos;kon
        </Link>
        <button onClick={() => setOpen((v) => !v)}
          className="hidden h-11 shrink-0 items-center gap-2 rounded-lg bg-brand-light px-4 text-[15px] font-medium text-brand hover:bg-violet-100 md:inline-flex">
          {open ? <IconClose className="h-5 w-5" /> : <IconMenu className="h-5 w-5" />} {t("catalog")}
        </button>
        <Suspense fallback={<div className="order-last basis-full md:order-none md:basis-auto md:flex-1" />}>
          <SearchBox />
        </Suspense>
        <nav className="ml-auto flex shrink-0 items-center">
          {me ? (
            <>
              <NavIcon href="/orders" label={t("orders")}><IconBox /></NavIcon>
              <button onClick={logout} className="hidden flex-col items-center gap-0.5 px-3 py-1 text-xs text-zinc-600 hover:text-ink sm:flex">
                <IconUser /> {t("logout")}
              </button>
            </>
          ) : (
            <NavIcon href="/login" label={t("login")}><IconUser /></NavIcon>
          )}
          <span className="hidden md:block"><NavIcon href="/compare" label={t("compare")} badge={compare.length || undefined}><IconScale /></NavIcon></span>
          <NavIcon href="/favorites" label={t("favorites")} badge={favorites.size || undefined}><IconHeart /></NavIcon>
          <NavIcon href="/cart" label={t("cart")} badge={cart?.items_count || undefined}><IconCart /></NavIcon>
        </nav>
      </div>
      {tree.length > 0 ? (
        <div className="no-scrollbar mx-auto flex max-w-7xl gap-6 overflow-x-auto px-4 pb-2.5 text-sm">
          {tree.flatMap((r) => r.children).map((c) => (
            <Link key={c.id} href={`/c/${c.slug}`}
              className={`shrink-0 ${pathname === `/c/${c.slug}` ? "text-brand" : "text-zinc-600 hover:text-ink"}`}>
              {c.name}
            </Link>
          ))}
        </div>
      ) : null}

      {open ? (
        <div className="absolute inset-x-0 top-full border-t border-line bg-white shadow-lg">
          <div className="mx-auto grid max-w-7xl grid-cols-[240px_1fr] gap-8 px-4 py-6">
            <ul className="border-r border-line pr-4">
              {tree.map((root, i) => (
                <li key={root.id}>
                  <button onMouseEnter={() => setActive(i)} onClick={() => setActive(i)}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-[15px] ${active === i ? "bg-surface font-medium" : "hover:bg-surface"}`}>
                    {root.name} <IconChevron className="h-4 w-4 text-zinc-400" />
                  </button>
                </li>
              ))}
            </ul>
            <div>
              {tree[active] ? (
                <>
                  <Link href={`/c/${tree[active].slug}`} className="text-lg font-bold hover:text-brand">{tree[active].name}</Link>
                  <ul className="mt-3 grid grid-cols-2 gap-x-8 gap-y-2 lg:grid-cols-3">
                    {tree[active].children.map((c) => (
                      <li key={c.id}><Link href={`/c/${c.slug}`} className="text-[15px] text-zinc-700 hover:text-brand">{c.name}</Link></li>
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
