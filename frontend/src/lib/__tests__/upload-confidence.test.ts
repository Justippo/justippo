import { describe, it, expect } from "vitest";
import {
  averageConfidence,
  formatConfidencePercent,
  getConfidenceBadgeVariant,
} from "../upload-confidence";

describe("getConfidenceBadgeVariant", () => {
  it("returns success at or above 0.8", () => {
    expect(getConfidenceBadgeVariant(0.8)).toBe("success");
    expect(getConfidenceBadgeVariant(0.95)).toBe("success");
  });

  it("returns warning between 0.5 and 0.8", () => {
    expect(getConfidenceBadgeVariant(0.5)).toBe("warning");
    expect(getConfidenceBadgeVariant(0.79)).toBe("warning");
  });

  it("returns error below 0.5", () => {
    expect(getConfidenceBadgeVariant(0.49)).toBe("error");
    expect(getConfidenceBadgeVariant(0.2)).toBe("error");
  });
});

describe("formatConfidencePercent", () => {
  it("rounds to whole percent", () => {
    expect(formatConfidencePercent(0.923)).toBe("92%");
  });
});

describe("averageConfidence", () => {
  it("ignores null confidence values", () => {
    expect(
      averageConfidence([{ confidence: 0.9 }, { confidence: null }, { confidence: 0.8 }])
    ).toBeCloseTo(0.85);
  });
});
