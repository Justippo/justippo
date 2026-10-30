"use client";

/**
 * MOBILE_GAP: DOM File API is not available in React Native.
 * For mobile, use expo-document-picker + expo-file-system.
 * See apps/mobile/README.md for guidance.
 * Tracked in: docs/mobile/mobile-compat.md
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { useOfflineMode } from "@/context/OfflineModeContext";
import type { TranslateResponse } from "@/lib/api-generated";
import { isTranslationTruncated } from "@/lib/translation-truncation";
import { useTranslationState, type TranslationOptions } from "./useTranslationState";

export type TranslationStatus = "empty" | "loading" | "success" | "error";

interface TranslateHookState {
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

const DEMO_TRANSLATE_DELAY_MS = 400;

/**
 * Canonical translation hook: live API when healthy, demo-fallback translate result
 * when sample-data mode is active (renders as normal success UI).
 */
export function useTranslate(): TranslateHookState {
  const { isOfflineMode, fallbackData } = useOfflineMode();
  const live = useTranslationState();
  const liveTranslate = live.translate;

  const [demoStatus, setDemoStatus] = useState<TranslationStatus>("empty");
  const [demoResult, setDemoResult] = useState<TranslateResponse | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);
  const [demoTruncated, setDemoTruncated] = useState(false);

  const translateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const fallbackTranslate = fallbackData?.translate;
  const useFallback = isOfflineMode && fallbackTranslate != null;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (translateTimerRef.current) {
        clearTimeout(translateTimerRef.current);
        translateTimerRef.current = null;
      }
    };
  }, []);

  const clearTranslateTimer = useCallback(() => {
    if (translateTimerRef.current) {
      clearTimeout(translateTimerRef.current);
      translateTimerRef.current = null;
    }
  }, []);

  const runFallbackTranslate = useCallback(() => {
    if (!fallbackTranslate) return;

    clearTranslateTimer();
    setDemoStatus("loading");
    setDemoError(null);
    setDemoResult(null);
    setDemoTruncated(false);

    translateTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      setDemoResult(fallbackTranslate);
      setDemoTruncated(isTranslationTruncated(fallbackTranslate));
      setDemoStatus("success");
      translateTimerRef.current = null;
    }, DEMO_TRANSLATE_DELAY_MS);
  }, [clearTranslateTimer, fallbackTranslate]);

  const translate = useCallback(
    (
      _documentId: string,
      _sourceLang: string,
      _targetLang: string,
      _pages: readonly { page: number; text: string }[],
      options?: TranslationOptions
    ) => {
      if (useFallback) {
        runFallbackTranslate();
        return;
      }
      if (options) {
        liveTranslate(_documentId, _sourceLang, _targetLang, _pages, options);
      } else {
        liveTranslate(_documentId, _sourceLang, _targetLang, _pages);
      }
    },
    [useFallback, runFallbackTranslate, liveTranslate]
  );

  const reset = useCallback(() => {
    if (useFallback) {
      clearTranslateTimer();
      setDemoStatus("empty");
      setDemoResult(null);
      setDemoError(null);
      setDemoTruncated(false);
      return;
    }
    live.reset();
  }, [useFallback, clearTranslateTimer, live]);

  if (useFallback) {
    return {
      status: demoStatus,
      result: demoResult,
      error: demoError,
      isTruncated: demoTruncated,
      translate,
      reset,
    };
  }

  return {
    status: live.status,
    result: live.result,
    error: live.error,
    isTruncated: live.isTruncated,
    translate,
    reset,
  };
}
