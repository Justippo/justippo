import { describe, expect, it } from "vitest";
import {
  buildCitationGatewayHref,
  trustedCitationUrl,
  trustedGuidanceUrl,
} from "./useCitationAccess";

describe("citation URL helpers", () => {
  it("accepts official EUR-Lex HTTPS URLs", () => {
    const source = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038";
    expect(trustedCitationUrl(source)).toBe(source);
  });

  it("rejects non-EU and credential-bearing URLs", () => {
    expect(trustedCitationUrl("https://example.com/document")).toBeNull();
    expect(trustedCitationUrl("https://user@eur-lex.europa.eu/document")).toBeNull();
    expect(trustedCitationUrl("http://eur-lex.europa.eu/document")).toBeNull();
  });

  it("builds a same-origin citation gateway path", () => {
    const href = buildCitationGatewayHref(
      "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32004L0038",
      "Directive 2004/38/EC"
    );
    expect(href).toMatch(/^\/citation\?/);
    expect(new URLSearchParams(href.split("?")[1]).get("title")).toBe("Directive 2004/38/EC");
  });
});

describe("trustedGuidanceUrl", () => {
  it("allows the curated Spanish Tax Agency host", () => {
    const source = "https://sede.agenciatributaria.gob.es/Sede/en_gb/no-residentes.html";
    expect(trustedGuidanceUrl(source)).toBe(source);
  });

  it("rejects uncurated and credential-bearing URLs", () => {
    expect(trustedGuidanceUrl("https://example.com/tax")).toBeNull();
    expect(trustedGuidanceUrl("https://user@sede.agenciatributaria.gob.es/tax")).toBeNull();
  });
});
