"use client";

import styles from "./SettingsView.module.css";
import { SettingsLayout } from "./SettingsLayout";
import { useSettingsView, type SettingsViewState } from "@/hooks/useSettingsView";
import { Badge, Button, Skeleton, Input } from "@/components/atoms";

interface SettingsViewProps {
  readonly className?: string;
  readonly forcedState?: SettingsViewState;
  readonly initialSection?: "profile" | "compliance" | "accessibility";
}

function SettingsPanel({ settings }: Readonly<{ settings: ReturnType<typeof useSettingsView> }>) {
  if (!settings.activeSection) {
    return (
      <div className={styles.centerState}>
        <h2 className={styles.panelTitle}>Choose a category</h2>
        <p className={styles.stateText}>
          Select Profile & security, Compliance, or Accessibility from the sidebar to manage your
          workspace preferences.
        </p>
      </div>
    );
  }

  if (settings.activeSection === "profile") {
    return (
      <div className={styles.panel}>
        <h2 className={styles.panelTitle}>Profile & security</h2>
        <p className={styles.panelDescription}>
          Manage your identity, interface language, theme, and notification preferences.
        </p>

        <div className={styles.form}>
          <label className={styles.field} htmlFor="settings-name">
            Full Name
            <Input
              id="settings-name"
              type="text"
              data-testid="settings-name"
              value={settings.name}
              onChange={(e) => settings.setName(e.target.value)}
              placeholder="e.g. Jane Doe"
            />
          </label>

          <label className={styles.field} htmlFor="settings-email">
            Email Address
            <Input
              id="settings-email"
              type="email"
              data-testid="settings-email"
              value={settings.email}
              onChange={(e) => settings.setEmail(e.target.value)}
              placeholder="e.g. jane@example.com"
            />
          </label>

          <label className={styles.field} htmlFor="settings-jurisdiction">
            Primary Jurisdiction
            <Input
              id="settings-jurisdiction"
              type="text"
              data-testid="settings-jurisdiction"
              value={settings.jurisdiction}
              onChange={(e) => settings.setJurisdiction(e.target.value)}
              placeholder="e.g. Germany"
            />
          </label>
          <label className={styles.field} htmlFor="settings-language">
            Interface language
            <select
              id="settings-language"
              data-testid="settings-language"
              value={settings.language}
              onChange={(event) => settings.setLanguage(event.target.value as "en" | "de" | "fr")}
              className={styles.select}
            >
              {settings.languageOptions.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field} htmlFor="settings-theme">
            Theme
            <select
              id="settings-theme"
              data-testid="settings-theme"
              value={settings.theme}
              onChange={(event) =>
                settings.setTheme(event.target.value as "light" | "dark" | "system")
              }
              className={styles.select}
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>

          <label className={styles.checkboxField}>
            <input
              type="checkbox"
              checked={settings.notifications}
              onChange={(event) => settings.setNotifications(event.target.checked)}
              data-testid="settings-notifications"
            />
            Enable product notifications
          </label>
        </div>
      </div>
    );
  }

  if (settings.activeSection === "compliance") {
    return (
      <div className={styles.panel}>
        <h2 className={styles.panelTitle}>Compliance & governance</h2>
        <p className={styles.panelDescription}>
          EvidenceEU is audited across eight GDPR and security domains. All domains must remain in a
          passing state for production use.
        </p>

        <ul className={styles.domainList} data-testid="settings-gdpr-domains">
          {settings.gdprDomains.map((domain) => (
            <li key={domain.id} className={styles.domainItem}>
              <div className={styles.domainHeader}>
                <span className={styles.domainTitle}>{domain.title}</span>
                <Badge variant="success" data-testid={`settings-domain-${domain.id}`}>
                  Pass
                </Badge>
              </div>
              <p className={styles.domainDescription}>{domain.description}</p>
            </li>
          ))}
        </ul>

        <h3 className={styles.panelSubtitle}>Data & privacy controls</h3>
        <p className={styles.panelDescription}>
          Manage your personal data in accordance with your GDPR rights.
        </p>
        <div className={styles.buttonGroup}>
          <Button
            variant="secondary"
            onClick={settings.onExportData}
            data-testid="settings-export-data"
          >
            Download my data
          </Button>
          <Button
            variant="error"
            onClick={settings.onDeleteAccount}
            data-testid="settings-delete-account"
          >
            Delete account
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <h2 className={styles.panelTitle}>Accessibility & UI</h2>
      <p className={styles.panelDescription}>
        Adjust motion and display preferences for a more comfortable experience.
      </p>

      <label className={styles.checkboxField}>
        <input
          type="checkbox"
          checked={settings.reducedMotion}
          onChange={(event) => settings.setReducedMotion(event.target.checked)}
          data-testid="settings-reduced-motion"
        />
        Reduce motion and animations
      </label>
    </div>
  );
}

export function SettingsView({
  className = "",
  forcedState,
  initialSection,
}: Readonly<SettingsViewProps>) {
  const settings = useSettingsView({ forcedState, initialSection });

  if (settings.viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.centerState} role="status" aria-label="Loading settings">
          <Skeleton height="1.5rem" width="200px" />
        </div>
      </div>
    );
  }

  if (settings.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.centerState} role="alert">
          <h1 className={styles.heading}>Settings</h1>
          <p className={styles.stateText} data-testid="settings-error">
            {settings.error}
          </p>
          <Button variant="primary" onClick={settings.onRetry}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      {settings.saved && (
        <div className={styles.toast} role="status" data-testid="settings-saved">
          Settings saved.
        </div>
      )}

      <SettingsLayout
        sections={settings.sections}
        activeSection={settings.activeSection}
        onSectionChange={settings.setActiveSection}
      >
        <SettingsPanel settings={settings} />
      </SettingsLayout>

      {settings.activeSection && (
        <div className={styles.actions}>
          <Button variant="primary" onClick={settings.onSave} data-testid="settings-save">
            Save settings
          </Button>
        </div>
      )}
    </div>
  );
}
