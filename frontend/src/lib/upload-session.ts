import type {
  DocumentClassification,
  DocumentExplanation,
  UploadResponse,
} from "@/lib/api-generated";
import type { SupportedLanguage } from "@evidenceeu/shared";

type SourceLanguage = SupportedLanguage;
type TargetLanguage = SupportedLanguage;
// prettier-ignore
export type PdfProcessingMode =
  "none" | "pdf_reference_translation" | "document_understanding_translation";

export interface UploadSessionData {
  readonly filename: string;
  readonly sourcePages: ReadonlyArray<Readonly<{ page: number; text: string }>>;
  readonly documentId: string;
  readonly pageCount: number;
  readonly sourceLang: SourceLanguage;
  readonly targetLang: TargetLanguage;
  readonly pdfReferenceEligible: boolean;
  readonly pdfProcessingMode: PdfProcessingMode;
  readonly classification: DocumentClassification | null;
  readonly documentExplanation: DocumentExplanation | null;
}

const UPLOAD_SESSION_KEY = "evidence-eu-document-data";
const EMPTY_UPLOAD_SESSION: UploadSessionData = {
  filename: "Document",
  sourcePages: [],
  documentId: "",
  pageCount: 0,
  sourceLang: "en",
  targetLang: "de",
  pdfReferenceEligible: false,
  pdfProcessingMode: "none",
  classification: null,
  documentExplanation: null,
};

const SUPPORTED_SOURCE_LANGUAGES: readonly SourceLanguage[] = ["en", "de", "fr"];

function normalizeSourceLanguage(languageCode?: string): SourceLanguage {
  return SUPPORTED_SOURCE_LANGUAGES.includes(languageCode as SourceLanguage)
    ? (languageCode as SourceLanguage)
    : "en";
}

function normalizeTargetLanguage(languageCode?: string): TargetLanguage {
  return SUPPORTED_SOURCE_LANGUAGES.includes(languageCode as TargetLanguage)
    ? (languageCode as TargetLanguage)
    : "de";
}

export function readUploadSession(): UploadSessionData {
  if (typeof window === "undefined") return EMPTY_UPLOAD_SESSION;
  try {
    const raw = sessionStorage.getItem(UPLOAD_SESSION_KEY);
    if (!raw) return EMPTY_UPLOAD_SESSION;
    const stored = JSON.parse(raw) as Partial<UploadSessionData>;
    return {
      filename: stored.filename || EMPTY_UPLOAD_SESSION.filename,
      sourcePages: Array.isArray(stored.sourcePages) ? stored.sourcePages : [],
      documentId: stored.documentId || "",
      pageCount:
        typeof stored.pageCount === "number" && stored.pageCount > 0
          ? stored.pageCount
          : Array.isArray(stored.sourcePages)
            ? stored.sourcePages.length
            : 0,
      sourceLang: normalizeSourceLanguage(stored.sourceLang),
      targetLang: normalizeTargetLanguage(stored.targetLang),
      pdfReferenceEligible: stored.pdfReferenceEligible === true,
      pdfProcessingMode:
        stored.pdfProcessingMode === "pdf_reference_translation" ||
        stored.pdfProcessingMode === "document_understanding_translation"
          ? stored.pdfProcessingMode
          : stored.pdfReferenceEligible === true
            ? "pdf_reference_translation"
            : "none",
      classification: stored.classification ?? null,
      documentExplanation: stored.documentExplanation ?? null,
    };
  } catch {
    return EMPTY_UPLOAD_SESSION;
  }
}

export function saveUploadSession(file: File, result: UploadResponse, targetLang = "de"): void {
  try {
    sessionStorage.setItem(
      UPLOAD_SESSION_KEY,
      JSON.stringify({
        filename: file.name,
        sourcePages: result.pages.map((page) => ({ page: page.page, text: page.text })),
        documentId: result.doc_id,
        pageCount: result.page_count,
        sourceLang: normalizeSourceLanguage(result.classification?.language_code),
        targetLang: normalizeTargetLanguage(result.target_language ?? targetLang),
        pdfReferenceEligible: result.pdf_processing?.route === "pdf_reference_translation",
        pdfProcessingMode: result.pdf_processing?.route ?? "none",
        classification: result.classification ?? null,
        documentExplanation: result.document_explanation ?? null,
      })
    );
  } catch (error) {
    console.error("Failed to save document data", error);
  }
}

export function updateUploadSessionTargetLanguage(targetLang: string): void {
  const current = readUploadSession();
  if (!current.documentId) return;
  try {
    sessionStorage.setItem(
      UPLOAD_SESSION_KEY,
      JSON.stringify({ ...current, targetLang: normalizeTargetLanguage(targetLang) })
    );
  } catch (error) {
    console.error("Failed to update document data", error);
  }
}

export function clearUploadSession(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(UPLOAD_SESSION_KEY);
  } catch (error) {
    console.error("Failed to clear document data", error);
  }
}
