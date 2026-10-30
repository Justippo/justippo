import type { Meta, StoryObj } from "@storybook/react";
import { AppShell } from "./AppShell";
import { AuthProvider } from "@/context/AuthContext";

const meta: Meta<typeof AppShell> = {
  title: "Shell/AppShell",
  component: AppShell,
  decorators: [
    (Story) => (
      <AuthProvider>
        <Story />
      </AuthProvider>
    ),
  ],
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof AppShell>;

export const Default: Story = {
  args: { children: <div style={{ padding: "2rem" }}>Page content here</div> },
};
