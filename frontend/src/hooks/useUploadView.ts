"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { ChangeEvent, DragEvent, FormEvent } from "react";
import { useDragAndDrop } from "./useDragAndDrop";
import { useFileValidation } from "./useFileValidation";
import { useUploadHistory } from "./useUploadHistory";
import { useUpload } from "./useUpload";
import {
  UPLOAD_ERROR_COPY,
  UPLOAD_LOW_QUALITY_WARNING,
  UPLOAD_PREVIEW_CHAR_LIMIT,
  UPLOAD_SAMPLE_RESULT,
  formatUploadPreviewNotice,
  type UploadHistoryItem,
} from "@/data/mockData";
import type { UploadResponse } from "@/lib/api-generated";
import { TARGET_LANGUAGE_OPTIONS, getDefaultTargetLanguage } from "@/lib/language-codes";
import {
  averageConfidence,
  formatConfidencePercent,
  getConfidenceBadgeVariant,
  type ConfidenceBadgeVariant,
} from "@/lib/upload-confidence";

export type UploadViewState = "loading" | "success" | "error" | "empty";

interface UseUploadViewOptions {
  readonly forcedState?: UploadViewState;
  readonly onContinue?: (targetLang: string, file: File | null) => void;
}

interface UploadPageRow {
  readonly page: number;
  readonly confidenceLabel: string;
  readonly confidenceVariant: ConfidenceBadgeVariant;
  readonly confidenceClassName: string;
  readonly previewText: string;
}

interface UseUploadViewResult {
  readonly viewState: UploadViewState;
  readonly result: UploadResponse | null;
  readonly error: string | null;
  readonly history: readonly UploadHistoryItem[];
  readonly isDragging: boolean;
  readonly file: File | null;
  readonly fileError: string | null;
  readonly gdprConsent: boolean;
  readonly consentError: string | null;
  readonly targetLang: string;
  readonly targetLanguageOptions: ReadonlyArray<Readonly<{ code: string; label: string }>>;
  readonly canSubmit: boolean;
  readonly previewLimit: number;
  readonly previewNotice: string | null;
  readonly averageConfidenceLabel: string;
  readonly averageConfidenceVariant: ConfidenceBadgeVariant;
  readonly averageConfidenceClassName: string;
  readonly pageRows: readonly UploadPageRow[];
  readonly lowQualityWarning: string | null;
  readonly translationModeNotice: string | null;
  readonly setGdprConsent: (value: boolean) => void;
  readonly setTargetLang: (value: string) => void;
  readonly onDragEnter: (event: DragEvent<HTMLDivElement>) => void;
  readonly onDragLeave: (event: DragEvent<HTMLDivElement>) => void;
  readonly onDragOver: (event: DragEvent<HTMLDivElement>) => void;
  readonly onDrop: (event: DragEvent<HTMLDivElement>) => void;
  readonly onBrowseClick: () => void;
  readonly onFileInputChange: (event: ChangeEvent<HTMLInputElement>) => void;
  readonly onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly onReset: () => void;
  readonly onContinueToTranslation: () => void;
  readonly onClearFile: () => void;
  readonly fileInputRef: RefObject<HTMLInputElement>;
}

const LOW_QUALITY_WARNING = UPLOAD_LOW_QUALITY_WARNING;

function getUploadError(error: string | null): string | null {
  return error ? UPLOAD_ERROR_COPY.unavailable : null;
}

function getConfidenceThemeClass(variant: ConfidenceBadgeVariant): string {
  // Badge component already applies variant color via CSS Module — no
  // Tailwind utility class needed (those classes aren't in Tailwind's
  // content scan path for hooks/ anyway).
  return "";
}

function buildPageRows(result: UploadResponse, previewLimit: number): readonly UploadPageRow[] {
  return result.pages.map((page) => {
    const confidence = page.confidence ?? 0;
    const rawText = page.text ?? "";
    const truncated = rawText.length > previewLimit;
    const previewText = truncated ? `${rawText.slice(0, previewLimit)}…` : rawText;

    const confidenceVariant =
      page.confidence != null ? getConfidenceBadgeVariant(confidence) : "warning";

    return {
      page: page.page,
      confidenceLabel: page.confidence != null ? formatConfidencePercent(confidence) : "—",
      confidenceVariant,
      confidenceClassName: getConfidenceThemeClass(confidenceVariant),
      previewText,
    };
  });
}

function buildPreviewNotice(result: UploadResponse, previewLimit: number): string | null {
  const truncatedPages = result.pages.filter(
    (page) => (page.text?.length ?? 0) > previewLimit
  ).length;
  if (truncatedPages === 0) {
    return null;
  }
  return formatUploadPreviewNotice(previewLimit);
}

export function useUploadView({
  forcedState,
  onContinue,
}: Readonly<UseUploadViewOptions> = {}): UseUploadViewResult {
  const uploadState = useUpload();
  const drag = useDragAndDrop();
  const { fileError, validate } = useFileValidation();
  const { history, recordUpload } = useUploadHistory();
  const fileInputRef = useRef<HTMLInputElement>(null!);
  const lastRecordedDocIdRef = useRef<string | null>(null);

  const [gdprConsent, setGdprConsent] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  const [targetLang, setTargetLang] = useState(getDefaultTargetLanguage);

  const applyFile = useCallback(
    (candidate: File) => {
      if (validate(candidate)) {
        drag.onFileSelect(candidate);
      }
    },
    [drag, validate]
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      drag.onDrop(event);
      const dropped = event.dataTransfer.files[0];
      if (dropped) {
        applyFile(dropped);
      }
    },
    [applyFile, drag]
  );

  const onFileInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const selected = event.target.files?.[0];
      if (selected) {
        applyFile(selected);
      }
    },
    [applyFile]
  );

  const onBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const onSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!drag.file) {
        return;
      }
      if (!gdprConsent) {
        setConsentError("GDPR consent is required before uploading.");
        return;
      }
      setConsentError(null);
      uploadState.upload(drag.file, targetLang);
    },
    [drag.file, gdprConsent, targetLang, uploadState]
  );

  const onReset = useCallback(() => {
    uploadState.reset();
    drag.clearFile();
    // React state (drag.file) is now null, but the native <input> element still
    // holds its previous value. Without clearing it, re-selecting the exact
    // same file after an error does not fire onChange (the browser only fires
    // it on a value change), leaving the user stuck unable to retry.
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setConsentError(null);
    setGdprConsent(false);
    lastRecordedDocIdRef.current = null;
  }, [drag, uploadState]);

  const onClearFile = useCallback(() => {
    drag.clearFile();
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setConsentError(null);
  }, [drag]);

  const onContinueToTranslation = useCallback(() => {
    onContinue?.(targetLang, drag.file);
  }, [drag.file, onContinue, targetLang]);

  useEffect(() => {
    if (forcedState) {
      return;
    }
    if (uploadState.status === "success" && uploadState.result && drag.file) {
      if (lastRecordedDocIdRef.current !== uploadState.result.doc_id) {
        recordUpload(drag.file.name, uploadState.result, targetLang);
        lastRecordedDocIdRef.current = uploadState.result.doc_id;
      }
      return;
    }
    if (uploadState.status === "empty") {
      lastRecordedDocIdRef.current = null;
    }
  }, [forcedState, uploadState.status, uploadState.result, drag.file, targetLang, recordUpload]);

  const liveViewState: UploadViewState =
    uploadState.status === "empty" ? "empty" : uploadState.status;

  const viewState = forcedState ?? liveViewState;
  const result =
    forcedState === "success"
      ? (UPLOAD_SAMPLE_RESULT as unknown as UploadResponse)
      : uploadState.result;
  const error =
    forcedState === "error" ? UPLOAD_ERROR_COPY.unavailable : getUploadError(uploadState.error);

  const successMetrics = useMemo(() => {
    if (!result || viewState !== "success") {
      return {
        averageConfidenceLabel: "—",
        averageConfidenceVariant: "warning" as ConfidenceBadgeVariant,
        averageConfidenceClassName: "bg-warning",
        pageRows: [] as UploadPageRow[],
        previewNotice: null as string | null,
        lowQualityWarning: null as string | null,
      };
    }

    const avg = averageConfidence(result.pages);
    const averageConfidenceVariant = getConfidenceBadgeVariant(avg);
    return {
      averageConfidenceLabel: formatConfidencePercent(avg),
      averageConfidenceVariant,
      averageConfidenceClassName: getConfidenceThemeClass(averageConfidenceVariant),
      pageRows: buildPageRows(result, UPLOAD_PREVIEW_CHAR_LIMIT),
      previewNotice: buildPreviewNotice(result, UPLOAD_PREVIEW_CHAR_LIMIT),
      lowQualityWarning: avg < 0.7 ? LOW_QUALITY_WARNING : null,
    };
  }, [result, viewState]);

  const canSubmit = Boolean(drag.file && gdprConsent && !fileError);
  const detectedSourceLanguage = result?.classification?.language_code;
  const targetLanguageOptions = useMemo(
    () => TARGET_LANGUAGE_OPTIONS.filter((option) => option.code !== detectedSourceLanguage),
    [detectedSourceLanguage]
  );

  useEffect(() => {
    if (result?.target_language && targetLang !== result.target_language) {
      setTargetLang(result.target_language);
      return;
    }
    if (targetLang === detectedSourceLanguage && targetLanguageOptions.length > 0) {
      setTargetLang(targetLanguageOptions[0].code);
    }
  }, [detectedSourceLanguage, result?.target_language, targetLang, targetLanguageOptions]);

  return {
    viewState,
    result: viewState === "success" ? result : uploadState.result,
    error,
    history,
    isDragging: drag.isDragging,
    file: drag.file,
    fileError,
    gdprConsent,
    consentError,
    targetLang,
    targetLanguageOptions,
    canSubmit,
    previewLimit: UPLOAD_PREVIEW_CHAR_LIMIT,
    previewNotice: successMetrics.previewNotice,
    averageConfidenceLabel: successMetrics.averageConfidenceLabel,
    averageConfidenceVariant: successMetrics.averageConfidenceVariant,
    averageConfidenceClassName: successMetrics.averageConfidenceClassName,
    pageRows: successMetrics.pageRows,
    lowQualityWarning: successMetrics.lowQualityWarning,
    translationModeNotice:
      result?.pdf_processing?.route === "document_understanding_translation"
        ? "This PDF will be translated from its extracted text for understanding. The translated view will not reproduce the PDF layout or fillable controls."
        : null,
    setGdprConsent: (value: boolean) => {
      setGdprConsent(value);
      if (value) {
        setConsentError(null);
      }
    },
    setTargetLang,
    onDragEnter: drag.onDragEnter,
    onDragLeave: drag.onDragLeave,
    onDragOver: drag.onDragOver,
    onDrop,
    onBrowseClick,
    onFileInputChange,
    onSubmit,
    onReset,
    onContinueToTranslation,
    onClearFile,
    fileInputRef,
  };
}
