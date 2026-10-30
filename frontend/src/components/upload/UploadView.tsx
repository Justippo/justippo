"use client";

import styles from "./UploadView.module.css";
import { useUploadView, type UploadViewState } from "@/hooks/useUploadView";
import { Button, Spinner, Badge, Skeleton } from "@/components/atoms";
import { formatConfidencePercent, getConfidenceBadgeVariant } from "@/lib/upload-confidence";
import { getLanguageLabel } from "@/lib/language-codes";
import { useT } from "@/hooks/useT";

interface UploadViewProps {
  readonly className?: string;
  readonly forcedState?: UploadViewState;
  readonly context?: "standalone" | "translation";
  readonly onContinue?: (targetLang: string, file: File | null) => void;
}

function formatUploadedAt(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function UploadView({
  className = "",
  forcedState,
  context = "standalone",
  onContinue,
}: Readonly<UploadViewProps>) {
  const upload = useUploadView({ forcedState, onContinue });
  const { t } = useT();
  const isTranslationFlow = context === "translation";
  const pageTitle = isTranslationFlow
    ? t("translation.upload.title")
    : t("translation.upload.documents_title");

  if (upload.viewState === "loading") {
    return (
      <div className={`${styles.container} ${className}`}>
        <h1 className={styles.pageTitle}>{pageTitle}</h1>
        <div
          className={styles.centerState}
          role="status"
          aria-label={t("translation.upload.uploading_aria")}
        >
          <div className={styles.successHeader}>
            <Skeleton height="1.5rem" width="200px" />
            <Skeleton height="1.5rem" width="80px" borderRadius="var(--stitch-radius-sm)" />
          </div>
          <div className={styles.tableSkeleton}>
            {[1, 2, 3].map((row) => (
              <div key={row} className={styles.tableRowSkeleton}>
                <Skeleton height="0.875rem" width="40px" />
                <Skeleton height="0.875rem" width="50px" />
                <Skeleton height="0.875rem" width="60%" />
              </div>
            ))}
          </div>
          <Spinner size="md" aria-label={t("translation.upload.processing")} />
          <p className={styles.stateText}>{t("translation.upload.extracting")}</p>
        </div>
      </div>
    );
  }

  if (upload.viewState === "error") {
    return (
      <div className={`${styles.container} ${className}`}>
        <h1 className={styles.pageTitle}>{pageTitle}</h1>
        <div className={styles.centerState} role="alert">
          <p className={styles.errorText} data-testid="upload-error">
            {upload.error}
          </p>
          <Button variant="primary" onClick={upload.onReset}>
            {t("common.try_again")}
          </Button>
        </div>
      </div>
    );
  }

  if (upload.viewState === "success" && upload.result) {
    return (
      <div className={`${styles.container} ${className}`}>
        <h1 className={styles.pageTitle}>{pageTitle}</h1>
        <div className={styles.successHeader}>
          <h2 className={styles.heading}>{t("translation.upload.processed")}</h2>
          <Badge
            variant={upload.averageConfidenceVariant}
            className={upload.averageConfidenceClassName}
            data-testid="upload-avg-confidence"
          >
            {t("translation.upload.ocr_quality")} {upload.averageConfidenceLabel}
          </Badge>
        </div>
        {upload.lowQualityWarning && (
          <p className={styles.warningText} role="status">
            {upload.lowQualityWarning}
          </p>
        )}
        {upload.previewNotice && <p className={styles.previewNotice}>{upload.previewNotice}</p>}
        {isTranslationFlow && upload.translationModeNotice && (
          <p className={styles.previewNotice} role="status">
            {upload.translationModeNotice}
          </p>
        )}
        <table className={styles.pagesTable}>
          <thead>
            <tr>
              <th scope="col">{t("translation.upload.page")}</th>
              <th scope="col">{t("translation.upload.confidence")}</th>
              <th scope="col">{t("translation.upload.text_preview")}</th>
            </tr>
          </thead>
          <tbody>
            {upload.pageRows.map((row) => (
              <tr key={row.page}>
                <td>{row.page}</td>
                <td>
                  <Badge variant={row.confidenceVariant} className={row.confidenceClassName}>
                    {row.confidenceLabel}
                  </Badge>
                </td>
                <td className={styles.textPreview} data-sensitive>
                  {row.previewText}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {isTranslationFlow && (
          <div className={styles.translationSetup}>
            <p className={styles.langLabel} data-testid="translation-target-confirmation">
              {t("translation.upload.target")}: {getLanguageLabel(upload.targetLang)}
            </p>
          </div>
        )}
        <div className={styles.actions}>
          {isTranslationFlow && (
            <Button variant="primary" onClick={upload.onContinueToTranslation}>
              {t("translation.upload.continue")}
            </Button>
          )}
          <Button variant={isTranslationFlow ? "ghost" : "primary"} onClick={upload.onReset}>
            {t("translation.upload.another")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.container} ${className}`}>
      <h1 className={styles.pageTitle}>{pageTitle}</h1>
      <p className={styles.intro}>{t("translation.upload.intro")}</p>

      <form onSubmit={upload.onSubmit}>
        <div
          className={`${styles.dropzone} ${upload.isDragging ? styles.dragging : ""}`}
          data-testid="upload-dropzone"
          onDragEnter={upload.onDragEnter}
          onDragLeave={upload.onDragLeave}
          onDragOver={upload.onDragOver}
          onDrop={upload.onDrop}
        >
          <p className={styles.dropText}>
            {upload.file ? upload.file.name : t("translation.upload.drop")}
          </p>
          <input
            ref={upload.fileInputRef}
            type="file"
            accept=".pdf,.docx,.png,.jpg,.jpeg"
            className={styles.hiddenInput}
            onChange={upload.onFileInputChange}
            aria-label={t("translation.upload.select_file")}
          />
          <Button type="button" variant="ghost" onClick={upload.onBrowseClick}>
            {t("translation.upload.browse")}
          </Button>
          <p className={styles.hint}>PDF, DOCX, PNG, JPEG · Max 15 MB</p>
        </div>

        {upload.fileError && (
          <p className={styles.errorText} data-testid="upload-error">
            {upload.fileError}
          </p>
        )}

        {upload.file && !upload.fileError && (
          <div className={styles.fileActions}>
            <label
              className={styles.langLabel}
              htmlFor={isTranslationFlow ? "translation-target-lang" : "upload-target-lang"}
            >
              {isTranslationFlow
                ? t("translation.upload.translate_into")
                : t("translate.target_label")}
              <select
                id={isTranslationFlow ? "translation-target-lang" : "upload-target-lang"}
                className={styles.langSelect}
                data-testid={isTranslationFlow ? "translation-lang-select" : "upload-lang-select"}
                value={upload.targetLang}
                onChange={(event) => upload.setTargetLang(event.target.value)}
              >
                {upload.targetLanguageOptions.map((language) => (
                  <option key={language.code} value={language.code}>
                    {t(`language.${language.code}`) === `language.${language.code}`
                      ? language.label
                      : t(`language.${language.code}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <div className={styles.consentBlock}>
          <label className={styles.consentLabel}>
            <input
              type="checkbox"
              checked={upload.gdprConsent}
              onChange={(event) => upload.setGdprConsent(event.target.checked)}
              data-testid="upload-gdpr-consent"
            />
            <span>{t("translation.upload.consent")}</span>
          </label>
          {upload.consentError && (
            <p className={styles.consentError} role="alert">
              {t("translation.upload.consent_required")}
            </p>
          )}
        </div>

        {upload.file && !upload.fileError && (
          <div className={styles.submitActions}>
            <Button type="submit" variant="primary" disabled={!upload.canSubmit}>
              {t("translation.upload.submit")}
            </Button>
            <Button type="button" variant="ghost" onClick={upload.onClearFile}>
              {t("common.cancel")}
            </Button>
          </div>
        )}
      </form>

      {!isTranslationFlow && (
        <section className={styles.historySection} aria-labelledby="upload-history-heading">
          <h2 id="upload-history-heading" className={styles.historyTitle}>
            Recent uploads
          </h2>
          {upload.history.length === 0 ? (
            <p className={styles.historyEmpty}>No uploads yet.</p>
          ) : (
            <ul className={styles.historyList}>
              {upload.history.map((item) => (
                <li key={item.id} className={styles.historyItem} data-testid="upload-history-item">
                  <div className={styles.historyMain}>
                    <span className={styles.historyFilename}>{item.filename}</span>
                    <span className={styles.historyMeta}>
                      {item.pageCount} pages · {item.targetLang.toUpperCase()} ·{" "}
                      {formatUploadedAt(item.uploadedAt)}
                    </span>
                  </div>
                  <Badge variant={getConfidenceBadgeVariant(item.avgConfidence)}>
                    {formatConfidencePercent(item.avgConfidence)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
