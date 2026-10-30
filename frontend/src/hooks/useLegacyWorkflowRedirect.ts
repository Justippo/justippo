"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useLegacyWorkflowRedirect(destination: string): void {
  const router = useRouter();

  useEffect(() => {
    router.replace(destination);
  }, [destination, router]);
}
