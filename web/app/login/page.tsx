"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { useApp } from "@/components/providers";
import { Button } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

function LoginInner() {
  const { t, loginDone } = useApp();
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";
  const [phone, setPhone] = useState("+998 ");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [demoCode, setDemoCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const requestCode = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ debug_code?: string }>("/auth/otp/request", { method: "POST", body: { phone }, auth: false });
      setDemoCode(r.debug_code ?? "");
      setStep("code");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ access: string; refresh: string }>("/auth/otp/verify", { method: "POST", body: { phone, code }, auth: false });
      await loginDone(r.access, r.refresh);
      router.push(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : t("wrongCode"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm rounded-3xl bg-white p-8 shadow-sm">
      <h1 className="mb-6 text-2xl font-bold">{t("login")}</h1>
      {step === "phone" ? (
        <form onSubmit={(e) => { e.preventDefault(); requestCode(); }} className="space-y-4">
          <label className="block">{t("phone")}
            <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoFocus className="mt-1 w-full text-lg" />
          </label>
          <Button type="submit" disabled={busy} className="w-full">{t("getCode")}</Button>
        </form>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); verify(); }} className="space-y-4">
          {demoCode ? (
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
              {t("demoCode")}: <b className="text-lg tracking-widest">{demoCode}</b>
            </p>
          ) : null}
          <label className="block">{t("code")}
            <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} inputMode="numeric" maxLength={6} autoFocus className="mt-1 w-full text-center text-2xl tracking-[0.5em]" />
          </label>
          <Button type="submit" disabled={busy || code.length < 6} className="w-full">{t("confirm")}</Button>
          <button type="button" onClick={() => setStep("phone")} className="w-full text-sm text-gray-500">{t("back")}</button>
        </form>
      )}
      {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginInner />
    </Suspense>
  );
}
