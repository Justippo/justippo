"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  PdfReferenceApiError,
  translatePdfReference,
  type PdfReferenceTranslationResponse,
} from "@/lib/api-generated";

export type PdfReferenceStatus = "empty" | "loading" | "success" | "error";

interface ActiveRequest {
  readonly controller: AbortController;
  readonly timeoutId: ReturnType<typeof setTimeout>;
}

interface PdfReferenceTranslationState {
  readonly status: PdfReferenceStatus;
  readonly result: PdfReferenceTranslationResponse | null;
  readonly error: string | null;
  readonly sourcePdfUrl: string | null;
  readonly translatedPdfUrl: string | null;
  readonly warningMessages: readonly string[];
  readonly translate: (
    file: File,
    sourceLanguage: string,
    targetLanguage: string,
    expectedPageCount: number
  ) => void;
  readonly reset: () => void;
}

const PDF_REFERENCE_TIMEOUT_MS = 310_000;
const PDF_REFERENCE_ERROR_COPY =
  "PDF reference translation could not be completed. Please try again.";
const BASE64_PATTERN = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

const WARNING_COPY: Readonly<Record<string, string>> = {
  NO_VERIFIED_EU_LAW_SOURCE: "No verified EU-law source was found for this document.",
  LEGAL_RETRIEVAL_UNAVAILABLE: "EU-law sources are temporarily unavailable.",
  EXPLANATION_GENERATION_UNAVAILABLE:
    "Verified sources are available, but a plain-language explanation could not be generated.",
  GENERATED_CITATIONS_UNVERIFIED:
    "The generated explanation was withheld because its citations could not be verified.",
  DOCUMENT_EXPLANATION_UNAVAILABLE:
    "The translated reference is ready, but document guidance is temporarily unavailable.",
  REFERENCE_COPY_ONLY: "This translated PDF is a reference copy, not an official replacement.",
  SIDECAR_LANGUAGE_PAIR_UNVERIFIED:
    "The translation service could not confirm its language-pair metadata.",
};

function errorCopy(error: unknown, aborted: boolean): string {
  if (aborted) {
    return "PDF translation took too long. Please try again.";
  }
  if (!(error instanceof PdfReferenceApiError)) {
    return PDF_REFERENCE_ERROR_COPY;
  }
  switch (error.code) {
    case "PASSWORD_REQUIRED":
      return "This PDF is password-protected. Upload an unprotected copy to continue.";
    case "PAGE_LIMIT_EXCEEDED":
      return "This PDF exceeds the current reference translation page limit.";
    case "FILE_TOO_LARGE":
      return "This PDF exceeds the current reference translation file-size limit.";
    case "INVALID_LANGUAGE_PAIR":
      return "Choose different source and target languages.";
    case "PROCESSING_TIMEOUT":
      return "PDF translation took too long. Please try again.";
    case "SERVICE_UNAVAILABLE":
      return "PDF reference translation is temporarily unavailable. Please try again later.";
    case "TRANSLATION_QUALITY_FAILED":
      return "The translated PDF did not pass readability and language checks. Please try again.";
    default:
      return PDF_REFERENCE_ERROR_COPY;
  }
}

function pdfBlobFromBase64(value: unknown): Blob {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length % 4 !== 0 ||
    !BASE64_PATTERN.test(value)
  ) {
    throw new Error("Invalid translated PDF payload");
  }

  let binary: string;
  try {
    binary = window.atob(value);
  } catch {
    throw new Error("Invalid translated PDF payload");
  }
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: "application/pdf" });
}

export function usePdfReferenceTranslation(sourceFile: File | null): PdfReferenceTranslationState {
  const [status, setStatus] = useState<PdfReferenceStatus>("empty");
  const [result, setResult] = useState<PdfReferenceTranslationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourcePdfUrl, setSourcePdfUrl] = useState<string | null>(null);
  const [translatedPdfUrl, setTranslatedPdfUrl] = useState<string | null>(null);
  const activeRequestRef = useRef<ActiveRequest | null>(null);
  const requestIdRef = useRef(0);
  const mountedRef = useRef(true);

  const cancelActiveRequest = useCallback(() => {
    if (!activeRequestRef.current) return;
    clearTimeout(activeRequestRef.current.timeoutId);
    activeRequestRef.current.controller.abort();
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

  useEffect(() => {
    if (!sourceFile) {
      setSourcePdfUrl(null);
      return;
    }
    const url = URL.createObjectURL(sourceFile);
    setSourcePdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [sourceFile]);

  useEffect(() => {
    if (!result) {
      setTranslatedPdfUrl(null);
      return;
    }
    try {
      const url = URL.createObjectURL(pdfBlobFromBase64(result.translated_pdf_b64));
      setTranslatedPdfUrl(url);
      return () => URL.revokeObjectURL(url);
    } catch {
      setTranslatedPdfUrl(null);
      setResult(null);
      setError(PDF_REFERENCE_ERROR_COPY);
      setStatus("error");
    }
  }, [result]);

  const translate = useCallback(
    async (
      file: File,
      sourceLanguage: string,
      targetLanguage: string,
      expectedPageCount: number
    ) => {
      const currentRequestId = ++requestIdRef.current;
      cancelActiveRequest();
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), PDF_REFERENCE_TIMEOUT_MS);
      activeRequestRef.current = { controller, timeoutId };
      setStatus("loading");
      setResult(null);
      setError(null);

      try {
        const response = await translatePdfReference(
          file,
          sourceLanguage,
          targetLanguage,
          expectedPageCount,
          undefined,
          controller.signal
        );
        if (
          response.source_language !== sourceLanguage.trim().toLowerCase() ||
          response.target_language !== targetLanguage.trim().toLowerCase()
        ) {
          throw new PdfReferenceApiError(
            "TRANSLATION_QUALITY_FAILED",
            "Translation response language pair did not match the active request",
            true
          );
        }
        if (mountedRef.current && requestIdRef.current === currentRequestId) {
          setResult(response);
          setStatus("success");
        }
      } catch (requestError) {
        if (mountedRef.current && requestIdRef.current === currentRequestId) {
          setError(errorCopy(requestError, controller.signal.aborted));
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
  }, [cancelActiveRequest]);

  return {
    status,
    result,
    error,
    sourcePdfUrl,
    translatedPdfUrl,
    warningMessages: (result?.warnings ?? []).map(
      (warning) => WARNING_COPY[warning] ?? "Some document guidance could not be produced."
    ),
    translate,
    reset,
  };
}
