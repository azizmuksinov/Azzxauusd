"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isStaffPath } from "./header";
import { useApp } from "./providers";

export function Footer() {
  const { t } = useApp();
  const pathname = usePathname();
  if (isStaffPath(pathname)) return null;
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
  return (
    <footer className="mt-20 border-t border-line bg-surface text-zinc-500">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <p className="text-lg font-extrabold tracking-tight text-brand">TexnoDo&apos;kon</p>
          <p className="mt-2 text-sm">{t("city")}</p>
        </div>
        {col(t("forBuyers"), [[t("howToOrder"), ""], [t("deliveryAndPay"), ""], [t("returns"), ""]])}
        {col(t("aboutUs"), [[t("contacts"), ""]])}
        <div>
          <h4 className="mb-3 text-sm font-semibold text-ink">{t("payMethods")}</h4>
          <p className="text-sm">Payme · Click · Uzum Bank · Uzcard · Humo</p>
        </div>
      </div>
      <div className="mx-auto flex max-w-7xl flex-wrap gap-x-5 gap-y-1 border-t border-line px-4 py-4 text-xs">
        <span>© 2026 TexnoDo&apos;kon</span>
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
