"use client";

import styles from "./NavigationBar.module.css";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/atoms";
import { Menu, User, Sun, Moon, Monitor } from "lucide-react";
import { useInterfaceLanguage } from "@/hooks/useInterfaceLanguage";
import { useT } from "@/hooks/useT";
import { useTheme } from "@/hooks/useTheme";

interface NavigationBarProps {
  readonly onMenuToggle?: () => void;
}

export function NavigationBar({ onMenuToggle }: Readonly<NavigationBarProps>) {
  const { isAuthenticated, logout } = useAuth();
  const { language, onLanguageChange } = useInterfaceLanguage();
  const { t } = useT();
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
    <header className={styles.nav}>
      <a href="#main-content" className={styles.skipLink}>
        {t("nav.skip_content")}
      </a>
      <div className={styles.inner}>
        <div className={styles.left}>
          <button
            type="button"
            className={styles.menuButton}
            onClick={onMenuToggle}
            aria-label={t("nav.toggle_menu")}
          >
            <Menu size={24} aria-hidden="true" />
          </button>
          <Link
            href={isAuthenticated ? "/dashboard" : "/"}
            className={styles.brand}
            aria-label={t("nav.logo_aria")}
          >
            EvidenceEU
          </Link>
        </div>
        <div className={styles.right}>
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
            className={styles.themeButton}
            onClick={toggleTheme}
            aria-label={getThemeAriaLabel()}
            data-testid="theme-toggle"
          >
            {getThemeIcon()}
          </button>
          {isAuthenticated && (
            <Link
              href="/settings"
              className={styles.accountLink}
              aria-label={t("nav.account_settings")}
            >
              <User size={18} aria-hidden="true" />
            </Link>
          )}
          {isAuthenticated ? (
            <Button variant="ghost" size="sm" onClick={logout} data-testid="nav-btn-logout">
              {t("nav.sign_out")}
            </Button>
          ) : (
            <Link href="/login" className={styles.signInButton} data-testid="nav-btn-login">
              {t("nav.sign_in")}
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
