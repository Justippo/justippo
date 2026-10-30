import type { LucideIcon } from "lucide-react";
import { Accessibility, Shield, User } from "lucide-react";
import styles from "./SettingsLayout.module.css";
import type { SettingsSectionId } from "@/data/mockData";

const SECTION_ICONS: Record<SettingsSectionId, LucideIcon> = {
  profile: User,
  compliance: Shield,
  accessibility: Accessibility,
};

interface SettingsSection {
  readonly id: SettingsSectionId;
  readonly label: string;
}

interface SettingsLayoutProps {
  readonly className?: string;
  readonly sections: readonly SettingsSection[];
  readonly activeSection: SettingsSectionId | null;
  readonly onSectionChange: (section: SettingsSectionId) => void;
  readonly children: React.ReactNode;
}

export function SettingsLayout({
  className = "",
  sections,
  activeSection,
  onSectionChange,
  children,
}: Readonly<SettingsLayoutProps>) {
  return (
    <div className={`${styles.layout} ${className}`} data-testid="settings-layout">
      <aside className={styles.sidebar} aria-label="Settings categories">
        <div className={styles.sidebarHeader}>
          <h1 className={styles.sidebarTitle}>Settings</h1>
          <p className={styles.sidebarSubtitle}>Workspace preferences</p>
        </div>
        <nav className={styles.nav}>
          {sections.map((section) => {
            const Icon = SECTION_ICONS[section.id];
            const isActive = activeSection === section.id;

            return (
              <button
                key={section.id}
                type="button"
                className={`${styles.navItem} ${isActive ? styles.navItemActive : ""}`}
                aria-current={isActive ? "page" : undefined}
                data-testid={`settings-nav-${section.id}`}
                onClick={() => onSectionChange(section.id)}
              >
                <Icon className={styles.navIcon} aria-hidden="true" />
                <span>{section.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <section className={styles.content} data-testid="settings-content">
        {children}
      </section>
    </div>
  );
}
