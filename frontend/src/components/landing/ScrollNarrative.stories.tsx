import type { Meta, StoryObj } from "@storybook/react";
import { ScrollNarrative } from "./ScrollNarrative";

const meta: Meta<typeof ScrollNarrative> = {
  title: "Organisms/ScrollNarrative",
  component: ScrollNarrative,
};

export default meta;

type Story = StoryObj<typeof ScrollNarrative>;

export const Default: Story = {
  args: {
    steps: [
      { id: "discover", label: "Discover" },
      { id: "act", label: "Act" },
    ],
    children: [
      <section key="discover">Understand the cross-border document challenge.</section>,
      <section key="act">Start a secure EvidenceEU workflow.</section>,
    ],
  },
};
