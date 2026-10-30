"use client";

import { useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { useTranslate } from "./useTranslate";
import { usePdfReferenceTranslation } from "./usePdfReferenceTranslation";
import { useIsClient } from "./useIsClient";
import { useTranslationExport } from "./useTranslationExport";
import {
  TRANSLATION_ERROR_COPY,
  TRANSLATION_SAMPLE_FILENAME,
  TRANSLATION_SAMPLE_RESULT,
  TRANSLATION_SAMPLE_SOURCE_PAGES,
} from "@/data/mockData";
import type {
  DocumentExplanation,
  PdfReferenceTranslationResponse,
  TranslateResponse,
} from "@/lib/api-generated";
import { isTranslationTruncated } from "@/lib/translation-truncation";
import { TARGET_LANGUAGE_OPTIONS, getDefaultTargetLanguage } from "@/lib/language-codes";
import {
  readUploadSession,
  updateUploadSessionTargetLanguage,
  type UploadSessionData,
} from "@/lib/upload-session";

interface SourcePage {
  page: number;
  text: string;
}

export interface SourceSection {
  readonly page: number;
  readonly index: number;
  readonly text: string;
}

const EMPTY_DOCUMENT: UploadSessionData = {
  filename: "Document",
  sourcePages: [],
  documentId: "",
  pageCount: 0,
  sourceLang: "en",
  targetLang: "de",
  pdfReferenceEligible: false,
  pdfProcessingMode: "none",
  classification: null,
  documentExplanation: null,
};
const EMPTY_SOURCE_PAGES: readonly SourcePage[] = [];

const FORCED_ERROR_MESSAGE = TRANSLATION_ERROR_COPY.unavailable;
const EXPLANATION_WARNING_COPY: Readonly<Record<string, string>> = {
  NO_VERIFIED_EU_LAW_SOURCE: "No verified EU-law source was found for this document.",
  LEGAL_RETRIEVAL_UNAVAILABLE: "EU-law sources are temporarily unavailable.",
  EXPLANATION_GENERATION_UNAVAILABLE:
    "Verified sources are available, but a plain-language explanation could not be generated.",
  GENERATED_CITATIONS_UNVERIFIED:
    "The plain-language summary could not be generated. The verified EU sources are listed below.",
  DOCUMENT_EXPLANATION_UNAVAILABLE:
    "Document guidance is temporarily unavailable; the extracted-text translation is still available.",
};

export type DocumentViewerState = "loading" | "success" | "error" | "empty";
export type TranslationResultMode = "translation" | "compare";

interface UseTranslationViewOptions {
  readonly forcedState?: DocumentViewerState;
  readonly initialResultMode?: TranslationResultMode;
  readonly referenceFile?: File | null;
}

interface TranslationViewState {
  readonly viewState: DocumentViewerState;
  readonly result: TranslateResponse | null;
  readonly referenceResult: PdfReferenceTranslationResponse | null;
  readonly isPdfReference: boolean;
  readonly isDocumentUnderstanding: boolean;
  readonly documentExplanation: DocumentExplanation | null;
  readonly documentExplanationWarnings: readonly string[];
  readonly sourcePdfUrl: string | null;
  readonly translatedPdfUrl: string | null;
  readonly referenceWarnings: readonly string[];
  readonly error: string | null;
  readonly isTruncated: boolean;
  readonly reset: () => void;
  readonly filename: string;
  readonly sourcePages: readonly SourcePage[];
  readonly sourceSections: readonly SourceSection[];
  readonly sourceLang: string;
  readonly targetLang: string;
  readonly resultMode: TranslationResultMode;
  readonly languageOptions: ReadonlyArray<Readonly<{ code: string; label: string }>>;
  readonly handleLanguageChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  readonly onShowTranslation: () => void;
  readonly onShowComparison: () => void;
  readonly onUploadClick: () => void;
  readonly canDownload: boolean;
  readonly onDownload: () => void;
}

/**
 * Controller hook for TranslationView / DocumentViewer: reads the uploaded
 * document from sessionStorage after hydration, auto-translates it, and manages
 * the target-language selection.
 */
export function useTranslationView({
  forcedState,
  initialResultMode = "translation",
  referenceFile = null,
}: Readonly<UseTranslationViewOptions> = {}): TranslationViewState {
  const {
    status: legacyStatus,
    result: legacyResult,
    error: legacyError,
    isTruncated: legacyIsTruncated,
    reset: resetLegacy,
    translate: translateLegacy,
  } = useTranslate();
  const {
    status: referenceStatus,
    result: referenceResult,
    error: referenceError,
    sourcePdfUrl,
    translatedPdfUrl,
    warningMessages: referenceWarnings,
    reset: resetReference,
    translate: translateReference,
  } = usePdfReferenceTranslation(referenceFile);
  const isClient = useIsClient();
  const router = useRouter();
  const [targetLang, setTargetLang] = useState(getDefaultTargetLanguage);
  const [resultMode, setResultMode] = useState<TranslationResultMode>(initialResultMode);
  const [documentData, setDocumentData] = useState<UploadSessionData>(EMPTY_DOCUMENT);

  const liveFilename = documentData.filename || "Document";
  const liveSourcePages = documentData.sourcePages || EMPTY_SOURCE_PAGES;
  const documentId = documentData.documentId || "";
  const pageCount = documentData.pageCount || liveSourcePages.length;
  const liveSourceLang = documentData.sourceLang || "en";
  const liveSourceSections = useMemo(
    () =>
      liveSourcePages.flatMap((page) => {
        const sections = page.text
          .replace(/\r\n?/g, "\n")
          .split(/\n\s*\n+/)
          .map((section) => section.replace(/\s*\n\s*/g, " ").trim())
          .filter(Boolean);
        return (sections.length > 0 ? sections : [page.text]).map((text, index) => ({
          page: page.page,
          index,
          text,
        }));
      }),
    [liveSourcePages]
  );

  useEffect(() => {
    if (isClient && !forcedState) {
      const session = readUploadSession();
      setDocumentData(session);
      const resolvedTarget =
        session.targetLang === session.sourceLang
          ? (TARGET_LANGUAGE_OPTIONS.find((option) => option.code !== session.sourceLang)?.code ??
            "de")
          : session.targetLang;
      setTargetLang(resolvedTarget);
    }
  }, [forcedState, isClient]);

  useEffect(() => {
    if (forcedState) {
      return;
    }
    if (
      isClient &&
      !referenceFile &&
      documentId &&
      liveSourcePages.length > 0 &&
      legacyStatus === "empty"
    ) {
      translateLegacy(documentId, liveSourceLang, targetLang, liveSourcePages, {
        classification: documentData.classification,
        includeDocumentExplanation:
          documentData.pdfProcessingMode === "document_understanding_translation",
      });
    }
  }, [
    forcedState,
    isClient,
    documentId,
    liveSourcePages,
    liveSourceLang,
    targetLang,
    legacyStatus,
    referenceFile,
    documentData.classification,
    documentData.pdfProcessingMode,
    translateLegacy,
  ]);

  useEffect(() => {
    if (!forcedState && isClient && referenceFile && documentId && referenceStatus === "empty") {
      translateReference(referenceFile, liveSourceLang, targetLang, pageCount);
    }
  }, [
    documentId,
    forcedState,
    isClient,
    liveSourceLang,
    pageCount,
    referenceStatus,
    referenceFile,
    targetLang,
    translateReference,
  ]);

  const handleLanguageChange = useCallback(
    (e: ChangeEvent<HTMLSelectElement>) => {
      const newLang = e.target.value;
      setTargetLang(newLang);
      updateUploadSessionTargetLanguage(newLang);
      if (!forcedState && referenceFile && documentId) {
        translateReference(referenceFile, liveSourceLang, newLang, pageCount);
      } else if (!forcedState && documentId && liveSourcePages.length > 0) {
        translateLegacy(documentId, liveSourceLang, newLang, liveSourcePages, {
          classification: documentData.classification,
          includeDocumentExplanation:
            documentData.pdfProcessingMode === "document_understanding_translation",
        });
      }
    },
    [
      documentId,
      documentData.classification,
      documentData.pdfProcessingMode,
      forcedState,
      liveSourceLang,
      liveSourcePages,
      pageCount,
      referenceFile,
      translateLegacy,
      translateReference,
    ]
  );

  const onUploadClick = useCallback(() => {
    router.push("/translation?start=upload");
  }, [router]);

  const onShowTranslation = useCallback(() => setResultMode("translation"), []);
  const onShowComparison = useCallback(() => setResultMode("compare"), []);

  const activeStatus = referenceFile ? referenceStatus : legacyStatus;
  const liveViewState: DocumentViewerState = activeStatus === "empty" ? "empty" : activeStatus;
  const viewState = forcedState ?? liveViewState;

  const filename = forcedState === "success" ? TRANSLATION_SAMPLE_FILENAME : liveFilename;
  const sourcePages = forcedState === "success" ? TRANSLATION_SAMPLE_SOURCE_PAGES : liveSourcePages;
  const sourceLang = forcedState === "success" ? "de" : liveSourceLang;
  const resolvedTargetLang = forcedState === "success" ? "en" : targetLang;
  const resolvedResult =
    forcedState === "success"
      ? (TRANSLATION_SAMPLE_RESULT as unknown as TranslateResponse)
      : legacyResult;
  const translationExport = useTranslationExport(resolvedResult, filename, resolvedTargetLang);
  const resolvedError =
    forcedState === "error" ? FORCED_ERROR_MESSAGE : referenceFile ? referenceError : legacyError;
  const resolvedTruncated =
    forcedState === "success"
      ? TRANSLATION_SAMPLE_RESULT.translated_pages != null &&
        isTranslationTruncated(TRANSLATION_SAMPLE_RESULT as unknown as TranslateResponse)
      : legacyIsTruncated;
  const isDocumentUnderstanding =
    !forcedState && documentData.pdfProcessingMode === "document_understanding_translation";
  const resolvedDocumentExplanation =
    resolvedResult?.document_explanation ?? documentData.documentExplanation;
  const documentExplanationWarnings = (resolvedDocumentExplanation?.warnings ?? []).map(
    (warning) =>
      EXPLANATION_WARNING_COPY[warning] ?? "Some document guidance could not be produced."
  );

  const reset = referenceFile ? resetReference : resetLegacy;
  const languageOptions = TARGET_LANGUAGE_OPTIONS.filter((option) => option.code !== sourceLang);

  return {
    viewState,
    result: resolvedResult,
    referenceResult,
    isPdfReference: Boolean(referenceFile && !forcedState),
    isDocumentUnderstanding,
    documentExplanation: isDocumentUnderstanding ? resolvedDocumentExplanation : null,
    documentExplanationWarnings,
    sourcePdfUrl,
    translatedPdfUrl,
    referenceWarnings,
    error: resolvedError,
    isTruncated: resolvedTruncated,
    reset,
    filename,
    sourcePages,
    sourceSections: liveSourceSections,
    sourceLang,
    targetLang: resolvedTargetLang,
    resultMode,
    languageOptions,
    handleLanguageChange,
    onShowTranslation,
    onShowComparison,
    onUploadClick,
    canDownload: translationExport.canDownload,
    onDownload: translationExport.downloadTranslatedText,
  };
}
