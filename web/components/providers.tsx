"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, tokens } from "@/lib/api";
import { type Key, type Lang, translate } from "@/lib/i18n";
import type { Cart } from "@/lib/types";

type Me = { id: number; phone: string; first_name: string; roles: string[] };

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: Key) => string;
  me: Me | null;
  ready: boolean;
  loginDone: (access: string, refresh: string) => Promise<void>;
  logout: () => void;
  cart: Cart | null;
  reloadCart: () => Promise<void>;
};

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("AppProvider yo'q");
  return ctx;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("uz");
  const [me, setMe] = useState<Me | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [ready, setReady] = useState(false);

  const reloadCart = useCallback(async () => {
    try {
      setCart(await api<Cart>("/cart"));
    } catch {
      setCart(null);
    }
  }, []);

  const loadMe = useCallback(async () => {
    if (!tokens.access()) {
      setMe(null);
      return;
    }
    try {
      setMe(await api<Me>("/me"));
    } catch {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    const saved = tokens.lang() as Lang | null;
    if (saved) setLangState(saved);
    Promise.all([loadMe(), reloadCart()]).finally(() => setReady(true));
  }, [loadMe, reloadCart]);

  const setLang = useCallback(
    (l: Lang) => {
      tokens.setLang(l);
      setLangState(l);
      document.documentElement.lang = l === "ru" ? "ru" : "uz";
      reloadCart();
    },
    [reloadCart],
  );

  const loginDone = useCallback(
    async (access: string, refresh: string) => {
      const guest = tokens.cart();
      tokens.save(access, refresh);
      if (guest) {
        try {
          await api("/cart/merge", { method: "POST", body: { guest_token: guest } });
        } catch {
          /* mehmon savati topilmasa — muammo emas */
        }
        tokens.setCart(null);
      }
      await Promise.all([loadMe(), reloadCart()]);
    },
    [loadMe, reloadCart],
  );

  const logout = useCallback(() => {
    const refresh = tokens.refresh();
    if (refresh) api("/auth/logout", { method: "POST", body: { refresh } }).catch(() => undefined);
    tokens.clear();
    setMe(null);
    reloadCart();
  }, [reloadCart]);

  const value = useMemo<Ctx>(
    () => ({ lang, setLang, t: (k) => translate(lang, k), me, ready, loginDone, logout, cart, reloadCart }),
    [lang, setLang, me, ready, loginDone, logout, cart, reloadCart],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
