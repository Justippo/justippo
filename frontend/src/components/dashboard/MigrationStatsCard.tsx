"use client";

import styles from "./MigrationStatsCard.module.css";
import { useMigrationStats, type MigrationStatsState } from "@/hooks/useMigrationStats";
import { Badge, Button, Skeleton, SkeletonCard } from "@/components/atoms";
import { getCountryFlagEmoji, getLanguageSuggestionForCountry } from "@/lib/eurostat";
import type { MigrationStats } from "@/lib/eurostat";
import { Globe } from "lucide-react";

interface MigrationStatsCardProps {
  readonly className?: string;
  readonly forcedState?: MigrationStatsState;
  readonly forcedStats?: MigrationStats | null;
}

function formatCount(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(0)}K`;
  }
  return String(count);
}

function MigrationStatsSkeleton() {
  return (
    <div className={styles.skeletonLayout} aria-hidden="true">
      <Skeleton height="1.5rem" width="200px" />
      <SkeletonCard />
      <Skeleton height="0.875rem" width="150px" />
    </div>
  );
}

export function MigrationStatsCard({
  className = "",
  forcedState,
  forcedStats,
}: Readonly<MigrationStatsCardProps>) {
  const hook = useMigrationStats();
  const viewState = forcedState ?? hook.viewState;
  const stats = forcedStats ?? hook.stats;

  if (viewState === "loading") {
    return (
      <section
        className={`${styles.container} ${className}`}
        aria-busy="true"
        aria-label="Loading migration statistics"
      >
        <MigrationStatsSkeleton />
      </section>
    );
  }

  if (viewState === "error") {
    return (
      <section className={`${styles.container} ${className}`} role="alert">
        <div className={styles.errorState}>
          <p className={styles.errorText}>Migration data unavailable</p>
          <Button variant="primary" onClick={hook.retry}>
            Retry
          </Button>
        </div>
      </section>
    );
  }

  if (viewState === "empty" || !stats) {
    return (
      <section className={`${styles.container} ${className}`}>
        <div className={styles.emptyState}>
          <Globe aria-hidden="true" className={styles.emptyIcon} />
          <p className={styles.emptyText}>Migration statistics unavailable</p>
        </div>
      </section>
    );
  }

  return (
    <section className={`${styles.container} ${className}`} aria-labelledby="migration-stats-title">
      <div className={styles.header}>
        <Globe aria-hidden="true" className={styles.headerIcon} />
        <h2 id="migration-stats-title" className={styles.title}>
          Migration Context
        </h2>
      </div>

      <p className={styles.headline}>
        <strong>{formatCount(stats.total)}</strong> non-EU citizens and stateless persons in the EU
      </p>

      <table className={styles.table}>
        <caption className={styles.caption}>
          Top EU member states by non-EU citizen population
        </caption>
        <thead>
          <tr>
            <th scope="col">Country</th>
            <th scope="col">Population</th>
            <th scope="col">Translation</th>
          </tr>
        </thead>
        <tbody>
          {stats.countries.map((country) => (
            <tr key={country.code}>
              <th scope="row">
                <span aria-label={`${country.label} flag`} role="img">
                  {getCountryFlagEmoji(country.code)}
                </span>{" "}
                {country.label}
              </th>
              <td>{formatCount(country.count)}</td>
              <td>
                <Badge variant="info">
                  {getLanguageSuggestionForCountry(country.code).toUpperCase()}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className={styles.attribution}>
        Source:{" "}
        <a
          href="https://ec.europa.eu/eurostat/databrowser/view/migr_pop1ctz/default/table"
          target="_blank"
          rel="noreferrer"
          className={styles.sourceLink}
        >
          Eurostat, migr_pop1ctz{stats.year ? `, ${stats.year}` : ""}
        </a>
      </p>
    </section>
  );
}
