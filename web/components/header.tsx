"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import type { CategoryNode } from "@/lib/types";

import { IconBox, IconCart, IconClose, IconHeart, IconMenu, IconPin, IconSearch, IconTruck, IconUser } from "./icons";
import { Illustration } from "./illustrations";
import { useApp } from "./providers";

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
      <div className="flex w-full items-center rounded-2xl bg-gray-100 ring-brand transition focus-within:bg-white focus-within:ring-2">
        <IconSearch className="ml-4 h-5 w-5 shrink-0 text-gray-400" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setFocus(true)}
          onBlur={() => setTimeout(() => setFocus(false), 150)}
          placeholder={t("searchPlaceholder")}
          className="w-full !rounded-none !border-0 !bg-transparent !px-3 !py-3 !ring-0"
        />
        <button className="m-1 shrink-0 rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-dark">
          {t("search")}
        </button>
      </div>
      {show ? (
        <div className="absolute left-0 right-0 top-full z-30 mt-2 overflow-hidden rounded-2xl bg-white py-2 shadow-xl ring-1 ring-gray-100">
          {suggest!.categories.map((c) => (
            <Link key={c.slug} href={`/c/${c.slug}`} className="flex items-center gap-3 px-4 py-2 text-sm hover:bg-gray-50">
              <span className="rounded-lg bg-brand-light px-2 py-0.5 text-xs font-semibold text-brand">{t("catalog")}</span>{c.name}
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
    <Link href={href} className="relative flex flex-col items-center gap-0.5 rounded-xl px-2 py-1 text-[11px] font-medium text-gray-600 hover:text-brand sm:px-3">
      {children}
      <span className="hidden sm:block">{label}</span>
      {badge ? (
        <span className="absolute -top-0.5 right-0.5 min-w-[1.25rem] rounded-full bg-rose-500 px-1 text-center text-[11px] font-bold leading-5 text-white sm:right-2">
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
        <Link href="/" className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-fuchsia-500 font-black">T</Link>
        <div className="leading-tight">
          <p className="font-bold">{title}</p>
          <p className="text-xs text-gray-400">{me ? `${me.first_name || ""} ${me.phone}`.trim() : "TexnoDo'kon"}</p>
        </div>
        <span className="ml-auto hidden rounded bg-amber-400/90 px-2 py-0.5 text-xs font-semibold text-gray-900 sm:inline">DEMO</span>
        {me ? <button onClick={logout} className="rounded-xl bg-white/10 px-3 py-2 text-sm hover:bg-white/20">Chiqish</button> : null}
      </div>
    </header>
  );
}

export function Header() {
  const { t, lang, setLang, me, logout, cart, favorites } = useApp();
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
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur">
      <div className="bg-gray-900 text-xs text-gray-300">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2">
          <span className="inline-flex items-center gap-1"><IconPin className="h-4 w-4 text-violet-300" />{t("city")}</span>
          <span className="hidden items-center gap-1 sm:inline-flex"><IconTruck className="h-4 w-4 text-violet-300" />{t("doorDelivery")}</span>
          <span className="ml-auto hidden rounded bg-amber-400/90 px-2 py-0.5 font-semibold text-gray-900 md:inline">{t("demo")}</span>
          <div className="flex overflow-hidden rounded-lg bg-white/10">
            {LANGS.map((l) => (
              <button key={l.code} onClick={() => setLang(l.code)}
                className={`px-2 py-0.5 ${lang === l.code ? "bg-white font-semibold text-gray-900" : "hover:text-white"}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="border-b border-gray-100">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-3 px-4 py-3">
          <Link href="/" className="flex shrink-0 items-center gap-2">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-gradient-to-br from-brand to-fuchsia-500 text-lg font-black text-white shadow-md">T</span>
            <span className="text-xl font-black tracking-tight text-gray-900">
              Texno<span className="text-brand">Do&apos;kon</span>
            </span>
          </Link>
          <button onClick={() => setOpen((v) => !v)}
            className={`hidden shrink-0 items-center gap-2 rounded-2xl px-4 py-3 text-sm font-bold transition md:inline-flex ${open ? "bg-gray-900 text-white" : "bg-brand text-white hover:bg-brand-dark"}`}>
            {open ? <IconClose className="h-5 w-5" /> : <IconMenu className="h-5 w-5" />} {t("catalog")}
          </button>
          <Suspense fallback={<div className="order-last basis-full md:order-none md:basis-auto md:flex-1" />}>
            <SearchBox />
          </Suspense>
          <nav className="ml-auto flex shrink-0 items-center">
            {me ? (
              <>
                <NavIcon href="/orders" label={t("orders")}><IconBox /></NavIcon>
                <button onClick={logout} className="hidden flex-col items-center gap-0.5 px-3 py-1 text-[11px] font-medium text-gray-600 hover:text-brand sm:flex">
                  <IconUser /> {t("logout")}
                </button>
              </>
            ) : (
              <NavIcon href="/login" label={t("login")}><IconUser /></NavIcon>
            )}
            <NavIcon href="/favorites" label={t("favorites")} badge={favorites.size || undefined}><IconHeart /></NavIcon>
            <NavIcon href="/cart" label={t("cart")} badge={cart?.items_count || undefined}><IconCart /></NavIcon>
          </nav>
        </div>
        {tree.length > 0 ? (
          <div className="mx-auto hidden max-w-7xl gap-1 overflow-x-auto px-4 pb-2 text-sm md:flex">
            {tree.flatMap((r) => r.children).map((c) => (
              <Link key={c.id} href={`/c/${c.slug}`}
                className={`shrink-0 rounded-xl px-3 py-1.5 font-medium hover:bg-gray-100 ${pathname === `/c/${c.slug}` ? "bg-brand-light text-brand" : "text-gray-600"}`}>
                {c.name}
              </Link>
            ))}
          </div>
        ) : null}
      </div>

      {open ? (
        <div className="absolute inset-x-0 top-full border-t border-gray-100 bg-white shadow-2xl">
          <div className="mx-auto grid max-w-7xl grid-cols-[260px_1fr] gap-6 px-4 py-6">
            <ul className="space-y-1 border-r border-gray-100 pr-4">
              {tree.map((root, i) => (
                <li key={root.id}>
                  <button onMouseEnter={() => setActive(i)} onClick={() => setActive(i)}
                    className={`flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm font-semibold ${active === i ? "bg-brand-light text-brand" : "hover:bg-gray-50"}`}>
                    <span className="h-9 w-9 overflow-hidden rounded-xl"><Illustration category={root.children[0]?.slug ?? root.slug} seed={i} /></span>
                    {root.name}
                  </button>
                </li>
              ))}
            </ul>
            <div>
              {tree[active] ? (
                <>
                  <Link href={`/c/${tree[active].slug}`} className="text-lg font-extrabold hover:text-brand">{tree[active].name}</Link>
                  <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
                    {tree[active].children.map((c, i) => (
                      <Link key={c.id} href={`/c/${c.slug}`} className="group overflow-hidden rounded-2xl bg-gray-50 ring-1 ring-gray-100 hover:ring-brand">
                        <div className="aspect-[4/3]"><Illustration category={c.slug} seed={i + 1} className="transition group-hover:scale-105" /></div>
                        <p className="px-3 py-2 text-sm font-semibold">{c.name}</p>
                      </Link>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}
