import { describe, expect, it } from "vitest";
import {
  createInitialJourneyState,
  journeyStatesEqual,
  isQuestionRepeated,
  isActionOffered,
  isSourceShown,
  isFactConfirmed,
  type JourneyState,
} from "@/lib/journey-state";

describe("journey-state", () => {
  describe("createInitialJourneyState", () => {
    it("creates empty initial state", () => {
      const state = createInitialJourneyState();

      expect(state.journey_type).toBeNull();
      expect(state.jurisdiction).toBeNull();
      expect(state.citizenship_group).toBeNull();
      expect(state.facts).toEqual({});
      expect(state.current_step).toBeNull();
      expect(state.completed_steps).toEqual([]);
      expect(state.offered_actions).toEqual([]);
      expect(state.asked_questions).toEqual([]);
      expect(state.confirmed_facts).toEqual([]);
      expect(state.shown_sources).toEqual([]);
      expect(state.turn_count).toBe(0);
    });
  });

  describe("journeyStatesEqual", () => {
    it("returns true for identical empty states", () => {
      const a = createInitialJourneyState();
      const b = createInitialJourneyState();
      expect(journeyStatesEqual(a, b)).toBe(true);
    });

    it("returns false when journey_type differs", () => {
      const a: JourneyState = {
        ...createInitialJourneyState(),
        journey_type: "work",
      };
      const b = createInitialJourneyState();
      expect(journeyStatesEqual(a, b)).toBe(false);
    });

    it("returns false when turn_count differs", () => {
      const a: JourneyState = {
        ...createInitialJourneyState(),
        turn_count: 1,
      };
      const b = createInitialJourneyState();
      expect(journeyStatesEqual(a, b)).toBe(false);
    });

    it("returns false when facts differ", () => {
      const a: JourneyState = {
        ...createInitialJourneyState(),
        facts: { job_offer: true },
      };
      const b = createInitialJourneyState();
      expect(journeyStatesEqual(a, b)).toBe(false);
    });

    it("returns false when completed_steps differ", () => {
      const a: JourneyState = {
        ...createInitialJourneyState(),
        completed_steps: ["citizenship"],
      };
      const b = createInitialJourneyState();
      expect(journeyStatesEqual(a, b)).toBe(false);
    });

    it("returns true for equivalent states with different object references", () => {
      const a: JourneyState = {
        ...createInitialJourneyState(),
        facts: { job_offer: true },
        completed_steps: ["citizenship"],
      };
      const b: JourneyState = {
        ...createInitialJourneyState(),
        facts: { job_offer: true },
        completed_steps: ["citizenship"],
      };
      expect(journeyStatesEqual(a, b)).toBe(true);
    });
  });

  describe("isQuestionRepeated", () => {
    it("returns false for new question", () => {
      const state = createInitialJourneyState();
      expect(isQuestionRepeated(state, "What do I need?")).toBe(false);
    });

    it("returns true for exact match", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        asked_questions: ["what do i need?"],
      };
      expect(isQuestionRepeated(state, "What do I need?")).toBe(true);
    });

    it("returns true for case-insensitive match", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        asked_questions: ["WHAT DO I NEED?"],
      };
      expect(isQuestionRepeated(state, "what do i need?")).toBe(true);
    });

    it("returns false for different question", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        asked_questions: ["what do i need?"],
      };
      expect(isQuestionRepeated(state, "How do I apply?")).toBe(false);
    });
  });

  describe("isActionOffered", () => {
    it("returns false for new action", () => {
      const state = createInitialJourneyState();
      expect(isActionOffered(state, "check_regulated_profession")).toBe(false);
    });

    it("returns true for offered action", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        offered_actions: ["check_regulated_profession"],
      };
      expect(isActionOffered(state, "check_regulated_profession")).toBe(true);
    });

    it("returns false for different action", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        offered_actions: ["check_regulated_profession"],
      };
      expect(isActionOffered(state, "start_application")).toBe(false);
    });
  });

  describe("isSourceShown", () => {
    it("returns false for new source", () => {
      const state = createInitialJourneyState();
      expect(isSourceShown(state, "EU Blue Card Directive")).toBe(false);
    });

    it("returns true for shown source", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        shown_sources: ["EU Blue Card Directive"],
      };
      expect(isSourceShown(state, "EU Blue Card Directive")).toBe(true);
    });
  });

  describe("isFactConfirmed", () => {
    it("returns false for new fact", () => {
      const state = createInitialJourneyState();
      expect(isFactConfirmed(state, "has_job_offer")).toBe(false);
    });

    it("returns true for confirmed fact", () => {
      const state: JourneyState = {
        ...createInitialJourneyState(),
        confirmed_facts: ["has_job_offer"],
      };
      expect(isFactConfirmed(state, "has_job_offer")).toBe(true);
    });
  });
});
