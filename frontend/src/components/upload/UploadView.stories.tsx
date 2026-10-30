import type { Meta, StoryObj } from "@storybook/react";
import { UploadView } from "./UploadView";

const meta: Meta<typeof UploadView> = {
  title: "Upload/UploadView",
  component: UploadView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof UploadView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
