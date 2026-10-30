import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import styles from "./ErrorView.module.css";
import { ERROR_PAGE_COPY } from "@/data/mockData";
import { Button } from "@/components/atoms";

interface ErrorViewProps {
  readonly className?: string;
  readonly onRetry?: () => void;
}

export function ErrorView({ className = "", onRetry }: Readonly<ErrorViewProps>) {
  return (
    <div className={`${styles.container} ${className}`} data-testid="error-view" role="alert">
      <div className={styles.iconWrap} aria-hidden="true">
        <AlertTriangle className={styles.icon} />
      </div>
      <h1 className={styles.title}>{ERROR_PAGE_COPY.title}</h1>
      <p className={styles.description}>{ERROR_PAGE_COPY.description}</p>
      <div className={styles.actions}>
        {onRetry && (
          <Button variant="primary" onClick={onRetry} data-testid="error-retry">
            {ERROR_PAGE_COPY.retryLabel}
          </Button>
        )}
        <Link href={ERROR_PAGE_COPY.homeHref} className={styles.secondaryAction}>
          {ERROR_PAGE_COPY.homeLabel}
        </Link>
      </div>
    </div>
  );
}
