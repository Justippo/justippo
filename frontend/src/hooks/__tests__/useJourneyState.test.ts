import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useJourneyState } from "@/hooks/useJourneyState";

describe("useJourneyState", () => {
  it("initializes with empty state", () => {
    const { result } = renderHook(() => useJourneyState());

    expect(result.current.state.journey_type).toBeNull();
    expect(result.current.state.turn_count).toBe(0);
    expect(result.current.state.asked_questions).toEqual([]);
    expect(result.current.state.offered_actions).toEqual([]);
  });

  it("records questions", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordQuestion("What do I need?");
    });

    expect(result.current.state.asked_questions).toEqual(["what do i need?"]);
  });

  it("records actions", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordAction("check_regulated_profession");
    });

    expect(result.current.state.offered_actions).toEqual(["check_regulated_profession"]);
  });

  it("records sources", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordSource("EU Blue Card Directive");
    });

    expect(result.current.state.shown_sources).toEqual(["EU Blue Card Directive"]);
  });

  it("records facts", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordFact("has_job_offer");
    });

    expect(result.current.state.confirmed_facts).toEqual(["has_job_offer"]);
  });

  it("completes steps", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.completeStep("citizenship");
    });

    expect(result.current.state.completed_steps).toEqual(["citizenship"]);
  });

  it("deduplicates completed steps", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.completeStep("citizenship");
      result.current.completeStep("citizenship");
    });

    expect(result.current.state.completed_steps).toEqual(["citizenship"]);
  });

  it("updates from backend response", () => {
    const { result } = renderHook(() => useJourneyState());

    const backendState = {
      journey_type: "work" as const,
      jurisdiction: "DE",
      citizenship_group: "non_eu" as const,
      facts: { job_offer: true },
      current_step: "profession_check",
      completed_steps: ["citizenship"],
      offered_actions: [],
      asked_questions: [],
      confirmed_facts: [],
      shown_sources: [],
      turn_count: 0,
    };

    act(() => {
      result.current.updateFromResponse(backendState);
    });

    expect(result.current.state.journey_type).toBe("work");
    expect(result.current.state.jurisdiction).toBe("DE");
    expect(result.current.state.citizenship_group).toBe("non_eu");
    expect(result.current.state.facts).toEqual({ job_offer: true });
    expect(result.current.state.current_step).toBe("profession_check");
    expect(result.current.state.completed_steps).toEqual(["citizenship"]);
    expect(result.current.state.turn_count).toBeGreaterThanOrEqual(1);
  });

  it("merges backend facts with local facts", () => {
    const { result } = renderHook(() => useJourneyState());

    // Write some initial local state via a backend update
    act(() => {
      result.current.updateFromResponse({
        journey_type: null,
        jurisdiction: null,
        citizenship_group: null,
        facts: { local_fact: true },
        current_step: null,
        completed_steps: [],
        offered_actions: [],
        asked_questions: [],
        confirmed_facts: [],
        shown_sources: [],
        turn_count: 0,
      });
    });

    // Then merge additional backend facts
    act(() => {
      result.current.updateFromResponse({
        journey_type: null,
        jurisdiction: null,
        citizenship_group: null,
        facts: { backend_fact: true },
        current_step: null,
        completed_steps: [],
        offered_actions: [],
        asked_questions: [],
        confirmed_facts: [],
        shown_sources: [],
        turn_count: 0,
      });
    });

    expect(result.current.state.facts).toEqual({
      local_fact: true,
      backend_fact: true,
    });
  });

  it("increments turn_count on update", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.updateFromResponse({
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
      });
    });

    expect(result.current.state.turn_count).toBe(1);
  });

  it("resets state", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordQuestion("What do I need?");
      result.current.completeStep("citizenship");
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.state.asked_questions).toEqual([]);
    expect(result.current.state.completed_steps).toEqual([]);
    expect(result.current.state.turn_count).toBe(0);
  });

  it("ignores null backend response", () => {
    const { result } = renderHook(() => useJourneyState());

    act(() => {
      result.current.recordQuestion("What do I need?");
    });

    act(() => {
      result.current.updateFromResponse(null);
    });

    expect(result.current.state.asked_questions).toEqual(["what do i need?"]);
  });
});
