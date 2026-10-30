import type { Meta, StoryObj } from "@storybook/react";
import { Badge } from "./Badge";

const meta: Meta<typeof Badge> = {
  title: "Atoms/Badge",
  component: Badge,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof Badge>;

export const Default: Story = {
  args: { children: "EN" },
};

export const Success: Story = {
  args: { children: "0.984", variant: "success" },
};

export const Error: Story = {
  args: { children: "Failed", variant: "error" },
};

export const Warning: Story = {
  args: { children: "Truncated", variant: "warning" },
};

export const Info: Story = {
  args: { children: "5 pages", variant: "info" },
};
