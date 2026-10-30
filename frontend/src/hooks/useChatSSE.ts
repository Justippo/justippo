"use client";

/**
 * MOBILE_GAP: EventSource is not available in React Native.
 * For mobile, use @microsoft/fetch-event-source or a similar
 * fetch-based SSE polyfill. See apps/mobile/README.md for guidance.
 * Tracked in: docs/mobile/mobile-compat.md
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { SEARCH_ERROR_COPY } from "@/data/mockData";
import { API_BASE } from "@/lib/config";
import type { JourneyState } from "@/lib/journey-state";
import type { SSEResult } from "@/hooks/useSearchSSE";
import type { SupportedLanguage } from "@evidenceeu/shared";

export interface ChatHistoryTurn {
  readonly role: "user" | "assistant";
  readonly content: string;
}

export interface ChatModelInfo {
  readonly provider: string;
  readonly provider_display: string;
  readonly model: string;
  readonly display_name: string;
}

export type ChatGuidanceOption =
  | {
      readonly label: string;
      readonly action: "submit";
      readonly query: string;
    }
  | {
      readonly label: string;
      readonly action: "compose";
      readonly prompt: string;
    };

export interface LegacyChatGuidanceOption {
  readonly label: string;
  readonly action?: undefined;
  readonly query: string;
}

export interface ChatGuidanceReference {
  readonly title: string;
  readonly url: string;
}

export interface ChatGuidance {
  readonly reason: "national_law" | "no_verified_source";
  readonly message: string;
  readonly question: string;
  readonly options: readonly (ChatGuidanceOption | LegacyChatGuidanceOption)[];
  readonly references: readonly ChatGuidanceReference[];
}

/* ── Structured journey response events ───────────────────────────────────── */

export interface ProgressSummary {
  readonly completed: number;
  readonly total: number;
}

export interface NextStepEvent {
  readonly step: string;
  readonly label: string;
  readonly description: string;
  readonly progress: ProgressSummary;
}

export interface ClarificationOption {
  readonly label: string;
  readonly value: string;
}

export interface ClarificationQuestionEvent {
  readonly question: string;
  readonly type: "yes_no" | "multiple_choice" | "free_text";
  readonly options?: readonly ClarificationOption[];
}

export interface DocumentItem {
  readonly name: string;
  readonly description: string;
  readonly required: boolean;
}

export interface DocumentChecklistEvent {
  readonly step: string;
  readonly documents: readonly DocumentItem[];
}

export interface ActionPlanStep {
  readonly label: string;
  readonly status: "completed" | "current" | "pending";
}

export interface ActionPlanEvent {
  readonly journey_type: string;
  readonly steps: readonly ActionPlanStep[];
}

interface ChatRequest {
  readonly message: string;
  readonly history: readonly ChatHistoryTurn[];
  readonly language: SupportedLanguage;
  readonly journey_state?: JourneyState | null;
}

type ChatStatus = "empty" | "loading" | "success" | "error";

interface ChatSSEState {
  readonly results: readonly SSEResult[];
  readonly answer: string;
  readonly model: ChatModelInfo | null;
  readonly guidance: ChatGuidance | null;
  readonly status: ChatStatus;
  readonly isStreaming: boolean;
  readonly error: string | null;
  /** Structured journey response events */
  readonly nextStep: NextStepEvent | null;
  readonly clarificationQuestion: ClarificationQuestionEvent | null;
  readonly documentChecklist: DocumentChecklistEvent | null;
  readonly actionPlan: ActionPlanEvent | null;
  readonly send: (
    message: string,
    history: readonly ChatHistoryTurn[],
    journeyState?: JourneyState | null,
    language?: SupportedLanguage
  ) => boolean;
  readonly retry: () => void;
  readonly reset: () => void;
}

const BACKOFF_MS = [2_000, 4_000, 8_000] as const;

interface ParsedEvent {
  readonly event: string;
  readonly data: unknown;
}

function parseEventBlock(block: string): ParsedEvent | null {
  const cleanBlock = block.replace(/\r\n?/g, "\n");
  let event = "message";
  const dataLines: string[] = [];

  for (const line of cleanBlock.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }

  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(raw) as unknown };
  } catch {
    return { event, data: raw };
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function useChatSSE(
  onJourneyStateUpdate?: (state: import("@/lib/journey-state").JourneyState) => void
): ChatSSEState {
  const [results, setResults] = useState<SSEResult[]>([]);
  const [answer, setAnswer] = useState("");
  const [model, setModel] = useState<ChatModelInfo | null>(null);
  const [guidance, setGuidance] = useState<ChatGuidance | null>(null);
  const [nextStep, setNextStep] = useState<NextStepEvent | null>(null);
  const [clarificationQuestion, setClarificationQuestion] =
    useState<ClarificationQuestionEvent | null>(null);
  const [documentChecklist, setDocumentChecklist] = useState<DocumentChecklistEvent | null>(null);
  const [actionPlan, setActionPlan] = useState<ActionPlanEvent | null>(null);
  const [status, setStatus] = useState<ChatStatus>("empty");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<ChatRequest | null>(null);
  const requestSequenceRef = useRef(0);
  const activeRequestIdRef = useRef<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryResolveRef = useRef<(() => void) | null>(null);
  const mountedRef = useRef(true);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    retryResolveRef.current?.();
    retryResolveRef.current = null;
  }, []);

  const abort = useCallback(() => {
    clearRetryTimer();
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, [clearRetryTimer]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abort();
    };
  }, [abort]);

  const startRequest = useCallback(
    (request: ChatRequest, requestId: number) => {
      abort();
      setResults([]);
      setAnswer("");
      setModel(null);
      setGuidance(null);
      setNextStep(null);
      setClarificationQuestion(null);
      setDocumentChecklist(null);
      setActionPlan(null);
      setStatus("loading");
      setIsStreaming(true);
      setError(null);

      const run = async (attempt: number): Promise<void> => {
        const controller = new AbortController();
        controllerRef.current = controller;
        let sawDone = false;

        const isCurrentRequest = (): boolean =>
          mountedRef.current &&
          activeRequestIdRef.current === requestId &&
          controllerRef.current === controller;

        const processEvent = (parsed: ParsedEvent): void => {
          if (!isCurrentRequest()) return;
          if (parsed.event === "journey_state_update" && typeof parsed.data === "object") {
            onJourneyStateUpdate?.(parsed.data as import("@/lib/journey-state").JourneyState);
          } else if (parsed.event === "result" && typeof parsed.data === "object") {
            setResults((previous) => [...previous, parsed.data as SSEResult]);
            setStatus("success");
          } else if (parsed.event === "answer_model" && typeof parsed.data === "object") {
            setModel(parsed.data as ChatModelInfo);
          } else if (parsed.event === "answer_chunk" && typeof parsed.data === "object") {
            const text = (parsed.data as { text?: unknown }).text;
            if (typeof text === "string") {
              setAnswer((previous) => previous + text);
              setStatus("success");
            }
          } else if (parsed.event === "guidance" && typeof parsed.data === "object") {
            setGuidance(parsed.data as ChatGuidance);
            setStatus("success");
          } else if (parsed.event === "next_step" && typeof parsed.data === "object") {
            setNextStep(parsed.data as NextStepEvent);
            setStatus("success");
          } else if (parsed.event === "clarification_question" && typeof parsed.data === "object") {
            setClarificationQuestion(parsed.data as ClarificationQuestionEvent);
            setStatus("success");
          } else if (parsed.event === "document_checklist" && typeof parsed.data === "object") {
            setDocumentChecklist(parsed.data as DocumentChecklistEvent);
            setStatus("success");
          } else if (parsed.event === "action_plan" && typeof parsed.data === "object") {
            setActionPlan(parsed.data as ActionPlanEvent);
            setStatus("success");
          } else if (parsed.event === "answer_error") {
            setModel(null);
            setGuidance(null);
          } else if (parsed.event === "error") {
            throw new Error("Chat application error");
          } else if (parsed.event === "done") {
            sawDone = true;
          }
        };

        try {
          const response = await fetch(`${API_BASE}/api/v1/chat/`, {
            method: "POST",
            headers: {
              Accept: "text/event-stream",
              "Content-Type": "application/json",
              "X-GDPR-Consent": "demo",
            },
            body: JSON.stringify(request),
            signal: controller.signal,
          });

          if (!response.ok || !response.body) {
            throw new Error(`Chat stream failed with status ${response.status}`);
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            let boundary = /\r\n\r\n|\r\n\r|\r\n\n|\r\r\n|\n\r\n|\r\r|\n\n/.exec(buffer);
            while (boundary) {
              const block = buffer.slice(0, boundary.index);
              buffer = buffer.slice(boundary.index + boundary[0].length);
              const parsed = parseEventBlock(block);
              if (parsed) processEvent(parsed);
              boundary = /\r\n\r\n|\r\n\r|\r\n\n|\r\r\n|\n\r\n|\r\r|\n\n/.exec(buffer);
            }
          }

          buffer += decoder.decode();
          const trailingEvent = parseEventBlock(buffer);
          if (trailingEvent) processEvent(trailingEvent);

          if (!sawDone) throw new Error("Chat stream ended before done");
          if (!isCurrentRequest()) return;
          controllerRef.current = null;
          activeRequestIdRef.current = null;
          setStatus((previous) => (previous === "loading" ? "success" : previous));
          setIsStreaming(false);
          setError(null);
        } catch (caught) {
          if (isAbortError(caught) || !isCurrentRequest()) {
            return;
          }

          if (attempt < BACKOFF_MS.length) {
            setResults([]);
            setAnswer("");
            setModel(null);
            setGuidance(null);
            setError(SEARCH_ERROR_COPY.retrying);
            await new Promise<void>((resolve) => {
              retryResolveRef.current = resolve;
              retryTimerRef.current = setTimeout(() => {
                retryTimerRef.current = null;
                retryResolveRef.current = null;
                resolve();
              }, BACKOFF_MS[attempt]);
            });
            if (mountedRef.current && controllerRef.current === controller) {
              await run(attempt + 1);
            }
            return;
          }

          controllerRef.current = null;
          activeRequestIdRef.current = null;
          setStatus("error");
          setIsStreaming(false);
          setError(SEARCH_ERROR_COPY.unavailable);
        }
      };

      void run(0);
    },
    [abort, onJourneyStateUpdate]
  );

  const send = useCallback(
    (
      message: string,
      history: readonly ChatHistoryTurn[],
      journeyState?: JourneyState | null,
      language: SupportedLanguage = "en"
    ): boolean => {
      if (activeRequestIdRef.current !== null) return false;
      const request: ChatRequest = {
        message: message.trim(),
        history: history.slice(-6),
        language,
        journey_state: journeyState,
      };
      requestSequenceRef.current += 1;
      const requestId = requestSequenceRef.current;
      activeRequestIdRef.current = requestId;
      requestRef.current = request;
      startRequest(request, requestId);
      return true;
    },
    [startRequest]
  );

  const retry = useCallback(() => {
    if (!requestRef.current || activeRequestIdRef.current !== null) return;
    requestSequenceRef.current += 1;
    const requestId = requestSequenceRef.current;
    activeRequestIdRef.current = requestId;
    startRequest(requestRef.current, requestId);
  }, [startRequest]);

  const reset = useCallback(() => {
    abort();
    activeRequestIdRef.current = null;
    requestRef.current = null;
    setResults([]);
    setAnswer("");
    setModel(null);
    setGuidance(null);
    setNextStep(null);
    setClarificationQuestion(null);
    setDocumentChecklist(null);
    setActionPlan(null);
    setStatus("empty");
    setIsStreaming(false);
    setError(null);
  }, [abort]);

  return {
    results,
    answer,
    model,
    guidance,
    nextStep,
    clarificationQuestion,
    documentChecklist,
    actionPlan,
    status,
    isStreaming,
    error,
    send,
    retry,
    reset,
  };
}
