"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Listing } from "@/components/listing";
import { useTitle } from "@/components/ui";

function SearchInner() {
  const q = useSearchParams().get("q") ?? "";
  useTitle(q ? `«${q}»` : null);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">«{q}»</h1>
      <Listing query={q} />
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense>
      <SearchInner />
    </Suspense>
  );
}
