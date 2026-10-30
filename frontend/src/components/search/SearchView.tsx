"use client";

import styles from "./SearchView.module.css";
import { useSearchPage, type SearchPageState } from "@/hooks/useSearchPage";
import { Button, Badge } from "@/components/atoms";
import { Skeleton, SkeletonText } from "@/components/atoms";
import { ExternalLink } from "lucide-react";

interface SearchViewProps {
  readonly className?: string;
  readonly forcedState?: SearchPageState;
}

export function SearchView({ className = "", forcedState }: Readonly<SearchViewProps>) {
  const {
    viewState,
    corpusLabel,
    searchPlaceholder,
    emptyText,
    emptyHintSuffix,
    results,
    error,
    retry,
    query,
    setQuery,
    handleSubmit,
  } = useSearchPage({ forcedState });

  if (viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`} aria-busy="true" aria-label="Searching">
        <div className={styles.header}>
          <Skeleton height="2rem" width="12rem" />
        </div>
        <Skeleton height="3rem" />
        <SkeletonText lines={3} />
      </div>
    );
  }

  if (viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.header}>
          <Badge variant="info" data-testid="search-corpus-badge">
            {corpusLabel}
          </Badge>
        </div>
        <div className={styles.errorState} role="alert" data-testid="search-error-box">
          <p className={styles.errorText}>{error}</p>
          <span data-testid="search-retry">
            <Button variant="primary" size="sm" onClick={retry}>
              Retry
            </Button>
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.header}>
        <h1 className={styles.heading}>Search documents</h1>
        <Badge variant="info" data-testid="search-corpus-badge">
          {corpusLabel}
        </Badge>
      </div>

      <form onSubmit={handleSubmit} className={styles.searchForm} role="search">
        <input
          id="search-input"
          name="q"
          type="search"
          placeholder={searchPlaceholder}
          aria-label="Search query"
          className={styles.searchInput}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" variant="primary">
          Search
        </Button>
      </form>

      {viewState === "empty" && (
        <div className={styles.emptyState} data-testid="search-empty-state">
          <p className={styles.emptyText}>{emptyText}</p>
          {emptyHintSuffix && (
            <p className={styles.emptyHint}>
              <a href="/login" className={styles.signInLink}>
                Sign in
              </a>{" "}
              {emptyHintSuffix}
            </p>
          )}
        </div>
      )}

      {viewState === "success" && results.length === 0 && (
        <div className={styles.emptyState}>
          <p className={styles.emptyText}>No results found. Try different keywords.</p>
        </div>
      )}

      {viewState === "success" && results.length > 0 && (
        <div data-testid="search-answer">
          <ul
            className={styles.resultsList}
            aria-label="Search results"
            data-testid="search-source-list"
          >
            {results.map((result) => (
              <li
                key={result.id || result.chunk_id || `result-${result.rank}`}
                className={styles.resultCard}
                data-testid="search-source-card"
              >
                <div className={styles.resultHeader}>
                  <Badge variant="info">
                    {result.source_language?.toUpperCase() ||
                      (result.type === "world" ? "DE" : result.type)}
                  </Badge>
                  <Badge variant="success">Rank {result.rank}</Badge>
                </div>
                <p className={styles.resultText}>{result.text}</p>
                {result.citationHref && (
                  <a
                    href={result.citationHref}
                    className={styles.citationLink}
                    target={result.citationTarget}
                    rel={result.citationTarget ? "noopener noreferrer" : undefined}
                  >
                    View cited document <ExternalLink size={14} aria-hidden="true" />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
