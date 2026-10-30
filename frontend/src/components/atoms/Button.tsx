import styles from "./Button.module.css";

interface ButtonProps {
  readonly children: React.ReactNode;
  readonly variant?: "primary" | "secondary" | "error" | "ghost";
  readonly size?: "sm" | "md" | "lg";
  readonly disabled?: boolean;
  readonly type?: "button" | "submit" | "reset";
  readonly onClick?: () => void;
  readonly className?: string;
  readonly "aria-label"?: string;
  readonly "data-testid"?: string;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  type = "button",
  onClick,
  className = "",
  "aria-label": ariaLabel,
  "data-testid": testId,
}: Readonly<ButtonProps>) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      data-testid={testId}
      className={`${styles.button} ${styles[variant]} ${styles[size]} ${className}`}
    >
      {children}
    </button>
  );
}
