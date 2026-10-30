import type { Meta, StoryObj } from "@storybook/react";
import { NavigationBar } from "./NavigationBar";
import { AuthProvider } from "@/context/AuthContext";

const meta: Meta<typeof NavigationBar> = {
  title: "Shell/NavigationBar",
  component: NavigationBar,
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
type Story = StoryObj<typeof NavigationBar>;

export const Default: Story = {};
