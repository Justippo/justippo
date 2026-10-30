import styles from "./Skeleton.module.css";

interface SkeletonProps {
  readonly width?: string;
  readonly height?: string;
  readonly borderRadius?: string;
  readonly className?: string;
}

export function Skeleton({
  width = "100%",
  height = "1rem",
  borderRadius,
  className = "",
}: Readonly<SkeletonProps>) {
  return (
    <div
      className={`${styles.skeleton} ${className}`}
      style={{ width, height, borderRadius }}
      aria-hidden="true"
    />
  );
}

interface SkeletonTextProps {
  readonly lines?: number;
  readonly lastLineWidth?: string;
  readonly className?: string;
}

export function SkeletonText({
  lines = 3,
  lastLineWidth = "60%",
  className = "",
}: Readonly<SkeletonTextProps>) {
  return (
    <div className={`${styles.textGroup} ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height="0.875rem" width={i === lines - 1 ? lastLineWidth : "100%"} />
      ))}
    </div>
  );
}

interface SkeletonCardProps {
  readonly className?: string;
}

export function SkeletonCard({ className = "" }: Readonly<SkeletonCardProps>) {
  return (
    <div className={`${styles.card} ${className}`} aria-hidden="true">
      <Skeleton height="1rem" width="40%" />
      <SkeletonText lines={2} />
    </div>
  );
}
