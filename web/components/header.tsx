"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { LANGS } from "@/lib/i18n";
import type { CategoryNode } from "@/lib/types";

import { useApp } from "./providers";
import { categoryIcon } from "./ui";

function SearchBox() {
  const { t } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [suggest, setSuggest] = useState<{ products: { slug: string; name: string }[] } | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setSuggest(null);
      return;
    }
    const id = setTimeout(() => {
      api(`/search/suggest?q=${encodeURIComponent(q)}`).then(setSuggest).catch(() => setSuggest(null));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  return (
    <form
      className="relative order-last flex basis-full md:order-none md:basis-auto md:flex-1"
      onSubmit={(e) => {
        e.preventDefault();
        setSuggest(null);
        if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
      }}
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("searchPlaceholder")}
        className="w-full rounded-l-xl border border-r-0 border-gray-200 px-4 py-2.5 outline-none focus:border-brand"
      />
      <button className="rounded-r-xl bg-brand px-5 text-white hover:bg-brand-dark">{t("search")}</button>
      {suggest && suggest.products.length > 0 ? (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 overflow-hidden rounded-xl bg-white shadow-lg ring-1 ring-gray-100">
          {suggest.products.map((p) => (
            <Link key={p.slug} href={`/p/${p.slug}`} onClick={() => setSuggest(null)}
              className="block px-4 py-2 text-sm hover:bg-brand-light">
              {p.name}
            </Link>
          ))}
        </div>
      ) : null}
    </form>
  );
}

export function Header() {
  const { t, lang, setLang, me, logout, cart } = useApp();
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<CategoryNode[]>([]);

  useEffect(() => {
    api<CategoryNode[]>("/categories").then(setTree).catch(() => setTree([]));
  }, [lang]);

  return (
    <header className="sticky top-0 z-40 bg-white shadow-sm">
      <div className="bg-amber-100 py-1 text-center text-xs text-amber-800">{t("demo")}</div>
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <Link href="/" className="shrink-0 text-xl font-extrabold text-brand">
          {t("shopName")}
        </Link>
        <button onClick={() => setOpen((v) => !v)}
          className="hidden shrink-0 rounded-xl bg-brand-light px-4 py-2.5 font-semibold text-brand md:block">
          ☰ {t("catalog")}
        </button>
        <Suspense fallback={<div className="order-last basis-full md:order-none md:basis-auto md:flex-1" />}>
          <SearchBox />
        </Suspense>
        <nav className="ml-auto flex shrink-0 items-center gap-2 text-sm sm:gap-3">
          <select value={lang} onChange={(e) => setLang(e.target.value as typeof lang)}
            className="rounded-lg border-gray-200 bg-transparent py-1 text-sm" aria-label="Til">
            {LANGS.map((l) => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
          {me ? (
            <>
              <Link href="/orders" className="hover:text-brand">📦<span className="hidden sm:inline"> {t("orders")}</span></Link>
              <button onClick={logout} className="hidden text-gray-500 hover:text-brand sm:inline">{t("logout")}</button>
            </>
          ) : (
            <Link href="/login" className="hover:text-brand">{t("login")}</Link>
          )}
          <Link href="/cart" className="relative rounded-xl bg-gray-50 px-3 py-2 hover:bg-brand-light">
            🛒 <span className="hidden sm:inline">{t("cart")}</span>
            {cart && cart.items_count > 0 ? (
              <span className="absolute -right-1 -top-1 rounded-full bg-brand px-1.5 text-xs text-white">
                {cart.items_count}
              </span>
            ) : null}
          </Link>
        </nav>
      </div>
      {open ? (
        <div className="absolute left-0 right-0 border-t bg-white shadow-lg" onMouseLeave={() => setOpen(false)}>
          <div className="mx-auto grid max-w-7xl grid-cols-2 gap-6 px-4 py-6 md:grid-cols-4">
            {tree.map((root) => (
              <div key={root.id}>
                <Link href={`/c/${root.slug}`} onClick={() => setOpen(false)} className="font-semibold hover:text-brand">
                  {categoryIcon(root.slug)} {root.name}
                </Link>
                <ul className="mt-2 space-y-1">
                  {root.children.map((c) => (
                    <li key={c.id}>
                      <Link href={`/c/${c.slug}`} onClick={() => setOpen(false)} className="text-sm text-gray-600 hover:text-brand">
                        {c.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </header>
  );
}
