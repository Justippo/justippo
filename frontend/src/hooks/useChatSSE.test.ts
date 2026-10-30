import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useChatSSE } from "./useChatSSE";

const SOURCE_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";

function streamResponse(): Response {
  const body = [
    "event: result",
    `data: ${JSON.stringify({
      id: "result-1",
      text: "Residence rights are governed by Directive 2004/38/EC.",
      rank: 1,
      source_url: SOURCE_URL,
      source_title: "Directive 2004/38/EC",
    })}`,
    "",
    "event: answer_model",
    `data: ${JSON.stringify({
      provider: "public-ai",
      provider_display: "Public AI",
      model: "swiss-ai/apertus-8b-instruct",
      display_name: "Apertus 8B",
    })}`,
    "",
    "event: answer_chunk",
    `data: ${JSON.stringify({ text: "Next steps:\n" })}`,
    "",
    "event: answer_chunk",
    `data: ${JSON.stringify({ text: "1. Confirm your residence category." })}`,
    "",
    "event: done",
    "data: [DONE]",
    "",
  ].join("\n");

  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("useChatSSE", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts bounded conversation context and consumes the typed stream", async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse());
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useChatSSE());
    const history = Array.from({ length: 8 }, (_, index) => ({
      role: (index % 2 === 0 ? "user" : "assistant") as "user" | "assistant",
      content: `Turn ${index + 1}`,
    }));

    act(() => result.current.send("What documents do I need?", history));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.status).toBe("success");
    expect(result.current.answer).toBe("Next steps:\n1. Confirm your residence category.");
    expect(result.current.results).toHaveLength(1);
    expect(result.current.model).toMatchObject({
      display_name: "Apertus 8B",
      provider_display: "Public AI",
    });

    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const payload = JSON.parse(String(request.body)) as {
      message: string;
      history: Array<{ content: string }>;
    };
    expect(payload.message).toBe("What documents do I need?");
    expect(payload.history).toHaveLength(6);
    expect(payload.history[0].content).toBe("Turn 3");
    expect((request.headers as Record<string, string>)["X-GDPR-Consent"]).toBe("demo");
  });

  it("accepts only one submission while a request is in flight", async () => {
    let resolveResponse: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve;
      })
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useChatSSE());

    let firstAccepted = false;
    let duplicateAccepted = true;
    act(() => {
      firstAccepted = result.current.send("Original question", []);
      duplicateAccepted = result.current.send("Original question", []);
    });

    expect(firstAccepted).toBe(true);
    expect(duplicateAccepted).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveResponse?.(streamResponse());
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
  });

  it("removes model attribution when answer generation fails", async () => {
    const response = new Response(
      [
        "event: answer_model",
        `data: ${JSON.stringify({
          provider: "public-ai",
          provider_display: "Public AI",
          model: "swiss-ai/apertus-8b-instruct",
          display_name: "Apertus 8B",
        })}`,
        "",
        "event: answer_error",
        `data: ${JSON.stringify({ message: "unavailable" })}`,
        "",
        "event: done",
        "data: [DONE]",
        "",
      ].join("\n"),
      { status: 200 }
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const { result } = renderHook(() => useChatSSE());

    act(() => result.current.send("Question", []));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.model).toBeNull();
  });

  it("consumes structured empty-result guidance", async () => {
    const guidance = {
      reason: "national_law",
      message: "Spanish tax obligations are primarily governed by national law.",
      question: "Which part would you like to explore next?",
      options: [{ label: "Tax residency", action: "submit", query: "Tax residency in Spain" }],
      references: [],
    };
    const response = new Response(
      [
        "event: guidance",
        `data: ${JSON.stringify(guidance)}`,
        "",
        "event: done",
        "data: [DONE]",
        "",
      ].join("\n"),
      { status: 200 }
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const { result } = renderHook(() => useChatSSE());

    act(() => result.current.send("What are the tax rules in Spain?", []));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.guidance).toEqual(guidance);
    expect(result.current.status).toBe("success");
  });

  it("handles CRLF delimiters split across stream chunks", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      `event: answer_chunk\r\ndata: ${JSON.stringify({ text: "Grounded answer" })}\r`,
      "\n\r",
      "\nevent: done\r\ndata: [DONE]\r",
      "\n\r\n",
    ];
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })));
    const { result } = renderHook(() => useChatSSE());

    act(() => result.current.send("Question", []));

    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.status).toBe("success");
    expect(result.current.answer).toBe("Grounded answer");
  });
});
