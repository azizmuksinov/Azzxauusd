"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

import { useApp } from "./providers";
import { errorText } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Xodim paneli: mijozlar chati. AI javob bera olmagan yoki mijoz operator so'ragan suhbatlar shu yerga tushadi.

type Row = {
  id: number; status: "ai" | "waiting" | "staff" | "closed"; status_label: string; customer: string; phone: string;
  unread_for_staff: number; last_message_at: string | null; last_text: string;
};
type Msg = { id: number; sender: "customer" | "ai" | "staff" | "system"; text: string; staff_name: string; created_at: string; products: { slug: string; name: string }[] };
type Detail = Row & { messages: Msg[] };

const STATUS_CLS: Record<string, string> = {
  waiting: "bg-amber-100 text-amber-800", staff: "bg-green-100 text-green-800", ai: "bg-zinc-100 text-zinc-600", closed: "bg-zinc-100 text-zinc-400",
};
const time = (v: string | null) => (v ? new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");

export function ChatsTab() {
  const { toast } = useApp();
  const [filter, setFilter] = useState<"open" | "">("open");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [open, setOpen] = useState<Detail | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const openId = useRef<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  openId.current = open?.id ?? null;

  const load = useCallback(async () => {
    try {
      const r = await api<{ results: Row[] }>(`/admin/chats?page_size=50${filter ? `&status=${filter}` : ""}`);
      setRows(r.results);
      if (openId.current) setOpen(await api<Detail>(`/admin/chats/${openId.current}`));
    } catch { /* keyingi yangilanishda olinadi */ }
  }, [filter]);
  useEffect(() => {
    void load();
    const id = setInterval(load, 5000); // yangi xabarlar har 5 soniyada
    return () => clearInterval(id);
  }, [load]);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }); }, [open?.messages.length, open?.id]);

  const act = async (fn: () => Promise<Detail>) => {
    setBusy(true);
    try {
      setOpen(await fn());
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const reply = (e: React.FormEvent) => {
    e.preventDefault();
    const v = text.trim();
    if (!v || !open) return;
    setText("");
    void act(() => api<Detail>(`/admin/chats/${open.id}/reply`, { method: "POST", body: { text: v } }));
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr] [&>*]:min-w-0">
      <Panel className={open ? "hidden lg:block" : ""}>
        <div className="mb-3 flex gap-1.5 text-sm">
          {([["open", "Javob kutayotgan"], ["", "Hammasi"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setFilter(k)}
              className={`rounded-full px-3 py-1.5 ${filter === k ? "bg-gray-900 text-white" : "bg-surface text-zinc-600"}`}>{label}</button>
          ))}
        </div>
        {rows === null ? <Loading /> : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-zinc-500">
            {filter ? "Javob kutayotgan suhbat yo'q. Oddiy savollarga AI yordamchi o'zi javob beradi." : "Hali suhbat yo'q."}
          </p>
        ) : (
          <ul className="max-h-[70vh] space-y-1 overflow-y-auto">
            {rows.map((r) => (
              <li key={r.id}>
                <button onClick={async () => setOpen(await api<Detail>(`/admin/chats/${r.id}`))}
                  className={`w-full rounded-xl border p-2.5 text-left transition ${open?.id === r.id ? "border-brand bg-brand-light/40" : "border-line hover:bg-surface"}`}>
                  <span className="flex items-center gap-2">
                    <b className="min-w-0 flex-1 truncate text-sm">{r.customer}{r.phone ? ` · ${r.phone}` : ""}</b>
                    {r.unread_for_staff ? <span className="rounded-full bg-sale px-1.5 text-xs font-bold leading-5 text-white">{r.unread_for_staff}</span> : null}
                  </span>
                  <span className="mt-0.5 block truncate text-[13px] text-zinc-500">{r.last_text}</span>
                  <span className="mt-1 flex items-center justify-between text-[11px]">
                    <span className={`rounded px-1.5 py-0.5 ${STATUS_CLS[r.status]}`}>{r.status_label}</span>
                    <span className="text-zinc-400">{time(r.last_message_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel className={`flex min-h-[60vh] flex-col ${open ? "" : "hidden lg:flex"}`}>
        {!open ? (
          <p className="m-auto max-w-sm text-center text-sm text-zinc-500">Suhbatni tanlang. Yozgan javobingiz mijozning chat oynasida darhol ko&apos;rinadi.</p>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-line pb-3">
              <button onClick={() => setOpen(null)} className="rounded-lg bg-surface px-2.5 py-1.5 text-sm lg:hidden">← Ro&apos;yxat</button>
              <div className="min-w-0 flex-1">
                <p className="truncate font-bold">{open.customer}</p>
                <p className="text-xs text-zinc-500">
                  {open.phone ? <a href={`tel:${open.phone}`} className="text-brand">{open.phone}</a> : "Telefon qoldirilmagan"} · {open.status_label}
                </p>
              </div>
              <Button variant="ghost" className="!h-9 !px-3 text-sm" disabled={busy || open.status === "ai"}
                onClick={() => act(() => api<Detail>(`/admin/chats/${open.id}/status`, { method: "POST", body: { status: "ai" } }))}>AI&apos;ga qaytarish</Button>
              <Button variant="ghost" className="!h-9 !px-3 text-sm" disabled={busy || open.status === "closed"}
                onClick={() => act(() => api<Detail>(`/admin/chats/${open.id}/status`, { method: "POST", body: { status: "closed" } }))}>Yopish</Button>
            </div>
            <div ref={listRef} className="max-h-[55vh] flex-1 space-y-2 overflow-y-auto pr-1">
              {open.messages.map((m) =>
                m.sender === "system" ? (
                  <p key={m.id} className="mx-auto max-w-md rounded-lg bg-surface px-3 py-1.5 text-center text-xs text-zinc-500">{m.text}</p>
                ) : (
                  <div key={m.id} className={`flex ${m.sender === "customer" ? "justify-start" : "justify-end"}`}>
                    <div className={`max-w-[80%] whitespace-pre-line rounded-2xl px-3.5 py-2 text-sm ${m.sender === "customer" ? "bg-surface" : m.sender === "ai" ? "bg-violet-50 text-zinc-700" : "bg-brand text-white"}`}>
                      <span className={`mb-0.5 block text-[11px] font-semibold ${m.sender === "staff" ? "text-white/80" : "text-zinc-500"}`}>
                        {m.sender === "customer" ? "Mijoz" : m.sender === "ai" ? "AI yordamchi" : m.staff_name || "Xodim"} · {time(m.created_at)}
                      </span>
                      {m.text}
                      {m.products?.length ? <span className="mt-1 block text-xs opacity-80">Tavsiya: {m.products.map((p) => p.name).join("; ")}</span> : null}
                    </div>
                  </div>
                ),
              )}
            </div>
            <form onSubmit={reply} className="mt-3 flex items-end gap-2 border-t border-line pt-3">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={4000} placeholder="Javob yozing… (Enter — yuborish)"
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) reply(e); }} className="min-h-[52px] flex-1 resize-none" />
              <Button type="submit" disabled={busy || !text.trim()}>Yuborish</Button>
            </form>
          </>
        )}
      </Panel>
    </div>
  );
}
