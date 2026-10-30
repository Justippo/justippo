interface IconProps {
  readonly name: string;
  readonly size?: number;
  readonly className?: string;
  readonly "aria-hidden"?: boolean;
  readonly "aria-label"?: string;
}

export function Icon({
  name,
  size = 24,
  className = "",
  "aria-hidden": ariaHidden = true,
  "aria-label": ariaLabel,
}: Readonly<IconProps>) {
  return (
    <svg
      width={size}
      height={size}
      aria-hidden={ariaHidden}
      aria-label={ariaLabel}
      className={className}
      role={ariaLabel ? "img" : undefined}
    >
      <use href={`/icons.svg#${name}`} />
    </svg>
  );
}
