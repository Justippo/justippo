"use client";

import { useCallback, useRef, useState } from "react";
import {
  type JourneyState,
  createInitialJourneyState,
  journeyStatesEqual,
} from "@/lib/journey-state";

/**
 * Return type for the useJourneyState hook.
 */
export interface UseJourneyStateReturn {
  /** Current journey state */
  readonly state: JourneyState;

  /** Update journey state from backend response */
  readonly updateFromResponse: (backendState: JourneyState | null) => void;

  /** Record a question that was asked */
  readonly recordQuestion: (question: string) => void;

  /** Record an action that was offered */
  readonly recordAction: (action: string) => void;

  /** Record a source that was shown */
  readonly recordSource: (source: string) => void;

  /** Record a fact that was confirmed */
  readonly recordFact: (fact: string) => void;

  /** Mark a step as completed */
  readonly completeStep: (step: string) => void;

  /** Reset journey state */
  readonly reset: () => void;

  /** Whether the state changed since last response */
  readonly hasChanges: boolean;
}

/**
 * Hook for managing structured ephemeral journey state.
 *
 * The state lives in browser memory and is submitted with each request.
 * The backend can update it based on the conversation.
 */
export function useJourneyState(): UseJourneyStateReturn {
  const [state, setState] = useState<JourneyState>(createInitialJourneyState);
  const previousStateRef = useRef<JourneyState>(createInitialJourneyState());

  const updateFromResponse = useCallback((backendState: JourneyState | null) => {
    if (!backendState) return;

    setState((prev) => {
      // Merge backend state with local state
      // Backend can update journey_type, jurisdiction, citizenship_group,
      // facts, current_step, completed_steps
      // Local state preserves offered_actions, asked_questions,
      // confirmed_facts, shown_sources (these are only tracked client-side)
      const merged: JourneyState = {
        journey_type: backendState.journey_type ?? prev.journey_type,
        jurisdiction: backendState.jurisdiction ?? prev.jurisdiction,
        citizenship_group: backendState.citizenship_group ?? prev.citizenship_group,
        facts: { ...prev.facts, ...backendState.facts },
        current_step: backendState.current_step ?? prev.current_step,
        completed_steps: [
          ...new Set([...prev.completed_steps, ...(backendState.completed_steps ?? [])]),
        ],
        offered_actions: prev.offered_actions,
        asked_questions: prev.asked_questions,
        confirmed_facts: prev.confirmed_facts,
        shown_sources: prev.shown_sources,
        turn_count: (backendState.turn_count ?? prev.turn_count) + 1,
      };

      return merged;
    });
  }, []);

  const recordQuestion = useCallback((question: string) => {
    const normalized = question.toLowerCase().trim();
    setState((prev) => ({
      ...prev,
      asked_questions: [...prev.asked_questions, normalized],
    }));
  }, []);

  const recordAction = useCallback((action: string) => {
    setState((prev) => ({
      ...prev,
      offered_actions: [...prev.offered_actions, action],
    }));
  }, []);

  const recordSource = useCallback((source: string) => {
    setState((prev) => ({
      ...prev,
      shown_sources: [...prev.shown_sources, source],
    }));
  }, []);

  const recordFact = useCallback((fact: string) => {
    setState((prev) => ({
      ...prev,
      confirmed_facts: [...prev.confirmed_facts, fact],
    }));
  }, []);

  const completeStep = useCallback((step: string) => {
    setState((prev) => ({
      ...prev,
      completed_steps: [...new Set([...prev.completed_steps, step])],
    }));
  }, []);

  const reset = useCallback(() => {
    setState(createInitialJourneyState());
    previousStateRef.current = createInitialJourneyState();
  }, []);

  const hasChanges = !journeyStatesEqual(previousStateRef.current, state);

  // Update previous state reference after render
  const updatePrevious = useCallback(() => {
    previousStateRef.current = state;
  }, [state]);

  return {
    state,
    updateFromResponse,
    recordQuestion,
    recordAction,
    recordSource,
    recordFact,
    completeStep,
    reset,
    hasChanges,
    // Expose for manual sync after successful request
    _updatePrevious: updatePrevious,
  } as UseJourneyStateReturn & { _updatePrevious: () => void };
}
