"use client";

/**
 * MOBILE_GAP: DOM File API is not available in React Native.
 * For mobile, use expo-document-picker + expo-file-system.
 * See apps/mobile/README.md for guidance.
 * Tracked in: docs/mobile/mobile-compat.md
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { useOfflineMode } from "@/context/OfflineModeContext";
import type { UploadResponse } from "@/lib/api-generated";
import { saveUploadSession } from "@/lib/upload-session";
import { useUploadState } from "./useUploadState";

export type UploadStatus = "empty" | "loading" | "success" | "error";
type UploadMode = "live" | "fallback";

interface UploadHookState {
  readonly status: UploadStatus;
  readonly result: UploadResponse | null;
  readonly error: string | null;
  readonly upload: (file: File, targetLang: string) => void;
  readonly reset: () => void;
}

const DEMO_UPLOAD_DELAY_MS = 400;

/**
 * Canonical upload hook: live OCR API when healthy, demo-fallback upload result
 * when sample-data mode is active (renders as normal success UI).
 */
export function useUpload(): UploadHookState {
  const { isOfflineMode, fallbackData } = useOfflineMode();
  const live = useUploadState();

  const [demoStatus, setDemoStatus] = useState<UploadStatus>("empty");
  const [demoResult, setDemoResult] = useState<UploadResponse | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [activeMode, setActiveMode] = useState<UploadMode | null>(null);

  const uploadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const fallbackUpload = fallbackData?.upload;
  const useFallback = isOfflineMode && fallbackUpload != null;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (uploadTimerRef.current) {
        clearTimeout(uploadTimerRef.current);
        uploadTimerRef.current = null;
      }
    };
  }, []);

  const clearUploadTimer = useCallback(() => {
    if (uploadTimerRef.current) {
      clearTimeout(uploadTimerRef.current);
      uploadTimerRef.current = null;
    }
  }, []);

  const runFallbackUpload = useCallback(
    (file: File, targetLang: string) => {
      if (!fallbackUpload) return;

      clearUploadTimer();
      setDemoStatus("loading");
      setDemoError(null);
      setDemoResult(null);

      uploadTimerRef.current = setTimeout(() => {
        if (!mountedRef.current) return;
        setDemoResult(fallbackUpload);
        setDemoStatus("success");
        saveUploadSession(file, fallbackUpload, targetLang);
        uploadTimerRef.current = null;
      }, DEMO_UPLOAD_DELAY_MS);
    },
    [clearUploadTimer, fallbackUpload]
  );

  const upload = useCallback(
    (file: File, targetLang: string) => {
      if (useFallback) {
        setActiveMode("fallback");
        runFallbackUpload(file, targetLang);
        return;
      }
      setActiveMode("live");
      live.upload(file, targetLang);
    },
    [useFallback, runFallbackUpload, live]
  );

  const reset = useCallback(() => {
    clearUploadTimer();
    setDemoStatus("empty");
    setDemoResult(null);
    setDemoError(null);
    live.reset();
    setActiveMode(null);
  }, [clearUploadTimer, live]);

  const returnFallback = activeMode === "fallback" || (activeMode === null && useFallback);

  if (returnFallback) {
    return {
      status: demoStatus,
      result: demoResult,
      error: demoError,
      upload,
      reset,
    };
  }

  return {
    status: live.status,
    result: live.result,
    error: live.error,
    upload,
    reset,
  };
}
