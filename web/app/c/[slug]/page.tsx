"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Listing } from "@/components/listing";
import { useApp } from "@/components/providers";
import { api } from "@/lib/api";

type Cat = { slug: string; name: string; breadcrumbs: { slug: string; name: string }[]; children: { slug: string; name: string }[] };

export default function CategoryPage() {
  const { slug } = useParams<{ slug: string }>();
  const { lang } = useApp();
  const [cat, setCat] = useState<Cat | null>(null);
  useEffect(() => {
    api<Cat>(`/categories/${slug}`).then(setCat).catch(() => setCat(null));
  }, [slug, lang]);

  return (
    <div className="space-y-4">
      <nav className="text-sm text-gray-500">
        <Link href="/" className="hover:text-brand">⌂</Link>
        {cat?.breadcrumbs.map((b) => (
          <span key={b.slug}> / <Link href={`/c/${b.slug}`} className="hover:text-brand">{b.name}</Link></span>
        ))}
      </nav>
      <h1 className="text-2xl font-extrabold tracking-tight">{cat?.name ?? ""}</h1>
      {cat && cat.children.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {cat.children.map((c) => (
            <Link key={c.slug} href={`/c/${c.slug}`} className="rounded-full bg-white px-4 py-1.5 text-sm shadow-sm hover:text-brand">{c.name}</Link>
          ))}
        </div>
      ) : null}
      <Suspense>
        <Listing category={slug} />
      </Suspense>
    </div>
  );
}
