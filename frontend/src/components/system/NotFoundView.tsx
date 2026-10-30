import Link from "next/link";
import { FileQuestion } from "lucide-react";
import styles from "./NotFoundView.module.css";
import { NOT_FOUND_COPY } from "@/data/mockData";

interface NotFoundViewProps {
  readonly className?: string;
}

export function NotFoundView({ className = "" }: Readonly<NotFoundViewProps>) {
  return (
    <div className={`${styles.container} ${className}`} data-testid="not-found-view">
      <div className={styles.iconWrap} aria-hidden="true">
        <FileQuestion className={styles.icon} />
      </div>
      <h1 className={styles.title}>{NOT_FOUND_COPY.title}</h1>
      <p className={styles.description}>{NOT_FOUND_COPY.description}</p>
      <Link href={NOT_FOUND_COPY.homeHref} className={styles.primaryAction}>
        {NOT_FOUND_COPY.homeLabel}
      </Link>
    </div>
  );
}
