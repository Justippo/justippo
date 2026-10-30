/**
 * Structured ephemeral journey state for guided-process chat.
 *
 * This state lives in browser memory and is submitted with each request.
 * The backend can update it based on the conversation and return the new state.
 */

/**
 * Journey types supported by the guided-process engine.
 */
export type JourneyType = "work" | "relocate" | "study" | "maintain" | "other";

/**
 * Citizenship groups for EU-law classification.
 */
export type CitizenshipGroup = "eu_citizen" | "non_eu" | "unknown";

/**
 * Journey state tracking where the user is in their guided process.
 */
export interface JourneyState {
  /** The detected journey type (set by backend on first turn) */
  readonly journey_type: JourneyType | null;

  /** Jurisdiction (e.g., "DE", "FR", "AT") */
  readonly jurisdiction: string | null;

  /** Citizenship group classification */
  readonly citizenship_group: CitizenshipGroup | null;

  /** Key facts collected so far (job offer, profession regulated, etc.) */
  readonly facts: Readonly<Record<string, unknown>>;

  /** Current step in the journey playbook */
  readonly current_step: string | null;

  /** Steps already completed */
  readonly completed_steps: ReadonlyArray<string>;

  /** Actions offered to the user (for repetition prevention) */
  readonly offered_actions: ReadonlyArray<string>;

  /** Questions already asked (for repetition prevention) */
  readonly asked_questions: ReadonlyArray<string>;

  /** Facts already confirmed (for repetition prevention) */
  readonly confirmed_facts: ReadonlyArray<string>;

  /** Sources already shown (for repetition prevention) */
  readonly shown_sources: ReadonlyArray<string>;

  /** Number of turns in this journey (for timeout detection) */
  readonly turn_count: number;
}

/**
 * Create an empty initial journey state.
 */
export function createInitialJourneyState(): JourneyState {
  return {
    journey_type: null,
    jurisdiction: null,
    citizenship_group: null,
    facts: {},
    current_step: null,
    completed_steps: [],
    offered_actions: [],
    asked_questions: [],
    confirmed_facts: [],
    shown_sources: [],
    turn_count: 0,
  };
}

/**
 * Check if two journey states are effectively equal (for change detection).
 */
export function journeyStatesEqual(a: JourneyState, b: JourneyState): boolean {
  return (
    a.journey_type === b.journey_type &&
    a.jurisdiction === b.jurisdiction &&
    a.citizenship_group === b.citizenship_group &&
    a.current_step === b.current_step &&
    a.turn_count === b.turn_count &&
    JSON.stringify(a.facts) === JSON.stringify(b.facts) &&
    JSON.stringify(a.completed_steps) === JSON.stringify(b.completed_steps) &&
    JSON.stringify(a.offered_actions) === JSON.stringify(b.offered_actions) &&
    JSON.stringify(a.asked_questions) === JSON.stringify(b.asked_questions) &&
    JSON.stringify(a.confirmed_facts) === JSON.stringify(b.confirmed_facts) &&
    JSON.stringify(a.shown_sources) === JSON.stringify(b.shown_sources)
  );
}

/**
 * Detect if a question has already been asked (repetition prevention).
 */
export function isQuestionRepeated(state: JourneyState, question: string): boolean {
  const normalized = question.toLowerCase().trim();
  return state.asked_questions.some((q) => q.toLowerCase().trim() === normalized);
}

/**
 * Detect if an action has already been offered (repetition prevention).
 */
export function isActionOffered(state: JourneyState, action: string): boolean {
  return state.offered_actions.includes(action);
}

/**
 * Detect if a source has already been shown (repetition prevention).
 */
export function isSourceShown(state: JourneyState, source: string): boolean {
  return state.shown_sources.includes(source);
}

/**
 * Detect if a fact has already been confirmed (repetition prevention).
 */
export function isFactConfirmed(state: JourneyState, fact: string): boolean {
  return state.confirmed_facts.includes(fact);
}
