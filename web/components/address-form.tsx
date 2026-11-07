"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Address } from "@/lib/types";

import { useApp } from "./providers";
import { Button } from "./ui";

type Opt = { id: number; name: string };

export function AddressForm({ onSaved, defaultPhone }: { onSaved: (a: Address) => void; defaultPhone: string }) {
  const { t, lang } = useApp();
  const [regions, setRegions] = useState<Opt[]>([]);
  const [districts, setDistricts] = useState<Opt[]>([]);
  const [region, setRegion] = useState<number | "">("");
  const [f, setF] = useState({
    district: "", street: "", house: "", apartment: "", entrance: "", floor: "", elevator: "none",
    landmark: "", recipient_name: "", recipient_phone: defaultPhone,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Opt[]>("/geo/regions").then(setRegions).catch(() => setRegions([]));
  }, [lang]);
  useEffect(() => {
    if (!region) return;
    api<Opt[]>(`/geo/regions/${region}/districts`).then(setDistricts).catch(() => setDistricts([]));
  }, [region, lang]);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((v) => ({ ...v, [k]: e.target.value }));

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const body = { ...f, district: Number(f.district), floor: f.floor ? Number(f.floor) : null };
      onSaved(await api<Address>("/me/addresses", { method: "POST", body }));
    } catch (e) {
      if (e instanceof ApiError) {
        const fields = (e.data.fields ?? {}) as Record<string, string[]>;
        setError(Object.keys(fields).length ? Object.entries(fields).map(([k, v]) => `${k}: ${v.join(", ")}`).join("; ") : e.message);
      } else setError(t("error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label>{t("region")}
        <select value={region} onChange={(e) => { setRegion(Number(e.target.value)); setF((v) => ({ ...v, district: "" })); }} className="mt-1 w-full">
          <option value="">—</option>
          {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </label>
      <label>{t("district")}
        <select value={f.district} onChange={set("district")} className="mt-1 w-full" disabled={!districts.length}>
          <option value="">—</option>
          {districts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      <label className="sm:col-span-2">{t("street")}<input value={f.street} onChange={set("street")} className="mt-1 w-full" /></label>
      <label>{t("house")}<input value={f.house} onChange={set("house")} className="mt-1 w-full" /></label>
      <label>{t("apartment")}<input value={f.apartment} onChange={set("apartment")} className="mt-1 w-full" /></label>
      <label>{t("entrance")}<input value={f.entrance} onChange={set("entrance")} className="mt-1 w-full" /></label>
      <label>{t("floor")}<input value={f.floor} onChange={set("floor")} inputMode="numeric" className="mt-1 w-full" /></label>
      <label className="sm:col-span-2">{t("elevator")}
        <select value={f.elevator} onChange={set("elevator")} className="mt-1 w-full">
          <option value="none">{t("elevatorNone")}</option>
          <option value="passenger">{t("elevatorPassenger")}</option>
          <option value="freight">{t("elevatorFreight")}</option>
        </select>
      </label>
      <label className="sm:col-span-2">{t("landmark")}<input value={f.landmark} onChange={set("landmark")} className="mt-1 w-full" /></label>
      <label>{t("recipient")}<input value={f.recipient_name} onChange={set("recipient_name")} className="mt-1 w-full" /></label>
      <label>{t("recipientPhone")}<input value={f.recipient_phone} onChange={set("recipient_phone")} className="mt-1 w-full" /></label>
      {error ? <p className="text-sm text-red-600 sm:col-span-2">{error}</p> : null}
      <Button onClick={save} disabled={busy || !f.district || !f.street || !f.house || !f.recipient_name} className="sm:col-span-2">
        {t("save")}
      </Button>
    </div>
  );
}
