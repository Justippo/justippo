"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSettingsState } from "./useSettingsState";
import { useUploadHistory } from "./useUploadHistory";
import { useT } from "./useT";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import {
  SETTINGS_GDPR_DOMAINS,
  SETTINGS_LANGUAGE_OPTIONS,
  SETTINGS_SECTIONS,
  type SettingsGdprDomain,
  type SettingsSectionId,
} from "@/data/mockData";
import type { SupportedLanguage } from "@evidenceeu/shared";

export type SettingsViewState = "loading" | "success" | "error" | "empty";

interface UseSettingsViewOptions {
  readonly forcedState?: SettingsViewState;
  readonly initialSection?: SettingsSectionId;
}

interface UseSettingsViewResult {
  readonly viewState: SettingsViewState;
  readonly sections: typeof SETTINGS_SECTIONS;
  readonly activeSection: SettingsSectionId | null;
  readonly gdprDomains: readonly SettingsGdprDomain[];
  readonly languageOptions: typeof SETTINGS_LANGUAGE_OPTIONS;
  readonly theme: "light" | "dark" | "system";
  readonly language: SupportedLanguage;
  readonly notifications: boolean;
  readonly reducedMotion: boolean;
  readonly name: string;
  readonly email: string;
  readonly jurisdiction: string;
  readonly saved: boolean;
  readonly error: string | null;
  readonly setActiveSection: (section: SettingsSectionId) => void;
  readonly setTheme: (theme: "light" | "dark" | "system") => void;
  readonly setLanguage: (language: SupportedLanguage) => void;
  readonly setNotifications: (enabled: boolean) => void;
  readonly setReducedMotion: (enabled: boolean) => void;
  readonly setName: (name: string) => void;
  readonly setEmail: (email: string) => void;
  readonly setJurisdiction: (jurisdiction: string) => void;
  readonly onSave: () => void;
  readonly onRetry: () => void;
  readonly onExportData: () => void;
  readonly onDeleteAccount: () => void;
}

const FORCED_ERROR_MESSAGE = "Settings could not be loaded. Please try again.";

function applyTheme(theme: "light" | "dark" | "system"): void {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const isDark = theme === "dark" || (theme === "system" && prefersDark);
  document.documentElement.classList.toggle("dark", isDark);
}

export function useSettingsView({
  forcedState,
  initialSection = "profile",
}: Readonly<UseSettingsViewOptions> = {}): UseSettingsViewResult {
  const settingsState = useSettingsState();
  const { history } = useUploadHistory();
  const { changeLanguage } = useT();
  const { logout } = useAuth();
  const router = useRouter();
  const [activeSection, setActiveSection] = useState<SettingsSectionId | null>(initialSection);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (forcedState) {
      return;
    }
    if (settingsState.status === "error") {
      setLoadError(FORCED_ERROR_MESSAGE);
    }
  }, [forcedState, settingsState.status]);

  useEffect(() => {
    if (forcedState || typeof window === "undefined") {
      return;
    }
    const stored = window.localStorage.getItem("evidenceeu_accessibility");
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as { reducedMotion?: boolean };
        setReducedMotion(Boolean(parsed.reducedMotion));
      } catch {
        // Ignore invalid accessibility preferences.
      }
    }
    applyTheme(settingsState.settings.theme);
  }, [forcedState, settingsState.settings.theme]);

  const onSave = useCallback(() => {
    if (forcedState) {
      return;
    }

    settingsState.save();
    void changeLanguage(settingsState.settings.language);
    applyTheme(settingsState.settings.theme);

    try {
      window.localStorage.setItem("evidenceeu_accessibility", JSON.stringify({ reducedMotion }));
      document.documentElement.classList.toggle("reduce-motion", reducedMotion);
    } catch {
      // localStorage unavailable — preferences stay in memory for this session.
    }
  }, [forcedState, settingsState, changeLanguage, reducedMotion]);

  const onRetry = useCallback(() => {
    if (forcedState) {
      return;
    }
    setLoadError(null);
    window.location.reload();
  }, [forcedState]);

  return useMemo(() => {
    if (forcedState) {
      const forcedSection: SettingsSectionId | null = forcedState === "empty" ? null : "compliance";

      return {
        viewState: forcedState,
        sections: SETTINGS_SECTIONS,
        activeSection: forcedSection,
        gdprDomains: SETTINGS_GDPR_DOMAINS,
        languageOptions: SETTINGS_LANGUAGE_OPTIONS,
        theme: "system",
        language: "en",
        notifications: true,
        reducedMotion: false,
        name: "",
        email: "",
        jurisdiction: "",
        saved: forcedState === "success",
        error: forcedState === "error" ? FORCED_ERROR_MESSAGE : null,
        setActiveSection,
        setTheme: () => undefined,
        setLanguage: () => undefined,
        setNotifications: () => undefined,
        setReducedMotion: () => undefined,
        setName: () => undefined,
        setEmail: () => undefined,
        setJurisdiction: () => undefined,
        onSave: () => undefined,
        onRetry: () => undefined,
        onExportData: () => undefined,
        onDeleteAccount: () => undefined,
      };
    }

    const liveViewState: SettingsViewState =
      settingsState.status === "loading"
        ? "loading"
        : settingsState.status === "error" || loadError
          ? "error"
          : "success";

    return {
      viewState: liveViewState,
      sections: SETTINGS_SECTIONS,
      activeSection,
      gdprDomains: SETTINGS_GDPR_DOMAINS,
      languageOptions: SETTINGS_LANGUAGE_OPTIONS,
      theme: settingsState.settings.theme,
      language: settingsState.settings.language,
      notifications: settingsState.settings.notifications,
      reducedMotion,
      name: settingsState.settings.name,
      email: settingsState.settings.email,
      jurisdiction: settingsState.settings.jurisdiction,
      saved: settingsState.saved,
      error: loadError ?? (settingsState.status === "error" ? FORCED_ERROR_MESSAGE : null),
      setActiveSection,
      setTheme: (theme) => settingsState.updateSettings({ theme }),
      setLanguage: (language) => settingsState.updateSettings({ language }),
      setNotifications: (enabled) => settingsState.updateSettings({ notifications: enabled }),
      setReducedMotion,
      setName: (name) => settingsState.updateSettings({ name }),
      setEmail: (email) => settingsState.updateSettings({ email }),
      setJurisdiction: (jurisdiction) => settingsState.updateSettings({ jurisdiction }),
      onSave,
      onRetry,
      onExportData: async () => {
        try {
          const { jsPDF } = await import("jspdf");
          const doc = new jsPDF();

          doc.setFontSize(20);
          doc.text("EvidenceEU Data Export", 20, 20);

          doc.setFontSize(12);
          doc.text("Personal Information:", 20, 40);
          doc.setFontSize(10);
          doc.text(`- Name: ${settingsState.settings.name || "Not provided"}`, 25, 50);
          doc.text(`- Email: ${settingsState.settings.email || "Not provided"}`, 25, 60);
          doc.text(
            `- Jurisdiction: ${settingsState.settings.jurisdiction || "Not provided"}`,
            25,
            70
          );

          doc.setFontSize(12);
          doc.text("Document History:", 20, 90);
          doc.setFontSize(10);
          let currentY = 100;
          if (history.length === 0) {
            doc.text("No document history available.", 25, currentY);
            currentY += 20;
          } else {
            history.slice(0, 5).forEach((item, index) => {
              const date = new Date(item.uploadedAt).toISOString().split("T")[0];
              const maxLen = 40;
              const shortName =
                item.filename.length > maxLen
                  ? item.filename.substring(0, maxLen) + "..."
                  : item.filename;
              const rawString = `${index + 1}. ${shortName} (Target: ${item.targetLang.toUpperCase()}) - ${date}`;
              // jsPDF's standard fonts break on non-Latin-1 unicode (e.g., macOS U+202F narrow no-break space).
              // Replace all non-Latin-1 characters with a standard space.
              const safeString = rawString.replace(/[^\x20-\xFF]/g, " ");
              doc.text(safeString, 25, currentY);
              currentY += 10;
            });
            currentY += 10;
          }

          doc.setFontSize(12);
          doc.text("Settings Preferences:", 20, currentY);
          currentY += 10;
          doc.setFontSize(10);
          doc.text(`- Theme: ${settingsState.settings.theme}`, 25, currentY);
          currentY += 10;
          doc.text(`- Language: ${settingsState.settings.language}`, 25, currentY);
          currentY += 10;
          doc.text(
            `- Notifications: ${settingsState.settings.notifications ? "Enabled" : "Disabled"}`,
            25,
            currentY
          );
          currentY += 10;
          doc.text(`- Reduced Motion: ${reducedMotion ? "Enabled" : "Disabled"}`, 25, currentY);

          doc.save("evidence-eu-data-export.pdf");
        } catch (error) {
          console.error("Failed to generate PDF:", error);
          alert("An error occurred while generating your data export.");
        }
      },
      onDeleteAccount: async () => {
        if (
          window.confirm(
            "Are you sure you want to permanently delete your account? This action cannot be undone."
          )
        ) {
          try {
            localStorage.removeItem("evidenceeu_settings");
            sessionStorage.removeItem("evidenceeu_upload_history");
          } catch {
            // ignore
          }
          await logout();
          router.replace("/");
        }
      },
    };
  }, [
    forcedState,
    settingsState,
    history,
    activeSection,
    reducedMotion,
    loadError,
    setActiveSection,
    onSave,
    onRetry,
    logout,
    router,
  ]);
}
