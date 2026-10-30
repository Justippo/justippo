import type { Meta, StoryObj } from "@storybook/react";
import { LandingView } from "./LandingView";

const meta: Meta<typeof LandingView> = {
  title: "Organisms/LandingView",
  component: LandingView,
};

export default meta;

type Story = StoryObj<typeof LandingView>;

export const Success: Story = {
  args: { forcedState: "success" },
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
