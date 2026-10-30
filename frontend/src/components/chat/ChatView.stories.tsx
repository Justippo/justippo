import type { Meta, StoryObj } from "@storybook/react";
import { ChatView } from "./ChatView";

const meta: Meta<typeof ChatView> = {
  title: "Chat/ChatView",
  component: ChatView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof ChatView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
