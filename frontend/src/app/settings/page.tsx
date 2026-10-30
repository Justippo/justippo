"use client";

import { RequireAuth } from "@/components/shell";
import { SettingsView } from "@/components/settings";

export default function SettingsPage() {
  return (
    <RequireAuth>
      <SettingsView />
    </RequireAuth>
  );
}
