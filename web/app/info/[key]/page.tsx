"use client";

import { useParams } from "next/navigation";

import { useApp } from "@/components/providers";
import { Loading, useTitle } from "@/components/ui";
import { loc } from "@/lib/site";

/** Ma'lumot sahifalari (yetkazish, qaytarish, biz haqimizda...) — matni admin paneldagi "Sayt" bo'limidan. */
export default function InfoPage() {
  const { key } = useParams<{ key: string }>();
  const { site, lang } = useApp();
  useTitle(loc(site?.pages[key]?.title, lang) || null);
  if (!site) return <Loading />;
  const page = site.pages[key];
  const body = loc(page?.body, lang);
  return (
    <article className="mx-auto max-w-3xl space-y-4 py-4">
      <h1 className="text-3xl font-bold tracking-tight">{loc(page?.title, lang) || "—"}</h1>
      {body ? <div className="whitespace-pre-line leading-7 text-zinc-700">{body}</div> : <p className="text-zinc-500">Tez orada.</p>}
      {key === "about" || key === "delivery" ? (
        <div className="space-y-1 rounded-xl border border-line p-4 text-sm text-zinc-600">
          {site.phone ? <p>Telefon: <a href={`tel:${site.phone.replace(/[^\d+]/g, "")}`} className="font-medium text-ink">{site.phone}</a></p> : null}
          {loc(site.address, lang) ? <p>Manzil: {loc(site.address, lang)}</p> : null}
          {loc(site.working_hours, lang) ? <p>Ish vaqti: {loc(site.working_hours, lang)}</p> : null}
        </div>
      ) : null}
    </article>
  );
}
