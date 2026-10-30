import styles from "./FeatureSection.module.css";

interface Feature {
  readonly id: string;
  readonly headline: string;
  readonly description: string;
  readonly stat: string;
  readonly statLabel: string;
}

interface FeatureSectionProps {
  readonly features: readonly Feature[];
}

export function FeatureSection({ features }: Readonly<FeatureSectionProps>) {
  return (
    <section className={styles.section} aria-label="Platform features">
      <div className={styles.grid}>
        {features.map((feature) => (
          <article key={feature.id} className={styles.card}>
            <div className={styles.statBlock}>
              <span className={styles.stat}>{feature.stat}</span>
              <span className={styles.statLabel}>{feature.statLabel}</span>
            </div>
            <h2 className={styles.headline}>{feature.headline}</h2>
            <p className={styles.description}>{feature.description}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
