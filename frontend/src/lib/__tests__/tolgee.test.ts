import { describe, expect, it } from "vitest";
import { buildTolgeeConfig } from "@/lib/tolgee";

describe("buildTolgeeConfig", () => {
  it("omits live platform credentials in production", () => {
    const config = buildTolgeeConfig({
      nodeEnv: "production",
      apiKey: "development-key",
      apiUrl: "https://app.tolgee.io",
    });

    expect(config).toEqual({
      defaultLanguage: "en",
      availableLanguages: ["en", "de", "fr"],
      fallbackLanguage: "en",
    });
    expect(config).not.toHaveProperty("apiKey");
    expect(config).not.toHaveProperty("apiUrl");
  });

  it("keeps live editing available in development when explicitly enabled", () => {
    expect(
      buildTolgeeConfig({
        nodeEnv: "development",
        apiKey: "development-key",
        apiUrl: "https://app.tolgee.io",
        liveEnabled: true,
      })
    ).toMatchObject({
      apiKey: "development-key",
      apiUrl: "https://app.tolgee.io",
    });
  });

  it("ignores a stray development key when live mode is not enabled", () => {
    const config = buildTolgeeConfig({
      nodeEnv: "development",
      apiKey: "development-key",
      apiUrl: "https://app.tolgee.io",
      liveEnabled: false,
    });

    expect(config).not.toHaveProperty("apiKey");
    expect(config).not.toHaveProperty("apiUrl");
  });

  it("does not enable live access without a development key", () => {
    const config = buildTolgeeConfig({ nodeEnv: "development" });

    expect(config).not.toHaveProperty("apiKey");
    expect(config).not.toHaveProperty("apiUrl");
  });
});
