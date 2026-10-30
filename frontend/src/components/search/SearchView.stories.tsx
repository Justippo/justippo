import type { Meta, StoryObj } from "@storybook/react";
import { SearchView } from "./SearchView";

const meta: Meta<typeof SearchView> = {
  title: "Search/SearchView",
  component: SearchView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof SearchView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
