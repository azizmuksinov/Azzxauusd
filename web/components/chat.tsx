"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/i18n";

import { IconChat, IconClose, IconUser } from "./icons";
import { useApp } from "./providers";

// Mijozlar chati: avval AI yordamchi javob beradi; mijoz xohlasa yoki AI bilmasa — operator (xodim paneli).

type ChatProduct = { slug: string; name: string; price: string; image: string };
type ChatMessage = { id: number; sender: "customer" | "ai" | "staff" | "system"; text: string; products: ChatProduct[]; staff_name: string };
type ChatState = { token: string; status: "ai" | "waiting" | "staff" | "closed"; messages: ChatMessage[] };

const TOKEN = "dokon.chat";
const getToken = () => { try { return localStorage.getItem(TOKEN) || ""; } catch { return ""; } };
const saveToken = (t: string) => { try { localStorage.setItem(TOKEN, t); } catch { /* saqlanmasa — shu seans uchun */ } };

export function ChatWidget() {
  const { t, lang } = useApp();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatState["status"]>("ai");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");
  const token = useRef("");
  const lastId = useRef(0);
  const openRef = useRef(false);
  const listRef = useRef<HTMLDivElement>(null);
  openRef.current = open;

  const merge = useCallback((s: ChatState) => {
    if (s.token) { token.current = s.token; saveToken(s.token); }
    setStatus(s.status);
    if (!s.messages.length) return;
    lastId.current = Math.max(lastId.current, ...s.messages.map((m) => m.id));
    setMessages((old) => {
      const have = new Set(old.map((m) => m.id));
      const fresh = s.messages.filter((m) => !have.has(m.id));
      if (fresh.length && !openRef.current) setUnread((n) => n + fresh.filter((m) => m.sender !== "customer").length);
      return fresh.length ? [...old, ...fresh] : old;
    });
  }, []);

  const pull = useCallback(async () => {
    if (!token.current) return;
    try {
      merge(await api<ChatState>(`/chat?token=${encodeURIComponent(token.current)}&after=${lastId.current}`, { auth: false }));
    } catch { /* tarmoq uzilsa keyingi safar olinadi */ }
  }, [merge]);

  // Avvalgi suhbat (shu brauzerda) tiklanadi.
  useEffect(() => { token.current = getToken(); void pull(); }, [pull]);
  // Operator javobini kutayotganda xabarlar tez-tez tekshiriladi (oyna yopiq bo'lsa — sekinroq, belgi uchun).
  useEffect(() => {
    if (status !== "waiting" && status !== "staff") return;
    const id = setInterval(pull, open ? 4000 : 20000);
    return () => clearInterval(id);
  }, [status, open, pull]);
  useEffect(() => { if (open) setUnread(0); }, [open, messages.length]);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }); }, [messages.length, open, busy]);

  const send = async (body: { text?: string; handoff?: boolean }) => {
    if (busy) return;
    setBusy(true);
    setError("");
    // Mijoz xabari darhol ko'rinadi; server javobi kelgach haqiqiy xabarlar bilan almashtiriladi.
    const temp: ChatMessage | null = body.text ? { id: -Date.now(), sender: "customer", text: body.text, products: [], staff_name: "" } : null;
    if (temp) setMessages((old) => [...old, temp]);
    try {
      const s = await api<ChatState>("/chat", { method: "POST", body: { token: token.current, lang, ...body } });
      if (temp) setMessages((old) => old.filter((m) => m.id !== temp.id));
      merge(s);
    } catch (e) {
      if (temp) setMessages((old) => old.filter((m) => m.id !== temp.id));
      if (temp) setText(temp.text);
      setError(e instanceof ApiError ? e.message : t("error"));
    } finally {
      setBusy(false);
    }
  };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = text.trim();
    if (!v) return;
    setText("");
    void send({ text: v });
  };

  if (pathname.startsWith("/xodim") || pathname.startsWith("/kuryer")) return null;
  // Telefonda pastki menyu (va tovar sahifasida xarid qatori) ustida turadi.
  const mobileBottom = pathname.startsWith("/p/") ? "bottom-[136px]" : "bottom-[72px]";
  const quick = [t("chatQ1"), t("chatQ2"), t("chatQ3")];

  return (
    <>
      {!open ? (
        <button onClick={() => setOpen(true)} aria-label={t("chatTitle")}
          className={`fixed right-3 z-30 grid h-14 w-14 place-items-center rounded-full bg-brand text-white shadow-[0_10px_30px_-8px_rgba(124,58,237,0.8)] transition hover:scale-105 hover:bg-brand-dark md:bottom-6 md:right-6 ${mobileBottom}`}>
          <IconChat className="h-7 w-7" />
          {unread ? <span className="animate-pop absolute -right-0.5 -top-0.5 min-w-[20px] rounded-full bg-sale px-1 text-center text-xs font-bold leading-5 text-white">{unread}</span> : null}
        </button>
      ) : (
        <div className="fixed inset-x-0 bottom-0 z-50 flex h-[82vh] flex-col overflow-hidden rounded-t-3xl border border-line bg-white shadow-2xl md:inset-x-auto md:bottom-6 md:right-6 md:h-[600px] md:max-h-[calc(100vh-48px)] md:w-[390px] md:rounded-3xl">
          <div className="flex items-center gap-3 bg-brand px-4 py-3 text-white">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-white/20"><IconChat className="h-5 w-5" /></span>
            <div className="min-w-0 flex-1 leading-tight">
              <p className="font-semibold">{t("chatTitle")}</p>
              <p className="truncate text-xs text-white/80">
                {status === "staff" ? t("chatStaffOn") : status === "waiting" ? t("chatWaiting") : t("chatAiOn")}
              </p>
            </div>
            {status === "ai" || status === "closed" ? (
              <button onClick={() => send({ handoff: true })} disabled={busy}
                className="inline-flex shrink-0 items-center gap-1 rounded-full bg-white/20 px-3 py-1.5 text-xs font-medium hover:bg-white/30 disabled:opacity-60">
                <IconUser className="h-4 w-4" /> {t("chatOperator")}
              </button>
            ) : null}
            <button onClick={() => setOpen(false)} aria-label={t("back")} className="grid h-9 w-9 shrink-0 place-items-center rounded-full hover:bg-white/20">
              <IconClose className="h-5 w-5" />
            </button>
          </div>

          <div ref={listRef} className="flex-1 space-y-2.5 overflow-y-auto px-3 py-3">
            <Bubble side="left" label={t("chatAiName")}>{t("chatHello")}</Bubble>
            {messages.length === 0 ? (
              <div className="flex flex-wrap gap-1.5 pl-1">
                {quick.map((q) => (
                  <button key={q} onClick={() => send({ text: q })} disabled={busy}
                    className="rounded-full border border-brand/40 px-3 py-1.5 text-[13px] text-brand transition hover:bg-brand-light disabled:opacity-60">{q}</button>
                ))}
              </div>
            ) : null}
            {messages.map((m) =>
              m.sender === "system" ? (
                <p key={m.id} className="mx-auto max-w-[90%] rounded-xl bg-surface px-3 py-2 text-center text-xs text-zinc-500">{m.text}</p>
              ) : (
                <Bubble key={m.id} side={m.sender === "customer" ? "right" : "left"}
                  label={m.sender === "ai" ? t("chatAiName") : m.sender === "staff" ? (m.staff_name || t("chatOperator")) : ""}>
                  {m.text}
                  {m.products?.length ? (
                    <span className="mt-2 block space-y-1.5">
                      {m.products.map((p) => (
                        <Link key={p.slug} href={`/p/${p.slug}`} onClick={() => setOpen(false)}
                          className="flex items-center gap-2.5 rounded-xl border border-line bg-white p-1.5 transition hover:border-brand">
                          {p.image ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={p.image} alt="" className="photo h-12 w-12 shrink-0 rounded-lg object-contain" />
                          ) : <span className="h-12 w-12 shrink-0 rounded-lg bg-brand-light" />}
                          <span className="min-w-0 flex-1">
                            <span className="line-clamp-2 text-[13px] leading-4 text-ink">{p.name}</span>
                            {p.price ? <span className="text-[13px] font-bold text-ink">{formatMoney(p.price, lang)}</span> : null}
                          </span>
                        </Link>
                      ))}
                    </span>
                  ) : null}
                </Bubble>
              ),
            )}
            {busy ? <Bubble side="left" label=""><span className="inline-flex gap-1 py-1"><Dot /><Dot d={150} /><Dot d={300} /></span></Bubble> : null}
            {error ? <p className="rounded-xl bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p> : null}
          </div>

          <form onSubmit={submit} className="flex items-end gap-2 border-t border-line p-3 pb-[calc(12px+env(safe-area-inset-bottom))]">
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={1000} placeholder={t("chatPlaceholder")}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }}
              className="max-h-28 min-h-[44px] flex-1 resize-none !rounded-2xl !py-2.5" />
            <button disabled={busy || !text.trim()} aria-label={t("chatSend")}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand text-white transition hover:bg-brand-dark disabled:opacity-50">
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M4 12 20 4l-5 16-3.5-6.5L4 12Z" /></svg>
            </button>
          </form>
        </div>
      )}
    </>
  );
}

function Bubble({ side, label, children }: { side: "left" | "right"; label: string; children: React.ReactNode }) {
  return (
    <div className={`flex ${side === "right" ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] whitespace-pre-line rounded-2xl px-3.5 py-2 text-[14px] leading-5 ${side === "right" ? "rounded-br-md bg-brand text-white" : "rounded-bl-md bg-surface text-ink"}`}>
        {label ? <span className="mb-0.5 block text-[11px] font-semibold text-brand">{label}</span> : null}
        {children}
      </div>
    </div>
  );
}

const Dot = ({ d = 0 }: { d?: number }) => (
  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" style={{ animationDelay: `${d}ms` }} />
);
