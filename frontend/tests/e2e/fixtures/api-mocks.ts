/**
 * API mock factories — intercept backend calls in E2E tests.
 *
 * All patterns use ** prefix so they match both local (http://localhost:8000)
 * and production (https://evidence-eu-worker.mc146.workers.dev) base URLs,
 * which are baked into the static export at build time.
 */

import type { Page } from "@playwright/test";

const SEARCH_RESULT = {
  answer: "Section 8 of the German Residence Act governs residence permit extensions.",
  sources: [
    {
      title: "German Residence Act — Section 8",
      url: "https://www.gesetze-im-internet.de/aufenthg_2004/__8.html",
      excerpt: "A residence permit may be extended under the rules applicable to its issue.",
      language: "en",
    },
  ],
  queryLanguage: "en",
  resultLanguages: ["en"],
};

const UPLOAD_RESULT = {
  doc_id: "550e8400-e29b-41d4-a716-446655440000",
  status: "processed",
  ephemeral: true,
  page_count: 1,
  target_language: "de",
  pages: [{ page: 1, text: "Extracted text content.", confidence: 0.97 }],
  classification: {
    document_type: "legal_document",
    language_code: "en",
    quality_score: 0.85,
    confidence: 0.8,
  },
  pdf_processing: {
    route: "pdf_reference_translation",
    output_mode: "reference",
    layout_preserved: true,
    original_unchanged: true,
    form_filling_supported: false,
  },
};

const TRANSLATE_RESULT = {
  job_id: "job-550e8400",
  status: "done",
  translated_pages: [{ page: 1, text: "Übersetzter Textinhalt." }],
  download_url: null,
};

const PDF_REFERENCE_TRANSLATE_RESULT = {
  request_id: "request-reference-550e8400",
  status: "done",
  ephemeral: true,
  output_mode: "reference",
  original_unchanged: true,
  form_filling_supported: false,
  source_language: "en",
  target_language: "de",
  translated_pdf_b64: "JVBERi0xLjcKJSVFT0Y=",
  translated_pdf_content_type: "application/pdf",
  detected_source_language: "en",
  layout_preserved: true,
  pages_processed: 1,
  classification: {
    document_type: "legal_document",
    language_code: "en",
    quality_score: 0.85,
    geographic_relevance: ["European"],
    safety_flags: [],
    confidence: 0.8,
  },
  document_explanation: {
    document_type: "legal_document",
    language: "de",
    requirements: [],
    explanation: "Dieses Dokument enthält rechtliche Informationen.",
    legal_context_status: "not_found",
    citations: [],
    warnings: ["NO_VERIFIED_EU_LAW_SOURCE"],
  },
  warnings: ["REFERENCE_COPY_ONLY"],
};

const SEARCH_SSE_RESULT = {
  id: "chunk-search-001",
  text: "EU Directive 2011/24 grants patients the right to receive healthcare in any EU member state.",
  type: "world",
  chunk_id: "chunk-search-001",
  entities: ["EU Directive 2011/24"],
  rank: 1,
};

/**
 * Mock EventSource at the JavaScript level for search SSE.
 * page.route() is unreliable with EventSource — intercepting at the JS level
 * gives deterministic control over event dispatch timing.
 */
async function installMockEventSource(page: Page, events: Array<{ type: string; data: unknown }>) {
  await page.addInitScript((eventsJson) => {
    const events = JSON.parse(eventsJson);
    class MockEventSource {
      static CLOSED = 2;
      static CONNECTING = 0;
      static OPEN = 1;
      readyState = 1;
      url: string;
      withCredentials = false;
      private listeners: Record<string, EventListener[]> = {};

      constructor(url: string) {
        this.url = url;
        this.readyState = 1;
        // Dispatch events asynchronously after construction
        setTimeout(() => {
          for (const event of events) {
            const listeners = this.listeners[event.type] || [];
            const messageEvent = new MessageEvent(event.type, { data: JSON.stringify(event.data) });
            for (const listener of listeners) listener(messageEvent);
            const onHandler = (this as any)[`on${event.type}`];
            if (typeof onHandler === "function") onHandler(messageEvent);
          }
        }, 50);
      }
      addEventListener(type: string, listener: EventListener) {
        if (!this.listeners[type]) this.listeners[type] = [];
        this.listeners[type].push(listener);
      }
      removeEventListener(type: string, listener: EventListener) {
        if (!this.listeners[type]) return;
        this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
      }
      close() {
        this.readyState = 2;
      }
      set onmessage(fn: any) {
        this.listeners["message"] = [fn];
      }
      set onerror(fn: any) {
        this.listeners["error"] = [fn];
      }
      set onopen(fn: any) {
        this.listeners["open"] = [fn];
      }
    }
    (window as any).EventSource = MockEventSource;
  }, JSON.stringify(events));
}

/** Mock GET /api/v1/search/ to return a successful canned SSE result */
export async function mockSearchSuccess(page: Page): Promise<void> {
  const events = [
    { type: "result", data: { ...SEARCH_SSE_RESULT, text: "EU Directive 2011/24 " } },
    {
      type: "result",
      data: {
        ...SEARCH_SSE_RESULT,
        id: "chunk-search-002",
        text: "grants patients the right ",
        rank: 2,
      },
    },
    {
      type: "result",
      data: {
        ...SEARCH_SSE_RESULT,
        id: "chunk-search-003",
        text: "to receive healthcare in any EU member state.",
        rank: 3,
      },
    },
    { type: "done", data: {} },
  ];
  await installMockEventSource(page, events);
}

/** Mock GET /api/v1/search/ to return an immediate error (triggers error state) */
export async function mockSearchError(page: Page): Promise<void> {
  // Override EventSource to immediately dispatch an error event + close
  await page.addInitScript(() => {
    class MockErrorEventSource {
      static CLOSED = 2;
      static CONNECTING = 0;
      static OPEN = 1;
      readyState = 1;
      url: string;
      withCredentials = false;
      private listeners: Record<string, EventListener[]> = {};

      constructor(url: string) {
        this.url = url;
        this.readyState = 2; // CLOSED
        setTimeout(() => {
          const listeners = this.listeners["error"] || [];
          const errorEvent = new Event("error");
          for (const listener of listeners) listener(errorEvent);
          const onHandler = (this as any)["onerror"];
          if (typeof onHandler === "function") onHandler(errorEvent);
        }, 50);
      }
      addEventListener(type: string, listener: EventListener) {
        if (!this.listeners[type]) this.listeners[type] = [];
        this.listeners[type].push(listener);
      }
      removeEventListener(type: string, listener: EventListener) {
        if (!this.listeners[type]) return;
        this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
      }
      close() {
        this.readyState = 2;
      }
      set onmessage(fn: any) {
        this.listeners["message"] = [fn];
      }
      set onerror(fn: any) {
        this.listeners["error"] = [fn];
      }
      set onopen(fn: any) {
        this.listeners["open"] = [fn];
      }
    }
    (window as any).EventSource = MockErrorEventSource;
  });
}

/** Mock POST /api/v1/documents/ to return a successful upload result + mock translate */
export async function mockUploadSuccess(page: Page): Promise<void> {
  await page.route("**/api/v1/documents/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(UPLOAD_RESULT),
    })
  );
  await page.route("**/api/v1/translate/**", async (route) => {
    // Artificial delay so the "translating" phase is visible long enough
    // for the E2E test to assert on the status element. Without this the
    // mock responds so fast (<50ms) that React batches the state transition
    // and the "translating" element never appears.
    await new Promise((r) => setTimeout(r, 2_000));
    const requestPath = new URL(route.request().url()).pathname;
    let responseBody: unknown = TRANSLATE_RESULT;
    if (requestPath.endsWith("/api/v1/translate/pdf-reference")) {
      const multipartBody = route.request().postData() ?? "";
      const targetLanguage =
        multipartBody.match(/name="target_language"\r?\n\r?\n(en|de|fr)/)?.[1] ?? "de";
      responseBody = {
        ...PDF_REFERENCE_TRANSLATE_RESULT,
        request_id: `request-reference-${targetLanguage}`,
        target_language: targetLanguage,
        document_explanation: {
          ...PDF_REFERENCE_TRANSLATE_RESULT.document_explanation,
          language: targetLanguage,
          explanation:
            targetLanguage === "fr"
              ? "Ce document contient des informations juridiques."
              : PDF_REFERENCE_TRANSLATE_RESULT.document_explanation.explanation,
        },
      };
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody),
    });
  });
}

/** Mock POST /api/v1/documents/ to return a backend validation error */
export async function mockUploadError(page: Page, detail = "Unsupported file type"): Promise<void> {
  await page.route("**/api/v1/documents/**", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail }),
    })
  );
}
