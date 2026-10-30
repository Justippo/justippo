import styles from "./CtaSection.module.css";

interface CtaSectionProps {
  readonly headline: string;
  readonly buttonLabel: string;
  readonly href: string;
}

export function CtaSection({ headline, buttonLabel, href }: Readonly<CtaSectionProps>) {
  return (
    <section className={styles.section} aria-label="Get started">
      <div className={styles.inner}>
        <h2 className={styles.headline}>{headline}</h2>
        <a href={href} className={styles.button}>
          {buttonLabel}
        </a>
      </div>
    </section>
  );
}
