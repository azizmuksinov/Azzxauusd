"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { loc } from "@/lib/site";

import { isStaffPath } from "./header";
import { Star8 } from "./illustrations-star";
import { useApp } from "./providers";

const SOCIAL_LABELS: Record<string, string> = { telegram: "Telegram", instagram: "Instagram", facebook: "Facebook", youtube: "YouTube" };

export function Footer() {
  const { t, lang, site } = useApp();
  const pathname = usePathname();
  if (isStaffPath(pathname)) return null;
  const name = site?.store_name || "TexnoDo'kon";
  const page = (key: string, fallback: string): [string, string] => [loc(site?.pages[key]?.title, lang) || fallback, `/info/${key}`];
  const h4 = "mb-3.5 text-[13px] font-semibold uppercase tracking-wider text-teal-300";
  const link = "transition hover:text-white";
  const col = (title: string, items: [string, string][]) => (
    <div>
      <h4 className={h4}>{title}</h4>
      <ul className="space-y-2.5 text-[15px]">
        {items.map(([label, href]) => (
          <li key={label}>{href ? <Link href={href} className={link}>{label}</Link> : <span>{label}</span>}</li>
        ))}
      </ul>
    </div>
  );
  const socials = Object.entries(site?.socials ?? {}).filter(([, v]) => v);
  const pays = (site?.pay_methods || "Payme · Click · Uzum Bank · Uzcard · Humo").split(/\s*[·,;|]\s*/).filter(Boolean);
  return (
    <footer className="relative mt-16 overflow-hidden rounded-t-[36px] bg-[#0a1f24] pb-24 text-white/60 md:mt-24 md:rounded-t-[48px] md:pb-0">
      <span className="tiles pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" />
      <Star8 className="pointer-events-none absolute -right-20 -top-20 h-72 w-72 text-white/[0.04]" />
      <div className="relative mx-auto grid max-w-7xl gap-x-8 gap-y-9 px-5 py-10 sm:grid-cols-2 md:py-14 lg:grid-cols-[1.3fr_1fr_1fr_1fr]">
        <div className="space-y-4 text-[15px]">
          <p className="flex items-center gap-2.5 font-display text-xl font-bold tracking-tight text-white">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-brand text-white"><Star8 className="h-5 w-5" /></span>
            {name}
          </p>
          {loc(site?.footer_about, lang) ? <p className="max-w-xs leading-6">{loc(site?.footer_about, lang)}</p> : <p>{loc(site?.city, lang) || t("city")}</p>}
          {socials.length ? (
            <p className="flex flex-wrap gap-2 pt-1">
              {socials.map(([k, v]) => (
                <a key={k} href={v} target="_blank" rel="noreferrer"
                  className="rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white ring-1 ring-white/10 transition hover:bg-brand">{SOCIAL_LABELS[k] ?? k}</a>
              ))}
            </p>
          ) : null}
        </div>
        {col(t("forBuyers"), [page("how-to-order", t("howToOrder")), page("delivery", t("deliveryAndPay")), page("returns", t("returns")), page("about", t("aboutUs")), [t("trackTitle"), "/track"]])}
        <div>
          <h4 className={h4}>{t("contacts")}</h4>
          <ul className="space-y-2.5 text-[15px]">
            {site?.phone ? <li><a href={`tel:${site.phone.replace(/[^\d+]/g, "")}`} className="font-display text-lg font-semibold text-white">{site.phone}</a></li> : null}
            {site?.email ? <li><a href={`mailto:${site.email}`} className={link}>{site.email}</a></li> : null}
            {loc(site?.address, lang) ? <li>{loc(site?.address, lang)}</li> : null}
            {loc(site?.working_hours, lang) ? <li>{loc(site?.working_hours, lang)}</li> : null}
          </ul>
        </div>
        <div>
          <h4 className={h4}>{t("payMethods")}</h4>
          <p className="flex flex-wrap gap-2">
            {pays.map((x) => <span key={x} className="rounded-xl bg-white/10 px-3 py-1.5 text-sm font-medium text-white/90 ring-1 ring-white/10">{x}</span>)}
          </p>
        </div>
      </div>
      <div className="relative mx-auto flex max-w-7xl flex-wrap gap-x-5 gap-y-1 border-t border-white/10 px-5 py-5 text-[13px]">
        <span>© 2026 {name}</span>
        <span className="text-white/35">Demo versiya</span>
        <span className="ml-auto flex gap-4">
          <Link href="/kuryer" className={link}>Kuryer</Link>
          <Link href="/xodim" className={link}>Xodimlar</Link>
          <a href="/admin/" className={link}>Admin</a>
          <a href="/api/docs/" className={link}>API</a>
        </span>
      </div>
    </footer>
  );
}
