import type { Meta, StoryObj } from "@storybook/react";
import { HeroSection } from "./HeroSection";

const meta: Meta<typeof HeroSection> = {
  title: "Landing/HeroSection",
  component: HeroSection,
  tags: ["autodocs"],
};

export default meta;
type Story = StoryObj<typeof HeroSection>;

export const Default: Story = {
  args: {
    headline: "Document intelligence for a borderless Europe.",
    subheadline: "Upload, translate, and search cross-border documents.",
    primaryCta: "Get started free",
    primaryHref: "/register",
    secondaryCta: "See how it works",
    secondaryHref: "#how-it-works",
  },
};
