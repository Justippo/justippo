"use client";

import { SettingsView } from "@/components/settings";
import { RequireAuth } from "@/components/shell";

export default function SecuritySettingsPage() {
  return (
    <RequireAuth>
      <SettingsView initialSection="profile" />
    </RequireAuth>
  );
}
