"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Listing } from "@/components/listing";

function SearchInner() {
  const q = useSearchParams().get("q") ?? "";
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">«{q}»</h1>
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
