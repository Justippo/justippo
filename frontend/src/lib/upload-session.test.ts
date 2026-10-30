import { beforeEach, describe, expect, it } from "vitest";
import type { UploadResponse } from "@/lib/api-generated";
import { readUploadSession, saveUploadSession } from "./upload-session";

const file = new File(["%PDF-1.7"], "form.pdf", { type: "application/pdf" });

const understandingResult: UploadResponse = {
  doc_id: "550e8400-e29b-41d4-a716-446655440000",
  status: "processed",
  ephemeral: true,
  page_count: 1,
  target_language: "fr",
  pages: [{ page: 1, text: "Wohnsitznachweis beifügen", confidence: 0.96 }],
  classification: {
    document_type: "residence_application",
    language_code: "de",
    quality_score: 0.9,
    geographic_relevance: ["Germany"],
    safety_flags: [],
    confidence: 0.9,
  },
  pdf_processing: {
    route: "document_understanding_translation",
    output_mode: "extracted_text",
    layout_preserved: false,
    original_unchanged: true,
    form_filling_supported: false,
  },
  document_explanation: {
    document_type: "residence_application",
    language: "en",
    requirements: [{ text: "Wohnsitznachweis beifügen", kind: "instruction", page_number: 1 }],
    legal_context_status: "not_found",
    citations: [],
    warnings: ["NO_VERIFIED_EU_LAW_SOURCE"],
  },
};

describe("upload session PDF processing mode", () => {
  beforeEach(() => sessionStorage.clear());

  it("persists the explicit understanding route and explanation", () => {
    saveUploadSession(file, understandingResult, "en");

    const session = readUploadSession();
    expect(session.pdfReferenceEligible).toBe(false);
    expect(session.pdfProcessingMode).toBe("document_understanding_translation");
    expect(session.targetLang).toBe("fr");
    expect(session.classification?.document_type).toBe("residence_application");
    expect(session.documentExplanation?.requirements[0].text).toContain("Wohnsitznachweis");
  });
});
