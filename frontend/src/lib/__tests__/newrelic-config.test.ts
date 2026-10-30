import { describe, expect, it } from "vitest";
import {
  NEW_RELIC_AGENT_URL,
  NEW_RELIC_AGENT_VERSION,
  getNewRelicScript,
  shouldEnableNewRelic,
} from "@/lib/newrelic-config";

const completeConfig = {
  accountId: "account-id",
  applicationId: "application-id",
  licenseKey: "browser-license-key",
};

describe("New Relic browser configuration", () => {
  it("requires an explicit opt-in flag", () => {
    expect(shouldEnableNewRelic({ enabled: false, ...completeConfig })).toBe(false);
    expect(shouldEnableNewRelic({ enabled: true, ...completeConfig })).toBe(true);
  });

  it("remains disabled when required browser configuration is incomplete", () => {
    expect(
      shouldEnableNewRelic({
        enabled: true,
        ...completeConfig,
        licenseKey: "",
      })
    ).toBe(false);
  });

  it("uses a pinned supported agent instead of the floating current loader", () => {
    expect(NEW_RELIC_AGENT_VERSION).toBe("1.317.0");
    expect(NEW_RELIC_AGENT_URL).toBe("https://js-agent.newrelic.com/nr-loader-spa-1.317.0.min.js");
    expect(NEW_RELIC_AGENT_URL).not.toContain("current");
  });

  it("emits no inline configuration without the opt-in flag", () => {
    expect(getNewRelicScript()).toBe("");
  });
});
