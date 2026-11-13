"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { IconChevron } from "@/components/icons";
import { Illustration } from "@/components/illustrations";
import { Star8 } from "@/components/illustrations-star";
import { useApp } from "@/components/providers";
import { Loading, useTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { CategoryNode } from "@/lib/types";

export default function CatalogPage() {
  const { t, lang } = useApp();
  useTitle(t("catalog"));
  const [tree, setTree] = useState<CategoryNode[] | null>(null);
  useEffect(() => {
    api<CategoryNode[]>("/categories").then(setTree).catch(() => setTree([]));
  }, [lang]);
  if (!tree) return <Loading />;
  return (
    <div className="space-y-5 md:space-y-7">
      <h1 className="font-display text-2xl font-bold tracking-tight md:text-[32px]">{t("catalog")}</h1>
      {tree.map((root, r) => (
        <section key={root.id} className="animate-fade-up rounded-[28px] bg-white p-4 shadow-card md:p-6" style={{ animationDelay: `${r * 60}ms` }}>
          <Link href={`/c/${root.slug}`} className="group mb-4 flex items-center gap-2.5 text-lg font-bold tracking-tight hover:text-brand md:text-xl">
            <Star8 className="h-5 w-5 text-brand" filled />
            {root.name}
            <IconChevron className="h-4 w-4 text-zinc-400 transition group-hover:translate-x-0.5 group-hover:text-brand" />
          </Link>
          <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4 md:grid-cols-6 md:gap-4 lg:grid-cols-8">
            {(root.children.length ? root.children : [root]).map((c) => (
              <Link key={c.id} href={`/c/${c.slug}`} className="group">
                <div className="aspect-square overflow-hidden rounded-2xl transition duration-300 group-hover:-translate-y-1 group-hover:shadow-lift">
                  <Illustration category={c.slug} className="transition duration-500 group-hover:scale-110" />
                </div>
                <p className="mt-2 text-center text-[13px] font-medium leading-4 text-ink group-hover:text-brand md:text-sm">{c.name}</p>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
