"use client";

import { Suspense } from "react";
import { SearchView } from "@/components/search";

export default function SearchPage() {
  return (
    <Suspense fallback={<div role="status" aria-label="Loading" />}>
      <SearchView />
    </Suspense>
  );
}
