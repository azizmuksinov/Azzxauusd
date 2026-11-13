"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";

import { useApp } from "./providers";

// Promokod: savatda kiritiladi, brauzerda saqlanadi va rasmiylashtirishda buyurtmaga qo'llanadi.

const KEY = "dokon.promo";
export const savedPromo = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };
export const savePromo = (code: string) => { try { if (code) localStorage.setItem(KEY, code); else localStorage.removeItem(KEY); } catch { /* xotira yopiq */ } };

/** Savatdagi promokod holati: `discount` — tovarlar summasidan chegirma (so'm). Savat o'zgarsa qayta tekshiriladi. */
export function usePromo(subtotal: string | undefined) {
  const { t } = useApp();
  const [code, setCode] = useState("");
  const [discount, setDiscount] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const check = useCallback(async (value: string, silent = false) => {
    const v = value.trim();
    if (!v) return;
    setBusy(true);
    if (!silent) setError("");
    try {
      const r = await api<{ code: string; discount: string }>("/promo/check", { method: "POST", body: { code: v } });
      setCode(r.code);
      setDiscount(Number(r.discount));
      savePromo(r.code);
    } catch (e) {
      setCode("");
      setDiscount(0);
      savePromo("");
      setError(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  }, [t]);
  const clear = useCallback(() => { setCode(""); setDiscount(0); setError(""); savePromo(""); }, []);

  // Saqlangan kod savat summasi o'zgarganda qayta tekshiriladi (chegirma summasi o'zgarishi mumkin).
  useEffect(() => {
    const saved = savedPromo();
    if (saved && subtotal) void check(saved, true);
  }, [subtotal, check]);

  return { code, discount, error, busy, apply: check, clear };
}

export function PromoBox({ promo }: { promo: ReturnType<typeof usePromo> }) {
  const { t, lang } = useApp();
  const [value, setValue] = useState("");
  if (promo.code) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-2xl bg-brand-light px-3.5 py-2.5 text-sm">
        <span className="min-w-0 truncate text-brand">
          <b>{promo.code}</b> · −{formatMoney(promo.discount, lang)}
        </span>
        <button onClick={promo.clear} className="shrink-0 text-xs text-zinc-500 underline hover:text-ink">{t("remove")}</button>
      </div>
    );
  }
  return (
    <form onSubmit={(e) => { e.preventDefault(); void promo.apply(value); }} className="space-y-1.5">
      <div className="flex gap-2">
        <input value={value} onChange={(e) => setValue(e.target.value.toUpperCase())} placeholder={t("promoPlaceholder")} maxLength={32}
          className="h-10 w-full min-w-0 !py-0 uppercase placeholder:normal-case" aria-label={t("promoPlaceholder")} />
        <button disabled={promo.busy || !value.trim()}
          className="h-11 shrink-0 rounded-full bg-surface px-5 text-sm font-semibold text-ink transition hover:bg-zinc-200 disabled:opacity-50">{t("promoApply")}</button>
      </div>
      {promo.error ? <p className="text-xs text-red-600">{promo.error}</p> : null}
    </form>
  );
}
