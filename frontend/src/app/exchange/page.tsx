"use client";

import { RequireAuth } from "@/components/shell";
import { ExchangeView } from "@/components/exchange";

export default function ExchangePage() {
  return (
    <RequireAuth>
      <ExchangeView />
    </RequireAuth>
  );
}
