import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((e: any) => void)[]> = {};
  onerror: ((e: any) => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    // Simulate connection open
    setTimeout(() => {
      this.readyState = 1;
    }, 0);
  }

  addEventListener(type: string, listener: (e: any) => void) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(listener);
  }

  close() {
    this.readyState = 2;
  }

  emit(type: string, data: any) {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    const handlers = this.listeners[type] || [];
    handlers.forEach((h) => h(event));
    if (type === "error" && this.onerror) this.onerror(event);
  }

  triggerTransportError() {
    this.readyState = 0;
    if (this.onerror) this.onerror({});
  }
}

(MockEventSource as any).CLOSED = 2;
(global as any).EventSource = MockEventSource;

import { useSearchSSE } from "./useSearchSSE";

describe("useSearchSSE", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts in empty state", () => {
    const { result } = renderHook(() => useSearchSSE());
    expect(result.current.status).toBe("empty");
    expect(result.current.results).toEqual([]);
    expect(result.current.answer).toBe("");
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("search with empty query stays empty", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("");
    });
    expect(result.current.status).toBe("empty");
  });

  it("search transitions to loading", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("test query");
    });
    expect(result.current.status).toBe("loading");
    expect(result.current.isStreaming).toBe(true);
    expect(MockEventSource.instances.length).toBe(1);
    expect(MockEventSource.instances[0].url).toContain("q=test%20query");
    expect(MockEventSource.instances[0].url).toContain("gdpr_consent=demo");
    expect(MockEventSource.instances[0].url).not.toContain("top_k");
  });

  it("accumulates generated answer chunks", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit("answer_chunk", { text: "First " });
      es.emit("answer_chunk", { text: "answer." });
    });

    expect(result.current.answer).toBe("First answer.");
    expect(result.current.status).toBe("success");
  });

  it("records a non-fatal answer generation error", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });

    act(() => {
      MockEventSource.instances[0].emit("answer_error", { message: "generation unavailable" });
    });

    expect(result.current.answerError).toBe("generation unavailable");
    expect(result.current.isStreaming).toBe(true);
  });

  it("appends results on result events", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];
    act(() => {
      es.emit("result", {
        id: "r1",
        text: "Result 1",
        type: "world",
        chunk_id: "c1",
        entities: [],
        rank: 1,
      });
    });
    expect(result.current.status).toBe("success");
    expect(result.current.results.length).toBe(1);
    expect(result.current.results[0].id).toBe("r1");
  });

  it("done event closes connection and resets retries", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];
    act(() => {
      es.emit("result", { id: "r1", text: "x", type: "t", chunk_id: "c", entities: [], rank: 1 });
    });
    act(() => {
      const handlers = es.listeners["done"] || [];
      handlers.forEach((h) => h({ data: "[DONE]" }));
    });
    expect(es.readyState).toBe(2);
    expect(result.current.status).toBe("success");
    expect(result.current.isStreaming).toBe(false);
  });

  it("server error event retries with backoff", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];

    // The browser dispatches a named `error` SSE message to both registered
    // error listeners and `onerror`; only one retry should be scheduled.
    act(() => {
      es.emit("error", { message: "server error" });
      es.emit("done", {});
    });
    expect(es.readyState).toBe(2); // closed
    expect(result.current.status).toBe("loading");

    // After 2s backoff, should retry
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(MockEventSource.instances.length).toBe(2);
  });

  it("transport error retries with backoff", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];

    act(() => {
      es.triggerTransportError();
    });

    expect(result.current.error).toContain("temporarily unavailable");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(MockEventSource.instances.length).toBe(2);
  });

  it("gives up after 3 retries on transport error", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });

    // Retry 1 (retriesRef 0->1): trigger error, wait 2s backoff
    let es = MockEventSource.instances[MockEventSource.instances.length - 1];
    act(() => {
      es.triggerTransportError();
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    // Retry 2 (retriesRef 1->2): trigger error, wait 4s backoff
    es = MockEventSource.instances[MockEventSource.instances.length - 1];
    act(() => {
      es.triggerTransportError();
    });
    act(() => {
      vi.advanceTimersByTime(4000);
    });

    // Retry 3 (retriesRef 2->3): trigger error, wait 8s backoff
    es = MockEventSource.instances[MockEventSource.instances.length - 1];
    act(() => {
      es.triggerTransportError();
    });
    act(() => {
      vi.advanceTimersByTime(8000);
    });

    // 4th connection — retriesRef is now 3 (= MAX_RETRIES), this error is final
    es = MockEventSource.instances[MockEventSource.instances.length - 1];
    act(() => {
      es.triggerTransportError();
    });

    expect(result.current.status).toBe("error");
    expect(result.current.error).toContain("temporarily unavailable");
  });

  it("reset clears all state", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.status).toBe("empty");
    expect(result.current.results).toEqual([]);
    expect(result.current.answer).toBe("");
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("retry restarts the search", () => {
    const { result } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const count = MockEventSource.instances.length;
    act(() => {
      result.current.retry();
    });
    expect(MockEventSource.instances.length).toBe(count + 1);
  });

  it("closes connection on unmount", () => {
    const { result, unmount } = renderHook(() => useSearchSSE());
    act(() => {
      result.current.search("query");
    });
    const es = MockEventSource.instances[0];
    unmount();
    expect(es.readyState).toBe(2);
  });
});
