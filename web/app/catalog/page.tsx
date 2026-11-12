"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Illustration } from "@/components/illustrations";
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
    <div className="space-y-8">
      <h1 className="text-2xl font-bold tracking-tight">{t("catalog")}</h1>
      {tree.map((root, r) => (
        <section key={root.id} className="animate-fade-up" style={{ animationDelay: `${r * 60}ms` }}>
          <Link href={`/c/${root.slug}`} className="mb-3 inline-block text-lg font-semibold hover:text-brand">{root.name}</Link>
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
            {(root.children.length ? root.children : [root]).map((c) => (
              <Link key={c.id} href={`/c/${c.slug}`} className="group">
                <div className="aspect-square overflow-hidden rounded-2xl transition duration-300 group-hover:-translate-y-0.5 group-hover:shadow-md">
                  <Illustration category={c.slug} className="transition duration-300 group-hover:scale-105" />
                </div>
                <p className="mt-1.5 text-center text-sm text-zinc-700">{c.name}</p>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
