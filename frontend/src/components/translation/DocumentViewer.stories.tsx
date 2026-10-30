import type { Meta, StoryObj } from "@storybook/react";
import { DocumentViewer } from "./DocumentViewer";
import { TRANSLATION_SAMPLE_RESULT, TRANSLATION_SAMPLE_SOURCE_PAGES } from "@/data/mockData";
import { TARGET_LANGUAGE_OPTIONS } from "@/lib/language-codes";

const meta: Meta<typeof DocumentViewer> = {
  title: "Translation/DocumentViewer",
  component: DocumentViewer,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof DocumentViewer>;

const baseArgs = {
  filename: "residence-permit-application.pdf",
  sourceLang: "de",
  targetLang: "en",
  resultMode: "translation" as const,
  languageOptions: TARGET_LANGUAGE_OPTIONS,
  sourcePages: TRANSLATION_SAMPLE_SOURCE_PAGES,
  onLanguageChange: () => undefined,
  onShowTranslation: () => undefined,
  onShowComparison: () => undefined,
  onReset: () => undefined,
  onUploadClick: () => undefined,
};

export const Empty: Story = {
  args: {
    ...baseArgs,
    viewState: "empty",
    result: null,
    isTruncated: false,
    error: null,
    sourcePages: [],
  },
};

export const Loading: Story = {
  args: {
    ...baseArgs,
    viewState: "loading",
    result: null,
    isTruncated: false,
    error: null,
    sourcePages: [],
  },
};

export const Success: Story = {
  args: {
    ...baseArgs,
    viewState: "success",
    result: TRANSLATION_SAMPLE_RESULT,
    isTruncated: true,
    error: null,
  },
};

export const Error: Story = {
  args: {
    ...baseArgs,
    viewState: "error",
    result: null,
    isTruncated: false,
    error: "Translation could not be completed. Check your connection and try again.",
    sourcePages: [],
  },
};
