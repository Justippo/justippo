"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  translateDocument,
  type DocumentClassification,
  type TranslateResponse,
} from "@/lib/api-generated";
import { isTranslationTruncated } from "@/lib/translation-truncation";
import { TRANSLATION_ERROR_COPY } from "@/data/mockData";
import type { SupportedLanguage } from "@evidenceeu/shared";

type TranslationStatus = "empty" | "loading" | "success" | "error";
type TargetLanguage = SupportedLanguage;

const VALID_LANGUAGES: readonly TargetLanguage[] = ["en", "de", "fr"];
const TRANSLATION_TIMEOUT_MS = 30_000;

interface ActiveTranslationRequest {
  readonly controller: AbortController;
  readonly timeoutId: ReturnType<typeof setTimeout>;
}

interface TranslationState {
  readonly status: TranslationStatus;
  readonly result: TranslateResponse | null;
  readonly error: string | null;
  readonly isTruncated: boolean;
  readonly translate: (
    documentId: string,
    sourceLang: string,
    targetLang: string,
    pages: readonly { page: number; text: string }[],
    options?: TranslationOptions
  ) => void;
  readonly reset: () => void;
}

export interface TranslationOptions {
  readonly classification?: DocumentClassification | null;
  readonly includeDocumentExplanation?: boolean;
}

export function useTranslationState(): TranslationState {
  const [status, setStatus] = useState<TranslationStatus>("empty");
  const [result, setResult] = useState<TranslateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isTruncated, setIsTruncated] = useState(false);
  const mountedRef = useRef(true);
  const requestIdRef = useRef(0);
  const activeRequestRef = useRef<ActiveTranslationRequest | null>(null);

  const cancelActiveRequest = useCallback(() => {
    const activeRequest = activeRequestRef.current;
    if (!activeRequest) return;
    clearTimeout(activeRequest.timeoutId);
    activeRequest.controller.abort();
    activeRequestRef.current = null;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
      cancelActiveRequest();
    };
  }, [cancelActiveRequest]);

  const translate = useCallback(
    async (
      documentId: string,
      sourceLang: string,
      targetLang: string,
      pages: readonly { page: number; text: string }[],
      options?: TranslationOptions
    ) => {
      const currentRequestId = ++requestIdRef.current;
      cancelActiveRequest();
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), TRANSLATION_TIMEOUT_MS);
      activeRequestRef.current = { controller, timeoutId };
      setStatus("loading");
      setError(null);
      setIsTruncated(false);
      try {
        const validLang = VALID_LANGUAGES.includes(targetLang as TargetLanguage)
          ? (targetLang as TargetLanguage)
          : "de";
        const res = await translateDocument(
          {
            document_id: documentId,
            source_language: sourceLang,
            target_language: validLang,
            preserve_layout: true,
            pages: [...pages],
            classification: options?.classification ?? undefined,
            include_document_explanation: options?.includeDocumentExplanation ?? false,
          },
          undefined,
          controller.signal
        );
        // Ignore stale responses from a previous language selection
        if (mountedRef.current && requestIdRef.current === currentRequestId) {
          setResult(res);
          setIsTruncated(isTranslationTruncated(res));
          if (res.status === "failed") {
            setError(res.error ?? TRANSLATION_ERROR_COPY.unavailable);
            setStatus("error");
          } else {
            setStatus("success");
          }
        }
      } catch (err) {
        if (mountedRef.current && requestIdRef.current === currentRequestId) {
          setError(
            controller.signal.aborted
              ? TRANSLATION_ERROR_COPY.timeout
              : err instanceof Error
                ? err.message
                : TRANSLATION_ERROR_COPY.unavailable
          );
          setStatus("error");
        }
      } finally {
        if (requestIdRef.current === currentRequestId) {
          clearTimeout(timeoutId);
          activeRequestRef.current = null;
        }
      }
    },
    [cancelActiveRequest]
  );

  const reset = useCallback(() => {
    requestIdRef.current += 1;
    cancelActiveRequest();
    setStatus("empty");
    setResult(null);
    setError(null);
    setIsTruncated(false);
  }, [cancelActiveRequest]);

  return { status, result, error, isTruncated, translate, reset };
}
