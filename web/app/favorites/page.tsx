"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconHeart } from "@/components/icons";
import { useApp } from "@/components/providers";
import { Grid, Loading, ProductCard } from "@/components/ui";
import { api } from "@/lib/api";
import type { Card } from "@/lib/types";

export default function FavoritesPage() {
  const { t, me, ready, favorites, lang } = useApp();
  const [items, setItems] = useState<Card[] | null>(null);

  useEffect(() => {
    if (me) api<Card[]>("/me/favorites").then(setItems).catch(() => setItems([]));
  }, [me, favorites.size, lang]);

  if (!ready) return <Loading />;
  if (!me) {
    return (
      <div className="rounded-2xl bg-white py-16 text-center border border-line">
        <IconHeart className="mx-auto h-12 w-12 text-rose-400" />
        <p className="mt-3 text-lg font-semibold">{t("loginToFav")}</p>
        <Link href="/login?next=/favorites" className="mt-5 inline-block rounded-2xl bg-brand px-6 py-3 font-bold text-white">{t("login")}</Link>
      </div>
    );
  }
  if (!items) return <Loading />;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">{t("favorites")}</h1>
      {items.length === 0 ? (
        <div className="rounded-2xl bg-white py-16 text-center text-zinc-500 border border-line">
          <IconHeart className="mx-auto h-12 w-12 text-zinc-300" />
          <p className="mt-3">{t("favoritesEmpty")}</p>
          <Link href="/" className="mt-4 inline-block font-semibold text-brand">{t("goShopping")}</Link>
        </div>
      ) : (
        <Grid>{items.map((p) => <ProductCard key={p.id} p={p} />)}</Grid>
      )}
    </div>
  );
}
