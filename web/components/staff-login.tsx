"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";

import { IconEye } from "./icons";
import { Star8 } from "./illustrations-star";
import { useApp } from "./providers";
import { Button } from "./ui";

type Demo = { label: string; login: string; password: string };

/** Xodim va kuryer kirishi: administrator bergan login va parol (SMS-kod xodimlar uchun ishlamaydi). */
function Inner({ area }: { area: "xodim" | "kuryer" }) {
  const { loginDone } = useApp();
  const router = useRouter();
  const next = useSearchParams().get("next") || `/${area}`;
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState<Demo[]>([]);

  useEffect(() => {
    api<Demo[]>("/auth/staff/demo", { auth: false }).then(setDemo).catch(() => setDemo([]));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ access: string; refresh: string }>("/auth/staff/login", { method: "POST", body: { login, password }, auth: false });
      await loginDone(r.access, r.refresh);
      router.replace(next.startsWith("/") ? next : `/${area}`);
    } catch (err) {
      const left = err instanceof ApiError ? Number(err.data.attempts_left) : NaN;
      const text = err instanceof ApiError ? err.message : "Xatolik yuz berdi. Qayta urinib ko'ring.";
      setError(left >= 1 && left <= 2 ? `${text} Yana ${left} ta urinish qoldi.` : text);
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md py-6 md:py-12">
      <form onSubmit={submit} className="space-y-4 rounded-[32px] bg-white p-6 shadow-card md:p-8">
        <span className="grid h-14 w-14 place-items-center rounded-2xl bg-brand text-white"><Star8 className="h-7 w-7" /></span>
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">{area === "kuryer" ? "Kuryer ilovasi" : "Xodim paneli"}</h1>
          <p className="mt-1 text-sm text-zinc-500">Administrator bergan login va parol bilan kiring.</p>
        </div>
        <label className="block">Login
          <input value={login} onChange={(e) => setLogin(e.target.value)} autoFocus autoCapitalize="none" autoCorrect="off"
            spellCheck={false} autoComplete="username" className="mt-1 w-full text-lg" />
        </label>
        <label className="block">Parol
          <span className="relative mt-1 block">
            <input value={password} onChange={(e) => setPassword(e.target.value)} type={show ? "text" : "password"}
              autoComplete="current-password" className="w-full pr-12 text-lg" />
            <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Parolni yashirish" : "Parolni ko'rsatish"}
              title={show ? "Parolni yashirish" : "Parolni ko'rsatish"}
              className={`absolute right-2 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-full transition hover:bg-surface ${show ? "text-brand" : "text-zinc-400"}`}>
              <IconEye className="h-5 w-5" />
            </button>
          </span>
        </label>
        {error ? <p className="rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        <Button type="submit" disabled={busy || !login.trim() || !password} className="w-full">{busy ? "Tekshirilmoqda…" : "Kirish"}</Button>
        <p className="text-xs leading-5 text-zinc-500">
          Login yoki parolni unutdingizmi? Uni faqat administrator yangilab bera oladi.
        </p>
        {demo.length ? (
          <div className="rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">
            <p className="font-semibold">Demo: namuna login va parol</p>
            <div className="mt-2 flex flex-col gap-2">
              {demo.map((d) => (
                <button key={d.login} type="button" onClick={() => { setLogin(d.login); setPassword(d.password); setShow(true); }}
                  className="rounded-2xl bg-white px-3 py-2 text-left ring-1 ring-amber-200 transition hover:ring-amber-400">
                  <span className="block text-xs text-amber-800">{d.label}</span>
                  <b>{d.login}</b> / <b>{d.password}</b>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </form>
    </div>
  );
}

export function StaffLogin({ area }: { area: "xodim" | "kuryer" }) {
  return <Suspense><Inner area={area} /></Suspense>;
}
