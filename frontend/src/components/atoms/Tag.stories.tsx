import type { Meta, StoryObj } from "@storybook/react";
import { Tag } from "./Tag";

const meta: Meta<typeof Tag> = {
  title: "Atoms/Tag",
  component: Tag,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof Tag>;

export const Default: Story = {
  args: { children: "PDF" },
};

export const Primary: Story = {
  args: { children: "English", variant: "primary" },
};

export const WithRemove: Story = {
  args: { children: "German", onRemove: () => {} },
};
