"use client";

import styles from "./BottomNav.module.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { usePrimaryNavigation } from "@/hooks/usePrimaryNavigation";
import { useT } from "@/hooks/useT";

export function BottomNav() {
  const { isAuthenticated } = useAuth();
  const items = usePrimaryNavigation(isAuthenticated);
  const { t } = useT();
  const pathname = usePathname() ?? "/";

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <nav className={styles.bottomNav} aria-label={t("nav.mobile")}>
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`${styles.item} ${isActive(item.href) ? styles.active : ""}`}
          aria-current={isActive(item.href) ? "page" : undefined}
        >
          <span className={styles.label}>{item.label}</span>
        </Link>
      ))}
    </nav>
  );
}
