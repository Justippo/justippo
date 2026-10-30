import styles from "./Spinner.module.css";

interface SpinnerProps {
  readonly size?: "sm" | "md" | "lg";
  readonly className?: string;
  readonly "aria-label"?: string;
}

export function Spinner({
  size = "md",
  className = "",
  "aria-label": ariaLabel = "Loading",
}: Readonly<SpinnerProps>) {
  return (
    <span
      role="status"
      aria-label={ariaLabel}
      className={`${styles.spinner} ${styles[size]} ${className}`}
    />
  );
}
