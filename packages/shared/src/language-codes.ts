const LANGUAGE_LABELS: Readonly<Record<string, string>> = {
  en: "English",
  de: "German",
  fr: "French",
};

const SUPPORTED_CODES = ["en", "de", "fr"] as const;

export function formatLanguageCode(code: string): string {
  return code.trim().toUpperCase() || "—";
}

export function getLanguageLabel(code: string): string {
  return LANGUAGE_LABELS[code.toLowerCase()] ?? formatLanguageCode(code);
}

export function formatLanguagePair(sourceLang: string, targetLang: string): string {
  return `${formatLanguageCode(sourceLang)} → ${formatLanguageCode(targetLang)}`;
}

export const TARGET_LANGUAGE_OPTIONS = [
  { code: "de", label: "German" },
  { code: "fr", label: "French" },
  { code: "en", label: "English" },
] as const;

export function getDefaultTargetLanguage(): string {
  if (typeof navigator === "undefined") return "en";
  const tag = navigator.language ?? "";
  const code = tag.split("-")[0].toLowerCase();
  return (SUPPORTED_CODES as readonly string[]).includes(code) ? code : "en";
}