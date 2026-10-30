"use client";

import styles from "./PublicCorpusView.module.css";
import { usePublicCorpus, type PublicCorpusState } from "@/hooks/usePublicCorpus";
import { Badge } from "@/components/atoms";
import { Skeleton, SkeletonText } from "@/components/atoms";
import { BookOpen, Globe } from "lucide-react";

interface PublicCorpusViewProps {
  readonly className?: string;
  readonly forcedState?: PublicCorpusState;
}

export function PublicCorpusView({ className = "", forcedState }: Readonly<PublicCorpusViewProps>) {
  const corpus = usePublicCorpus({ forcedState });

  if (corpus.viewState === "loading") {
    return (
      <div
        className={`${styles.container} ${className}`}
        aria-busy="true"
        aria-label="Loading public corpus"
      >
        <Skeleton height="2.5rem" />
        <SkeletonText lines={2} />
        <Skeleton height="8rem" />
      </div>
    );
  }

  if (corpus.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.errorState} role="alert">
          <p className={styles.errorText}>{corpus.errorMessage}</p>
          <a href="/public" className={styles.retryLink}>
            Retry
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.hero}>
        <div className={styles.heroIcon} aria-hidden="true">
          <Globe size={28} />
        </div>
        <h1 className={styles.heading}>{corpus.meta.title}</h1>
        <p className={styles.description}>{corpus.meta.description}</p>
        <div className={styles.badges}>
          <Badge variant="info" data-testid="public-corpus-source">
            Powered by {corpus.meta.source}
          </Badge>
          <Badge variant="default">{corpus.meta.languages.join(" · ")}</Badge>
        </div>
      </div>

      {corpus.viewState === "empty" && (
        <div className={styles.emptyState}>
          <p className={styles.emptyText}>No public documents are available right now.</p>
          <a href="/search" className={styles.emptyAction}>
            Search the corpus
          </a>
        </div>
      )}

      {corpus.viewState === "success" && corpus.documents.length > 0 && (
        <section aria-labelledby="corpus-documents-heading">
          <h2 id="corpus-documents-heading" className={styles.sectionTitle}>
            Featured documents
          </h2>
          <ul className={styles.documentList}>
            {corpus.documents.map((doc) => (
              <li key={doc.id} className={styles.documentCard} data-testid="public-corpus-doc">
                <div className={styles.documentIcon} aria-hidden="true">
                  <BookOpen size={18} />
                </div>
                <div className={styles.documentBody}>
                  <h3 className={styles.documentTitle}>{doc.title}</h3>
                  <p className={styles.documentMeta}>
                    {doc.jurisdiction} · {doc.language} · {doc.category}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className={styles.cta}>
        <p className={styles.ctaText}>Need to search or translate your own documents?</p>
        <a href="/register" className={styles.ctaLink}>
          Create a free account
        </a>
      </div>
    </div>
  );
}
