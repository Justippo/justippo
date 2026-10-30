import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "./Button";

const meta: Meta<typeof Button> = {
  title: "Atoms/Button",
  component: Button,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof Button>;

export const Primary: Story = {
  args: { children: "Upload Document", variant: "primary" },
};

export const Secondary: Story = {
  args: { children: "Cancel", variant: "secondary" },
};

export const Error: Story = {
  args: { children: "Delete", variant: "error" },
};

export const Ghost: Story = {
  args: { children: "Learn more", variant: "ghost" },
};

export const Disabled: Story = {
  args: { children: "Submit", disabled: true },
};

export const Small: Story = {
  args: { children: "Retry", size: "sm" },
};

export const Large: Story = {
  args: { children: "Get Started", size: "lg" },
};
