import { describe, it, expect, vi, beforeEach } from "vitest";

const mockUpload = vi.fn();
const mockTranslate = vi.fn();
const mockTranslatePdfReference = vi.fn();
const mockHealth = vi.fn();
const mockCreateRoom = vi.fn();

vi.mock("./gen/sdk.gen", () => ({
  uploadDocumentApiV1DocumentsPost: (...args: unknown[]) => mockUpload(...args),
  translateDocumentApiV1TranslatePost: (...args: unknown[]) => mockTranslate(...args),
  translatePdfReferenceDocumentApiV1TranslatePdfReferencePost: (...args: unknown[]) =>
    mockTranslatePdfReference(...args),
  healthCheckApiV1HealthGet: (...args: unknown[]) => mockHealth(...args),
  createRoomApiV1ExchangeRoomsPost: (...args: unknown[]) => mockCreateRoom(...args),
  getDocumentApiV1DocumentsDocumentIdGet: vi.fn(),
  getTranslationStatusApiV1TranslateStatusJobIdGet: vi.fn(),
  searchDocumentsApiV1SearchPost: vi.fn(),
  readinessCheckApiV1HealthReadyGet: vi.fn(),
  pipelineStatusApiV1HealthPipelineGet: vi.fn(),
  listSupportedLanguagesApiV1TranslateLanguagesGet: vi.fn(),
}));

import {
  GDPR_HEADERS,
  uploadDocument,
  translateDocument,
  translatePdfReference,
  checkHealth,
  createExchangeRoom,
} from "./index";

describe("api-generated facade", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uploadDocument sends GDPR header and file body", async () => {
    mockUpload.mockResolvedValue({
      data: {
        doc_id: "doc-1",
        status: "processed",
        ephemeral: true,
        page_count: 1,
        pages: [],
        classification: {},
      },
      response: { ok: true, status: 200 },
    });
    const file = new File(["pdf"], "test.pdf", { type: "application/pdf" });

    await uploadDocument(file, "de");

    expect(mockUpload).toHaveBeenCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({ target_lang: "de" }),
        headers: expect.objectContaining(GDPR_HEADERS),
      })
    );
  });

  it("translateDocument sends JSON body with GDPR header", async () => {
    mockTranslate.mockResolvedValue({
      data: { job_id: "j1", status: "done", translated_pages: [] },
      response: { ok: true, status: 200 },
    });

    await translateDocument({
      document_id: "doc-1",
      target_language: "de",
      pages: [{ page: 1, text: "Hello" }],
    });

    expect(mockTranslate).toHaveBeenCalledWith(
      expect.objectContaining({
        body: expect.objectContaining({ document_id: "doc-1", target_language: "de" }),
        headers: expect.objectContaining({
          ...GDPR_HEADERS,
          "Content-Type": "application/json",
        }),
      })
    );
  });

  it("translateDocument forwards request cancellation", async () => {
    mockTranslate.mockResolvedValue({
      data: { job_id: "j1", status: "done", translated_pages: [] },
      response: { ok: true, status: 200 },
    });
    const controller = new AbortController();

    await translateDocument(
      {
        document_id: "doc-1",
        target_language: "de",
        pages: [{ page: 1, text: "Hello" }],
      },
      undefined,
      controller.signal
    );

    expect(mockTranslate).toHaveBeenCalledWith(
      expect.objectContaining({ signal: controller.signal })
    );
  });

  it("translatePdfReference sends the original file with consent and cancellation", async () => {
    const payload = {
      request_id: "request-1",
      source_language: "en",
      target_language: "de",
      translated_pdf_b64: "JVBERg==",
      detected_source_language: "en",
      layout_preserved: true,
      pages_processed: 1,
      classification: {},
      document_explanation: {
        document_type: "unknown",
        language: "de",
        requirements: [],
        legal_context_status: "not_found",
        citations: [],
      },
    };
    mockTranslatePdfReference.mockResolvedValue({
      data: payload,
      response: { ok: true, status: 200 },
    });
    const file = new File(["pdf"], "form.pdf", { type: "application/pdf" });
    const controller = new AbortController();

    await expect(
      translatePdfReference(file, "en", "de", 1, undefined, controller.signal)
    ).resolves.toEqual(payload);
    expect(mockTranslatePdfReference).toHaveBeenCalledWith(
      expect.objectContaining({
        body: {
          file,
          source_language: "en",
          target_language: "de",
          expected_page_count: 1,
        },
        headers: expect.objectContaining(GDPR_HEADERS),
        signal: controller.signal,
      })
    );
  });

  it("checkHealth throws on non-ok response", async () => {
    mockHealth.mockResolvedValue({
      data: undefined,
      error: { detail: "down" },
      response: { ok: false, status: 503 },
    });

    await expect(checkHealth()).rejects.toThrow(/Health check failed \(503\)/);
  });

  it("checkHealth returns liveness payload on success", async () => {
    const payload = { status: "ok", version: "1.0.0", sprint: 3 };
    mockHealth.mockResolvedValue({
      data: payload,
      response: { ok: true, status: 200 },
    });

    await expect(checkHealth()).resolves.toEqual(payload);
  });

  it("createExchangeRoom sends participants with GDPR consent", async () => {
    mockCreateRoom.mockResolvedValue({
      data: { room_id: "!permit:evidence.eu" },
      response: { ok: true, status: 200 },
    });

    await expect(createExchangeRoom(["@reviewer:evidence.eu"])).resolves.toEqual({
      room_id: "!permit:evidence.eu",
    });
    expect(mockCreateRoom).toHaveBeenCalledWith(
      expect.objectContaining({
        body: { participants: ["@reviewer:evidence.eu"] },
        headers: expect.objectContaining(GDPR_HEADERS),
      })
    );
  });

  it.each([
    [
      401,
      { detail: "Matrix authentication required" },
      "matrix_authentication_required",
    ],
    [
      403,
      { detail: { detail: "feature not enabled", flag: "ENABLE_MATRIX_EXCHANGE" } },
      "matrix_exchange_disabled",
    ],
    [
      502,
      {
        detail: {
          code: "matrix_room_creation_failed",
          message: "The Matrix room could not be created.",
        },
      },
      "matrix_room_creation_failed",
    ],
    [
      502,
      {
        detail: {
          code: "matrix_invitation_forbidden",
          message: "The participant's Matrix server rejected the invitation.",
        },
      },
      "matrix_invitation_forbidden",
    ],
    [
      429,
      {
        detail: {
          code: "matrix_rate_limited",
          message: "Matrix is limiting room requests.",
        },
      },
      "matrix_rate_limited",
    ],
  ] as const)("createExchangeRoom maps HTTP %s to %s", async (status, error, expectedCode) => {
    mockCreateRoom.mockResolvedValue({
      data: undefined,
      error,
      response: { ok: false, status },
    });

    await expect(createExchangeRoom(["@reviewer:evidence.eu"])).rejects.toMatchObject({
      status,
      code: expectedCode,
    });
  });
});
