import type { Meta, StoryObj } from "@storybook/react";
import { CompareView } from "./CompareView";

const meta: Meta<typeof CompareView> = {
  title: "Compare/CompareView",
  component: CompareView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof CompareView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
