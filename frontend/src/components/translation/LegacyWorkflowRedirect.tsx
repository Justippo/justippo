"use client";

import { useLegacyWorkflowRedirect } from "@/hooks/useLegacyWorkflowRedirect";
import styles from "./TranslationView.module.css";

interface LegacyWorkflowRedirectProps {
  readonly destination: string;
}

export function LegacyWorkflowRedirect({ destination }: Readonly<LegacyWorkflowRedirectProps>) {
  useLegacyWorkflowRedirect(destination);

  return (
    <div className={styles.checking} role="status">
      Opening Translate…
    </div>
  );
}
