"use client";

import { Suspense } from "react";
import { LoginView } from "@/components/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={<div role="status" aria-label="Loading" />}>
      <LoginView />
    </Suspense>
  );
}
