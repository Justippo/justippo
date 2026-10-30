import type { Meta, StoryObj } from "@storybook/react";
import { ExchangeView } from "./ExchangeView";

const meta: Meta<typeof ExchangeView> = {
  title: "Exchange/ExchangeView",
  component: ExchangeView,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof ExchangeView>;

export const Empty: Story = { args: { forcedState: "empty" } };
export const Loading: Story = { args: { forcedState: "loading" } };
export const Success: Story = { args: { forcedState: "success" } };
export const Error: Story = { args: { forcedState: "error" } };
