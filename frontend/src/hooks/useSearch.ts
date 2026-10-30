"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useOfflineMode } from "@/context/OfflineModeContext";
import type { SearchSSEEvent } from "@/lib/api-generated";
import { useSearchSSE } from "./useSearchSSE";

export type SSEResult = SearchSSEEvent;
export type SearchStatus = "empty" | "loading" | "success" | "error";

interface SearchState {
  readonly results: readonly SSEResult[];
  readonly status: SearchStatus;
  readonly error: string | null;
  readonly retry: () => void;
  readonly search: (query: string) => void;
  readonly reset: () => void;
}

const DEMO_STREAM_DELAY_MS = 300;

/**
 * Canonical search hook: live SSE when the API is healthy, demo-fallback results
 * when sample-data mode is active (§1.5 — search always returns results offline).
 */
export function useSearch(): SearchState {
  const { isOfflineMode, fallbackData } = useOfflineMode();
  const {
    results: liveResults,
    status: liveStatus,
    error: liveError,
    retry: liveRetry,
    search: liveSearch,
    reset: liveReset,
  } = useSearchSSE();

  const [demoResults, setDemoResults] = useState<SSEResult[]>([]);
  const [demoStatus, setDemoStatus] = useState<SearchStatus>("empty");
  const [demoError, setDemoError] = useState<string | null>(null);

  const queryRef = useRef("");
  const streamTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const fallbackResults = fallbackData?.search;
  const useFallback = isOfflineMode && Array.isArray(fallbackResults) && fallbackResults.length > 0;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (streamTimerRef.current) {
        clearTimeout(streamTimerRef.current);
        streamTimerRef.current = null;
      }
    };
  }, []);

  const clearStreamTimer = useCallback(() => {
    if (streamTimerRef.current) {
      clearTimeout(streamTimerRef.current);
      streamTimerRef.current = null;
    }
  }, []);

  const runFallbackSearch = useCallback(
    (_query: string) => {
      clearStreamTimer();
      setDemoStatus("loading");
      setDemoError(null);
      setDemoResults([]);

      streamTimerRef.current = setTimeout(() => {
        if (!mountedRef.current) return;
        setDemoResults([...(fallbackResults ?? [])]);
        setDemoStatus("success");
        streamTimerRef.current = null;
      }, DEMO_STREAM_DELAY_MS);
    },
    [clearStreamTimer, fallbackResults]
  );

  const search = useCallback(
    (query: string) => {
      queryRef.current = query;

      if (!query.trim()) {
        if (useFallback) {
          clearStreamTimer();
          setDemoStatus("empty");
          setDemoResults([]);
          setDemoError(null);
        } else {
          liveSearch("");
        }
        return;
      }

      if (useFallback) {
        runFallbackSearch(query);
        return;
      }

      liveSearch(query);
    },
    [useFallback, clearStreamTimer, runFallbackSearch, liveSearch]
  );

  const retry = useCallback(() => {
    if (!queryRef.current.trim()) return;

    if (useFallback) {
      runFallbackSearch(queryRef.current);
      return;
    }

    liveRetry();
  }, [useFallback, runFallbackSearch, liveRetry]);

  const reset = useCallback(() => {
    queryRef.current = "";
    if (useFallback) {
      clearStreamTimer();
      setDemoStatus("empty");
      setDemoResults([]);
      setDemoError(null);
      return;
    }
    liveReset();
  }, [useFallback, clearStreamTimer, liveReset]);

  if (useFallback) {
    return {
      results: demoResults,
      status: demoStatus,
      error: demoError,
      retry,
      search,
      reset,
    };
  }

  return {
    results: liveResults,
    status: liveStatus,
    error: liveError,
    retry: liveRetry,
    search,
    reset: liveReset,
  };
}
