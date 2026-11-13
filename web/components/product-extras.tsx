"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Card } from "@/lib/types";

import { IconBox, IconCart, IconHeart, IconHome, IconMenu, IconStar, IconUser } from "./icons";
import { Illustration } from "./illustrations";
import { useApp } from "./providers";
import { Button, Grid, ProductCard, SectionTitle } from "./ui";

// --- Rasm galereyasi va video ---
function youtubeId(url: string): string | null {
  const m = url.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/))([\w-]{11})/);
  return m ? m[1] : null;
}

export function Gallery({ images, video, category, children }: {
  images: { id: number; url: string }[]; video?: string; category: string; children?: React.ReactNode;
}) {
  const [broken, setBroken] = useState<string[]>([]); // ochilmagan suratlar ko'rsatilmaydi
  const slides: ({ kind: "img"; url: string } | { kind: "video"; url: string })[] = images
    .filter((i) => !broken.includes(i.url)).map((i) => ({ kind: "img" as const, url: i.url }));
  if (video) slides.push({ kind: "video", url: video });
  const [i, setI] = useState(0);
  const [zoom, setZoom] = useState(false);
  const cur = slides[Math.min(i, Math.max(0, slides.length - 1))];
  const fail = (url: string) => setBroken((b) => (b.includes(url) ? b : [...b, url]));

  return (
    <div className="flex flex-col-reverse gap-3 md:flex-row">
      {slides.length > 1 ? (
        <div className="no-scrollbar flex gap-2.5 overflow-x-auto p-1 md:max-h-[500px] md:flex-col md:overflow-y-auto">
          {slides.map((s, k) => (
            <button key={k} onClick={() => setI(k)} onMouseEnter={() => setI(k)}
              className={`photo relative h-[68px] w-[68px] shrink-0 overflow-hidden rounded-2xl ring-2 ring-offset-2 ring-offset-page transition ${k === i ? "ring-brand" : "ring-transparent hover:ring-line"}`}>
              {s.kind === "img" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={s.url} alt="" onError={() => fail(s.url)} className="photo h-full w-full object-contain p-1" />
              ) : (
                <span className="grid h-full w-full place-items-center bg-[#0a1f24] text-white">▶</span>
              )}
            </button>
          ))}
        </div>
      ) : null}
      <div className={`relative aspect-square flex-1 overflow-hidden rounded-[28px] shadow-card md:aspect-auto md:h-[500px] ${cur ? "photo" : "bg-white"}`}>
        {!cur ? (
          <Illustration category={category} />
        ) : cur.kind === "img" ? (
          <button className="h-full w-full cursor-zoom-in" onClick={() => setZoom(true)} aria-label="Kattalashtirish">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img key={cur.url} src={cur.url} alt="" onError={() => fail(cur.url)} className="photo h-full w-full animate-[fadeIn_.25s_ease-out] object-contain p-5 md:p-8" />
          </button>
        ) : (
          <VideoPlayer url={cur.url} />
        )}
        {children}
        {slides.length > 1 ? (
          <div className="absolute bottom-3 left-1/2 flex -translate-x-1/2 gap-1.5 rounded-full bg-black/10 px-2 py-1.5 md:hidden">
            {slides.map((_, k) => <span key={k} className={`h-1.5 rounded-full transition-all ${k === i ? "w-5 bg-brand" : "w-1.5 bg-black/25"}`} />)}
          </div>
        ) : null}
      </div>
      {zoom && cur?.kind === "img" ? (
        <div className="fixed inset-0 z-[60] grid animate-[fadeIn_.15s_ease-out] place-items-center bg-black/85 p-4" onClick={() => setZoom(false)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={cur.url} alt="" className="photo max-h-full max-w-full rounded-3xl object-contain" />
          <button className="absolute right-4 top-4 grid h-11 w-11 place-items-center rounded-full bg-white/15 text-2xl text-white" aria-label="Yopish">×</button>
        </div>
      ) : null}
    </div>
  );
}

function VideoPlayer({ url }: { url: string }) {
  const yt = youtubeId(url);
  if (yt) {
    return (
      <iframe src={`https://www.youtube-nocookie.com/embed/${yt}?rel=0`} title="Video" className="h-full w-full"
        allow="accelerometer; autoplay; encrypted-media; picture-in-picture" allowFullScreen />
    );
  }
  return <video src={url} controls playsInline className="h-full w-full bg-black object-contain" />;
}

// --- Sharhlar ---
type ReviewItem = { id: number; rating: number; text: string; pros: string; cons: string; author: string; reply: string; created_at: string };
type ReviewsData = { results: ReviewItem[]; rating_avg: string; rating_count: number; distribution: Record<string, number>; can_review: boolean };

function StarsInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" onClick={() => onChange(n)} aria-label={`${n}`} className="transition hover:scale-110">
          <IconStar className={`h-8 w-8 ${n <= value ? "text-amber-400" : "text-zinc-200"}`} />
        </button>
      ))}
    </div>
  );
}

export function Reviews({ slug }: { slug: string }) {
  const { me, lang, toast } = useApp();
  const [data, setData] = useState<ReviewsData | null>(null);
  const [form, setForm] = useState({ rating: 0, text: "", pros: "", cons: "" });
  const [open, setOpen] = useState(false);

  const load = () => api<ReviewsData>(`/products/${slug}/reviews`).then(setData).catch(() => setData(null));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, me?.id]);

  if (!data) return null;
  const total = data.rating_count || 0;
  return (
    <section id="reviews" className="scroll-mt-40">
      <SectionTitle title={lang === "ru" ? "Отзывы" : "Sharhlar"} />
      <div className="grid items-start gap-5 lg:grid-cols-[300px_1fr]">
        <div className="rounded-3xl bg-white p-5 shadow-card">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-4xl font-bold">{total ? Number(data.rating_avg).toFixed(1) : "—"}</span>
            <span className="text-sm text-zinc-500">{total} {lang === "ru" ? "отзывов" : "ta sharh"}</span>
          </div>
          <div className="mt-3 space-y-1.5">
            {Object.entries(data.distribution).sort((a, b) => Number(b[0]) - Number(a[0])).map(([star, n]) => (
              <div key={star} className="flex items-center gap-2 text-sm">
                <span className="w-3 text-zinc-500">{star}</span>
                <IconStar className="h-3.5 w-3.5 text-amber-400" />
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
                  <span className="block h-full rounded-full bg-amber-400 transition-all duration-700" style={{ width: total ? `${(n / total) * 100}%` : "0%" }} />
                </span>
                <span className="w-6 text-right text-xs text-zinc-500">{n}</span>
              </div>
            ))}
          </div>
          {data.can_review ? (
            <Button className="mt-4 w-full" onClick={() => setOpen((v) => !v)}>{lang === "ru" ? "Написать отзыв" : "Sharh yozish"}</Button>
          ) : (
            <p className="mt-4 text-xs text-zinc-500">
              {me ? "Sharhni tovarni qabul qilib olgandan keyin yozish mumkin." : "Sharh yozish uchun tizimga kiring va tovarni xarid qiling."}
            </p>
          )}
        </div>
        <div className="space-y-3">
          {open ? (
            <form className="animate-fade-up space-y-3 rounded-3xl bg-white p-5 shadow-card" onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api(`/products/${slug}/reviews`, { method: "POST", body: form });
                toast("Rahmat! Sharhingiz qo'shildi");
                setOpen(false);
                await load();
              } catch (err) {
                toast(err instanceof ApiError ? err.message : "Xatolik", "error");
              }
            }}>
              <StarsInput value={form.rating} onChange={(rating) => setForm({ ...form, rating })} />
              <input placeholder="Afzalliklari" value={form.pros} onChange={(e) => setForm({ ...form, pros: e.target.value })} className="w-full" />
              <input placeholder="Kamchiliklari" value={form.cons} onChange={(e) => setForm({ ...form, cons: e.target.value })} className="w-full" />
              <textarea placeholder="Izoh" rows={3} value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} className="w-full" />
              <Button type="submit" disabled={!form.rating}>Yuborish</Button>
            </form>
          ) : null}
          {data.results.length === 0 ? <p className="rounded-3xl bg-white p-5 text-sm text-zinc-500 shadow-card">Hali sharh yo&apos;q.</p> : null}
          {data.results.map((r) => (
            <article key={r.id} className="rounded-3xl bg-white p-5 shadow-card">
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-brand-light text-sm font-semibold text-brand">{r.author[0]}</span>
                <div>
                  <p className="text-sm font-medium">{r.author}</p>
                  <p className="text-xs text-zinc-400">{new Date(r.created_at).toLocaleDateString(lang === "ru" ? "ru-RU" : "uz-UZ")}</p>
                </div>
                <span className="ml-auto flex">{[1, 2, 3, 4, 5].map((n) => <IconStar key={n} className={`h-4 w-4 ${n <= r.rating ? "text-amber-400" : "text-zinc-200"}`} />)}</span>
              </div>
              {r.pros ? <p className="mt-2 text-sm"><b>Afzalliklari:</b> {r.pros}</p> : null}
              {r.cons ? <p className="mt-1 text-sm"><b>Kamchiliklari:</b> {r.cons}</p> : null}
              {r.text ? <p className="mt-1 text-sm text-zinc-700">{r.text}</p> : null}
              {r.reply ? <p className="mt-2 rounded-2xl bg-surface p-3 text-sm"><b>Do&apos;kon javobi:</b> {r.reply}</p> : null}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

// --- Yaqinda ko'rilganlar (faqat shu brauzerda) ---
const RECENT_KEY = "dokon.recent";

export function rememberViewed(card: Card) {
  try {
    const list: Card[] = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    const next = [card, ...list.filter((c) => c.id !== card.id)].slice(0, 12);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // brauzer xotirasi yopiq bo'lishi mumkin
  }
}

export function RecentlyViewed({ exclude }: { exclude?: number }) {
  const { lang } = useApp();
  const [items, setItems] = useState<Card[]>([]);
  useEffect(() => {
    try {
      setItems((JSON.parse(localStorage.getItem(RECENT_KEY) || "[]") as Card[]).filter((c) => c.id !== exclude).slice(0, 5));
    } catch {
      setItems([]);
    }
  }, [exclude]);
  if (!items.length) return null;
  return (
    <section>
      <SectionTitle title={lang === "ru" ? "Вы недавно смотрели" : "Yaqinda ko'rganlaringiz"} />
      <Grid>{items.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
    </section>
  );
}

// --- Telefon uchun pastki menyu ---
export function BottomNav() {
  const { t, cart, favorites, me, lang } = useApp();
  const pathname = usePathname();
  if (pathname.startsWith("/kuryer") || pathname.startsWith("/xodim")) return null;
  const items: [string, string, React.ReactNode, number?][] = [
    ["/", lang === "ru" ? "Главная" : "Asosiy", <IconHome key="h" className="h-6 w-6" />],
    ["/catalog", t("catalog"), <IconMenu key="c" className="h-6 w-6" />],
    ["/cart", t("cart"), <IconCart key="k" className="h-6 w-6" />, cart?.items_count],
    ["/favorites", t("favorites"), <IconHeart key="f" className="h-6 w-6" />, favorites.size],
    [me ? "/orders" : "/login", me ? t("orders") : t("login"), me ? <IconBox key="u" className="h-6 w-6" /> : <IconUser key="u" className="h-6 w-6" />],
  ];
  return (
    <nav className="fixed inset-x-3 bottom-[calc(10px+env(safe-area-inset-bottom))] z-40 rounded-[26px] bg-white/95 p-1.5 shadow-dock ring-1 ring-black/5 backdrop-blur-xl md:hidden">
      <div className="grid grid-cols-5">
        {items.map(([href, label, icon, badge]) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link key={href} href={href}
              className={`relative flex flex-col items-center gap-0.5 rounded-[20px] py-1.5 text-[11px] font-medium transition ${active ? "bg-brand-light text-brand" : "text-zinc-500 active:bg-surface"}`}>
              {icon}
              <span className="max-w-full truncate px-1">{label}</span>
              {badge ? (
                <span key={badge} className="animate-pop absolute right-[18%] top-0.5 min-w-[18px] rounded-full bg-sale px-1 text-center text-[10px] font-bold leading-[18px] text-white ring-2 ring-white">{badge}</span>
              ) : null}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
