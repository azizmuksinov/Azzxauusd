"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { L, SectionKey, Site } from "@/lib/site";

import { useApp } from "./providers";
import { errorText } from "./staff";
import { Button, Loading, Panel } from "./ui";

// Admin: do'kon sahifalari (Sayt), tizim sozlamalari va xodimlar rollari.

const SECTION_LABELS: Record<SectionKey, string> = {
  hero: "Bannerlar (yuqori qism)",
  categories: "Kategoriyalar",
  deals: "Chegirmalar",
  popular: "Ommabop tovarlar",
  new: "Yangi tovarlar",
  brands: "Brendlar",
  recent: "Yaqinda ko'rilganlar",
};
const SOCIALS = ["telegram", "instagram", "facebook", "youtube"] as const;

function Bi({ label, value, onChange, area = false }: { label: string; value: L; onChange: (v: L) => void; area?: boolean }) {
  const input = (lang: "uz" | "ru") =>
    area ? (
      <textarea rows={6} value={value[lang]} onChange={(e) => onChange({ ...value, [lang]: e.target.value })} className="mt-1 w-full" />
    ) : (
      <input value={value[lang]} onChange={(e) => onChange({ ...value, [lang]: e.target.value })} className="mt-1 w-full" />
    );
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm">{label} (o&apos;zbekcha){input("uz")}</label>
      <label className="block text-sm">{label} (ruscha){input("ru")}</label>
    </div>
  );
}

export function SiteTab() {
  const { toast, reloadSite } = useApp();
  const [s, setS] = useState<Site | null>(null);
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState("delivery");

  useEffect(() => {
    api<Site>("/admin/site").then(setS);
  }, []);
  if (!s) return <Loading />;

  const save = async () => {
    setBusy(true);
    try {
      setS(await api<Site>("/admin/site", { method: "PUT", body: s }));
      await reloadSite();
      toast("Sayt yangilandi");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const move = (i: number, d: number) => {
    const list = [...s.home_sections];
    const j = i + d;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    setS({ ...s, home_sections: list });
  };

  return (
    <div className="space-y-4">
      <Panel className="space-y-3">
        <h2 className="font-bold">Do&apos;kon va aloqa</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block text-sm">Do&apos;kon nomi<input value={s.store_name} onChange={(e) => setS({ ...s, store_name: e.target.value })} className="mt-1 w-full" /></label>
          <label className="block text-sm">Telefon<input value={s.phone} onChange={(e) => setS({ ...s, phone: e.target.value })} placeholder="+998 71 200-00-00" className="mt-1 w-full" /></label>
          <label className="block text-sm">E-pochta<input value={s.email} onChange={(e) => setS({ ...s, email: e.target.value })} className="mt-1 w-full" /></label>
        </div>
        <Bi label="Shahar" value={s.city} onChange={(v) => setS({ ...s, city: v })} />
        <Bi label="Manzil" value={s.address} onChange={(v) => setS({ ...s, address: v })} />
        <Bi label="Ish vaqti" value={s.working_hours} onChange={(v) => setS({ ...s, working_hours: v })} />
        <div className="grid gap-3 sm:grid-cols-4">
          {SOCIALS.map((k) => (
            <label key={k} className="block text-sm capitalize">{k}
              <input value={s.socials[k]} onChange={(e) => setS({ ...s, socials: { ...s.socials, [k]: e.target.value } })} placeholder="https://" className="mt-1 w-full" />
            </label>
          ))}
        </div>
      </Panel>

      <Panel className="space-y-3">
        <div className="flex items-center gap-3">
          <h2 className="mr-auto font-bold">E&apos;lon qatori (sayt tepasida)</h2>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={s.announcement.enabled} onChange={(e) => setS({ ...s, announcement: { ...s.announcement, enabled: e.target.checked } })} /> Ko&apos;rsatish
          </label>
        </div>
        <Bi label="Matn" value={s.announcement.text} onChange={(v) => setS({ ...s, announcement: { ...s.announcement, text: v } })} />
        <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
          <label className="block text-sm">Havola (ixtiyoriy)<input value={s.announcement.link} onChange={(e) => setS({ ...s, announcement: { ...s.announcement, link: e.target.value } })} placeholder="/c/muzlatkichlar" className="mt-1 w-full" /></label>
          <label className="block text-sm">Rang<input type="color" value={s.announcement.color} onChange={(e) => setS({ ...s, announcement: { ...s.announcement, color: e.target.value } })} className="mt-1 h-10 w-full p-1" /></label>
        </div>
      </Panel>

      <Panel className="space-y-3">
        <h2 className="font-bold">Bosh sahifa bo&apos;limlari</h2>
        <p className="text-xs text-zinc-500">Tartibini o&apos;zgartiring, yashiring yoki sarlavhasini yozing (bo&apos;sh — standart sarlavha).</p>
        <div className="space-y-2">
          {s.home_sections.map((sec, i) => (
            <div key={sec.key} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-2.5">
              <div className="flex flex-col">
                <button onClick={() => move(i, -1)} disabled={i === 0} className="px-1 text-zinc-500 disabled:opacity-30">▲</button>
                <button onClick={() => move(i, 1)} disabled={i === s.home_sections.length - 1} className="px-1 text-zinc-500 disabled:opacity-30">▼</button>
              </div>
              <label className="flex w-52 items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={sec.enabled} onChange={(e) => setS({ ...s, home_sections: s.home_sections.map((x, j) => (j === i ? { ...x, enabled: e.target.checked } : x)) })} />
                {SECTION_LABELS[sec.key]}
              </label>
              {["deals", "popular", "new", "brands"].includes(sec.key) ? (
                <>
                  <input value={sec.title.uz} placeholder="Sarlavha (uz)" onChange={(e) => setS({ ...s, home_sections: s.home_sections.map((x, j) => (j === i ? { ...x, title: { ...x.title, uz: e.target.value } } : x)) })} className="min-w-0 flex-1" />
                  <input value={sec.title.ru} placeholder="Заголовок (ru)" onChange={(e) => setS({ ...s, home_sections: s.home_sections.map((x, j) => (j === i ? { ...x, title: { ...x.title, ru: e.target.value } } : x)) })} className="min-w-0 flex-1" />
                </>
              ) : null}
            </div>
          ))}
        </div>
        <p className="text-xs text-zinc-500">Bannerlar va chegirmalar — &quot;Marketing&quot; bo&apos;limida.</p>
      </Panel>

      <Panel className="space-y-3">
        <h2 className="font-bold">Ma&apos;lumot sahifalari va futer</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(s.pages).map(([k, p]) => (
            <button key={k} onClick={() => setPage(k)} className={`rounded-lg px-3 py-1.5 text-sm ${page === k ? "bg-ink text-white" : "bg-surface"}`}>{p.title.uz}</button>
          ))}
        </div>
        {s.pages[page] ? (
          <>
            <Bi label="Sarlavha" value={s.pages[page].title} onChange={(v) => setS({ ...s, pages: { ...s.pages, [page]: { ...s.pages[page], title: v } } })} />
            <Bi label="Matn" area value={s.pages[page].body} onChange={(v) => setS({ ...s, pages: { ...s.pages, [page]: { ...s.pages[page], body: v } } })} />
            <a href={`/info/${page}`} target="_blank" rel="noreferrer" className="text-sm text-brand underline">Saytda ko&apos;rish</a>
          </>
        ) : null}
        <Bi label="Futerdagi qisqa matn" value={s.footer_about} onChange={(v) => setS({ ...s, footer_about: v })} />
        <label className="block text-sm">To&apos;lov usullari (futerda)<input value={s.pay_methods} onChange={(e) => setS({ ...s, pay_methods: e.target.value })} className="mt-1 w-full" /></label>
      </Panel>

      <div className="sticky bottom-4 flex justify-end">
        <Button disabled={busy} onClick={save} className="shadow-lg">{busy ? "Saqlanmoqda…" : "Saytni saqlash"}</Button>
      </div>
    </div>
  );
}

type SettingRow = { key: string; value: unknown; default: unknown; description: string; type: string; nullable: boolean };

export function SettingsTab() {
  const { toast } = useApp();
  const [rows, setRows] = useState<SettingRow[] | null>(null);
  const [edit, setEdit] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const r = await api<SettingRow[]>("/admin/settings");
    setRows(r);
    setEdit(Object.fromEntries(r.map((x) => [x.key, x.value === null || x.value === undefined ? "" : String(x.value)])));
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  if (!rows) return <Loading />;

  const save = async () => {
    const changed: Record<string, unknown> = {};
    for (const r of rows) {
      const v = edit[r.key];
      const cur = r.value === null || r.value === undefined ? "" : String(r.value);
      if (v === cur) continue;
      if (v === "") changed[r.key] = null;
      else if (r.type === "bool") changed[r.key] = v === "true";
      else if (r.type === "int") changed[r.key] = Number(v);
      else changed[r.key] = v;
    }
    if (!Object.keys(changed).length) return toast("O'zgarish yo'q");
    try {
      await api("/admin/settings", { method: "PATCH", body: changed });
      toast("Sozlamalar saqlandi");
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };

  return (
    <Panel className="space-y-3">
      <h2 className="font-bold">Tizim sozlamalari</h2>
      <p className="text-xs text-zinc-500">Bo&apos;sh qoldirilsa — cheklovsiz/standart (agar ruxsat etilgan bo&apos;lsa).</p>
      <div className="divide-y divide-line">
        {rows.map((r) => (
          <div key={r.key} className="grid gap-2 py-3 sm:grid-cols-[1fr_220px] sm:items-center">
            <div>
              <p className="text-sm font-medium">{r.description}</p>
              <p className="text-xs text-zinc-400">{r.key} · standart: {r.default === null ? "—" : String(r.default)}</p>
            </div>
            {r.type === "bool" ? (
              <select value={edit[r.key]} onChange={(e) => setEdit({ ...edit, [r.key]: e.target.value })}>
                <option value="true">Ha</option>
                <option value="false">Yo&apos;q</option>
              </select>
            ) : (
              <input value={edit[r.key] ?? ""} onChange={(e) => setEdit({ ...edit, [r.key]: e.target.value })}
                inputMode={r.type === "int" || r.type === "decimal" ? "decimal" : "text"} />
            )}
          </div>
        ))}
      </div>
      <Button onClick={save}>Saqlash</Button>
    </Panel>
  );
}

type Staff = {
  id: number; phone: string; login: string | null; has_password: boolean; first_name: string; last_name: string;
  roles: string[]; is_active: boolean; last_login: string | null;
};
type Page<T> = { results: T[] } | T[];
const list = <T,>(p: Page<T>): T[] => (Array.isArray(p) ? p : p.results);
const ROLES: [string, string][] = [
  ["admin", "Administrator"],
  ["content_manager", "Kontent menejeri"],
  ["warehouse", "Omborchi"],
  ["logistics_manager", "Logistika menejeri"],
  ["finance", "Moliya (kassir)"],
  ["support", "Qo'llab-quvvatlash"],
];

/** Tasodifiy parol: o'qilishi oson belgilar (0/O, 1/l kabi adashtiradiganlari yo'q). */
function randomPassword(length = 12): string {
  const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const buf = new Uint32Array(length);
  crypto.getRandomValues(buf);
  return Array.from(buf, (n) => chars[n % chars.length]).join("");
}

const EMPTY_STAFF = { phone: "", first_name: "", login: "", password: "", roles: ["content_manager"] };

/** Xodimga login va parol berish/almashtirish (faqat administrator). */
function Credentials({ u, onDone }: { u: Staff; onDone: () => Promise<void> }) {
  const { toast } = useApp();
  const [login, setLogin] = useState(u.login ?? "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const body: Record<string, string> = {};
      if (login.trim() && login.trim().toLowerCase() !== (u.login ?? "")) body.login = login.trim();
      if (password) body.password = password;
      await api(`/admin/staff/${u.id}`, { method: "PATCH", body });
      toast(password ? "Saqlandi. Xodim yangi parol bilan qayta kiradi" : "Login saqlandi");
      await onDone();
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  };
  const changed = (login.trim() && login.trim().toLowerCase() !== (u.login ?? "")) || !!password;
  return (
    <div className="w-full space-y-2 rounded-2xl bg-surface p-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]">
        <input value={login} onChange={(e) => setLogin(e.target.value)} placeholder="Login" autoCapitalize="none" autoComplete="off" spellCheck={false} />
        <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder={u.has_password ? "Yangi parol" : "Parol"} autoComplete="off" spellCheck={false} />
        <button type="button" onClick={() => setPassword(randomPassword())} className="h-11 rounded-2xl bg-white px-3 text-sm font-medium ring-1 ring-line hover:text-brand">Tasodifiy</button>
        <Button disabled={busy || !changed || (!u.has_password && !password) || !login.trim()} onClick={save} className="!h-11">Saqlash</Button>
      </div>
      <p className="text-xs text-zinc-500">
        Parol kamida 10 belgi. U keyin ko&apos;rsatilmaydi — hozir yozib oling va xodimga bering. Parol almashganda xodimning ochiq seanslari yopiladi.
      </p>
    </div>
  );
}

export function StaffTab() {
  const { toast, me } = useApp();
  const [rows, setRows] = useState<Staff[] | null>(null);
  const [q, setQ] = useState("");
  const [add, setAdd] = useState(EMPTY_STAFF);
  const [edit, setEdit] = useState<number | null>(null);
  const [issued, setIssued] = useState<{ login: string; password: string } | null>(null); // hozirgina berilgan parol

  const load = useCallback(async () => {
    setRows(list(await api<Page<Staff>>(`/admin/staff?page_size=200${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ""}`)));
  }, [q]);
  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
  }, [load]);

  const patch = async (u: Staff, body: Record<string, unknown>, done: string) => {
    try {
      await api(`/admin/staff/${u.id}`, { method: "PATCH", body });
      toast(done);
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const create = async () => {
    try {
      await api("/admin/staff", { method: "POST", body: add });
      toast("Xodim qo'shildi");
      setIssued({ login: add.login.trim().toLowerCase(), password: add.password });
      setAdd(EMPTY_STAFF);
      await load();
    } catch (e) {
      toast(errorText(e), "error");
    }
  };
  const toggle = (roles: string[], r: string) => (roles.includes(r) ? roles.filter((x) => x !== r) : [...roles, r]);

  return (
    <div className="space-y-4">
      <Panel className="space-y-3">
        <h2 className="font-bold">Xodim qo&apos;shish</h2>
        <p className="text-sm text-zinc-500">Xodim panelga faqat siz bergan login va parol bilan kiradi. SMS-kod xodimlar uchun ishlamaydi.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm">Telefon<input value={add.phone} onChange={(e) => setAdd({ ...add, phone: e.target.value })} placeholder="+998 90 123 45 67" className="mt-1 w-full" /></label>
          <label className="block text-sm">Ismi<input value={add.first_name} onChange={(e) => setAdd({ ...add, first_name: e.target.value })} className="mt-1 w-full" /></label>
          <label className="block text-sm">Login
            <input value={add.login} onChange={(e) => setAdd({ ...add, login: e.target.value })} placeholder="masalan: ali.ombor" autoCapitalize="none" autoComplete="off" spellCheck={false} className="mt-1 w-full" />
          </label>
          <label className="block text-sm">Parol (kamida 10 belgi)
            <span className="mt-1 flex gap-2">
              <input value={add.password} onChange={(e) => setAdd({ ...add, password: e.target.value })} autoComplete="off" spellCheck={false} className="w-full" />
              <button type="button" onClick={() => setAdd({ ...add, password: randomPassword() })} className="shrink-0 rounded-2xl bg-surface px-3 text-sm font-medium hover:text-brand">Tasodifiy</button>
            </span>
          </label>
        </div>
        <div className="flex flex-wrap gap-3 text-sm">
          {ROLES.map(([k, l]) => (
            <label key={k} className="flex items-center gap-1.5">
              <input type="checkbox" checked={add.roles.includes(k)} onChange={() => setAdd({ ...add, roles: toggle(add.roles, k) })} /> {l}
            </label>
          ))}
        </div>
        <Button disabled={!add.phone || !add.login.trim() || add.password.length < 10} onClick={create}>Qo&apos;shish</Button>
        {issued ? (
          <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-brand-light p-3 text-sm">
            <p className="flex-1">
              Xodimga bering — login: <b className="select-all">{issued.login}</b>, parol: <b className="select-all">{issued.password}</b>.
              <span className="block text-xs text-zinc-600">Parol keyin ko&apos;rsatilmaydi. Hozir yozib oling.</span>
            </p>
            <button onClick={() => setIssued(null)} className="rounded-full bg-white px-3 py-1.5 text-xs font-medium">Yozib oldim</button>
          </div>
        ) : null}
        <p className="text-xs text-zinc-500">Kuryerlar &quot;Kuryerlar&quot; bo&apos;limida qo&apos;shiladi, login va parol esa shu yerda — ro&apos;yxatda beriladi.</p>
      </Panel>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Telefon yoki ism bo'yicha qidirish" className="w-full sm:max-w-sm" />
      {!rows ? <Loading /> : (
        <div className="divide-y divide-line rounded-xl border border-line bg-white">
          {rows.map((u) => (
            <div key={u.id} className={`flex flex-wrap items-center gap-3 p-3 ${u.is_active ? "" : "opacity-60"}`}>
              <div className="min-w-[200px]">
                <p className="text-sm font-medium">{[u.first_name, u.last_name].filter(Boolean).join(" ") || "—"}{u.is_active ? "" : " · bloklangan"}</p>
                <p className="text-xs text-zinc-500">{u.phone}</p>
                <p className="mt-0.5 text-xs">
                  {u.has_password ? <span className="font-medium text-brand">Login: {u.login}</span> : <span className="font-medium text-red-600">Login/parol berilmagan — kira olmaydi</span>}
                </p>
              </div>
              <div className="flex flex-1 flex-wrap gap-x-3 gap-y-1 text-xs">
                {ROLES.map(([k, l]) => (
                  <label key={k} className="flex items-center gap-1">
                    <input type="checkbox" checked={u.roles.includes(k)} onChange={() => patch(u, { roles: toggle(u.roles.filter((r) => r !== "courier"), k) }, "Rollar yangilandi")} /> {l}
                  </label>
                ))}
                {u.roles.includes("courier") ? <span className="rounded bg-surface px-1.5">Kuryer</span> : null}
              </div>
              <div className="flex gap-2 text-xs font-medium">
                <button onClick={() => setEdit(edit === u.id ? null : u.id)} className="rounded-full bg-brand-light px-3 py-1.5 text-brand hover:bg-brand hover:text-white">
                  {u.has_password ? "Parolni almashtirish" : "Login/parol berish"}
                </button>
                {u.id !== me?.id ? (
                  <button onClick={() => patch(u, { is_active: !u.is_active }, u.is_active ? "Xodim bloklandi" : "Blok olindi")}
                    className="rounded-full bg-surface px-3 py-1.5 text-zinc-600 hover:text-red-600">
                    {u.is_active ? "Bloklash" : "Blokdan chiqarish"}
                  </button>
                ) : null}
              </div>
              {edit === u.id ? <Credentials key={`${u.id}-${u.login}-${u.has_password}`} u={u} onDone={async () => { setEdit(null); await load(); }} /> : null}
            </div>
          ))}
          {rows.length === 0 ? <p className="p-6 text-center text-sm text-zinc-500">Topilmadi</p> : null}
        </div>
      )}
    </div>
  );
}
