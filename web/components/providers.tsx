"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, tokens } from "@/lib/api";
import { type Key, type Lang, translate } from "@/lib/i18n";
import type { Site } from "@/lib/site";
import type { Card, Cart } from "@/lib/types";

type Me = { id: number; phone: string; first_name: string; roles: string[] };
type Toast = { id: number; text: string; kind: "ok" | "error" };

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
  addToCart: (variantId: number, qty?: number) => Promise<boolean>;
  favorites: Set<number>;
  toggleFavorite: (productId: number) => Promise<void>;
  toast: (text: string, kind?: Toast["kind"]) => void;
  site: Site | null;
  reloadSite: () => Promise<void>;
};

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("AppProvider yo'q");
  return ctx;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [lang, setLangState] = useState<Lang>("uz");
  const [me, setMe] = useState<Me | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [ready, setReady] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);

  const [site, setSite] = useState<Site | null>(null);
  const reloadSite = useCallback(async () => {
    try {
      setSite(await api<Site>("/site", { auth: false }));
    } catch {
      /* sayt matnlari bo'lmasa — standart matnlar ko'rsatiladi */
    }
  }, []);
  useEffect(() => {
    reloadSite();
  }, [reloadSite]);

  const toast = useCallback((text: string, kind: Toast["kind"] = "ok") => {
    const id = ++seq.current;
    setToasts((l) => [...l, { id, text, kind }]);
    setTimeout(() => setToasts((l) => l.filter((x) => x.id !== id)), 2800);
  }, []);

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
      setFavorites(new Set());
      return;
    }
    try {
      setMe(await api<Me>("/me"));
      const fav = await api<Card[]>("/me/favorites");
      setFavorites(new Set(fav.map((p) => p.id)));
    } catch {
      setMe(null);
    }
  }, []);

  useEffect(() => {
    const saved = tokens.lang() as Lang | null;
    if (saved) setLangState(saved);
    Promise.all([loadMe(), reloadCart()]).finally(() => setReady(true));
  }, [loadMe, reloadCart]);

  useEffect(() => {
    const onExpired = () => {
      setMe(null);
      setFavorites(new Set());
    };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

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
    setFavorites(new Set());
    reloadCart();
  }, [reloadCart]);

  const addToCart = useCallback(
    async (variantId: number, qty = 1) => {
      try {
        await api("/cart/items", { method: "POST", body: { variant_id: variantId, qty } });
        await reloadCart();
        toast(translate(lang, "added"));
        return true;
      } catch (e) {
        toast(e instanceof ApiError ? e.message : translate(lang, "error"), "error");
        return false;
      }
    },
    [reloadCart, toast, lang],
  );

  const toggleFavorite = useCallback(
    async (productId: number) => {
      if (!me) {
        toast(translate(lang, "loginToFav"));
        router.push(`/login?next=${encodeURIComponent(window.location.pathname)}`);
        return;
      }
      const has = favorites.has(productId);
      setFavorites((s) => {
        const n = new Set(s);
        if (has) n.delete(productId);
        else n.add(productId);
        return n;
      });
      try {
        if (has) await api(`/me/favorites/${productId}`, { method: "DELETE" });
        else await api("/me/favorites", { method: "POST", body: { product_id: productId } });
        toast(translate(lang, has ? "removedFav" : "addedFav"));
      } catch {
        toast(translate(lang, "error"), "error");
      }
    },
    [me, favorites, toast, lang, router],
  );

  const value = useMemo<Ctx>(
    () => ({
      lang, setLang, t: (k) => translate(lang, k), me, ready, loginDone, logout, cart, reloadCart,
      addToCart, favorites, toggleFavorite, toast, site, reloadSite,
    }),
    [lang, setLang, me, ready, loginDone, logout, cart, reloadCart, addToCart, favorites, toggleFavorite, toast, site, reloadSite],
  );
  return (
    <AppContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex flex-col items-center gap-2 px-4">
        {toasts.map((x) => (
          <div key={x.id}
            className={`animate-[fadeUp_.25s_ease-out] rounded-2xl px-5 py-3 text-sm font-medium text-white shadow-lg ${x.kind === "ok" ? "bg-gray-900" : "bg-red-600"}`}>
            {x.text}
          </div>
        ))}
      </div>
    </AppContext.Provider>
  );
}
