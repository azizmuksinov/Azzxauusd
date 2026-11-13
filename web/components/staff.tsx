"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ApiError } from "@/lib/api";
import { formatMoney, statusLabel } from "@/lib/i18n";

import { useApp } from "./providers";
import { Loading } from "./ui";

// Xodimlar va kuryer sahifalari uchun umumiy elementlar (interfeys hozircha o'zbek tilida).

export const sum = (v: string | number | null | undefined) => formatMoney(v, "uz");

const STATUS_COLORS: Record<string, string> = {
  paid: "bg-emerald-50 text-emerald-700",
  cod_confirmed: "bg-emerald-50 text-emerald-700",
  picking: "bg-amber-50 text-amber-700",
  packed: "bg-sky-50 text-sky-700",
  handed_to_courier: "bg-indigo-50 text-indigo-700",
  in_transit: "bg-indigo-50 text-indigo-700",
  out_for_delivery: "bg-teal-50 text-teal-700",
  delivered: "bg-green-100 text-green-800",
  refused_at_door: "bg-red-50 text-red-700",
  returned: "bg-gray-100 text-gray-700",
  cancelled: "bg-gray-100 text-gray-500",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_COLORS[status] ?? "bg-gray-100 text-gray-700"}`}>
      {statusLabel("uz", status)}
    </span>
  );
}

const RESULT: Record<string, [string, string]> = {
  pending: ["Kutilmoqda", "bg-gray-100 text-gray-600"],
  delivered: ["Yetkazildi", "bg-green-100 text-green-800"],
  refused: ["Rad etildi", "bg-red-50 text-red-700"],
  failed: ["Topilmadi", "bg-amber-50 text-amber-700"],
  not_visited: ["Borilmadi", "bg-gray-100 text-gray-500"],
};

export function ResultBadge({ result }: { result: string }) {
  const [label, cls] = RESULT[result] ?? [result, "bg-gray-100"];
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{label}</span>;
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const fields = e.data.fields as Record<string, unknown> | undefined;
    if (fields) return `${e.message} ${JSON.stringify(fields)}`;
    return e.message;
  }
  return "Xatolik yuz berdi";
}

/** Kirmagan bo'lsa — login; kerakli rol bo'lmasa — xabar. */
export function RoleGate({ roles, next, children }: { roles: string[]; next: string; children: React.ReactNode }) {
  const { me, ready } = useApp();
  const router = useRouter();
  useEffect(() => {
    if (!ready || me) return;
    // Xodim/kuryer ilovasi (PWA) doirasidagi kirish sahifasi — ilova ichida ochiladi.
    const base = ["/xodim", "/kuryer"].find((p) => next.startsWith(p));
    router.replace(`${base ? `${base}/kirish` : "/login"}?next=${encodeURIComponent(next)}`);
  }, [ready, me, router, next]);
  if (!ready || !me) return <Loading />;
  const ok = me.roles.includes("admin") || me.roles.some((r) => roles.includes(r));
  if (!ok) {
    return (
      <div className="mx-auto max-w-md rounded-3xl bg-white p-8 text-center ring-1 ring-gray-100">
        <p className="text-lg font-bold">Bu sahifa xodimlar uchun</p>
        <p className="mt-2 text-sm text-gray-500">
          {me.phone} raqamida kerakli rol yo&apos;q ({roles.join(", ")}). Administrator rol berishi kerak.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4">
      {tabs.map(([k, label]) => (
        <button key={k} onClick={() => onChange(k)}
          className={`shrink-0 rounded-2xl px-4 py-2.5 text-sm font-semibold transition ${value === k ? "bg-gray-900 text-white" : "bg-white text-gray-700 ring-1 ring-gray-200 hover:ring-gray-300"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="rounded-3xl bg-white p-8 text-center text-sm text-gray-500 ring-1 ring-gray-100">{text}</p>;
}
