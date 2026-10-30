"use client";

import { ExternalLink } from "lucide-react";
import { Spinner } from "@/components/atoms";
import { useCitationAccess } from "@/hooks/useCitationAccess";
import styles from "./CitationAccessView.module.css";

export function CitationAccessView() {
  const citation = useCitationAccess();

  if (citation.isLoading) {
    return (
      <main className={styles.page}>
        <div className={styles.card} role="status" aria-label="Checking session">
          <Spinner size="md" />
        </div>
      </main>
    );
  }

  if (!citation.isValid || !citation.sourceUrl) {
    return (
      <main className={styles.page}>
        <div className={styles.card} role="alert">
          <h1 className={styles.heading}>Citation unavailable</h1>
          <p className={styles.body}>This citation does not point to a verified official source.</p>
          <a className={styles.secondaryAction} href="/search">
            Return to search
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <p className={styles.eyebrow}>Verified EUR-Lex citation</p>
        <h1 className={styles.heading}>{citation.sourceTitle}</h1>
        {citation.isAuthenticated ? (
          <>
            <p className={styles.body}>Continue to EUR-Lex to read the full cited document.</p>
            <a
              className={styles.primaryAction}
              href={citation.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open official document <ExternalLink size={16} aria-hidden="true" />
            </a>
          </>
        ) : (
          <>
            <p className={styles.body}>
              Sign in or create an account to read the full cited document.
            </p>
            <div className={styles.actions}>
              <a className={styles.primaryAction} href={citation.signInHref}>
                Sign in
              </a>
              <a className={styles.secondaryAction} href={citation.signUpHref}>
                Create account
              </a>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
