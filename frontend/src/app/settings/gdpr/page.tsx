"use client";

import { SettingsView } from "@/components/settings";
import { RequireAuth } from "@/components/shell";

export default function GdprSettingsPage() {
  return (
    <RequireAuth>
      <SettingsView initialSection="compliance" />
    </RequireAuth>
  );
}
