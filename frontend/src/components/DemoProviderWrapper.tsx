"use client";

import { ConnectingOverlay } from "@/components/system";

interface DemoProviderWrapperProps {
  readonly children: React.ReactNode;
}

export function DemoProviderWrapper({ children }: Readonly<DemoProviderWrapperProps>) {
  return <ConnectingOverlay>{children}</ConnectingOverlay>;
}
