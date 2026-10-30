import styles from "./Badge.module.css";

interface BadgeProps {
  readonly children: React.ReactNode;
  readonly variant?: "default" | "success" | "error" | "warning" | "info";
  readonly className?: string;
  readonly "data-testid"?: string;
}

export function Badge({
  children,
  variant = "default",
  className = "",
  "data-testid": testId,
}: Readonly<BadgeProps>) {
  return (
    <span className={`${styles.badge} ${styles[variant]} ${className}`} data-testid={testId}>
      {children}
    </span>
  );
}
