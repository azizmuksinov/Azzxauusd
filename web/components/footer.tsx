"use client";

import { useApp } from "./providers";

export function Footer() {
  const { t } = useApp();
  const col = (title: string, items: [string, string][]) => (
    <div>
      <h4 className="mb-3 text-sm font-bold text-white">{title}</h4>
      <ul className="space-y-2 text-sm">
        {items.map(([label, href]) => (
          <li key={label}>{href ? <a href={href} className="hover:text-white">{label}</a> : <span>{label}</span>}</li>
        ))}
      </ul>
    </div>
  );
  return (
    <footer className="mt-16 bg-gray-900 text-gray-400">
      <div className="mx-auto grid max-w-7xl gap-8 px-4 py-12 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-brand to-fuchsia-500 font-black text-white">T</span>
            <span className="text-lg font-black text-white">Texno<span className="text-violet-400">Do&apos;kon</span></span>
          </div>
          <p className="mt-3 text-sm leading-6">{t("doorDelivery")}. {t("checkAtDoor")}.</p>
        </div>
        {col(t("forBuyers"), [[t("howToOrder"), ""], [t("deliveryAndPay"), ""], [t("returns"), ""]])}
        {col(t("aboutUs"), [[t("contacts"), ""], [t("admin"), "/admin/"], ["API", "/api/docs/"]])}
        <div>
          <h4 className="mb-3 text-sm font-bold text-white">{t("payMethods")}</h4>
          <div className="flex flex-wrap gap-2">
            {["Payme", "Click", "Uzum Bank", "Uzcard", "Humo"].map((x) => (
              <span key={x} className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold text-gray-200">{x}</span>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t border-white/10 py-4 text-center text-xs">© 2026 TexnoDo&apos;kon · {t("allRights")} · {t("demo")}</div>
    </footer>
  );
}
