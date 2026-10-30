"use client";

import styles from "./Sidebar.module.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { usePrimaryNavigation } from "@/hooks/usePrimaryNavigation";
import { useIsMobile } from "@/hooks/useIsMobile";
import { useT } from "@/hooks/useT";

interface SidebarProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: Readonly<SidebarProps>) {
  const { isAuthenticated } = useAuth();
  const navigationItems = usePrimaryNavigation(isAuthenticated);
  const { t } = useT();
  const isMobile = useIsMobile();
  // Active route indicator — derived from the current pathname so the sidebar
  // shows which section the user is on (background highlight + left accent).
  const pathname = usePathname() ?? "/";

  const isHidden = isMobile && !isOpen;

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <>
      {isOpen && <div className={styles.overlay} onClick={onClose} aria-hidden="true" />}
      <aside
        className={`${styles.sidebar} ${isOpen ? styles.open : ""}`}
        aria-label={t("nav.sidebar")}
      >
        <nav className={styles.nav} aria-hidden={isHidden}>
          {navigationItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.link} ${isActive(item.href) ? styles.active : ""}`}
              tabIndex={isHidden ? -1 : undefined}
              onClick={onClose}
              aria-current={isActive(item.href) ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
    </>
  );
}
