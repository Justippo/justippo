import type { Meta, StoryObj } from "@storybook/react";
import { PDF_REFERENCE_SAMPLE_RESULT } from "@/data/mockData";
import { TARGET_LANGUAGE_OPTIONS } from "@/lib/language-codes";
import { PdfReferenceResult } from "./PdfReferenceResult";

const meta: Meta<typeof PdfReferenceResult> = {
  title: "Translation/PdfReferenceResult",
  component: PdfReferenceResult,
  tags: ["autodocs"],
  args: {
    filename: "residence-application.pdf",
    sourceLang: "de",
    targetLang: "en",
    resultMode: "translation",
    languageOptions: TARGET_LANGUAGE_OPTIONS,
    result: PDF_REFERENCE_SAMPLE_RESULT,
    sourcePdfUrl: "about:blank",
    translatedPdfUrl: "about:blank",
    warnings: ["This translated PDF is a reference copy, not an official replacement."],
    error: null,
    onLanguageChange: () => undefined,
    onShowTranslation: () => undefined,
    onShowComparison: () => undefined,
    onReset: () => undefined,
    onUploadClick: () => undefined,
  },
};

export default meta;
type Story = StoryObj<typeof PdfReferenceResult>;

export const Success: Story = { args: { viewState: "success" } };
export const Loading: Story = { args: { viewState: "loading", result: null } };
export const Error: Story = {
  args: {
    viewState: "error",
    result: null,
    error: "PDF reference translation could not be completed. Please try again.",
  },
};
export const Empty: Story = { args: { viewState: "empty", result: null } };
