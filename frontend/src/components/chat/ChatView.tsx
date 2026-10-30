"use client";

import styles from "./ChatView.module.css";
import { useChatView, type ChatViewState } from "@/hooks/useChatView";
import { Badge, Button } from "@/components/atoms";
import { SkeletonText } from "@/components/atoms";
import { JourneyPanel } from "@/components/chat/JourneyPanel";

interface ChatViewProps {
  readonly className?: string;
  readonly forcedState?: ChatViewState;
}

export function ChatView({ className = "", forcedState }: Readonly<ChatViewProps>) {
  const chat = useChatView({ forcedState });

  if (chat.viewState === "loading") {
    return (
      <div
        className={`${styles.container} ${className}`}
        role="status"
        aria-busy="true"
        aria-label="Loading chat"
      >
        <SkeletonText lines={2} />
        <SkeletonText lines={4} />
      </div>
    );
  }

  if (chat.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <div className={styles.header}>
          <h1 className={styles.heading}>{chat.heading}</h1>
          <Badge variant="info" data-testid="chat-corpus-badge">
            {chat.corpusLabel}
          </Badge>
        </div>
        <div className={styles.errorState} role="alert">
          <p className={styles.errorText}>{chat.errorMessage}</p>
          <a href="/chat" className={styles.retryLink}>
            Try again
          </a>
        </div>
      </div>
    );
  }

  const hasJourneyContent =
    chat.chatNextStep !== null ||
    chat.chatClarification !== null ||
    chat.chatDocumentChecklist !== null ||
    chat.chatActionPlan !== null;

  return (
    <div className={`${styles.container} ${className}`}>
      <div className={styles.header}>
        <h1 className={styles.heading}>{chat.heading}</h1>
        <Badge variant="info" data-testid="chat-corpus-badge">
          {chat.corpusLabel}
        </Badge>
      </div>

      <div className={styles.disclaimer} role="note">
        <strong>Note:</strong> This assistant provides EU-level legal research citations, not legal
        advice. Answers are generated strictly from verified official sources and do not account for
        your national procedures or personal circumstances. Always confirm requirements with a
        qualified professional or the relevant authority before acting.
      </div>

      <div className={hasJourneyContent ? styles.workspace : undefined}>
        {hasJourneyContent && (
          <JourneyPanel
            nextStep={chat.chatNextStep}
            clarificationQuestion={chat.chatClarification}
            documentChecklist={chat.chatDocumentChecklist}
            actionPlan={chat.chatActionPlan}
            onSelectOption={chat.selectClarificationOption}
          />
        )}
        <div>
          {chat.viewState === "empty" && (
            <div className={styles.emptyState}>
              <p className={styles.emptyText}>{chat.emptyText}</p>
            </div>
          )}

          {chat.viewState === "success" && chat.messages.length > 0 && (
            <div className={styles.messages} aria-label="Conversation" aria-live="polite">
              {chat.messages.map((msg) => (
                <div key={msg.id} className={`${styles.message} ${styles[msg.role]}`}>
                  <div className={styles.bubble}>
                    <p className={styles.content}>{msg.content || "Searching…"}</p>
                    {msg.role === "assistant" && msg.model && (
                      <p className={styles.modelAttribution} title={msg.model.model}>
                        Answered by {msg.model.display_name} via {msg.model.provider_display} ·
                        Retrieved with Hindsight
                      </p>
                    )}
                    {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                      <div className={styles.sources}>
                        {msg.sources.map((src) => (
                          <a
                            key={src.title}
                            href={src.url}
                            className={styles.sourceLink}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <Badge variant="info">{src.title}</Badge>
                          </a>
                        ))}
                      </div>
                    )}
                    {msg.role === "assistant" && msg.guidance && (
                      <div className={styles.guidance}>
                        <p className={styles.guidanceQuestion}>{msg.guidance.question}</p>
                        <div
                          className={styles.guidanceOptions}
                          aria-label="Suggested next questions"
                        >
                          {msg.guidance.options.map((option) => (
                            <button
                              key={`${option.action ?? "submit"}-${option.label}`}
                              type="button"
                              className={styles.guidanceOption}
                              onClick={() => chat.selectGuidanceOption(option, msg.id)}
                              disabled={chat.isSubmitting}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                        {msg.guidance.references.length > 0 && (
                          <div className={styles.guidanceReferences}>
                            <span>Official reference:</span>
                            {msg.guidance.references.map((reference) => (
                              <a
                                key={reference.url}
                                href={reference.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {reference.title}
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <form className={styles.inputArea} onSubmit={chat.handleSubmit}>
        <label className={styles.inputLabel} htmlFor="chat-query">
          {chat.placeholder}
        </label>
        <input
          id="chat-query"
          type="text"
          className={styles.chatInput}
          placeholder={chat.placeholder}
          value={chat.query}
          onChange={(event) => chat.setQuery(event.target.value)}
          disabled={!chat.isInputEnabled || chat.isSubmitting}
          aria-describedby={chat.showSignInPrompt ? "chat-sign-in-hint" : "chat-input-hint"}
        />
        {chat.showSignInPrompt ? (
          <p id="chat-sign-in-hint" className={styles.loginPrompt}>
            <a href="/login" className={styles.loginLink}>
              Sign in
            </a>{" "}
            to ask questions using the EUR-Lex public corpus.
          </p>
        ) : (
          <p id="chat-input-hint" className={styles.inputHint}>
            {chat.inputHint}
          </p>
        )}
        {chat.errorMessage && (
          <div className={styles.inlineError} role="alert">
            <p>{chat.errorMessage}</p>
            <Button type="button" variant="secondary" onClick={chat.retry}>
              Try again
            </Button>
          </div>
        )}
        {chat.isInputEnabled && (
          <div className={styles.sendButton}>
            <Button type="submit" variant="primary" disabled={chat.isSubmitDisabled}>
              {chat.isSubmitting ? "Searching…" : "Send"}
            </Button>
          </div>
        )}
      </form>
    </div>
  );
}
