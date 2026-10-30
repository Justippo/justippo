import type { Meta, StoryObj } from "@storybook/react";
import { OnboardingView } from "./OnboardingView";

const meta: Meta<typeof OnboardingView> = {
  title: "Organisms/OnboardingView",
  component: OnboardingView,
};

export default meta;

type Story = StoryObj<typeof OnboardingView>;

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
