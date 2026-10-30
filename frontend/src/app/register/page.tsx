"use client";

import { Suspense } from "react";
import { RegisterView } from "@/components/auth";

export default function RegisterPage() {
  return (
    <Suspense fallback={<div role="status" aria-label="Loading" />}>
      <RegisterView />
    </Suspense>
  );
}
