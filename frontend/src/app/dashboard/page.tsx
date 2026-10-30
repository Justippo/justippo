"use client";

import { RequireAuth } from "@/components/shell";
import { DashboardView } from "@/components/dashboard";

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardView />
    </RequireAuth>
  );
}
