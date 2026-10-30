import type { Meta, StoryObj } from "@storybook/react";
import { Input } from "./Input";

const meta: Meta<typeof Input> = {
  title: "Atoms/Input",
  component: Input,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof Input>;

export const Default: Story = {
  args: { id: "search", placeholder: "Search documents..." },
};

export const Disabled: Story = {
  args: { id: "disabled-input", placeholder: "Disabled", disabled: true },
};

export const WithValue: Story = {
  args: { id: "filled", value: "contract liability" },
};
