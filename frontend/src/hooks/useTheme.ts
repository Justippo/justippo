"use client";

import { useState, useEffect, useCallback } from "react";

type Theme = "light" | "dark" | "system";

const THEME_KEY = "evidenceeu_settings";

function getStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as { theme?: Theme };
      if (parsed.theme) return parsed.theme;
    }
  } catch {
    // localStorage unavailable
  }
  return "system";
}

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  const resolved = theme === "system" ? getSystemTheme() : theme;
  const html = document.documentElement;
  if (resolved === "dark") {
    html.classList.add("dark");
  } else {
    html.classList.remove("dark");
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>("system");
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = getStoredTheme();
    setTheme(stored);
    applyTheme(stored);
    setResolvedTheme(stored === "system" ? getSystemTheme() : stored);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      if (theme === "system") {
        const systemTheme = getSystemTheme();
        applyTheme("system");
        setResolvedTheme(systemTheme);
      }
    };
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    const themes: Theme[] = ["light", "dark", "system"];
    const currentIndex = themes.indexOf(theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    setTheme(nextTheme);
    try {
      const stored = localStorage.getItem(THEME_KEY);
      const settings = stored ? JSON.parse(stored) : {};
      settings.theme = nextTheme;
      localStorage.setItem(THEME_KEY, JSON.stringify(settings));
    } catch {
      // localStorage unavailable
    }
    applyTheme(nextTheme);
    setResolvedTheme(nextTheme === "system" ? getSystemTheme() : nextTheme);
  }, [theme]);

  const setThemeExplicit = useCallback((newTheme: Theme) => {
    setTheme(newTheme);
    try {
      const stored = localStorage.getItem(THEME_KEY);
      const settings = stored ? JSON.parse(stored) : {};
      settings.theme = newTheme;
      localStorage.setItem(THEME_KEY, JSON.stringify(settings));
    } catch {
      // localStorage unavailable
    }
    applyTheme(newTheme);
    setResolvedTheme(newTheme === "system" ? getSystemTheme() : newTheme);
  }, []);

  return {
    theme,
    resolvedTheme,
    toggleTheme,
    setTheme: setThemeExplicit,
  };
}
