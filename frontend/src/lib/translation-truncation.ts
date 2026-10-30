import type { TranslateResponse } from "@/lib/api-generated";

const TRUNCATION_MARKER = "[truncated]";

export function isTranslationTruncated(result: TranslateResponse): boolean {
  return result.translated_pages?.some((page) => page.text.endsWith(TRUNCATION_MARKER)) ?? false;
}

export function stripTruncationMarker(text: string): string {
  return text.replaceAll(TRUNCATION_MARKER, "");
}
