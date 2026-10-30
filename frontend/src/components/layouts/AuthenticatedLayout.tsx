"use client";

import styles from "./AuthenticatedLayout.module.css";
import { NavigationBar } from "@/components/shell/NavigationBar";
import { Sidebar } from "@/components/shell/Sidebar";
import { Footer } from "@/components/shell/Footer";
import { BottomNav } from "@/components/shell/BottomNav";
import { useSidebarState } from "@/hooks/useSidebarState";

interface AuthenticatedLayoutProps {
  readonly children: React.ReactNode;
}

export function AuthenticatedLayout({ children }: Readonly<AuthenticatedLayoutProps>) {
  const { isOpen, toggle, close } = useSidebarState();

  return (
    <div className={styles.shell}>
      <NavigationBar onMenuToggle={toggle} />
      <div className={styles.body}>
        <Sidebar isOpen={isOpen} onClose={close} />
        <main id="main-content" className={styles.main}>
          <div className={styles.content}>{children}</div>
        </main>
      </div>
      <Footer />
      <BottomNav />
      <div
        aria-live="polite"
        aria-atomic="false"
        className={styles.srOnly}
        id="sse-announcements"
      />
    </div>
  );
}
