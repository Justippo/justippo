import { TRANSLATION_TRUNCATION_NOTICE } from "@/data/mockData";
import { stripTruncationMarker } from "@/lib/translation-truncation";
import styles from "./DocumentViewer.module.css";
import type { ChangeEvent } from "react";
import { Button, Badge, Skeleton, SkeletonText } from "@/components/atoms";
import { LanguagePairBadge } from "./LanguagePairBadge";
import { DocumentExplanationPanel } from "./DocumentExplanationPanel";
import { TranslationQualityPanel } from "./TranslationQualityPanel";
import type { DocumentViewerState, TranslationResultMode } from "@/hooks/useTranslationView";
import type { DocumentExplanation, TranslateResponse } from "@/lib/api-generated";
import { getLanguageLabel } from "@/lib/language-codes";
import { Columns2, Download, FileUp, Languages, ShieldCheck } from "lucide-react";
import { useT } from "@/hooks/useT";

interface SourcePage {
  readonly page: number;
  readonly text: string;
}

interface SourceSection {
  readonly page: number;
  readonly index: number;
  readonly text: string;
}

interface LanguageOption {
  readonly code: string;
  readonly label: string;
}

interface DocumentViewerProps {
  readonly className?: string;
  readonly viewState: DocumentViewerState;
  readonly filename: string;
  readonly sourceLang: string;
  readonly targetLang: string;
  readonly resultMode: TranslationResultMode;
  readonly languageOptions: readonly LanguageOption[];
  readonly sourcePages: readonly SourcePage[];
  readonly sourceSections: readonly SourceSection[];
  readonly result: TranslateResponse | null;
  readonly isTruncated: boolean;
  readonly isDocumentUnderstanding?: boolean;
  readonly documentExplanation?: DocumentExplanation | null;
  readonly documentExplanationWarnings?: readonly string[];
  readonly error: string | null;
  readonly onLanguageChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  readonly onShowTranslation: () => void;
  readonly onShowComparison: () => void;
  readonly onReset: () => void;
  readonly onUploadClick: () => void;
  readonly canDownload?: boolean;
  readonly onDownload?: () => void;
}

export function DocumentViewer({
  className = "",
  viewState,
  filename,
  sourceLang,
  targetLang,
  resultMode,
  languageOptions,
  sourcePages,
  sourceSections,
  result,
  isTruncated,
  isDocumentUnderstanding = false,
  documentExplanation = null,
  documentExplanationWarnings = [],
  error,
  onLanguageChange,
  onShowTranslation,
  onShowComparison,
  onReset,
  onUploadClick,
  canDownload = false,
  onDownload,
}: Readonly<DocumentViewerProps>) {
  const { t } = useT();
  const interfaceLanguageLabel = (languageCode: string, fallback: string) => {
    const translatedLabel = t(`language.${languageCode}`);
    return translatedLabel === `language.${languageCode}` ? fallback : translatedLabel;
  };

  const renderToolbar = () => (
    <div className={styles.toolbar} data-testid="viewer-toolbar">
      <div className={styles.toolbarStart}>
        <h1 className={styles.title} data-testid="viewer-title">
          {t("translation.viewer.result_title")}
        </h1>
        <div className={styles.filename} data-testid="viewer-filename">
          {filename}
        </div>
      </div>
      <div className={styles.toolbarEnd}>
        {viewState === "success" && (
          <div
            className={styles.viewToggle}
            role="group"
            aria-label={t("translation.viewer.result_view")}
          >
            <button
              type="button"
              className={`${styles.viewToggleButton} ${
                resultMode === "translation" ? styles.viewToggleButtonActive : ""
              }`}
              aria-pressed={resultMode === "translation"}
              onClick={onShowTranslation}
            >
              <Languages size={16} aria-hidden="true" />
              {t("translation.viewer.translation")}
            </button>
            <button
              type="button"
              className={`${styles.viewToggleButton} ${
                resultMode === "compare" ? styles.viewToggleButtonActive : ""
              }`}
              aria-pressed={resultMode === "compare"}
              onClick={onShowComparison}
            >
              <Columns2 size={16} aria-hidden="true" />
              {t("translation.viewer.compare")}
            </button>
          </div>
        )}
        {viewState === "success" && canDownload && (
          <Button variant="ghost" onClick={onDownload} data-testid="download-translation">
            <Download size={16} aria-hidden="true" />
            {t("translation.viewer.download_text")}
          </Button>
        )}
        <Button variant="ghost" onClick={onUploadClick} data-testid="translate-another">
          <FileUp size={16} aria-hidden="true" />
          {t("translation.viewer.another")}
        </Button>
        <LanguagePairBadge sourceLang={sourceLang} targetLang={targetLang} />
        <select
          data-testid="viewer-lang"
          value={targetLang}
          onChange={onLanguageChange}
          aria-label={t("translate.target_label")}
        >
          {languageOptions.map((language) => (
            <option key={language.code} value={language.code}>
              {interfaceLanguageLabel(language.code, language.label)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );

  if (viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`} data-testid="viewer-panels">
        {renderToolbar()}
        <div
          className={styles.sideBySide}
          role="status"
          aria-label={t("translation.viewer.translating_document")}
        >
          {sourceSections.map((section) => (
            <div key={`${section.page}-${section.index}`} className={styles.pageRow}>
              <div className={styles.panel} data-testid="viewer-panel-original">
                <Badge variant="info">
                  {t("translation.viewer.section")} {section.index + 1} —{" "}
                  {interfaceLanguageLabel(sourceLang, getLanguageLabel(sourceLang))}
                </Badge>
                <p className={styles.pageText}>{section.text}</p>
              </div>
              <div className={styles.panel} role="group" aria-label={t("translate.status.pending")}>
                <Skeleton height="1rem" width="140px" borderRadius="var(--stitch-radius-sm)" />
                <SkeletonText lines={3} lastLineWidth="55%" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`} data-testid="viewer-panels" role="alert">
        {renderToolbar()}
        <div className={styles.centerState}>
          <p className={styles.errorText} data-testid="viewer-error">
            {error}
          </p>
          <Button variant="primary" onClick={onReset}>
            {t("common.try_again")}
          </Button>
        </div>
      </div>
    );
  }

  if (viewState === "success" && result?.translated_pages) {
    return (
      <div className={`${styles.container} ${className}`} data-testid="viewer-panels">
        {renderToolbar()}

        {isDocumentUnderstanding && (
          <section
            className="rounded-lg border border-primary bg-surface-container-lowest p-md"
            aria-label={t("translation.viewer.understanding_notice")}
          >
            <div className="flex gap-sm">
              <ShieldCheck className="shrink-0 text-primary" size={24} aria-hidden="true" />
              <div>
                <h2 className="text-headline-md text-on-surface">
                  {t("translation.viewer.understanding_title")}
                </h2>
                <p className="mt-xs text-body-md text-on-surface-variant">
                  {t("translation.viewer.understanding_body")}
                </p>
              </div>
            </div>
          </section>
        )}

        {isTruncated && (
          <div className={styles.truncationBanner} data-testid="truncated-banner" role="status">
            {TRANSLATION_TRUNCATION_NOTICE}
          </div>
        )}

        {result.status === "partial" && (
          <div
            className={styles.partialBanner}
            data-testid="partial-translation-banner"
            role="status"
          >
            {t("translation.viewer.partial")}
          </div>
        )}

        <div
          className={styles.sideBySide}
          data-testid="viewer-panels-content"
          data-result-mode={resultMode}
        >
          {result.translated_pages.flatMap((page) => {
            const sections = page.sections
              ? page.sections
              : [
                  {
                    index: 0,
                    source_text:
                      sourcePages.find((sourcePage) => sourcePage.page === page.page)?.text ||
                      t("translation.viewer.source_unavailable"),
                    translated_text: page.text,
                  },
                ];

            return sections.map((section) => (
              <div
                key={`${page.page}-${section.index}`}
                className={`${styles.pageRow} ${
                  resultMode === "translation" ? styles.translationOnlyRow : ""
                }`}
              >
                {resultMode === "compare" && (
                  <div
                    className={styles.panel}
                    lang={sourceLang}
                    data-testid="viewer-panel-original"
                  >
                    <Badge variant="info">
                      {t("translation.viewer.section")} {section.index + 1} —{" "}
                      {interfaceLanguageLabel(sourceLang, getLanguageLabel(sourceLang))}
                    </Badge>
                    <p
                      className={styles.pageText}
                      data-testid={`viewer-panel-original-text-${page.page}-${section.index}`}
                      data-sensitive
                    >
                      {section.source_text}
                    </p>
                  </div>
                )}
                <div
                  className={`${styles.panel} ${
                    resultMode === "translation" ? styles.translationPanel : ""
                  }`}
                  lang={targetLang}
                  data-testid={
                    section.status === "failed"
                      ? "viewer-panel-translation-failed"
                      : "viewer-panel-translated"
                  }
                >
                  <Badge variant={section.status === "failed" ? "warning" : "success"}>
                    {t("translation.viewer.section")} {section.index + 1} —{" "}
                    {interfaceLanguageLabel(targetLang, getLanguageLabel(targetLang))}
                  </Badge>
                  <p
                    className={styles.pageText}
                    data-testid={`viewer-panel-translated-text-${page.page}-${section.index}`}
                  >
                    {section.status === "failed"
                      ? `${t("translation.viewer.failed_before")} ${section.attempts ?? 2} ${t(
                          "translation.viewer.failed_after"
                        )}`
                      : stripTruncationMarker(section.translated_text)}
                  </p>
                </div>
              </div>
            ));
          })}
        </div>
        {result.quality_report && (
          <TranslationQualityPanel
            report={result.quality_report}
            glossaryTermsApplied={result.glossary_terms_applied ?? 0}
          />
        )}
        {isDocumentUnderstanding && documentExplanation && (
          <DocumentExplanationPanel
            explanation={documentExplanation}
            warnings={documentExplanationWarnings}
          />
        )}
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`} data-testid="viewer-panels">
      {renderToolbar()}
      <div className={styles.centerState}>
        <h2 className={styles.heading}>{t("translation.viewer.translation")}</h2>
        <p className={styles.stateText}>{t("translation.viewer.empty_body")}</p>
        <Button variant="primary" onClick={onUploadClick} data-testid="viewer-upload-cta">
          {t("translation.viewer.start")}
        </Button>
      </div>
    </div>
  );
}
