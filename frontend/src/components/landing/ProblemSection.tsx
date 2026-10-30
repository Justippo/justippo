import styles from "./ProblemSection.module.css";

interface ProblemSectionProps {
  readonly headline: string;
  readonly points: readonly string[];
}

export function ProblemSection({ headline, points }: Readonly<ProblemSectionProps>) {
  return (
    <section className={styles.section} aria-label="The problem">
      <div className={styles.inner}>
        <h2 className={styles.headline}>{headline}</h2>
        <ul className={styles.list}>
          {points.map((point) => (
            <li key={point} className={styles.item}>
              {point}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
