import styles from "./Input.module.css";

interface InputProps {
  readonly id: string;
  readonly type?: "text" | "email" | "password" | "search" | "url";
  readonly value?: string;
  readonly placeholder?: string;
  readonly disabled?: boolean;
  readonly required?: boolean;
  readonly "aria-label"?: string;
  readonly "aria-describedby"?: string;
  readonly "data-testid"?: string;
  readonly onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  readonly onFocus?: () => void;
  readonly onBlur?: () => void;
  readonly className?: string;
}

export function Input({
  id,
  type = "text",
  value,
  placeholder,
  disabled = false,
  required = false,
  "aria-label": ariaLabel,
  "aria-describedby": ariaDescribedBy,
  "data-testid": testId,
  onChange,
  onFocus,
  onBlur,
  className = "",
}: Readonly<InputProps>) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      required={required}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
      data-testid={testId}
      onChange={onChange}
      onFocus={onFocus}
      onBlur={onBlur}
      className={`${styles.input} ${className}`}
    />
  );
}
