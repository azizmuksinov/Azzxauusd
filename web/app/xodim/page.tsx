"use client";

import { useCallback, useEffect, useState } from "react";

import { AiCardsTab } from "@/components/ai-cards";
import { MarketingTab } from "@/components/marketing-admin";
import { ProductsTab } from "@/components/products-admin";
import { useApp } from "@/components/providers";
import { Empty, ResultBadge, RoleGate, StatusBadge, Tabs, errorText, sum } from "@/components/staff";
import { Button, Loading, Panel } from "@/components/ui";
import { api } from "@/lib/api";

type OrderRow = {
  number: string; status: string; payment_method: string; total: string; paid_amount: string; items_count: number;
  recipient_name: string; recipient_phone: string; district: Record<string, string> | string | null;
  delivery_vehicle: string; failed_attempts: number; in_route: string | null; created_at: string;
};
type OrderItem = { id: number; sku: string; name: string; qty: number; variant_id: number; serial_tracking: string; serials: { id: number }[] };
type OrderDetail = OrderRow & { items: OrderItem[]; address: string };
type Courier = { id: number; name: string; phone: string; vehicle: string; warehouse: number | null; is_active: boolean; outstanding_cash: string };
type Stop = { id: number; sequence: number; result: string; order: { number: string; status: string; recipient_name: string; address: string; amount_due: string } };
type Route = {
  id: number; number: string; date: string; status: string; status_label: string; courier: Courier;
  warehouse_name: string; stops_total: number; stops_done: number; stops?: Stop[];
};
type Warehouse = { id: number; name: string; code: string };
type CashRow = { courier: Courier; amount: string; orders: number; collections: { id: number; order: string; amount: string }[] };
type Account = { id: number; name: string; kind: string; is_active: boolean };
type Handover = { id: number; number: string; courier: string; account: string; amount: string; orders_count: number; created_at: string };
type Page<T> = { results: T[] } | T[];

const list = <T,>(p: Page<T>): T[] => (Array.isArray(p) ? p : p.results);
const districtName = (d: OrderRow["district"]) => (typeof d === "string" ? d : d?.uz ?? "");

type Tab = "products" | "marketing" | "picking" | "routes" | "cash" | "refunds" | "couriers" | "ai";

export default function StaffPage() {
  return (
    <RoleGate roles={["warehouse", "logistics_manager", "finance", "support", "content_manager"]} next="/xodim">
      <StaffApp />
    </RoleGate>
  );
}

function StaffApp() {
  const { me } = useApp();
  const has = (...r: string[]) => !!me && (me.roles.includes("admin") || r.some((x) => me.roles.includes(x)));
  const tabs: [Tab, string][] = [];
  if (has("warehouse", "logistics_manager", "support")) tabs.push(["picking", "Yig'ish"], ["routes", "Marshrutlar"]);
  if (has("finance")) tabs.push(["cash", "Kuryer kassasi"], ["refunds", "Qaytarishlar"]);
  if (has("logistics_manager", "support")) tabs.push(["couriers", "Kuryerlar"]);
  if (has("content_manager")) tabs.unshift(["products", "Tovarlar"]);
  if (has("content_manager")) tabs.push(["ai", "AI kartochkalar"], ["marketing", "Marketing"]);
  const [tab, setTab] = useState<Tab>(tabs[0]?.[0] ?? "picking");

  return (
    <div className="space-y-5">
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "picking" ? <PickingTab /> : null}
      {tab === "routes" ? <RoutesTab /> : null}
      {tab === "cash" ? <CashTab /> : null}
      {tab === "refunds" ? <RefundsTab /> : null}
      {tab === "couriers" ? <CouriersTab /> : null}
      {tab === "ai" ? <AiCardsTab /> : null}
      {tab === "products" ? <ProductsTab /> : null}
      {tab === "marketing" ? <MarketingTab /> : null}
    </div>
  );
}

function useRun() {
  const { toast } = useApp();
  return async (fn: () => Promise<unknown>, ok: string, after?: () => unknown) => {
    try {
      await fn();
      toast(ok);
      await after?.();
      return true;
    } catch (e) {
      toast(errorText(e), "error");
      return false;
    }
  };
}

// --- Yig'ish ---
function PickingTab() {
  const run = useRun();
  const [rows, setRows] = useState<OrderRow[] | null>(null);
  const [open, setOpen] = useState<OrderDetail | null>(null);

  const load = useCallback(async () => {
    setRows(list(await api<Page<OrderRow>>("/admin/orders?status=paid,cod_confirmed,picking&page_size=100")));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  if (!rows) return <Loading />;
  const groups: [string, string][] = [["paid,cod_confirmed", "Yig'ish kutilmoqda"], ["picking", "Yig'ilmoqda"]];
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {groups.map(([statuses, title]) => {
        const items = rows.filter((r) => statuses.split(",").includes(r.status));
        return (
          <Panel key={title}>
            <h2 className="mb-3 font-bold">{title} <span className="text-gray-400">({items.length})</span></h2>
            {!items.length ? <p className="text-sm text-gray-500">Bo&apos;sh</p> : null}
            <div className="space-y-2">
              {items.map((r) => (
                <div key={r.number} className="rounded-2xl p-3 ring-1 ring-gray-100">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-semibold">{r.number} <span className="text-xs text-gray-500">· {r.items_count} dona{r.delivery_vehicle === "truck" ? " · yirik" : ""}</span></p>
                      <p className="text-xs text-gray-500">{r.recipient_name} · {districtName(r.district)}</p>
                    </div>
                    <StatusBadge status={r.status} />
                  </div>
                  <div className="mt-2 flex gap-2">
                    {r.status !== "picking" ? (
                      <Button className="!py-2 text-sm" onClick={() => run(() => api(`/admin/orders/${r.number}/start-picking`, { method: "POST" }), "Yig'ish boshlandi", load)}>
                        Yig&apos;ishni boshlash
                      </Button>
                    ) : (
                      <Button className="!py-2 text-sm" onClick={async () => setOpen(await api<OrderDetail>(`/admin/orders/${r.number}`))}>
                        Qadoqlash
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        );
      })}
      {open ? <PackDialog order={open} onClose={() => setOpen(null)} onDone={async () => { setOpen(null); await load(); }} /> : null}
    </div>
  );
}

function PackDialog({ order, onClose, onDone }: { order: OrderDetail; onClose: () => void; onDone: () => Promise<void> }) {
  const run = useRun();
  const [options, setOptions] = useState<Record<number, { id: number; serial_number: string; imei1: string | null }[]>>({});
  const [chosen, setChosen] = useState<Record<number, number[]>>({});
  const tracked = order.items.filter((i) => i.serial_tracking !== "none");

  useEffect(() => {
    tracked.forEach(async (i) => {
      const units = list(await api<Page<{ id: number; serial_number: string; imei1: string | null }>>(`/admin/serials?variant=${i.variant_id}&status=in_stock&page_size=100`));
      setOptions((o) => ({ ...o, [i.id]: units }));
    });
  }, [order.number]);

  const ready = tracked.every((i) => (chosen[i.id]?.length ?? 0) === i.qty);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold">Qadoqlash: {order.number}</h3>
        <p className="text-sm text-gray-500">{order.recipient_name} · {order.address}</p>
        <ul className="mt-4 space-y-3">
          {order.items.map((i) => (
            <li key={i.id} className="rounded-2xl p-3 ring-1 ring-gray-100">
              <p className="font-semibold">{i.name} × {i.qty}</p>
              <p className="text-xs text-gray-500">{i.sku}</p>
              {i.serial_tracking !== "none" ? (
                <div className="mt-2 space-y-1">
                  <p className="text-xs font-semibold text-amber-700">{i.qty} ta seriya raqam / IMEI tanlang (skanerlang):</p>
                  {(options[i.id] ?? []).map((u) => {
                    const sel = chosen[i.id] ?? [];
                    const on = sel.includes(u.id);
                    return (
                      <label key={u.id} className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={on} className="h-4 w-4 accent-violet-700"
                          onChange={() => setChosen({ ...chosen, [i.id]: on ? sel.filter((x) => x !== u.id) : [...sel, u.id] })} />
                        {u.imei1 || u.serial_number}
                      </label>
                    );
                  })}
                  {options[i.id] && !options[i.id].length ? <p className="text-xs text-red-600">Omborda bo&apos;sh seriyali dona yo&apos;q.</p> : null}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        <div className="mt-5 grid grid-cols-2 gap-2">
          <Button variant="ghost" onClick={onClose}>Yopish</Button>
          <Button disabled={!ready}
            onClick={() => run(() => api(`/admin/orders/${order.number}/pack`, { method: "POST", body: { serials: chosen } }), "Qadoqlandi", onDone)}>
            Qadoqlandi
          </Button>
        </div>
      </div>
    </div>
  );
}

// --- Marshrutlar ---
function RoutesTab() {
  const run = useRun();
  const [routes, setRoutes] = useState<Route[] | null>(null);
  const [ready, setReady] = useState<OrderRow[]>([]);
  const [couriers, setCouriers] = useState<Courier[]>([]);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [form, setForm] = useState({ courier: "", warehouse: "", date: new Date().toISOString().slice(0, 10) });
  const [picked, setPicked] = useState<string[]>([]);
  const [openRoute, setOpenRoute] = useState<Route | null>(null);

  const load = useCallback(async () => {
    const [r, o] = await Promise.all([
      api<Page<Route>>("/admin/route-sheets?status=draft,issued&page_size=50"),
      api<Page<OrderRow>>("/admin/orders?status=packed,in_transit&unrouted=1&page_size=100"),
    ]);
    setRoutes(list(r));
    setReady(list(o));
    setPicked([]);
  }, []);

  useEffect(() => {
    load();
    api<Page<Courier>>("/admin/couriers").then((c) => setCouriers(list(c).filter((x) => x.is_active))).catch(() => setCouriers([]));
    api<Page<Warehouse>>("/admin/warehouses").then((w) => {
      const ws = list(w);
      setWarehouses(ws);
      setForm((f) => ({ ...f, warehouse: f.warehouse || String(ws[0]?.id ?? "") }));
    }).catch(() => setWarehouses([]));
  }, [load]);

  const show = async (id: number) => setOpenRoute(await api<Route>(`/admin/route-sheets/${id}`));
  const refresh = async () => {
    await load();
    if (openRoute) await show(openRoute.id);
  };

  if (!routes) return <Loading />;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
      <Panel>
        <h2 className="mb-3 font-bold">Yangi marshrut varag&apos;i</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">Kuryer
            <select value={form.courier} className="mt-1 w-full" onChange={(e) => {
              const c = couriers.find((x) => String(x.id) === e.target.value);
              // Kuryerning asosiy ombori avtomatik tanlanadi.
              setForm({ ...form, courier: e.target.value, warehouse: c?.warehouse ? String(c.warehouse) : form.warehouse });
            }}>
              <option value="">— tanlang —</option>
              {couriers.map((c) => <option key={c.id} value={c.id}>{c.name}{c.vehicle === "truck" ? " (yuk mashinasi)" : ""}</option>)}
            </select>
          </label>
          <label className="text-sm">Ombor
            <select value={form.warehouse} onChange={(e) => setForm({ ...form, warehouse: e.target.value })} className="mt-1 w-full">
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </label>
          <label className="text-sm">Sana
            <input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="mt-1 w-full" />
          </label>
        </div>
        <p className="mb-2 mt-4 text-sm font-semibold">Jo&apos;natishga tayyor buyurtmalar ({ready.length})</p>
        {!ready.length ? <p className="text-sm text-gray-500">Qadoqlangan buyurtma yo&apos;q — avval &quot;Yig&apos;ish&quot; bo&apos;limida qadoqlang.</p> : null}
        <div className="space-y-2">
          {ready.map((o) => {
            const on = picked.includes(o.number);
            return (
              <label key={o.number} className={`flex cursor-pointer items-center gap-3 rounded-2xl p-3 ring-1 ${on ? "bg-brand-light ring-brand" : "ring-gray-100"}`}>
                <input type="checkbox" checked={on} className="h-4 w-4 accent-violet-700"
                  onChange={() => setPicked(on ? picked.filter((x) => x !== o.number) : [...picked, o.number])} />
                <div className="flex-1 text-sm">
                  <p className="font-semibold">{o.number} · {o.recipient_name}</p>
                  <p className="text-xs text-gray-500">{districtName(o.district)} · {o.items_count} dona{o.delivery_vehicle === "truck" ? " · yuk mashinasi kerak" : ""}{o.failed_attempts ? ` · urinishlar: ${o.failed_attempts}` : ""}</p>
                </div>
                <StatusBadge status={o.status} />
              </label>
            );
          })}
        </div>
        <Button className="mt-4 w-full" disabled={!form.courier || !form.warehouse}
          onClick={() => run(async () => {
            const r = await api<Route>("/admin/route-sheets", { method: "POST", body: { courier: Number(form.courier), warehouse: Number(form.warehouse), date: form.date, orders: picked } });
            setOpenRoute(r);
          }, "Marshrut varag'i yaratildi", load)}>
          Marshrut yaratish{picked.length ? ` (${picked.length} ta buyurtma)` : ""}
        </Button>
      </Panel>

      <div className="space-y-3">
        <h2 className="font-bold">Faol marshrutlar</h2>
        {!routes.length ? <Empty text="Faol marshrut yo'q" /> : null}
        {routes.map((r) => (
          <button key={r.id} onClick={() => show(r.id)}
            className={`flex w-full items-center justify-between rounded-2xl bg-white p-4 text-left ring-1 ${openRoute?.id === r.id ? "ring-brand" : "ring-gray-100"}`}>
            <div>
              <p className="font-semibold">{r.number} · {r.courier.name}</p>
              <p className="text-xs text-gray-500">{r.date} · {r.warehouse_name} · {r.stops_done}/{r.stops_total}</p>
            </div>
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${r.status === "issued" ? "bg-violet-50 text-violet-700" : "bg-gray-100 text-gray-600"}`}>{r.status_label}</span>
          </button>
        ))}
        {openRoute ? (
          <Panel>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-bold">{openRoute.number} — {openRoute.courier.name}</h3>
              <span className="text-sm text-gray-500">{openRoute.status_label}</span>
            </div>
            <ul className="space-y-2">
              {(openRoute.stops ?? []).map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 rounded-xl p-2 text-sm ring-1 ring-gray-100">
                  <span><b>#{s.sequence}</b> {s.order.number} · {s.order.recipient_name}</span>
                  <span className="flex items-center gap-2">
                    {openRoute.status === "draft" ? (
                      <button className="text-xs text-red-600 underline"
                        onClick={() => run(() => api(`/admin/route-sheets/${openRoute.id}/stops/${s.id}`, { method: "DELETE" }), "Olib tashlandi", refresh)}>
                        olib tashlash
                      </button>
                    ) : <ResultBadge result={s.result} />}
                    <StatusBadge status={s.order.status} />
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-4">
              {openRoute.status === "draft" ? (
                <Button className="w-full" onClick={() => run(() => api(`/admin/route-sheets/${openRoute.id}/issue`, { method: "POST" }), "Kuryerga berildi", refresh)}>
                  Kuryerga berish (tovar ombordan chiqadi)
                </Button>
              ) : null}
              {openRoute.status === "issued" ? (
                <Button variant="dark" className="w-full" onClick={() => run(() => api(`/admin/route-sheets/${openRoute.id}/close`, { method: "POST" }), "Marshrut yopildi", async () => { setOpenRoute(null); await load(); })}>
                  Kun yakuni: marshrutni yopish (qaytgan tovarlar omborga)
                </Button>
              ) : null}
            </div>
          </Panel>
        ) : null}
      </div>
    </div>
  );
}

// --- Kuryer kassasi ---
// --- Mijozlarga pul qaytarish ---
type RefundRow = OrderRow & { refund_due: string; payment_status: string };

function RefundsTab() {
  const run = useRun();
  const [rows, setRows] = useState<RefundRow[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [account, setAccount] = useState("");

  const load = useCallback(async () => {
    setRows(list(await api<Page<RefundRow>>("/admin/orders?payment_status=refund_pending&page_size=100")));
  }, []);
  useEffect(() => {
    load();
    api<Account[]>("/admin/backoffice/cash-accounts").then((a) => {
      const active = a.filter((x) => x.is_active);
      setAccounts(active);
      setAccount(String(active[0]?.id ?? ""));
    });
  }, [load]);

  if (!rows) return <Loading />;
  return (
    <Panel>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-bold">Mijozga qaytariladigan pullar</h2>
        <label className="flex items-center gap-2 text-sm">Qaysi hisobdan:
          <select value={account} onChange={(e) => setAccount(e.target.value)} className="text-sm">
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
      </div>
      <p className="mb-4 text-xs text-gray-500">
        Eshikda sababi bilan rad etilsa — yetkazish narxi ham qaytariladi; 3 urinishda bog&apos;lanib bo&apos;lmasa — yetkazish narxi qaytarilmaydi.
      </p>
      {!rows.length ? <p className="text-sm text-gray-500">Qaytariladigan pul yo&apos;q.</p> : null}
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.number} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl p-3 ring-1 ring-gray-100">
            <div>
              <p className="font-semibold">{r.number} · {r.recipient_name}</p>
              <p className="text-xs text-gray-500">{r.recipient_phone} · <StatusBadge status={r.status} /></p>
            </div>
            <div className="flex items-center gap-3">
              <b>{sum(r.refund_due)}</b>
              <Button className="!h-9 text-sm" disabled={!account}
                onClick={() => run(() => api(`/admin/orders/${r.number}/refund`, { method: "POST", body: { account: Number(account) } }), "Qaytarildi — kassadan chiqim yozildi", load)}>
                Qaytarildi
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function CashTab() {
  const run = useRun();
  const [rows, setRows] = useState<CashRow[] | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [account, setAccount] = useState("");
  const [history, setHistory] = useState<Handover[]>([]);

  const load = useCallback(async () => {
    const [r, h] = await Promise.all([api<CashRow[]>("/admin/courier-cash"), api<Page<Handover>>("/admin/courier-cash/handovers")]);
    setRows(r);
    setHistory(list(h));
  }, []);
  useEffect(() => {
    load();
    api<Account[]>("/admin/backoffice/cash-accounts").then((a) => {
      const cash = a.filter((x) => x.kind === "cash" && x.is_active);
      setAccounts(cash);
      setAccount(String(cash[0]?.id ?? ""));
    });
  }, [load]);

  if (!rows) return <Loading />;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="font-bold">Kuryerlardagi naqd pul</h2>
          <select value={account} onChange={(e) => setAccount(e.target.value)} className="text-sm">
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        {!rows.length ? <p className="text-sm text-gray-500">Hamma naqd pul topshirilgan.</p> : null}
        <div className="space-y-3">
          {rows.map((r) => (
            <div key={r.courier.id} className="rounded-2xl p-4 ring-1 ring-gray-100">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold">{r.courier.name}</p>
                  <p className="text-xs text-gray-500">{r.courier.phone} · {r.orders} ta buyurtma</p>
                </div>
                <p className="text-lg font-black">{sum(r.amount)}</p>
              </div>
              <ul className="mt-2 text-xs text-gray-600">
                {r.collections.map((c) => <li key={c.id} className="flex justify-between"><span>{c.order}</span><span>{sum(c.amount)}</span></li>)}
              </ul>
              <Button className="mt-3 w-full !py-2.5" disabled={!account}
                onClick={() => run(() => api("/admin/courier-cash/handovers", { method: "POST", body: { courier: r.courier.id, account: Number(account) } }), "Qabul qilindi — kassaga kirim yozildi", load)}>
                {sum(r.amount)} qabul qildim
              </Button>
            </div>
          ))}
        </div>
      </Panel>
      <Panel>
        <h2 className="mb-3 font-bold">Topshirishlar tarixi</h2>
        {!history.length ? <p className="text-sm text-gray-500">Hali yo&apos;q</p> : null}
        <ul className="space-y-2 text-sm">
          {history.map((h) => (
            <li key={h.id} className="flex items-center justify-between rounded-xl p-2 ring-1 ring-gray-100">
              <span><b>{h.number}</b> · {h.courier} · {h.orders_count} ta</span>
              <span className="font-semibold">{sum(h.amount)}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

// --- Kuryerlar ---
function CouriersTab() {
  const run = useRun();
  const [rows, setRows] = useState<Courier[] | null>(null);
  const [form, setForm] = useState({ phone: "+998 ", first_name: "", vehicle: "standard" });
  const load = useCallback(async () => setRows(list(await api<Page<Courier>>("/admin/couriers"))), []);
  useEffect(() => {
    load();
  }, [load]);

  if (!rows) return <Loading />;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel>
        <h2 className="mb-3 font-bold">Kuryerlar</h2>
        <ul className="space-y-2">
          {rows.map((c) => (
            <li key={c.id} className="flex items-center justify-between rounded-2xl p-3 ring-1 ring-gray-100">
              <div>
                <p className="font-semibold">{c.name}</p>
                <p className="text-xs text-gray-500">{c.phone} · {c.vehicle === "truck" ? "Yuk mashinasi" : "Yengil avtomobil"}</p>
              </div>
              <span className="text-sm">{Number(c.outstanding_cash) ? sum(c.outstanding_cash) : ""}</span>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel>
        <h2 className="mb-3 font-bold">Yangi kuryer</h2>
        <div className="space-y-3">
          <label className="block text-sm">Telefon<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} className="mt-1 w-full" /></label>
          <label className="block text-sm">Ism<input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} className="mt-1 w-full" /></label>
          <label className="block text-sm">Transport
            <select value={form.vehicle} onChange={(e) => setForm({ ...form, vehicle: e.target.value })} className="mt-1 w-full">
              <option value="standard">Yengil avtomobil</option>
              <option value="truck">Yuk mashinasi (yirik texnika)</option>
            </select>
          </label>
          <Button className="w-full" disabled={!form.first_name}
            onClick={() => run(() => api("/admin/couriers", { method: "POST", body: form }), "Kuryer qo'shildi", load)}>
            Qo&apos;shish
          </Button>
        </div>
      </Panel>
    </div>
  );
}
