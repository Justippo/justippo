import { act, renderHook, waitFor } from "@testing-library/react";
import type { FormEvent } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const stream = vi.hoisted(() => ({
  results: [] as Array<Record<string, unknown>>,
  answer: "",
  model: null as null | {
    provider: string;
    provider_display: string;
    model: string;
    display_name: string;
  },
  guidance: null as null | {
    reason: "national_law" | "no_verified_source";
    message: string;
    question: string;
    options: Array<
      | { label: string; action: "submit"; query: string }
      | { label: string; action: "compose"; prompt: string }
      | { label: string; query: string }
    >;
    references: Array<{ title: string; url: string }>;
  },
  status: "empty" as "empty" | "loading" | "success" | "error",
  isStreaming: false,
  error: null as string | null,
  send: vi.fn(),
  retry: vi.fn(),
  reset: vi.fn(),
}));

vi.mock("@/context/AuthContext", () => ({
  useAuth: () => ({ isAuthenticated: true, isLoading: false }),
}));

vi.mock("@/hooks/useChatSSE", () => ({
  useChatSSE: () => stream,
}));

import { useChatView } from "./useChatView";

describe("useChatView", () => {
  beforeEach(() => {
    stream.results = [];
    stream.answer = "";
    stream.model = null;
    stream.guidance = null;
    stream.status = "empty";
    stream.isStreaming = false;
    stream.error = null;
    stream.send.mockReset();
    stream.send.mockReturnValue(true);
    stream.retry.mockReset();
  });

  it("submits a trimmed conversational RAG question", () => {
    const { result } = renderHook(() => useChatView());

    act(() => {
      result.current.setQuery("  Spanish remote-work tax rules  ");
    });
    act(() => {
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>);
    });

    expect(stream.send).toHaveBeenCalledWith(
      "Spanish remote-work tax rules",
      [],
      expect.anything(),
      "en"
    );
    expect(result.current.messages[0]).toMatchObject({
      role: "user",
      content: "Spanish remote-work tax rules",
    });
    expect(result.current.messages[1]).toMatchObject({ role: "assistant", content: "" });
    expect(result.current.query).toBe("");
  });

  it("does not append a duplicate turn when the stream rejects an in-flight submission", () => {
    stream.send.mockReturnValueOnce(true).mockReturnValueOnce(false);
    const { result } = renderHook(() => useChatView());

    act(() => result.current.setQuery("yes it is recognized in my home country"));
    act(() =>
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>)
    );
    act(() => result.current.setQuery("yes it is recognized in my home country"));
    act(() =>
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>)
    );

    expect(stream.send).toHaveBeenCalledTimes(2);
    expect(result.current.messages.filter((message) => message.role === "user")).toHaveLength(1);
  });

  it("streams the grounded answer and verified citation into the active turn", async () => {
    const { result, rerender } = renderHook(() => useChatView());
    act(() => {
      result.current.setQuery("residence rights");
    });
    act(() => {
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>);
    });

    stream.results = [
      {
        id: "result-1",
        text: "Residence rights are governed by Directive 2004/38/EC.",
        rank: 1,
        source_url: "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038",
        source_title: "Directive 2004/38/EC",
      },
    ];
    stream.answer = "EU citizens retain residence rights under the directive.";
    stream.model = {
      provider: "public-ai",
      provider_display: "Public AI",
      model: "swiss-ai/apertus-8b-instruct",
      display_name: "Apertus 8B",
    };
    stream.status = "success";
    stream.isStreaming = false;
    rerender();

    await waitFor(() => {
      expect(result.current.messages[1]).toMatchObject({
        role: "assistant",
        content: "EU citizens retain residence rights under the directive.",
        sources: [
          {
            title: "Directive 2004/38/EC",
            url: "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038",
          },
        ],
        model: stream.model,
      });
    });
  });

  it("sends the six most recent completed turns as ephemeral context", () => {
    const { result } = renderHook(() => useChatView());

    const questions = [
      "Question one",
      "Question two",
      "Question three",
      "Question four",
      "Question five",
      "Question six",
      "Question seven",
      "Question eight",
    ];
    for (const question of questions) {
      act(() => result.current.setQuery(question));
      act(() => {
        result.current.handleSubmit({
          preventDefault: vi.fn(),
        } as unknown as FormEvent<HTMLFormElement>);
      });
      stream.isStreaming = false;
    }

    const lastCall = stream.send.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("Question eight");
    expect(lastCall?.[1]).toHaveLength(6);
    expect(lastCall?.[2]).toMatchObject({
      asked_questions: expect.any(Array),
    });
    expect(lastCall?.[1][0]).toMatchObject({ role: "user", content: "Question two" });
  });

  it("falls back to the top retrieved excerpt when no generated answer is available", async () => {
    const { result, rerender } = renderHook(() => useChatView());
    act(() => {
      result.current.setQuery("residence rights");
    });
    act(() => {
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>);
    });

    stream.results = [
      {
        id: "result-1",
        text: "Residence rights are governed by Directive 2004/38/EC.",
        rank: 1,
      },
    ];
    stream.status = "success";
    stream.isStreaming = false;
    rerender();

    await waitFor(() => {
      expect(result.current.messages[1].content).toBe(
        "Residence rights are governed by Directive 2004/38/EC."
      );
    });
  });

  it("renders query-relevant guidance without introducing an unrelated country", async () => {
    const { result, rerender } = renderHook(() => useChatView());
    act(() => result.current.setQuery("What are the tax rules in Spain?"));
    act(() => {
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>);
    });

    stream.results = [];
    stream.guidance = {
      reason: "national_law",
      message: "Spanish tax obligations are primarily governed by national law.",
      question: "Which part would you like to explore next?",
      options: [
        {
          label: "Tax residency",
          action: "submit",
          query: "How is individual tax residency determined in Spain?",
        },
      ],
      references: [
        {
          title: "Spanish Tax Agency — tax residency",
          url: "https://sede.agenciatributaria.gob.es/Sede/en_gb/no-residentes/residencia-personas-fisicas-juridicas.html",
        },
      ],
    };
    stream.status = "success";
    stream.isStreaming = false;
    rerender();

    await waitFor(() => {
      expect(result.current.messages[1].content).toContain("Spanish tax obligations");
      expect(result.current.messages[1].content).not.toContain("Germany");
      expect(result.current.messages[1].guidance?.options[0].label).toBe("Tax residency");
    });

    const guidance = result.current.messages[1].guidance;
    act(() => result.current.selectGuidanceOption(guidance!.options[0], "chat-assistant-1"));
    expect(stream.send).toHaveBeenLastCalledWith(
      "How is individual tax residency determined in Spain?",
      expect.any(Array),
      expect.anything(),
      "en"
    );
  });

  it("opens a guided composer without submitting or repeating the original question", async () => {
    const { result, rerender } = renderHook(() => useChatView());
    act(() => result.current.setQuery("How do I get a work permit in Germany?"));
    act(() =>
      result.current.handleSubmit({
        preventDefault: vi.fn(),
      } as unknown as FormEvent<HTMLFormElement>)
    );

    stream.guidance = {
      reason: "national_law",
      message: "The applicable route depends on your situation.",
      question: "Tell me which situation applies to you:",
      options: [
        {
          label: "Add my status",
          action: "compose",
          prompt: "Describe your citizenship and whether you have a German job offer.",
        },
      ],
      references: [],
    };
    stream.status = "success";
    stream.isStreaming = false;
    rerender();

    await waitFor(() => expect(result.current.messages[1].guidance).toBeDefined());
    act(() =>
      result.current.selectGuidanceOption(
        result.current.messages[1].guidance!.options[0],
        "chat-assistant-1"
      )
    );

    expect(stream.send).toHaveBeenCalledTimes(1);
    expect(result.current.query).toBe("");
    expect(result.current.placeholder).toContain("citizenship");
    expect(result.current.messages[1].guidance).toBeUndefined();
  });
});
