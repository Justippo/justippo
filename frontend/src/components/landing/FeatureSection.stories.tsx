import type { Meta, StoryObj } from "@storybook/react";
import { FeatureSection } from "./FeatureSection";

const meta: Meta<typeof FeatureSection> = {
  title: "Landing/FeatureSection",
  component: FeatureSection,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof FeatureSection>;

const mockFeatures = [
  { id: "upload", headline: "Upload", description: "Drop docs.", stat: "98%", statLabel: "OCR" },
  {
    id: "translate",
    headline: "Translate",
    description: "AI translate.",
    stat: "3",
    statLabel: "Languages",
  },
  {
    id: "search",
    headline: "Search",
    description: "RAG search.",
    stat: "<3s",
    statLabel: "Latency",
  },
];

export const Default: Story = { args: { features: mockFeatures } };
export const Empty: Story = { args: { features: [] } };
