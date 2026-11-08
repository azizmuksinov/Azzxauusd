"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { loc } from "@/lib/site";

import { isStaffPath } from "./header";
import { useApp } from "./providers";

const SOCIAL_LABELS: Record<string, string> = { telegram: "Telegram", instagram: "Instagram", facebook: "Facebook", youtube: "YouTube" };

export function Footer() {
  const { t, lang, site } = useApp();
  const pathname = usePathname();
  if (isStaffPath(pathname)) return null;
  const name = site?.store_name || "TexnoDo'kon";
  const page = (key: string, fallback: string): [string, string] => [loc(site?.pages[key]?.title, lang) || fallback, `/info/${key}`];
  const col = (title: string, items: [string, string][]) => (
    <div>
      <h4 className="mb-3 text-sm font-semibold text-ink">{title}</h4>
      <ul className="space-y-2 text-sm">
        {items.map(([label, href]) => (
          <li key={label}>{href ? <Link href={href} className="hover:text-ink">{label}</Link> : <span>{label}</span>}</li>
        ))}
      </ul>
    </div>
  );
  const socials = Object.entries(site?.socials ?? {}).filter(([, v]) => v);
  return (
    <footer className="mt-20 border-t border-line bg-surface text-zinc-500">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-2 text-sm">
          <p className="text-lg font-extrabold tracking-tight text-brand">{name}</p>
          {loc(site?.footer_about, lang) ? <p>{loc(site?.footer_about, lang)}</p> : <p>{loc(site?.city, lang) || t("city")}</p>}
          {socials.length ? (
            <p className="flex flex-wrap gap-3 pt-1">
              {socials.map(([k, v]) => <a key={k} href={v} target="_blank" rel="noreferrer" className="hover:text-ink">{SOCIAL_LABELS[k] ?? k}</a>)}
            </p>
          ) : null}
        </div>
        {col(t("forBuyers"), [page("how-to-order", t("howToOrder")), page("delivery", t("deliveryAndPay")), page("returns", t("returns"))])}
        <div>
          <h4 className="mb-3 text-sm font-semibold text-ink">{t("contacts")}</h4>
          <ul className="space-y-2 text-sm">
            {site?.phone ? <li><a href={`tel:${site.phone.replace(/[^\d+]/g, "")}`} className="font-medium text-ink">{site.phone}</a></li> : null}
            {site?.email ? <li><a href={`mailto:${site.email}`} className="hover:text-ink">{site.email}</a></li> : null}
            {loc(site?.address, lang) ? <li>{loc(site?.address, lang)}</li> : null}
            {loc(site?.working_hours, lang) ? <li>{loc(site?.working_hours, lang)}</li> : null}
            <li><Link href="/info/about" className="hover:text-ink">{loc(site?.pages.about?.title, lang) || t("aboutUs")}</Link></li>
          </ul>
        </div>
        <div>
          <h4 className="mb-3 text-sm font-semibold text-ink">{t("payMethods")}</h4>
          <p className="text-sm">{site?.pay_methods || "Payme · Click · Uzum Bank · Uzcard · Humo"}</p>
        </div>
      </div>
      <div className="mx-auto flex max-w-7xl flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-4 text-xs">
        <span>© 2026 {name}</span>
        <span className="text-zinc-400">Demo versiya</span>
        <span className="ml-auto flex gap-4">
          <Link href="/kuryer" className="hover:text-ink">Kuryer</Link>
          <Link href="/xodim" className="hover:text-ink">Xodimlar</Link>
          <a href="/admin/" className="hover:text-ink">Admin</a>
          <a href="/api/docs/" className="hover:text-ink">API</a>
        </span>
      </div>
    </footer>
  );
}
