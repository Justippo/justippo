"use client";

import { Suspense } from "react";
import { DocumentViewer } from "./DocumentViewer";
import { PdfReferenceResult } from "./PdfReferenceResult";
import { UploadView } from "@/components/upload/UploadView";
import {
  useTranslationView,
  type DocumentViewerState,
  type TranslationResultMode,
} from "@/hooks/useTranslationView";
import { useTranslationWorkflow } from "@/hooks/useTranslationWorkflow";
import { useT } from "@/hooks/useT";
import styles from "./TranslationView.module.css";

interface TranslationViewProps {
  readonly className?: string;
  readonly forcedState?: DocumentViewerState;
}

interface TranslationResultStepProps extends TranslationViewProps {
  readonly initialResultMode?: TranslationResultMode;
  readonly referenceFile?: File | null;
  readonly onUploadClick?: () => void;
}

function TranslationResultStep({
  className,
  forcedState,
  initialResultMode,
  referenceFile = null,
  onUploadClick,
}: Readonly<TranslationResultStepProps>) {
  const viewer = useTranslationView({ forcedState, initialResultMode, referenceFile });
  const handleUploadClick = onUploadClick ?? viewer.onUploadClick;

  if (viewer.isPdfReference) {
    return (
      <PdfReferenceResult
        className={className}
        viewState={viewer.viewState}
        filename={viewer.filename}
        sourceLang={viewer.sourceLang}
        targetLang={viewer.targetLang}
        resultMode={viewer.resultMode}
        languageOptions={viewer.languageOptions}
        result={viewer.referenceResult}
        sourcePdfUrl={viewer.sourcePdfUrl}
        translatedPdfUrl={viewer.translatedPdfUrl}
        warnings={viewer.referenceWarnings}
        error={viewer.error}
        onLanguageChange={viewer.handleLanguageChange}
        onShowTranslation={viewer.onShowTranslation}
        onShowComparison={viewer.onShowComparison}
        onReset={viewer.reset}
        onUploadClick={handleUploadClick}
      />
    );
  }

  return (
    <DocumentViewer
      className={className}
      viewState={viewer.viewState}
      filename={viewer.filename}
      sourceLang={viewer.sourceLang}
      targetLang={viewer.targetLang}
      resultMode={viewer.resultMode}
      languageOptions={viewer.languageOptions}
      sourcePages={viewer.sourcePages}
      sourceSections={viewer.sourceSections}
      result={viewer.result}
      isTruncated={viewer.isTruncated}
      isDocumentUnderstanding={viewer.isDocumentUnderstanding}
      documentExplanation={viewer.documentExplanation}
      documentExplanationWarnings={viewer.documentExplanationWarnings}
      error={viewer.error}
      onLanguageChange={viewer.handleLanguageChange}
      onShowTranslation={viewer.onShowTranslation}
      onShowComparison={viewer.onShowComparison}
      onReset={viewer.reset}
      onUploadClick={handleUploadClick}
      canDownload={viewer.canDownload}
      onDownload={viewer.onDownload}
    />
  );
}

function TranslationWorkflowStep({ className }: Readonly<Pick<TranslationViewProps, "className">>) {
  const workflow = useTranslationWorkflow();
  const { t } = useT();

  if (workflow.stage === "checking") {
    return (
      <div className={`${styles.checking} ${className}`} role="status">
        {t("translation.workflow.preparing")}
      </div>
    );
  }

  if (workflow.stage === "upload") {
    return (
      <UploadView className={className} context="translation" onContinue={workflow.onContinue} />
    );
  }

  return (
    <TranslationResultStep
      className={className}
      initialResultMode={workflow.resultMode}
      referenceFile={workflow.referenceFile}
      onUploadClick={workflow.onChooseAnother}
    />
  );
}

export function TranslationView({ className = "", forcedState }: Readonly<TranslationViewProps>) {
  const { t } = useT();

  if (forcedState) {
    return <TranslationResultStep className={className} forcedState={forcedState} />;
  }

  return (
    <Suspense
      fallback={
        <div className={`${styles.checking} ${className}`} role="status">
          {t("translation.workflow.preparing")}
        </div>
      }
    >
      <TranslationWorkflowStep className={className} />
    </Suspense>
  );
}
