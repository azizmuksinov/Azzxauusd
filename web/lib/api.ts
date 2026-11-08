"use client";

// API kliyenti: JWT (access/refresh), mehmon savati tokeni, til sarlavhasi, xato formati.
export class ApiError extends Error {
  code: string;
  status: number;
  data: Record<string, unknown>;
  constructor(status: number, data: Record<string, unknown>) {
    const err = (data?.error ?? {}) as Record<string, unknown>;
    super(String(err.message ?? "Xatolik"));
    this.status = status;
    this.code = String(err.code ?? "error");
    this.data = err;
  }
}

const ACCESS = "dokon.access";
const REFRESH = "dokon.refresh";
const CART = "dokon.cart";
const LANG = "dokon.lang";

const store = {
  get: (k: string) => (typeof window === "undefined" ? null : window.localStorage.getItem(k)),
  set: (k: string, v: string | null) => {
    if (typeof window === "undefined") return;
    if (v === null) window.localStorage.removeItem(k);
    else window.localStorage.setItem(k, v);
  },
};

export const tokens = {
  access: () => store.get(ACCESS),
  refresh: () => store.get(REFRESH),
  save: (access: string, refresh: string) => {
    store.set(ACCESS, access);
    store.set(REFRESH, refresh);
  },
  clear: () => {
    const had = store.get(ACCESS) !== null;
    store.set(ACCESS, null);
    store.set(REFRESH, null);
    // Seans bekor bo'ldi (masalan, server qayta ishga tushdi) — ilova foydalanuvchini chiqarib yuboradi.
    if (had && typeof window !== "undefined") window.dispatchEvent(new Event("auth:expired"));
  },
  cart: () => store.get(CART),
  setCart: (v: string | null) => store.set(CART, v),
  lang: () => store.get(LANG),
  setLang: (v: string) => store.set(LANG, v),
};

let refreshing: Promise<boolean> | null = null;

async function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh();
  if (!refresh) return false;
  refreshing ??= fetch("/api/v1/auth/token/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  })
    .then(async (r) => {
      if (!r.ok) {
        tokens.clear();
        return false;
      }
      const d = await r.json();
      tokens.save(d.access, d.refresh);
      return true;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

type Opts = { method?: string; body?: unknown; headers?: Record<string, string>; auth?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(opts.headers ?? {}) };
  const lang = tokens.lang();
  if (lang) headers["Accept-Language"] = lang === "uz_cyrl" ? "uz-cyrl" : lang;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  const access = tokens.access();
  if (access && opts.auth !== false) headers.Authorization = `Bearer ${access}`;
  const cart = tokens.cart();
  if (cart && !access) headers["X-Cart-Token"] = cart;

  const res = await fetch(`/api/v1${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    cache: "no-store",
  });
  if (res.status === 401 && access && retry && (await refreshAccess())) {
    return api<T>(path, opts, false);
  }
  if (res.status === 401 && access) tokens.clear();
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new ApiError(res.status, data);
  const cartToken = res.headers.get("X-Cart-Token");
  if (cartToken && !tokens.access()) tokens.setCart(cartToken);
  return data as T;
}

/** Fayl yuklash (multipart). */
export async function apiUpload<T = any>(path: string, form: FormData): Promise<T> {
  const send = () =>
    fetch(`/api/v1${path}`, {
      method: "POST",
      headers: { Accept: "application/json", ...(tokens.access() ? { Authorization: `Bearer ${tokens.access()}` } : {}) },
      body: form,
    });
  let res = await send();
  if (res.status === 401 && (await refreshAccess())) res = await send();
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
