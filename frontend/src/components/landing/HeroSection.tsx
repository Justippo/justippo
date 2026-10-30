import styles from "./HeroSection.module.css";

interface HeroSectionProps {
  readonly headline: string;
  readonly subheadline: string;
  readonly primaryCta: string;
  readonly primaryHref: string;
  readonly secondaryCta: string;
  readonly secondaryHref: string;
}

export function HeroSection({
  headline,
  subheadline,
  primaryCta,
  primaryHref,
  secondaryCta,
  secondaryHref,
}: Readonly<HeroSectionProps>) {
  return (
    <section className={styles.hero} aria-label="Hero">
      <div className={styles.imageWrap}>
        <picture>
          <source
            type="image/avif"
            srcSet="/assets/hero-640.avif 640w, /assets/hero-1280.avif 1280w, /assets/hero-1920.avif 1920w"
            sizes="100vw"
          />
          <source
            type="image/webp"
            srcSet="/assets/hero-640.webp 640w, /assets/hero-1280.webp 1280w, /assets/hero-1920.webp 1920w"
            sizes="100vw"
          />
          {/* Static export cannot optimize Next Image at request time. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            {...{ fetchPriority: "high" }}
            src="/assets/hero.jpg"
            alt=""
            width="1920"
            height="1280"
            loading="eager"
            decoding="async"
            className={styles.heroImage}
          />
        </picture>
        <div className={styles.imageOverlay} aria-hidden="true" />
      </div>
      <div className={styles.content}>
        <h1 className={styles.headline}>{headline}</h1>
        <p className={styles.subheadline}>{subheadline}</p>
        <div className={styles.cta}>
          <a href={primaryHref} className={styles.primaryCta}>
            {primaryCta}
          </a>
          <a href={secondaryHref} className={styles.secondaryCta}>
            {secondaryCta}
          </a>
        </div>
      </div>
    </section>
  );
}
