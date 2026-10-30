import styles from "./Tag.module.css";

interface TagProps {
  readonly children: React.ReactNode;
  readonly variant?: "default" | "primary" | "success" | "error";
  readonly onRemove?: () => void;
  readonly className?: string;
}

export function Tag({
  children,
  variant = "default",
  onRemove,
  className = "",
}: Readonly<TagProps>) {
  return (
    <span className={`${styles.tag} ${styles[variant]} ${className}`}>
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove"
          className={styles.removeButton}
        >
          &times;
        </button>
      )}
    </span>
  );
}
