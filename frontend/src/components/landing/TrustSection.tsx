import { FileText, Lock, Users, type LucideIcon } from "lucide-react";
import styles from "./TrustSection.module.css";

interface TrustItem {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly icon: "Lock" | "FileText" | "Users";
}

interface TrustSectionProps {
  readonly items: readonly TrustItem[];
}

const ICONS: Record<TrustItem["icon"], LucideIcon> = {
  Lock,
  FileText,
  Users,
};

export function TrustSection({ items }: Readonly<TrustSectionProps>) {
  return (
    <section className={styles.section} aria-label="Trust and compliance">
      <h2 className={styles.heading}>Built for EU compliance</h2>
      <div className={styles.grid}>
        {items.map((item) => {
          const Icon = ICONS[item.icon];
          return (
            <div key={item.id} className={styles.card}>
              <span className={styles.icon} aria-hidden="true">
                <Icon size="1.25rem" strokeWidth={1.75} />
              </span>
              <h3 className={styles.cardTitle}>{item.title}</h3>
              <p className={styles.cardDescription}>{item.description}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
