import { test as base } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] as const;

type A11yScanOptions = {
  exclude?: string[];
  include?: string[];
  disabledRules?: string[];
};

function buildAxe(page: import("@playwright/test").Page, options: A11yScanOptions = {}) {
  const builder = new AxeBuilder({ page }).withTags([...WCAG_TAGS]);
  if (options.exclude) builder.exclude(options.exclude);
  if (options.include) builder.include(options.include);
  if (options.disabledRules) {
    options.disabledRules.forEach((rule) => builder.disableRules(rule));
  }
  return builder;
}

type AxeScanResults = Awaited<ReturnType<ReturnType<typeof buildAxe>["analyze"]>>;

type AccessibilityFixture = {
  scan: (options?: A11yScanOptions) => Promise<AxeScanResults>;
  assertNoViolations: (options?: A11yScanOptions) => Promise<void>;
};

export const test = base.extend<AccessibilityFixture>({
  scan: async ({ page }, use) => {
    await use(async (options = {}) => buildAxe(page, options).analyze());
  },
  assertNoViolations: async ({ page }, use) => {
    await use(async (options = {}) => {
      const results = await buildAxe(page, options).analyze();
      if (results.violations.length > 0) {
        const details = results.violations
          .map((v) => {
            const nodes = v.nodes
              .map(
                (n) =>
                  `    - target: ${JSON.stringify(n.target)}\n      html: ${n.html}\n      summary: ${n.failureSummary?.replace(/\n/g, "\n        ")}`
              )
              .join("\n");
            return `${v.id} (${v.impact ?? "unknown"}): ${v.description}\n  Help: ${v.helpUrl}\n  Nodes: ${v.nodes.length}\n${nodes}`;
          })
          .join("\n");
        throw new Error(`WCAG 2.1 AA accessibility violations found:\n${details}`);
      }
    });
  },
});

export { expect } from "@playwright/test";
