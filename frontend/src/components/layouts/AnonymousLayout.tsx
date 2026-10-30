"use client";

import styles from "./AnonymousLayout.module.css";
import Link from "next/link";
import { Sun, Moon, Monitor } from "lucide-react";
import { useT } from "@/hooks/useT";
import { useInterfaceLanguage } from "@/hooks/useInterfaceLanguage";
import { useTheme } from "@/hooks/useTheme";

interface AnonymousLayoutProps {
  readonly children: React.ReactNode;
}

export function AnonymousLayout({ children }: Readonly<AnonymousLayoutProps>) {
  const { t } = useT();
  const { language, onLanguageChange } = useInterfaceLanguage();
  const { theme, resolvedTheme, toggleTheme } = useTheme();

  const getThemeIcon = () => {
    if (theme === "system") return <Monitor size={18} aria-hidden="true" />;
    if (resolvedTheme === "dark") return <Moon size={18} aria-hidden="true" />;
    return <Sun size={18} aria-hidden="true" />;
  };

  const getThemeAriaLabel = () => {
    if (theme === "system") return t("nav.theme_system");
    if (resolvedTheme === "dark") return t("nav.theme_dark");
    return t("nav.theme_light");
  };

  return (
    <div className={styles.shell}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Link href="/" className={styles.brand} aria-label={t("nav.logo_aria")}>
            EvidenceEU
          </Link>
          <nav className={styles.navLinks} aria-label={t("nav.public")}>
            <Link href="/public" className={styles.navLink}>
              {t("nav.corpus")}
            </Link>
          </nav>
          <div className={styles.anonRight}>
            <label className={styles.languageLabel}>
              <span className={styles.srOnly}>{t("nav.lang_switch")}</span>
              <select
                data-testid="interface-language-select"
                aria-label={t("nav.lang_switch")}
                value={language}
                onChange={onLanguageChange}
                className={styles.languageSelect}
              >
                <option value="en">EN</option>
                <option value="de">DE</option>
                <option value="fr">FR</option>
              </select>
            </label>
            <button
              type="button"
              className={styles.themeToggle}
              onClick={toggleTheme}
              aria-label={getThemeAriaLabel()}
              data-testid="theme-toggle"
            >
              {getThemeIcon()}
            </button>
            <Link href="/login" className={styles.signInLink}>
              {t("nav.sign_in")}
            </Link>
          </div>
        </div>
      </header>
      <main id="main-content" className={styles.main}>
        {children}
      </main>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span className={styles.footerBrand}>{t("footer.tagline")}</span>
          <nav className={styles.footerLinks} aria-label={t("nav.legal")}>
            <Link href="/privacy" className={styles.footerLink}>
              {t("footer.privacy")}
            </Link>
            <span className={styles.footerLink} aria-hidden="true">
              ·
            </span>
            <Link href="/terms" className={styles.footerLink}>
              {t("footer.terms")}
            </Link>
            <span className={styles.footerLink} aria-hidden="true">
              ·
            </span>
            <Link href="/settings/gdpr" className={styles.footerLink}>
              {t("nav.gdpr")}
            </Link>
          </nav>
          <p className={styles.footerCopy}>&copy; 2026 Quantic MSSE Capstone</p>
        </div>
      </footer>
    </div>
  );
}
