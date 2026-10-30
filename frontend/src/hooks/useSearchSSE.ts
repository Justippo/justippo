"use client";

/**
 * MOBILE_GAP: EventSource is not available in React Native.
 * For mobile, use @microsoft/fetch-event-source or a similar
 * fetch-based SSE polyfill. See apps/mobile/README.md for guidance.
 * Tracked in: docs/mobile/mobile-compat.md
 */

import { useState, useRef, useCallback, useEffect } from "react";
import { SEARCH_ERROR_COPY } from "@/data/mockData";
import { API_BASE } from "@/lib/config";
import type { SearchSSEEvent } from "@/lib/api-generated";

export type SSEResult = SearchSSEEvent;

type SearchStatus = "empty" | "loading" | "success" | "error";

interface SearchSSEState {
  readonly results: readonly SSEResult[];
  readonly answer: string;
  readonly answerError: string | null;
  readonly status: SearchStatus;
  readonly isStreaming: boolean;
  readonly error: string | null;
  readonly retry: () => void;
  readonly search: (query: string) => void;
  readonly reset: () => void;
}

const BACKOFF_MS = [2000, 4000, 8000] as const;
const MAX_RETRIES = 3;

export function useSearchSSE(): SearchSSEState {
  const [results, setResults] = useState<SSEResult[]>([]);
  const [answer, setAnswer] = useState("");
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [status, setStatus] = useState<SearchStatus>("empty");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const queryRef = useRef("");
  const mountedRef = useRef(true);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
    };
  }, []);

  const closeConnection = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const startSearch = useCallback(
    (query: string) => {
      if (!query.trim()) {
        setStatus("empty");
        setResults([]);
        setAnswer("");
        setAnswerError(null);
        setIsStreaming(false);
        setError(null);
        return;
      }

      closeConnection();
      setStatus("loading");
      setIsStreaming(true);
      setError(null);
      setResults([]);
      setAnswer("");
      setAnswerError(null);

      const url = `${API_BASE}/api/v1/search/?q=${encodeURIComponent(query)}&gdpr_consent=demo`;
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("result", (event) => {
        if (!mountedRef.current || esRef.current !== es) return;
        try {
          const data = JSON.parse(event.data) as SSEResult;
          setResults((prev) => [...prev, data]);
          setStatus("success");
        } catch {
          // malformed JSON — skip this event
        }
      });

      es.addEventListener("answer_chunk", (event) => {
        if (!mountedRef.current || esRef.current !== es) return;
        try {
          const data = JSON.parse(event.data) as { text?: unknown };
          if (typeof data.text === "string") {
            setAnswer((previous) => previous + data.text);
            setStatus("success");
          }
        } catch {
          // malformed JSON — skip this event
        }
      });

      es.addEventListener("answer_error", (event) => {
        if (!mountedRef.current || esRef.current !== es) return;
        try {
          const data = JSON.parse(event.data) as { message?: unknown };
          if (typeof data.message === "string") setAnswerError(data.message);
        } catch {
          setAnswerError("Answer generation is temporarily unavailable.");
        }
      });

      es.addEventListener("results_complete", () => {
        // Retrieved RAG hits are fully delivered; the client can render them
        // now. The answer (if any) streams in after this as a progressive
        // enhancement and does not block result display.
        if (!mountedRef.current || esRef.current !== es) return;
        setStatus((prev) => (prev === "loading" ? "success" : prev));
      });

      es.addEventListener("done", () => {
        if (!mountedRef.current || esRef.current !== es) return;
        closeConnection();
        retriesRef.current = 0;
        setIsStreaming(false);
        // If no results came through, keep success (empty results list rendered)
        setStatus((prev) => (prev === "loading" ? "success" : prev));
      });

      es.addEventListener("error", (event) => {
        // Server-sent error event (application-level)
        if (!mountedRef.current || esRef.current !== es) return;
        closeConnection();
        // Counts against retry budget
        if (retriesRef.current < MAX_RETRIES) {
          const delay = BACKOFF_MS[retriesRef.current] ?? 8000;
          retriesRef.current++;
          retryTimerRef.current = setTimeout(() => {
            retryTimerRef.current = null;
            if (mountedRef.current) {
              startSearch(queryRef.current);
            }
          }, delay);
        } else {
          setStatus("error");
          setIsStreaming(false);
          setError(SEARCH_ERROR_COPY.unavailable);
          retriesRef.current = 0;
        }
      });

      // Transport-level error (connection drop or HTTP error)
      es.onerror = (event) => {
        // `event: error` SSE messages also reach the browser's `onerror`
        // handler. The application-level listener above already owns those.
        if (event instanceof MessageEvent) return;
        if (!mountedRef.current || esRef.current !== es) return;

        // When the connection is closed (HTTP error, server unreachable),
        // there is nothing to retry — set the error state immediately.
        if (es.readyState === EventSource.CLOSED) {
          closeConnection();
          setStatus("error");
          setIsStreaming(false);
          setError(SEARCH_ERROR_COPY.unavailable);
          retriesRef.current = 0;
          return;
        }

        closeConnection();

        if (retriesRef.current < MAX_RETRIES) {
          const delay = BACKOFF_MS[retriesRef.current] ?? 8000;
          retriesRef.current++;
          setError(SEARCH_ERROR_COPY.retrying);
          retryTimerRef.current = setTimeout(() => {
            retryTimerRef.current = null;
            if (mountedRef.current) {
              startSearch(queryRef.current);
            }
          }, delay);
        } else {
          setStatus("error");
          setIsStreaming(false);
          setError(SEARCH_ERROR_COPY.unavailable);
          retriesRef.current = 0;
        }
      };
    },
    [closeConnection]
  );

  const search = useCallback(
    (query: string) => {
      queryRef.current = query;
      retriesRef.current = 0;
      startSearch(query);
    },
    [startSearch]
  );

  const retry = useCallback(() => {
    if (queryRef.current) {
      retriesRef.current = 0;
      startSearch(queryRef.current);
    }
  }, [startSearch]);

  const reset = useCallback(() => {
    closeConnection();
    setResults([]);
    setAnswer("");
    setAnswerError(null);
    setStatus("empty");
    setIsStreaming(false);
    setError(null);
    retriesRef.current = 0;
    queryRef.current = "";
  }, [closeConnection]);

  return {
    results,
    answer,
    answerError,
    status,
    isStreaming,
    error,
    retry,
    search,
    reset,
  };
}
