"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/context/AuthContext";
import { CHAT_AUTH_PROMPT, CHAT_EMPTY_PROMPT, CHAT_MESSAGES } from "@/data/mockData";
import {
  useChatSSE,
  type ActionPlanEvent,
  type ChatGuidance,
  type ChatGuidanceOption,
  type ChatModelInfo,
  type ClarificationQuestionEvent,
  type DocumentChecklistEvent,
  type LegacyChatGuidanceOption,
  type NextStepEvent,
} from "@/hooks/useChatSSE";
import { trustedCitationUrl, trustedGuidanceUrl } from "@/hooks/useCitationAccess";
import { useJourneyState } from "@/hooks/useJourneyState";

export type ChatViewState = "loading" | "success" | "error" | "empty";

interface ChatSource {
  readonly title: string;
  readonly url: string;
}

interface ChatMessage {
  readonly id: string;
  readonly role: "user" | "assistant";
  readonly content: string;
  readonly sources?: readonly ChatSource[];
  readonly model?: ChatModelInfo;
  readonly guidance?: ChatGuidance;
}

interface UseChatViewOptions {
  readonly forcedState?: ChatViewState;
}

interface UseChatViewResult {
  readonly viewState: ChatViewState;
  readonly heading: string;
  readonly corpusLabel: string;
  readonly placeholder: string;
  readonly isAuthenticated: boolean;
  readonly isInputEnabled: boolean;
  readonly isSubmitDisabled: boolean;
  readonly isSubmitting: boolean;
  readonly showSignInPrompt: boolean;
  readonly inputHint: string | null;
  readonly emptyText: string;
  readonly messages: readonly ChatMessage[];
  readonly errorMessage: string | null;
  readonly query: string;
  readonly setQuery: (value: string) => void;
  readonly handleSubmit: (event: FormEvent<HTMLFormElement>) => void;
  readonly selectGuidanceOption: (
    option: ChatGuidanceOption | LegacyChatGuidanceOption,
    messageId: string
  ) => void;
  readonly retry: () => void;
  /** Structured journey state for guided-process engine */
  readonly journeyState: import("@/lib/journey-state").JourneyState;
  /** Reset journey state (called when starting a new conversation) */
  readonly resetJourney: () => void;
  /** Structured journey response events */
  readonly chatNextStep: NextStepEvent | null;
  readonly chatClarification: ClarificationQuestionEvent | null;
  readonly chatDocumentChecklist: DocumentChecklistEvent | null;
  readonly chatActionPlan: ActionPlanEvent | null;
  readonly selectClarificationOption: (value: string) => void;
}

const EMPTY_ANSWER =
  "I could not find a verified source that directly answers this question. Try adding the country, legal topic, and details about your situation.";
const ANSWER_UNAVAILABLE = "Search is temporarily unavailable — please try again.";

function sourcesFromResults(
  results: ReturnType<typeof useChatSSE>["results"]
): readonly ChatSource[] {
  const seen = new Set<string>();
  const sources: ChatSource[] = [];

  for (const result of results) {
    const url = trustedCitationUrl(result.source_url);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    sources.push({
      title: result.source_title || result.document_id || "Official EU source",
      url,
    });
  }

  return sources;
}

export function useChatView({ forcedState }: Readonly<UseChatViewOptions> = {}): UseChatViewResult {
  const { isAuthenticated } = useAuth();
  const journey = useJourneyState();
  const stream = useChatSSE(journey.updateFromResponse);
  const [query, setQuery] = useState("");
  const [composerPrompt, setComposerPrompt] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const activeAssistantIdRef = useRef<string | null>(null);
  const sequenceRef = useRef(0);

  const updateActiveAssistant = useCallback(
    (content: string, sources: readonly ChatSource[], model: ChatModelInfo | null) => {
      const activeId = activeAssistantIdRef.current;
      if (!activeId) return;

      setMessages((previous) =>
        previous.map((message) => {
          if (message.id !== activeId) return message;
          if (model) return { ...message, content, sources, model };
          const { model: _previousModel, ...messageWithoutModel } = message;
          return { ...messageWithoutModel, content, sources };
        })
      );
    },
    []
  );

  useEffect(() => {
    if (!activeAssistantIdRef.current) return;

    const sources = sourcesFromResults(stream.results);
    if (stream.guidance) {
      const guidance = {
        ...stream.guidance,
        references: stream.guidance.references.flatMap((reference) => {
          const url = trustedGuidanceUrl(reference.url);
          return url ? [{ ...reference, url }] : [];
        }),
      };
      const activeId = activeAssistantIdRef.current;
      if (activeId) {
        setMessages((previous) =>
          previous.map((message) =>
            message.id === activeId
              ? {
                  ...message,
                  content: guidance.message,
                  sources: [],
                  guidance,
                }
              : message
          )
        );
      }
      return;
    }
    if (stream.status === "error") {
      updateActiveAssistant(ANSWER_UNAVAILABLE, sources, null);
      return;
    }

    if (stream.answer) {
      updateActiveAssistant(stream.answer, sources, stream.model);
      return;
    }

    if (!stream.isStreaming && stream.status === "success") {
      updateActiveAssistant(stream.results[0]?.text || EMPTY_ANSWER, sources, null);
    }
  }, [
    stream.answer,
    stream.guidance,
    stream.isStreaming,
    stream.model,
    stream.results,
    stream.status,
    updateActiveAssistant,
  ]);

  const sendMessage = useCallback(
    (submittedQuery: string) => {
      if (!isAuthenticated || !submittedQuery || stream.isStreaming) return;

      sequenceRef.current += 1;
      const sequence = sequenceRef.current;
      const userMessage: ChatMessage = {
        id: `chat-user-${sequence}`,
        role: "user",
        content: submittedQuery,
      };
      const assistantMessage: ChatMessage = {
        id: `chat-assistant-${sequence}`,
        role: "assistant",
        content: "",
      };

      const history = messages
        .filter((message) => message.content && message.content !== ANSWER_UNAVAILABLE)
        .slice(-6)
        .map(({ role, content }) => ({ role, content }));

      // Record the question for repetition detection
      journey.recordQuestion(submittedQuery);

      if (!stream.send(submittedQuery, history, journey.state, "en")) return;

      activeAssistantIdRef.current = assistantMessage.id;
      setMessages((previous) => [...previous, userMessage, assistantMessage]);
      setQuery("");
      setComposerPrompt(null);
    },
    [isAuthenticated, messages, stream, journey]
  );

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const submittedQuery = query.trim();
      if (!submittedQuery) return;
      setQuery("");
      sendMessage(submittedQuery);
    },
    [query, sendMessage]
  );

  const selectGuidanceOption = useCallback(
    (option: ChatGuidanceOption | LegacyChatGuidanceOption, messageId: string) => {
      setMessages((previous) =>
        previous.map((message) => {
          if (message.id !== messageId) return message;
          const { guidance: _guidance, ...withoutGuidance } = message;
          return withoutGuidance;
        })
      );

      // Record the action for repetition detection
      if ("query" in option) {
        journey.recordAction(option.query);
      }

      if (option.action === "compose") {
        setQuery("");
        setComposerPrompt(option.prompt);
        window.setTimeout(() => document.getElementById("chat-query")?.focus(), 0);
        return;
      }

      sendMessage(option.query.trim());
    },
    [sendMessage, journey]
  );

  const selectClarificationOption = useCallback(
    (value: string) => {
      const clarification = stream.clarificationQuestion;
      if (!clarification) return;

      const option = clarification.options?.find((o) => o.value === value);
      const submittedQuery = option ? option.label : value;
      journey.recordAction(`clarification:${value}`);
      sendMessage(submittedQuery);
    },
    [stream.clarificationQuestion, sendMessage, journey]
  );

  const prompt = isAuthenticated ? CHAT_AUTH_PROMPT : CHAT_EMPTY_PROMPT;
  const liveViewState: ChatViewState = messages.length > 0 ? "success" : "empty";
  const viewState = forcedState ?? liveViewState;
  const visibleMessages = forcedState === "success" ? CHAT_MESSAGES : messages;
  const isInputEnabled = isAuthenticated;
  const isSubmitDisabled = !isInputEnabled || !query.trim() || stream.isStreaming;

  return useMemo(
    () => ({
      viewState,
      heading: prompt.heading,
      corpusLabel: prompt.corpusLabel,
      placeholder: composerPrompt ?? prompt.placeholder,
      isAuthenticated,
      isInputEnabled,
      isSubmitDisabled,
      isSubmitting: stream.isStreaming,
      showSignInPrompt: !isAuthenticated,
      inputHint: isAuthenticated ? CHAT_AUTH_PROMPT.inputHint : null,
      emptyText: "Ask a question about EU regulations or cross-border legal requirements.",
      messages: visibleMessages,
      errorMessage:
        forcedState === "error"
          ? "We could not load the conversation. Refresh the page or try again."
          : stream.error,
      query,
      setQuery,
      handleSubmit,
      selectGuidanceOption,
      retry: stream.retry,
      journeyState: journey.state,
      resetJourney: journey.reset,
      chatNextStep: stream.nextStep,
      chatClarification: stream.clarificationQuestion,
      chatDocumentChecklist: stream.documentChecklist,
      chatActionPlan: stream.actionPlan,
      selectClarificationOption,
    }),
    [
      forcedState,
      composerPrompt,
      handleSubmit,
      isAuthenticated,
      isInputEnabled,
      isSubmitDisabled,
      journey.reset,
      journey.state,
      prompt,
      query,
      selectClarificationOption,
      selectGuidanceOption,
      stream.actionPlan,
      stream.clarificationQuestion,
      stream.documentChecklist,
      stream.error,
      stream.isStreaming,
      stream.nextStep,
      stream.retry,
      viewState,
      visibleMessages,
    ]
  );
}
