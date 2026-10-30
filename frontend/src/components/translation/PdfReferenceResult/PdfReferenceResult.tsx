import type { ChangeEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Columns2,
  Download,
  ExternalLink,
  FileText,
  FileUp,
  Languages,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/atoms";
import type { DocumentViewerState, TranslationResultMode } from "@/hooks/useTranslationView";
import type { PdfReferenceTranslationResponse } from "@/lib/api-generated";
import { useT } from "@/hooks/useT";

interface LanguageOption {
  readonly code: string;
  readonly label: string;
}

interface PdfReferenceResultProps {
  readonly className?: string;
  readonly viewState: DocumentViewerState;
  readonly filename: string;
  readonly sourceLang: string;
  readonly targetLang: string;
  readonly resultMode: TranslationResultMode;
  readonly languageOptions: ReadonlyArray<LanguageOption>;
  readonly result: PdfReferenceTranslationResponse | null;
  readonly sourcePdfUrl: string | null;
  readonly translatedPdfUrl: string | null;
  readonly warnings: readonly string[];
  readonly error: string | null;
  readonly onLanguageChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  readonly onShowTranslation: () => void;
  readonly onShowComparison: () => void;
  readonly onReset: () => void;
  readonly onUploadClick: () => void;
}

export function PdfReferenceResult({
  className = "",
  viewState,
  filename,
  sourceLang,
  targetLang,
  resultMode,
  languageOptions,
  result,
  sourcePdfUrl,
  translatedPdfUrl,
  warnings,
  error,
  onLanguageChange,
  onShowTranslation,
  onShowComparison,
  onReset,
  onUploadClick,
}: Readonly<PdfReferenceResultProps>) {
  const { t } = useT();
  const interfaceLanguageLabel = (languageCode: string, fallback: string) => {
    const translatedLabel = t(`language.${languageCode}`);
    return translatedLabel === `language.${languageCode}` ? fallback : translatedLabel;
  };

  return (
    <main className={`mx-auto max-w-container-max space-y-lg ${className}`}>
      <header className="flex flex-wrap items-center justify-between gap-md border-b border-outline-variant pb-md">
        <div>
          <h1 className="text-headline-lg text-on-surface">{t("translation.pdf.title")}</h1>
          <p className="mt-xs text-label-sm text-on-surface-variant">{filename}</p>
        </div>
        <div className="flex flex-wrap items-center gap-sm">
          <Button variant="ghost" onClick={onUploadClick} data-testid="translate-another">
            <FileUp size={16} aria-hidden="true" />
            {t("translation.viewer.another")}
          </Button>
          {viewState === "success" && (
            <div
              className="inline-flex rounded-full border border-outline-variant bg-surface-container-low p-xs"
              role="group"
              aria-label={t("translation.pdf.view")}
            >
              <button
                type="button"
                className={`inline-flex items-center gap-xs rounded-full px-sm py-xs text-label-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus ${
                  resultMode === "translation"
                    ? "bg-surface-container-lowest font-bold text-primary"
                    : "text-on-surface-variant"
                }`}
                aria-pressed={resultMode === "translation"}
                onClick={onShowTranslation}
              >
                <Languages size={16} aria-hidden="true" />
                {t("translation.viewer.translation")}
              </button>
              <button
                type="button"
                className={`inline-flex items-center gap-xs rounded-full px-sm py-xs text-label-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus ${
                  resultMode === "compare"
                    ? "bg-surface-container-lowest font-bold text-primary"
                    : "text-on-surface-variant"
                }`}
                aria-pressed={resultMode === "compare"}
                onClick={onShowComparison}
              >
                <Columns2 size={16} aria-hidden="true" />
                {t("translation.viewer.compare")}
              </button>
            </div>
          )}
          <span className="rounded-full bg-primary-container px-sm py-xs text-label-sm text-on-primary">
            {sourceLang.toUpperCase()} → {targetLang.toUpperCase()}
          </span>
          <label className="sr-only" htmlFor="pdf-reference-target-language">
            {t("translate.target_label")}
          </label>
          <select
            id="pdf-reference-target-language"
            value={targetLang}
            onChange={onLanguageChange}
            disabled={viewState === "loading"}
            aria-busy={viewState === "loading"}
            className="rounded-full border border-outline-variant bg-surface px-sm py-xs text-label-sm text-on-surface focus:border-primary focus:outline focus:outline-2 focus:outline-focus"
          >
            {languageOptions.map((language) => (
              <option key={language.code} value={language.code}>
                {interfaceLanguageLabel(language.code, language.label)}
              </option>
            ))}
          </select>
        </div>
      </header>

      {viewState === "loading" && (
        <section
          className="rounded-lg border border-outline-variant bg-surface-container-lowest p-xl text-center"
          role="status"
          aria-live="polite"
        >
          <FileText className="mx-auto text-primary" size={32} aria-hidden="true" />
          <h2 className="mt-md text-headline-md text-on-surface">
            {t("translation.pdf.translating")} {sourceLang.toUpperCase()} →{" "}
            {targetLang.toUpperCase()}
          </h2>
          <p className="mt-sm text-body-md text-on-surface-variant">
            {t("translation.pdf.loading_body")}
          </p>
          <div className="mx-auto mt-lg h-sm max-w-md overflow-hidden rounded-full bg-outline-variant">
            <div className="h-full w-2/3 animate-pulse rounded-full bg-primary motion-reduce:animate-none" />
          </div>
        </section>
      )}

      {viewState === "error" && (
        <section
          className="rounded-lg border border-error bg-surface-container-lowest p-xl text-center"
          role="alert"
        >
          <AlertTriangle className="mx-auto text-error" size={32} aria-hidden="true" />
          <h2 className="mt-md text-headline-md text-on-surface">
            {t("translation.pdf.not_completed")}
          </h2>
          <p className="mt-sm text-body-md text-error" data-testid="pdf-reference-error">
            {error}
          </p>
          <div className="mt-lg flex justify-center gap-sm">
            <Button variant="primary" onClick={onReset}>
              {t("common.try_again")}
            </Button>
            <Button variant="ghost" onClick={onUploadClick}>
              {t("translation.pdf.choose_another")}
            </Button>
          </div>
        </section>
      )}

      {viewState === "empty" && (
        <section className="rounded-lg border border-outline-variant bg-surface-container-lowest p-xl text-center">
          <FileText className="mx-auto text-primary" size={32} aria-hidden="true" />
          <h2 className="mt-md text-headline-md text-on-surface">
            {t("translation.pdf.none_selected")}
          </h2>
          <p className="mt-sm text-body-md text-on-surface-variant">
            {t("translation.pdf.none_body")}
          </p>
          <Button variant="primary" className="mt-lg" onClick={onUploadClick}>
            {t("translation.pdf.choose")}
          </Button>
        </section>
      )}

      {viewState === "success" && result && translatedPdfUrl && (
        <>
          <section
            className="rounded-lg border border-primary bg-surface-container-lowest p-md"
            aria-label={t("translation.pdf.reference_notice")}
          >
            <div className="flex gap-sm">
              <ShieldCheck className="shrink-0 text-primary" size={24} aria-hidden="true" />
              <div>
                <h2 className="text-headline-md text-on-surface">
                  {t("translation.pdf.reference_only")}
                </h2>
                <p className="mt-xs text-body-md text-on-surface-variant">
                  {t("translation.pdf.reference_body")}
                </p>
              </div>
            </div>
          </section>

          {warnings.length > 0 && (
            <section className="space-y-xs" aria-label={t("translation.pdf.translation_notices")}>
              {warnings.map((warning) => (
                <p
                  key={warning}
                  className="rounded-md border border-warning bg-surface-container-lowest p-sm text-label-sm text-warning"
                >
                  {warning}
                </p>
              ))}
            </section>
          )}

          <section
            className={`grid gap-md ${resultMode === "compare" ? "lg:grid-cols-2" : "grid-cols-1"}`}
            aria-label={t("translation.pdf.viewer")}
          >
            {resultMode === "compare" && sourcePdfUrl && (
              <div className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest">
                <h2 className="border-b border-outline-variant p-sm text-headline-md text-on-surface">
                  {t("translation.pdf.original")}
                </h2>
                <iframe
                  title={`Original PDF: ${filename}`}
                  src={sourcePdfUrl}
                  className="h-[36rem] w-full"
                />
              </div>
            )}
            <div className="overflow-hidden rounded-lg border border-outline-variant bg-surface-container-lowest">
              <div className="flex flex-wrap items-center justify-between gap-sm border-b border-outline-variant p-sm">
                <h2 className="text-headline-md text-on-surface">
                  {t("translation.pdf.translated_reference")}
                </h2>
                <div className="flex gap-sm">
                  <a
                    href={translatedPdfUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-xs rounded-md px-sm py-xs text-label-sm font-bold text-primary focus:outline focus:outline-2 focus:outline-focus"
                  >
                    <ExternalLink size={16} aria-hidden="true" /> {t("translation.pdf.open")}
                  </a>
                  <a
                    href={translatedPdfUrl}
                    download={`translated-${filename}`}
                    className="inline-flex items-center gap-xs rounded-md bg-primary px-sm py-xs text-label-sm font-bold text-on-primary focus:outline focus:outline-2 focus:outline-focus"
                  >
                    <Download size={16} aria-hidden="true" /> {t("translation.pdf.download")}
                  </a>
                </div>
              </div>
              <iframe
                key={result.request_id}
                title={`Translated PDF reference: ${filename}`}
                src={translatedPdfUrl}
                className="h-[36rem] w-full"
              />
            </div>
          </section>

          <div className="grid gap-md lg:grid-cols-2">
            <section className="rounded-lg border border-outline-variant bg-surface-container-lowest p-lg">
              <h2 className="flex items-center gap-xs text-headline-md text-on-surface">
                <CheckCircle2 className="text-success" size={20} aria-hidden="true" />
                {t("translation.explanation.requirements_title")}
              </h2>
              {result.document_explanation.requirements.length > 0 ? (
                <ul className="mt-md space-y-sm">
                  {result.document_explanation.requirements.map((requirement) => (
                    <li
                      key={`${requirement.kind}-${requirement.page_number}-${requirement.text}`}
                      className="border-l-2 border-primary pl-sm text-body-md text-on-surface"
                    >
                      {requirement.text}
                      {requirement.page_number && (
                        <span className="ml-xs text-label-sm text-on-surface-variant">
                          {t("translation.upload.page")} {requirement.page_number}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-md text-body-md text-on-surface-variant">
                  {t("translation.explanation.no_requirements")}
                </p>
              )}
            </section>

            <section className="rounded-lg border border-outline-variant bg-surface-container-lowest p-lg">
              <h2 className="text-headline-md text-on-surface">
                {t("translation.explanation.eu_context")}
              </h2>
              {result.document_explanation.explanation ? (
                <p
                  className="mt-md whitespace-pre-wrap text-body-md text-on-surface"
                  data-sensitive
                >
                  {result.document_explanation.explanation}
                </p>
              ) : (
                <p className="mt-md text-body-md text-on-surface-variant">
                  {t("translation.explanation.no_summary")}
                </p>
              )}
              {result.document_explanation.citations.length > 0 && (
                <ol className="mt-md space-y-sm">
                  {result.document_explanation.citations.map((citation) => (
                    <li key={citation.url} className="text-body-md text-on-surface">
                      <a
                        href={citation.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-bold text-primary underline focus:outline focus:outline-2 focus:outline-focus"
                      >
                        {t("translation.explanation.source")} {citation.source_number}:{" "}
                        {citation.title}
                      </a>
                      <p className="mt-xs text-label-sm text-on-surface-variant">
                        {citation.excerpt}
                      </p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        </>
      )}
    </main>
  );
}
