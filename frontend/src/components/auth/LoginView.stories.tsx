import type { Meta, StoryObj } from "@storybook/react";
import { LoginView } from "./LoginView";

const meta: Meta<typeof LoginView> = {
  title: "Organisms/LoginView",
  component: LoginView,
};

export default meta;

type Story = StoryObj<typeof LoginView>;

export const Success: Story = {
  args: { forcedState: "empty" },
};

export const Loading: Story = {
  args: { forcedState: "loading" },
};

export const Error: Story = {
  args: { forcedState: "error" },
};

export const Empty: Story = {
  args: { forcedState: "empty" },
};
