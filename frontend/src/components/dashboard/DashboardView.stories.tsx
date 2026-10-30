import type { Meta, StoryObj } from "@storybook/react";
import { DashboardView } from "./DashboardView";

const meta: Meta<typeof DashboardView> = {
  title: "Dashboard/DashboardView",
  component: DashboardView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof DashboardView>;

export const Success: Story = { args: { forcedState: "success" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Empty: Story = { args: { forcedState: "empty" } };
export const Error: Story = { args: { forcedState: "error" } };
