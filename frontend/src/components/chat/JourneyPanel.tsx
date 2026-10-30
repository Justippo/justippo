"use client";

import { Check, Circle, ChevronRight, FileText, HelpCircle } from "lucide-react";
import type {
  ActionPlanEvent,
  ClarificationQuestionEvent,
  DocumentChecklistEvent,
  NextStepEvent,
} from "@/hooks/useChatSSE";
import styles from "./JourneyPanel.module.css";

interface JourneyPanelProps {
  readonly nextStep: NextStepEvent | null;
  readonly clarificationQuestion: ClarificationQuestionEvent | null;
  readonly documentChecklist: DocumentChecklistEvent | null;
  readonly actionPlan: ActionPlanEvent | null;
  readonly onSelectOption?: (value: string) => void;
}

export function JourneyPanel({
  nextStep,
  clarificationQuestion,
  documentChecklist,
  actionPlan,
  onSelectOption,
}: Readonly<JourneyPanelProps>) {
  const hasContent = nextStep || clarificationQuestion || documentChecklist || actionPlan;
  if (!hasContent) return null;

  return (
    <aside className={styles.panel} aria-label="Journey progress">
      {actionPlan && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Your action plan</h3>
          <ol className={styles.stepsList}>
            {actionPlan.steps.map((step) => (
              <li
                key={step.label}
                className={`${styles.stepItem} ${styles[step.status]}`}
                aria-current={step.status === "current" ? "step" : undefined}
              >
                <span className={styles.stepIcon}>
                  {step.status === "completed" ? (
                    <Check size={16} aria-hidden="true" />
                  ) : (
                    <Circle size={16} aria-hidden="true" />
                  )}
                </span>
                <span className={styles.stepLabel}>{step.label}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {nextStep && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <ChevronRight size={16} aria-hidden="true" />
            Current step: {nextStep.label}
          </h3>
          <p className={styles.description}>{nextStep.description}</p>
          <p className={styles.progress}>
            Step {nextStep.progress.completed + 1} of {nextStep.progress.total}
          </p>
        </section>
      )}

      {clarificationQuestion && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <HelpCircle size={16} aria-hidden="true" />
            We need to know
          </h3>
          <p className={styles.question}>{clarificationQuestion.question}</p>
          {clarificationQuestion.options && clarificationQuestion.options.length > 0 && (
            <div className={styles.optionsList}>
              {clarificationQuestion.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={styles.optionButton}
                  onClick={() => onSelectOption?.(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </section>
      )}

      {documentChecklist && documentChecklist.documents.length > 0 && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>
            <FileText size={16} aria-hidden="true" />
            Documents you may need
          </h3>
          <ul className={styles.docsList}>
            {documentChecklist.documents.map((doc) => (
              <li key={doc.name} className={styles.docItem}>
                <span className={styles.docName}>
                  {doc.name}
                  {doc.required && (
                    <span className={styles.requiredBadge} aria-label="Required">
                      Required
                    </span>
                  )}
                </span>
                <span className={styles.docDescription}>{doc.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
