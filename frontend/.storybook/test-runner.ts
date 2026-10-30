// .storybook/test-runner.ts
import { getStorybookTestRunner } from "@storybook/test-runner";

const testRunnerConfig = {
  async preVisit(page) {
    // Add any setup code here
    await page.addInitScript(() => {
      window.StorybookTestRunnerError = class StorybookTestRunnerError extends Error {
        constructor(message) {
          super(message);
          this.name = 'StorybookTestRunnerError';
        }
      };
    });
  },
};

export default testRunnerConfig;
