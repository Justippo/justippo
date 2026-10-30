import type { Meta, StoryObj } from "@storybook/react";
import { SettingsView } from "./SettingsView";

const meta: Meta<typeof SettingsView> = {
  title: "Settings/SettingsView",
  component: SettingsView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof SettingsView>;

export const Success: Story = { args: { forcedState: "success" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Empty: Story = { args: { forcedState: "empty" } };
export const Error: Story = { args: { forcedState: "error" } };
