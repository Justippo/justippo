"use client";

import { useState, useCallback } from "react";

interface SidebarState {
  readonly isOpen: boolean;
  readonly toggle: () => void;
  readonly close: () => void;
}

export function useSidebarState(): SidebarState {
  const [isOpen, setIsOpen] = useState(false);

  const toggle = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  return { isOpen, toggle, close };
}
