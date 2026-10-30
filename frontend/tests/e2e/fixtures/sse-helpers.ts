/**
 * SSE stream helpers — parse and build Server-Sent Events payloads.
 *
 * Used to validate the streaming contract of GET /api/v1/search/
 * once the backend switches to SSE (Sprint 3).
 */

export interface SSEEvent {
  type: "result" | "source" | "error" | "done";
  data?: unknown;
}

/** Build an SSE text body from a list of events */
export function buildSSEStream(events: SSEEvent[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

/** Parse an SSE text body into typed events */
export function parseSSEStream(body: string): SSEEvent[] {
  return body
    .split("\n\n")
    .filter(Boolean)
    .map((chunk) => {
      const line = chunk.replace(/^data: /, "");
      try {
        return JSON.parse(line) as SSEEvent;
      } catch {
        return null;
      }
    })
    .filter((e): e is SSEEvent => e !== null);
}
