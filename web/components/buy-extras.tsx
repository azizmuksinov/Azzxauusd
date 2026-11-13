"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";
import { loc } from "@/lib/site";

import { IconCheck, IconClose } from "./icons";
import { useApp } from "./providers";
import { Button } from "./ui";

// Tovar sahifasi qo'shimchalari: muddatli to'lov kalkulyatori, 1 bosishda xarid, "kelganda xabar bering".

/** Muddatli to'lov: rejalar sayt sozlamalaridan (oy va ustama foizi). Faqat hisob-kitob — shartnoma emas. */
export function Installments({ price }: { price: string | number }) {
  const { site, t, lang } = useApp();
  const cfg = site?.installments;
  const [months, setMonths] = useState<number | null>(null);
  if (!cfg?.enabled || !cfg.plans.length) return null;
  const plan = cfg.plans.find((p) => p.months === months) ?? cfg.plans[cfg.plans.length - 1];
  const total = Number(price) * (1 + plan.percent / 100);
  const monthly = Math.ceil(total / plan.months / 1000) * 1000;
  return (
    <div className="rounded-2xl bg-brand-light p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-sm font-semibold text-brand">{t("installment")}</span>
        {cfg.plans.map((p) => (
          <button key={p.months} onClick={() => setMonths(p.months)}
            className={`rounded-full px-2.5 py-1 text-xs font-medium transition ${p.months === plan.months ? "bg-brand text-white" : "bg-white text-ink hover:text-brand"}`}>
            {p.months} {t("monthsShort")}
          </button>
        ))}
      </div>
      <p className="mt-2 text-[15px] text-ink">
        <b className="text-lg">{formatMoney(monthly, lang)}</b> × {plan.months} {t("monthsShort")}
      </p>
      <p className="text-xs text-zinc-500">
        {t("installmentTotal")}: {formatMoney(monthly * plan.months, lang)}
        {plan.percent === 0 ? ` · ${t("installmentNoMarkup")}` : ""}
        {loc(cfg.note, lang) ? ` · ${loc(cfg.note, lang)}` : ""}
      </p>
    </div>
  );
}

/** Telefon qoldirish oynasi: tez buyurtma ("quick") yoki tovar kelganda xabar ("stock"). */
export function LeadButton({ kind, variantId, qty = 1, className = "" }: {
  kind: "quick" | "stock"; variantId: number; qty?: number; className?: string;
}) {
  const { t, me } = useApp();
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  useEffect(() => { if (open && me) { setPhone((v) => v || me.phone || ""); setName((v) => v || me.first_name || ""); } }, [open, me]);
  useEffect(() => { setDone(false); }, [variantId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(kind === "quick" ? "/quick-orders" : "/stock-requests", { method: "POST", body: { variant_id: variantId, phone, name, ...(kind === "quick" ? { qty } : {}) } });
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button onClick={() => setOpen(true)}
        className={`inline-flex h-11 w-full items-center justify-center rounded-xl border border-brand/50 px-4 text-[15px] font-semibold text-brand transition hover:bg-brand-light ${className}`}>
        {kind === "quick" ? t("quickBuy") : t("notifyMe")}
      </button>
      {open ? (
        <div className="fixed inset-0 z-[60] grid animate-[fadeIn_.15s_ease-out] place-items-end bg-black/50 sm:place-items-center sm:p-4" onClick={() => setOpen(false)}>
          <div className="w-full rounded-t-3xl border border-line bg-white p-5 pb-[calc(20px+env(safe-area-inset-bottom))] sm:max-w-sm sm:rounded-3xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold">{kind === "quick" ? t("quickBuy") : t("notifyMe")}</h3>
                <p className="mt-0.5 text-sm text-zinc-500">{kind === "quick" ? t("quickBuyText") : t("notifyMeText")}</p>
              </div>
              <button onClick={() => setOpen(false)} aria-label={t("back")} className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface"><IconClose className="h-5 w-5" /></button>
            </div>
            {done ? (
              <div className="py-4 text-center">
                <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-700"><IconCheck className="h-6 w-6" /></span>
                <p className="mt-3 font-semibold">{kind === "quick" ? t("quickBuyDone") : t("notifyMeDone")}</p>
                <Button className="mt-4 w-full" onClick={() => setOpen(false)}>OK</Button>
              </div>
            ) : (
              <form onSubmit={submit} className="space-y-3">
                <label className="block">{t("phone")}
                  <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" required placeholder="+998 90 123 45 67" className="mt-1 w-full" />
                </label>
                <label className="block">{t("yourName")}
                  <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} className="mt-1 w-full" />
                </label>
                {error ? <p className="text-sm text-red-600">{error}</p> : null}
                <Button type="submit" className="w-full" disabled={busy || !phone.trim()}>{kind === "quick" ? t("quickBuySend") : t("notifyMeSend")}</Button>
              </form>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
