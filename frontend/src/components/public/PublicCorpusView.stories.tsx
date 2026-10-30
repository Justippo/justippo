import type { Meta, StoryObj } from "@storybook/react";
import { PublicCorpusView } from "./PublicCorpusView";

const meta: Meta<typeof PublicCorpusView> = {
  title: "Public/PublicCorpusView",
  component: PublicCorpusView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof PublicCorpusView>;

export const Success: Story = { args: { forcedState: "success" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Empty: Story = { args: { forcedState: "empty" } };
export const Error: Story = { args: { forcedState: "error" } };
