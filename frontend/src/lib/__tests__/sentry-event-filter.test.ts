import type { ErrorEvent } from "@sentry/nextjs";
import { describe, expect, it } from "vitest";
import { filterBrowserSentryEvent } from "@/lib/sentry-event-filter";

describe("Sentry browser event filtering", () => {
  it("drops errors whose stack is entirely inside the New Relic loader", () => {
    const event: ErrorEvent = {
      type: undefined,
      exception: {
        values: [
          {
            type: "TypeError",
            value: "l.uJ is not a function",
            stacktrace: {
              frames: [
                { filename: "https://js-agent.newrelic.com/nr-spa-1.318.0.min.js" },
                { filename: "https://js-agent.newrelic.com/nr-loader-spa-current.min.js" },
              ],
            },
          },
        ],
      },
    };

    expect(filterBrowserSentryEvent(event)).toBeNull();
  });

  it("keeps an event when any application frame is present", () => {
    const event: ErrorEvent = {
      type: undefined,
      exception: {
        values: [
          {
            type: "TypeError",
            value: "l.uJ is not a function",
            stacktrace: {
              frames: [
                { filename: "https://js-agent.newrelic.com/nr-spa-1.318.0.min.js" },
                { filename: "https://evidence-eu-frontend.pages.dev/_next/static/app.js" },
              ],
            },
          },
        ],
      },
    };

    expect(filterBrowserSentryEvent(event)).toBe(event);
  });

  it("keeps chained exceptions when any exception lacks a New Relic-only stack", () => {
    const event: ErrorEvent = {
      type: undefined,
      exception: {
        values: [
          {
            type: "TypeError",
            stacktrace: {
              frames: [{ filename: "https://js-agent.newrelic.com/nr-spa-1.318.0.min.js" }],
            },
          },
          { type: "Error", value: "Application callback failed" },
        ],
      },
    };

    expect(filterBrowserSentryEvent(event)).toBe(event);
  });

  it("drops the verified Tolgee fetch Event rejection", () => {
    const event: ErrorEvent = {
      type: undefined,
      exception: {
        values: [{ type: "Event", value: "Event captured as promise rejection" }],
      },
      breadcrumbs: [
        {
          category: "console",
          message: 'Tolgee: Failed to fetch record for "en"',
        },
      ],
    };

    expect(filterBrowserSentryEvent(event)).toBeNull();
  });

  it("keeps unrelated Event promise rejections", () => {
    const event: ErrorEvent = {
      type: undefined,
      exception: {
        values: [{ type: "Event", value: "Event captured as promise rejection" }],
      },
      breadcrumbs: [{ category: "console", message: "Upload request failed" }],
    };

    expect(filterBrowserSentryEvent(event)).toBe(event);
  });

  it("keeps hydration and ordinary application errors", () => {
    const hydrationEvent: ErrorEvent = {
      type: undefined,
      exception: {
        values: [{ type: "Error", value: "Hydration failed because the HTML did not match" }],
      },
    };

    expect(filterBrowserSentryEvent(hydrationEvent)).toBe(hydrationEvent);
  });
});
