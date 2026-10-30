"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import {
  clearUploadSession,
  readUploadSession,
  updateUploadSessionTargetLanguage,
} from "@/lib/upload-session";
import type { TranslationResultMode } from "./useTranslationView";

export type TranslationWorkflowStage = "checking" | "upload" | "translate";

interface TranslationWorkflowState {
  readonly stage: TranslationWorkflowStage;
  readonly resultMode: TranslationResultMode;
  readonly referenceFile: File | null;
  readonly onContinue: (targetLang: string, file: File | null) => void;
  readonly onChooseAnother: () => void;
}

export function useTranslationWorkflow(): TranslationWorkflowState {
  const [stage, setStage] = useState<TranslationWorkflowStage>("checking");
  const [resultMode, setResultMode] = useState<TranslationResultMode>("translation");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const requestedView = searchParams?.get("view") ?? null;
  const requestedStart = searchParams?.get("start") ?? null;
  const requestedDocumentId = searchParams?.get("documentId") ?? null;
  const isViewerRoute = pathname === "/viewer";

  useEffect(() => {
    setResultMode(requestedView === "compare" ? "compare" : "translation");
    // Explicit upload start: always clear and go to upload
    if (requestedStart === "upload") {
      clearUploadSession();
      setStage("upload");
      return;
    }
    // Viewer route, compare view, and an explicit documentId (set by onContinue
    // below, or a bookmarked/shared link) preserve session and skip to translate.
    if (isViewerRoute || requestedView === "compare" || requestedDocumentId) {
      const existing = readUploadSession();
      setStage(existing.documentId ? "translate" : "upload");
      return;
    }
    // Fresh visit to /translation: clear and start at upload
    clearUploadSession();
    setStage("upload");
  }, [requestedStart, requestedView, requestedDocumentId, isViewerRoute]);

  const onContinue = useCallback(
    (targetLang: string, file: File | null) => {
      updateUploadSessionTargetLanguage(targetLang);
      const session = readUploadSession();
      setReferenceFile(
        session.pdfProcessingMode === "pdf_reference_translation" &&
          file?.type === "application/pdf"
          ? file
          : null
      );
      setStage("translate");
      // Reflect the active document in the URL so the translation view is
      // shareable/bookmarkable and a page refresh can be validated against
      // the session (sessionStorage remains the source of truth for content;
      // this is a URL-level pointer, not a second storage mechanism).
      if (session.documentId) {
        router.replace(`/translation?documentId=${encodeURIComponent(session.documentId)}`);
      }
    },
    [router]
  );

  const onChooseAnother = useCallback(() => {
    setReferenceFile(null);
    clearUploadSession();
    setStage("upload");
    if (requestedStart !== "upload") {
      router.replace("/translation?start=upload");
    }
  }, [requestedStart, router]);

  return { stage, resultMode, referenceFile, onContinue, onChooseAnother };
}
