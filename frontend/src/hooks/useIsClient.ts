"use client";

import { useEffect, useState } from "react";

/**
 * Returns false during SSR/static export and the first render, then true after
 * hydration. Lets components gate browser-only logic (sessionStorage, query
 * params) without tripping hydration mismatches.
 */
export function useIsClient(): boolean {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  return isClient;
}
