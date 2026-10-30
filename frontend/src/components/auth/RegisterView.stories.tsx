import type { Meta, StoryObj } from "@storybook/react";
import { RegisterView } from "./RegisterView";

const meta: Meta<typeof RegisterView> = {
  title: "Organisms/RegisterView",
  component: RegisterView,
};

export default meta;

type Story = StoryObj<typeof RegisterView>;

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
