import type { Meta, StoryObj } from "@storybook/react";
import { OfflineBanner } from "./OfflineBanner";
import { NotFoundView } from "./NotFoundView";
import { ErrorView } from "./ErrorView";

const offlineMeta: Meta<typeof OfflineBanner> = {
  title: "System/OfflineBanner",
  component: OfflineBanner,
  tags: ["autodocs"],
};

export default offlineMeta;
type OfflineStory = StoryObj<typeof OfflineBanner>;

export const Default: OfflineStory = {};

export const NotFound: StoryObj<typeof NotFoundView> = {
  render: () => <NotFoundView />,
};

export const Error: StoryObj<typeof ErrorView> = {
  render: () => <ErrorView onRetry={() => undefined} />,
};
