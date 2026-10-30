"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { SupportedLanguage } from "@evidenceeu/shared";

const SETTINGS_KEY = "evidenceeu_settings";

interface Settings {
  readonly theme: "light" | "dark" | "system";
  readonly language: SupportedLanguage;
  readonly notifications: boolean;
  readonly name: string;
  readonly email: string;
  readonly jurisdiction: string;
}

const DEFAULT_SETTINGS: Settings = {
  theme: "system",
  language: "en",
  notifications: true,
  name: "",
  email: "",
  jurisdiction: "",
};

type SettingsStatus = "loading" | "success" | "error";

interface SettingsState {
  readonly status: SettingsStatus;
  readonly settings: Settings;
  readonly saved: boolean;
  readonly updateSettings: (partial: Partial<Settings>) => void;
  readonly save: () => void;
}

export function useSettingsState(): SettingsState {
  const [status, setStatus] = useState<SettingsStatus>("loading");
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SETTINGS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<Settings>;
        setSettings({ ...DEFAULT_SETTINGS, ...parsed });
      }
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    return () => {
      if (savedTimerRef.current) {
        clearTimeout(savedTimerRef.current);
      }
    };
  }, []);

  const updateSettings = useCallback((partial: Partial<Settings>) => {
    setSettings((prev) => ({ ...prev, ...partial }));
    setSaved(false);
  }, []);

  const save = useCallback(() => {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
    } catch {
      // localStorage unavailable
    }
    setSaved(true);
    if (savedTimerRef.current) {
      clearTimeout(savedTimerRef.current);
    }
    savedTimerRef.current = setTimeout(() => {
      savedTimerRef.current = null;
      setSaved(false);
    }, 2000);
  }, [settings]);

  return { status, settings, saved, updateSettings, save };
}
