"use client";

import { useCallback, useEffect, useState } from "react";

import { useApp } from "@/components/providers";
import { Empty, ResultBadge, RoleGate, StatusBadge, errorText, sum } from "@/components/staff";
import { Button, Loading } from "@/components/ui";
import { ApiError, api } from "@/lib/api";

type Item = { id: number; sku: string; name: string; variant_name: string; qty: number; line_total: string };
type StopOrder = {
  number: string; status: string; payment_method: string; total: string; paid_amount: string; amount_due: string;
  recipient_name: string; recipient_phone: string; address: string; customer_comment: string;
  delivery_vehicle: string; failed_attempts: number; items: Item[];
  address_snapshot: { landmark?: string; intercom?: string; elevator?: string };
};
type Stop = { id: number; sequence: number; result: string; started_at: string | null; order: StopOrder };
type Route = { id: number; number: string; date: string; status: string; warehouse_name: string; stops_total: number; stops_done: number; stops?: Stop[] };
type CourierMe = { name: string; phone: string; vehicle: string; outstanding_cash: string };
type Cash = { outstanding: string; collections: { id: number; order: string; amount: string; created_at: string }[]; handovers: { number: string; amount: string; account: string; created_at: string }[] };

const FAIL_REASONS: [string, string][] = [
  ["not_home", "Mijoz uyda yo'q"],
  ["no_answer", "Telefonni ko'tarmadi"],
  ["wrong_address", "Manzil noto'g'ri"],
  ["rescheduled", "Boshqa vaqtni so'radi"],
];

const CHECKS: [string, string][] = [
  ["packaging_intact", "Qadoq butun"],
  ["appearance_ok", "Tashqi ko'rinishda nuqson yo'q"],
  ["complete_set", "Komplekt to'liq"],
  ["powered_on", "Yoqib ko'rildi"],
];

export default function CourierPage() {
  return (
    <RoleGate roles={["courier"]} next="/kuryer">
      <CourierApp />
    </RoleGate>
  );
}

function CourierApp() {
  const { toast } = useApp();
  const [me, setMe] = useState<CourierMe | null>(null);
  const [routes, setRoutes] = useState<Route[] | null>(null);
  const [route, setRoute] = useState<Route | null>(null);
  const [cash, setCash] = useState<Cash | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, rs, c] = await Promise.all([
        api<CourierMe>("/courier/me"), api<Route[]>("/courier/routes"), api<Cash>("/courier/cash"),
      ]);
      setMe(m);
      setRoutes(rs);
      setCash(c);
      const current = rs[0];
      setRoute(current ? await api<Route>(`/courier/routes/${current.id}`) : null);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError && e.status === 403 ? "Kuryer profili topilmadi — logist sizni kuryer sifatida qo'shishi kerak." : errorText(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      await load();
      return true;
    } catch (e) {
      toast(errorText(e), "error");
      return false;
    }
  };

  if (error) return <Empty text={error} />;
  if (!me || !routes) return <Loading />;

  const stops = route?.stops ?? [];
  const pending = stops.filter((s) => s.result === "pending");
  const done = stops.filter((s) => s.result !== "pending");

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-3xl bg-gradient-to-br from-brand to-fuchsia-500 p-4 text-white">
          <p className="text-xs text-white/80">Mendagi naqd pul</p>
          <p className="mt-1 text-xl font-black">{sum(cash?.outstanding ?? "0")}</p>
          <p className="mt-1 text-xs text-white/80">Kun oxirida kassirga topshiriladi</p>
        </div>
        <div className="rounded-3xl bg-white p-4 ring-1 ring-gray-100">
          <p className="text-xs text-gray-500">Bugungi marshrut</p>
          <p className="mt-1 text-xl font-black">{route ? `${route.stops_done} / ${route.stops_total}` : "—"}</p>
          <p className="mt-1 text-xs text-gray-500">{route ? `${route.number} · ${route.warehouse_name}` : "Marshrut berilmagan"}</p>
        </div>
      </div>

      {routes.length > 1 ? (
        <div className="flex gap-2">
          {routes.map((r) => (
            <button key={r.id} onClick={async () => setRoute(await api<Route>(`/courier/routes/${r.id}`))}
              className={`rounded-xl px-3 py-1.5 text-sm font-semibold ${route?.id === r.id ? "bg-gray-900 text-white" : "bg-white ring-1 ring-gray-200"}`}>
              {r.number}
            </button>
          ))}
        </div>
      ) : null}

      {!route ? <Empty text="Sizga hozircha marshrut berilmagan. Logist marshrut varag'ini berganda shu yerda chiqadi." /> : null}

      {pending.map((s) => <StopCard key={s.id} stop={s} act={act} reload={load} />)}

      {done.length ? <h2 className="pt-2 text-sm font-bold uppercase tracking-wide text-gray-500">Yakunlangan</h2> : null}
      {done.map((s) => (
        <div key={s.id} className="flex items-center justify-between rounded-2xl bg-white p-3 text-sm ring-1 ring-gray-100">
          <span><b>#{s.sequence}</b> {s.order.number} · {s.order.recipient_name}</span>
          <ResultBadge result={s.result} />
        </div>
      ))}

      {cash && cash.collections.length ? (
        <details className="rounded-3xl bg-white p-4 ring-1 ring-gray-100">
          <summary className="cursor-pointer font-semibold">Olingan naqd pullar ({cash.collections.length})</summary>
          <ul className="mt-3 space-y-1 text-sm">
            {cash.collections.map((c) => (
              <li key={c.id} className="flex justify-between"><span>{c.order}</span><b>{sum(c.amount)}</b></li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

type Act = (fn: () => Promise<unknown>, ok: string) => Promise<boolean>;

function StopCard({ stop, act, reload }: { stop: Stop; act: Act; reload: () => Promise<void> }) {
  const o = stop.order;
  const [mode, setMode] = useState<"" | "deliver" | "refuse" | "fail">("");
  const started = o.status === "out_for_delivery";
  const due = Number(o.amount_due);
  const a = o.address_snapshot || {};

  return (
    <article className="overflow-hidden rounded-3xl bg-white ring-1 ring-gray-100">
      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-gray-500">#{stop.sequence} · {o.number}{o.delivery_vehicle === "truck" ? " · yirik tovar" : ""}</p>
            <p className="text-lg font-bold">{o.recipient_name}</p>
          </div>
          <StatusBadge status={o.status} />
        </div>
        <p className="text-sm leading-6">{o.address}</p>
        {a.landmark || a.intercom ? <p className="text-xs text-gray-500">{[a.landmark && `Mo'ljal: ${a.landmark}`, a.intercom && `Domofon: ${a.intercom}`].filter(Boolean).join(" · ")}</p> : null}
        {o.customer_comment ? <p className="rounded-xl bg-gray-50 p-2 text-sm">💬 {o.customer_comment}</p> : null}
        <ul className="text-sm text-gray-700">
          {o.items.map((i) => <li key={i.id}>• {i.name}{i.variant_name ? ` (${i.variant_name})` : ""} × {i.qty}</li>)}
        </ul>
        <div className="flex items-center justify-between rounded-2xl bg-gray-50 p-3">
          <span className="text-sm text-gray-600">{due > 0 ? "Mijozdan olinadi" : "To'langan"}</span>
          <b className={due > 0 ? "text-lg text-gray-900" : "text-green-700"}>{due > 0 ? sum(o.amount_due) : "✓"}</b>
        </div>
        {o.failed_attempts ? <p className="text-xs font-semibold text-amber-700">Oldingi urinishlar: {o.failed_attempts}</p> : null}
        <div className="grid grid-cols-2 gap-2">
          <a href={`tel:${o.recipient_phone}`} className="rounded-2xl bg-gray-100 py-3 text-center font-semibold">📞 Qo&apos;ng&apos;iroq</a>
          {!started ? (
            <Button onClick={() => act(() => api(`/courier/stops/${stop.id}/start`, { method: "POST" }), "Mijozga SMS yuborildi")}>Yo&apos;lga chiqdim</Button>
          ) : (
            <Button onClick={() => setMode(mode === "deliver" ? "" : "deliver")}>Topshirish</Button>
          )}
          {started ? <Button variant="danger" onClick={() => setMode(mode === "refuse" ? "" : "refuse")}>Rad etdi</Button> : null}
          <Button variant="ghost" onClick={() => setMode(mode === "fail" ? "" : "fail")} className={started ? "" : "col-span-2"}>Yetkazib bo&apos;lmadi</Button>
        </div>
      </div>
      {mode === "deliver" ? <DeliverForm stop={stop} act={act} reload={reload} /> : null}
      {mode === "refuse" ? <RefuseForm stop={stop} act={act} /> : null}
      {mode === "fail" ? <FailForm stop={stop} act={act} /> : null}
    </article>
  );
}

function DeliverForm({ stop, act, reload }: { stop: Stop; act: Act; reload: () => Promise<void> }) {
  const o = stop.order;
  const due = Number(o.amount_due);
  const { toast } = useApp();
  const [checks, setChecks] = useState<Record<string, boolean>>({ packaging_intact: false, appearance_ok: false, complete_set: false, powered_on: false });
  const [receivedBy, setReceivedBy] = useState(o.recipient_name);
  const [qr, setQr] = useState<{ provider: string; amount: string; payment_url: string; qr_svg: string } | null>(null);
  const required = ["packaging_intact", "appearance_ok", "complete_set"].every((k) => checks[k]);

  const submit = (door_payment: string) =>
    act(
      () => api(`/courier/stops/${stop.id}/deliver`, { method: "POST", body: { door_payment, inspection: checks, received_by: receivedBy } }),
      "Topshirildi — akt yaratildi",
    );

  const showQr = async (provider: string) => {
    try {
      setQr(await api(`/courier/stops/${stop.id}/qr`, { method: "POST", body: { provider } }));
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <div className="space-y-3 border-t border-gray-100 bg-gray-50/60 p-4">
      <p className="text-sm font-semibold">Mijoz bilan birga tekshiring:</p>
      {CHECKS.map(([k, label]) => (
        <label key={k} className="flex items-center gap-3 rounded-xl bg-white p-3 ring-1 ring-gray-100">
          <input type="checkbox" checked={checks[k]} onChange={(e) => setChecks({ ...checks, [k]: e.target.checked })} className="h-5 w-5 accent-violet-700" />
          <span className="text-sm">{label}{k === "powered_on" ? " (iloji bo'lsa)" : ""}</span>
        </label>
      ))}
      <label className="block text-sm">Qabul qilgan shaxs
        <input value={receivedBy} onChange={(e) => setReceivedBy(e.target.value)} className="mt-1 w-full" />
      </label>
      {!required ? <p className="text-xs text-amber-700">Qadoq, tashqi ko&apos;rinish va komplektni belgilang. Nuqson bo&apos;lsa — &quot;Rad etdi&quot;.</p> : null}

      {due > 0 ? (
        <>
          <p className="text-sm">Mijozdan olinadi: <b>{sum(o.amount_due)}</b></p>
          <div className="grid grid-cols-2 gap-2">
            <Button disabled={!required || !receivedBy} onClick={() => submit("cash")}>💵 Naqd oldim</Button>
            <Button variant="dark" disabled={!required} onClick={() => showQr("payme")}>QR: Payme</Button>
            <Button variant="dark" disabled={!required} onClick={() => showQr("click")} className="col-span-2">QR: Click</Button>
          </div>
          {qr ? (
            <div className="space-y-2 rounded-2xl bg-white p-4 text-center ring-1 ring-gray-100">
              <p className="text-sm">Mijoz {qr.provider === "payme" ? "Payme" : "Click"} ilovasida skanerlaydi: <b>{sum(qr.amount)}</b></p>
              <div className="mx-auto w-56 [&_svg]:h-auto [&_svg]:w-full" dangerouslySetInnerHTML={{ __html: qr.qr_svg }} />
              <div className="grid grid-cols-2 gap-2">
                <Button variant="ghost" onClick={reload}>To&apos;lovni tekshirish</Button>
                {process.env.NEXT_PUBLIC_DEMO === "1" ? (
                  <Button variant="ghost" onClick={() => act(() => api(`/courier/stops/${stop.id}/demo-qr-pay`, { method: "POST" }), "Demo: mijoz QR orqali to'ladi")}>
                    Demo: mijoz to&apos;ladi
                  </Button>
                ) : null}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <Button disabled={!required || !receivedBy} onClick={() => submit("prepaid")} className="w-full">✓ Topshirdim</Button>
      )}
    </div>
  );
}

function RefuseForm({ stop, act }: { stop: Stop; act: Act }) {
  const [reason, setReason] = useState("");
  return (
    <div className="space-y-3 border-t border-gray-100 bg-red-50/40 p-4">
      <label className="block text-sm">Rad etish sababi
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Masalan: korpusda chiziq bor" className="mt-1 w-full" />
      </label>
      <Button variant="danger" disabled={!reason.trim()} className="w-full"
        onClick={() => act(() => api(`/courier/stops/${stop.id}/refuse`, { method: "POST", body: { reason } }), "Rad etildi — tovarni omborga qaytaring")}>
        Tasdiqlash
      </Button>
    </div>
  );
}

function FailForm({ stop, act }: { stop: Stop; act: Act }) {
  const [outcome, setOutcome] = useState("not_home");
  const [comment, setComment] = useState("");
  return (
    <div className="space-y-3 border-t border-gray-100 bg-amber-50/40 p-4">
      <div className="grid grid-cols-2 gap-2">
        {FAIL_REASONS.map(([k, label]) => (
          <button key={k} onClick={() => setOutcome(k)}
            className={`rounded-xl px-3 py-2 text-sm ${outcome === k ? "bg-gray-900 text-white" : "bg-white ring-1 ring-gray-200"}`}>{label}</button>
        ))}
      </div>
      <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Izoh (ixtiyoriy)" className="w-full" />
      <p className="text-xs text-gray-600">3 ta muvaffaqiyatsiz urinishdan keyin tovar omborga qaytariladi.</p>
      <Button variant="dark" className="w-full"
        onClick={() => act(() => api(`/courier/stops/${stop.id}/fail`, { method: "POST", body: { outcome, comment } }), "Urinish yozildi")}>
        Tasdiqlash
      </Button>
    </div>
  );
}
