import type { Meta, StoryObj } from "@storybook/react";
import { LanguagePairBadge } from "./LanguagePairBadge";

const meta: Meta<typeof LanguagePairBadge> = {
  title: "Translation/LanguagePairBadge",
  component: LanguagePairBadge,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof LanguagePairBadge>;

export const GermanToEnglish: Story = {
  args: { sourceLang: "de", targetLang: "en" },
};

export const EnglishToFrench: Story = {
  args: { sourceLang: "en", targetLang: "fr" },
};
