// SPDX-License-Identifier: MIT
/**
 * Shared TypeScript Types — EvidenceEU Cross-Platform
 *
 * Extracted from frontend/src/types/index.ts for use by both
 * web (Next.js) and mobile (Expo) apps.
 *
 * @platform web mobile
 */

export type SupportedLanguage = "en" | "de" | "fr";

export interface PageContent {
  readonly page: number;
  readonly text: string;
}

export interface DocumentSource {
  readonly title: string;
  readonly url: string;
  readonly excerpt: string;
  readonly language: SupportedLanguage;
  readonly documentType: "regulation" | "form" | "guideline" | "contract" | "other";
}

export interface SearchResultType {
  readonly answer: string;
  readonly sources: readonly DocumentSource[];
  readonly queryLanguage: SupportedLanguage;
  readonly resultLanguages: readonly SupportedLanguage[];
}

export interface DocumentMetadata {
  readonly documentId: string;
  readonly filename: string;
  readonly status: "queued" | "processing" | "ready" | "failed";
  readonly detectedLanguage: SupportedLanguage;
  readonly pageCount: number;
  readonly createdAt: string;
  readonly translations: ReadonlyArray<{
    readonly language: SupportedLanguage;
    readonly status: "queued" | "processing" | "done" | "failed";
    readonly downloadUrl?: string;
  }>;
}

export interface TranslationJobType {
  readonly jobId: string;
  readonly status: "queued" | "processing" | "done" | "failed";
  readonly translatedPages?: ReadonlyArray<{ readonly page: number; readonly text: string }>;
  readonly downloadUrl?: string;
  readonly error?: string;
}

export interface DocumentUploadResult {
  readonly documentId: string;
  readonly pageCount: number;
  readonly pages: ReadonlyArray<{ readonly page: number; readonly text: string; readonly confidence: number | null }>;
  readonly classification: {
    readonly documentType: string;
    readonly languageCode: string;
    readonly qualityScore: number;
    readonly confidence: number;
  };
}
