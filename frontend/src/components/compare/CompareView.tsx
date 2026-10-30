"use client";

import { GitCompare } from "lucide-react";
import styles from "./CompareView.module.css";
import { useCompareView, type CompareViewState } from "@/hooks/useCompareView";
import { Badge, Button, Skeleton, SkeletonText } from "@/components/atoms";
import { Columns2, AlignJustify } from "lucide-react";

interface CompareViewProps {
  readonly className?: string;
  readonly forcedState?: CompareViewState;
}

const BLOCK_LABELS = {
  unchanged: "Unchanged",
  added: "Added",
  removed: "Removed",
  modified: "Modified",
} as const;

function blockBadgeVariant(type: keyof typeof BLOCK_LABELS) {
  if (type === "unchanged") return "default";
  if (type === "added") return "success";
  if (type === "removed") return "error";
  return "warning";
}

export function CompareView({ className = "", forcedState }: Readonly<CompareViewProps>) {
  const compare = useCompareView({ forcedState });

  if (compare.viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`}>
        <Skeleton height="1.5rem" width="240px" />
        <div className={styles.diffList} role="status" aria-label="Computing differences">
          {[1, 2, 3].map((i) => (
            <div key={i} className={`${styles.block} ${styles.unchanged}`}>
              <Skeleton height="1rem" width="64px" borderRadius="var(--stitch-radius-sm)" />
              <SkeletonText lines={2} lastLineWidth="65%" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (compare.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.centerState} role="alert">
          <h1 className={styles.heading}>Compare documents</h1>
          <p className={styles.stateText} data-testid="compare-error">
            {compare.error}
          </p>
          <Button variant="primary" onClick={compare.reset}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (compare.viewState === "success" && compare.blocks.length > 0) {
    const isSideBySide = compare.viewMode === "side-by-side";
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.header}>
          <div className={styles.headerRow}>
            <h1 className={styles.heading}>Document comparison</h1>
            <button
              type="button"
              className={styles.toggleButton}
              onClick={compare.onToggleViewMode}
              aria-label={isSideBySide ? "Switch to unified view" : "Switch to side-by-side view"}
              data-testid="compare-toggle-view"
            >
              {isSideBySide ? <AlignJustify size={16} /> : <Columns2 size={16} />}
              {isSideBySide ? "Unified" : "Side by side"}
            </button>
          </div>
          {compare.filename && (
            <p className={styles.filename} data-testid="compare-filename">
              {compare.filename}
            </p>
          )}
        </div>
        <div className={isSideBySide ? styles.diffListSideBySide : styles.diffList}>
          {compare.blocks.map((block, index) => (
            <div
              key={index}
              className={`${styles.block} ${styles[block.type]} ${
                isSideBySide ? styles.blockSideBySide : ""
              }`}
              data-testid="compare-block"
              tabIndex={0}
            >
              <Badge
                variant={blockBadgeVariant(block.type)}
                data-testid={`compare-badge-${block.type}`}
              >
                {BLOCK_LABELS[block.type]}
              </Badge>
              {isSideBySide ? (
                <div className={styles.sideBySideContent}>
                  <p className={styles.blockText}>{block.sourceText}</p>
                  {block.targetText ? (
                    <p className={styles.targetText}>{block.targetText}</p>
                  ) : (
                    <p
                      className={`${styles.blockText} ${styles.placeholderText}`}
                      aria-hidden="true"
                    >
                      —
                    </p>
                  )}
                </div>
              ) : (
                <>
                  <p className={styles.blockText}>{block.sourceText}</p>
                  {block.targetText && <p className={styles.targetText}>{block.targetText}</p>}
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.centerState}>
        <h1 className={styles.heading}>Compare documents</h1>
        <div className={styles.emptyIcon} aria-hidden="true">
          <GitCompare size="1em" strokeWidth={1.5} />
        </div>
        <p className={styles.stateText}>
          No documents selected for comparison. Upload and translate a document first, then return
          here to see a side-by-side diff.
        </p>
        <a href="/translation?start=upload" className={styles.stateAction}>
          Translate a document
        </a>
      </div>
    </div>
  );
}
