"use client";

import { SettingsView } from "@/components/settings";
import { RequireAuth } from "@/components/shell";

export default function LanguageSettingsPage() {
  return (
    <RequireAuth>
      <SettingsView initialSection="profile" />
    </RequireAuth>
  );
}
