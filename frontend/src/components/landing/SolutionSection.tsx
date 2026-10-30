import { Globe, Search, Shield, type LucideIcon } from "lucide-react";
import styles from "./SolutionSection.module.css";

interface Pillar {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly icon: "Search" | "Globe" | "Shield";
}

interface SolutionSectionProps {
  readonly pillars: readonly Pillar[];
}

const ICONS: Record<Pillar["icon"], LucideIcon> = {
  Search,
  Globe,
  Shield,
};

export function SolutionSection({ pillars }: Readonly<SolutionSectionProps>) {
  return (
    <section id="how-it-works" className={styles.section} aria-label="Solution pillars">
      <div className={styles.inner}>
        <h2 className={styles.heading}>One platform. Three pillars.</h2>
        <div className={styles.grid}>
          {pillars.map((pillar) => {
            const Icon = ICONS[pillar.icon];
            return (
              <article key={pillar.id} className={styles.card}>
                <span className={styles.icon} aria-hidden="true">
                  <Icon size={28} strokeWidth={1.75} />
                </span>
                <h3 className={styles.title}>{pillar.title}</h3>
                <p className={styles.description}>{pillar.description}</p>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
