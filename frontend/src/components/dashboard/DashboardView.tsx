"use client";

import styles from "./DashboardView.module.css";
import { useDashboard, type DashboardViewState } from "@/hooks/useDashboard";
import { Badge, Button, Skeleton, SkeletonCard } from "@/components/atoms";
import { DASHBOARD_COPY } from "@/data/mockData";
import { Languages, Mail, Search, ShieldCheck } from "lucide-react";
import { MigrationStatsCard } from "@/components/dashboard/MigrationStatsCard";

interface DashboardViewProps {
  readonly className?: string;
  readonly forcedState?: DashboardViewState;
}

function DashboardSkeleton() {
  return (
    <div className={styles.skeletonLayout} aria-hidden="true">
      <div className={styles.statusSection}>
        <Skeleton height="1.125rem" width="120px" />
        <div className={styles.statusGrid}>
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
      <SkeletonCard />
    </div>
  );
}

export function DashboardView({ className = "", forcedState }: Readonly<DashboardViewProps>) {
  const dashboard = useDashboard({ forcedState });

  return (
    <div className={`${styles.container} ${className}`}>
      <h1 className={styles.heading}>Dashboard</h1>

      {dashboard.viewState === "loading" && (
        <div className={styles.loadingState} aria-busy="true" aria-label="Loading dashboard">
          <DashboardSkeleton />
        </div>
      )}

      {dashboard.viewState === "error" && (
        <div className={styles.errorState} role="alert">
          <p className={styles.errorText}>{dashboard.errorMessage}</p>
          <Button variant="primary" onClick={dashboard.retry}>
            Retry
          </Button>
        </div>
      )}

      {dashboard.viewState === "empty" && (
        <div className={styles.emptyState}>
          <h2 className={styles.sectionTitle}>{DASHBOARD_COPY.emptyTitle}</h2>
          <p className={styles.emptyText}>{DASHBOARD_COPY.emptyDescription}</p>
          <a href="/translation?start=upload" className={styles.emptyAction}>
            {DASHBOARD_COPY.emptyAction}
          </a>
        </div>
      )}

      {dashboard.viewState === "success" && (
        <>
          <section className={styles.privacySection} aria-labelledby="dashboard-privacy-title">
            <div className={styles.privacyCard}>
              <ShieldCheck aria-hidden="true" className={styles.privacyIcon} />
              <div>
                <h2 id="dashboard-privacy-title" className={styles.sectionTitle}>
                  {DASHBOARD_COPY.privacyTitle}
                </h2>
                <p className={styles.privacyText}>{DASHBOARD_COPY.privacyDescription}</p>
              </div>
            </div>
          </section>

          <section className={styles.quickSection}>
            <h2 className={styles.sectionTitle}>Quick actions</h2>
            <div className={styles.quickGrid}>
              <a href="/translation?start=upload" className={styles.quickAction}>
                <Languages aria-hidden="true" />
                Translate document
              </a>
              <a href="/search" className={styles.quickAction}>
                <Search aria-hidden="true" />
                Search
              </a>
              <a href="/exchange" className={styles.quickAction}>
                <Mail aria-hidden="true" />
                Exchange
              </a>
            </div>
          </section>

          <section className={styles.statusSection}>
            <h2 className={styles.sectionTitle}>System Status</h2>
            <div className={styles.statusGrid}>
              {dashboard.statusCards.map((card) => (
                <div key={card.label} className={styles.statusCard}>
                  <Badge variant={card.badgeVariant}>{card.badgeText}</Badge>
                  <span className={styles.statusLabel}>{card.label}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
