"use client";

import styles from "./Footer.module.css";
import { useT } from "@/hooks/useT";

export function Footer() {
  const { t } = useT();

  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <p className={styles.copy}>&copy; 2026 Quantic MSSE Capstone</p>
        <nav className={styles.links} aria-label={t("nav.footer")}>
          <a href="/privacy" className={styles.link}>
            {t("footer.privacy")}
          </a>
          <a href="/terms" className={styles.link}>
            {t("footer.terms")}
          </a>
          <a href="/settings" className={styles.link}>
            {t("nav.settings")}
          </a>
        </nav>
      </div>
    </footer>
  );
}
