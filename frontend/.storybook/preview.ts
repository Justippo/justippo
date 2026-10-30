import type { Preview } from "@storybook/react";
import { createElement } from "react";

import { TolgeeClientProvider } from "../src/components/TolgeeClientProvider";
import "../src/styles/tokens.css";

const preview: Preview = {
  decorators: [
    (Story) => createElement(TolgeeClientProvider, null, createElement(Story)),
  ],
  parameters: {
    a11y: {
      // WCAG 2.1 AA — violations fail CI when run via test-runner
      test: "error",
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
