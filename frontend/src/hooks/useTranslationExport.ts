"use client";

import { useCallback, useMemo } from "react";
import type { TranslateResponse } from "@/lib/api-generated";

interface TranslationExportState {
  readonly canDownload: boolean;
  readonly downloadTranslatedText: () => void;
}

function translatedFilename(filename: string, targetLang: string): string {
  const base = filename.replace(/\.[^.]+$/, "") || "document";
  const safeBase = base.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
  return `${safeBase}-translated-${targetLang}.txt`;
}

export function buildTranslationExportText(
  result: TranslateResponse,
  filename: string,
  targetLang: string
): string {
  const pageBlocks = (result.translated_pages ?? []).map((page) => {
    const sections = page.sections ?? [];
    const pageText =
      sections.length > 0
        ? sections
            .map((section) =>
              section.status === "failed"
                ? `[Section ${section.index + 1} could not be translated after ${section.attempts ?? 2} attempts.]`
                : section.translated_text
            )
            .join("\n\n")
        : page.text;
    return `Page ${page.page}\n${pageText}`;
  });

  return [
    "EvidenceEU translated text",
    `Source file: ${filename}`,
    `Target language: ${targetLang.toUpperCase()}`,
    "",
    ...pageBlocks,
  ].join("\n");
}

export function useTranslationExport(
  result: TranslateResponse | null,
  filename: string,
  targetLang: string
): TranslationExportState {
  const exportText = useMemo(
    () => (result ? buildTranslationExportText(result, filename, targetLang) : ""),
    [filename, result, targetLang]
  );
  const canDownload = Boolean(result?.translated_pages?.length && result.status !== "failed");

  const downloadTranslatedText = useCallback(() => {
    if (!canDownload) {
      return;
    }
    const blob = new Blob([exportText], { type: "text/plain;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = translatedFilename(filename, targetLang);
    anchor.hidden = true;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  }, [canDownload, exportText, filename, targetLang]);

  return { canDownload, downloadTranslatedText };
}
