import type { Meta, StoryObj } from "@storybook/react";
import { BottomNav } from "./BottomNav";

const meta: Meta<typeof BottomNav> = {
  title: "Shell/BottomNav",
  component: BottomNav,
  tags: ["autodocs"],
  parameters: {
    viewport: { defaultViewport: "mobile1" },
  },
};

export default meta;
type Story = StoryObj<typeof BottomNav>;

export const Default: Story = {};
