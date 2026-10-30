"use client";

import { useMemo } from "react";
import { createTolgeeInstance } from "@/lib/tolgee";
import { getPreferredInterfaceLanguage } from "@/lib/interface-language";

export function useTolgeeClient(): ReturnType<typeof createTolgeeInstance> {
  return useMemo(() => createTolgeeInstance(getPreferredInterfaceLanguage()), []);
}
