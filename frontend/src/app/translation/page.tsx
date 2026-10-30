"use client";

import { RequireAuth } from "@/components/shell";
import { TranslationView } from "@/components/translation";

export default function TranslationPage() {
  return (
    <RequireAuth>
      <TranslationView />
    </RequireAuth>
  );
}
