import type { Meta, StoryObj } from "@storybook/react";
import { TranslationView } from "./TranslationView";

const meta: Meta<typeof TranslationView> = {
  title: "Translation/TranslationView",
  component: TranslationView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof TranslationView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
