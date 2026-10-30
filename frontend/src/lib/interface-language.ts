export const APP_LANGUAGES = ["en", "de", "fr"] as const;

export type AppLanguage = (typeof APP_LANGUAGES)[number];

export const DEFAULT_APP_LANGUAGE: AppLanguage = "en";
export const INTERFACE_LANGUAGE_STORAGE_KEY = "evidenceeu_interface_language";

export function isAppLanguage(value: string | null | undefined): value is AppLanguage {
  return APP_LANGUAGES.includes(value as AppLanguage);
}

function readLocaleCookie(): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const localeCookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("NEXT_LOCALE="));

  return localeCookie?.split("=")[1] ?? null;
}

export function getPreferredInterfaceLanguage(): AppLanguage {
  const cookieLanguage = readLocaleCookie();
  if (isAppLanguage(cookieLanguage)) {
    return cookieLanguage;
  }

  if (typeof window !== "undefined") {
    try {
      const storedLanguage = window.localStorage.getItem(INTERFACE_LANGUAGE_STORAGE_KEY);
      if (isAppLanguage(storedLanguage)) {
        return storedLanguage;
      }
    } catch {
      // Storage may be unavailable in hardened browser contexts.
    }
  }

  return DEFAULT_APP_LANGUAGE;
}

export function persistInterfaceLanguage(language: AppLanguage): void {
  if (typeof document !== "undefined") {
    document.documentElement.lang = language;
    document.cookie = `NEXT_LOCALE=${language}; Path=/; Max-Age=31536000; SameSite=Lax`;
  }

  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(INTERFACE_LANGUAGE_STORAGE_KEY, language);
    } catch {
      // The active Tolgee language still applies for this browser session.
    }
  }
}
