// SPDX-License-Identifier: MIT

// SPDX-License-Identifier: MIT
import { describe, it, expect } from "vitest";
import { computeDiff, splitIntoBlocks, type DiffBlock } from "../diff";

describe("splitIntoBlocks", () => {
  it("splits on double newlines", () => {
    const text = "First paragraph.\n\nSecond paragraph.\n\nThird.";
    expect(splitIntoBlocks(text)).toEqual(["First paragraph.", "Second paragraph.", "Third."]);
  });

  it("splits on single newlines when no double newlines", () => {
    const text = "Line one\nLine two\nLine three";
    expect(splitIntoBlocks(text)).toEqual(["Line one", "Line two", "Line three"]);
  });

  it("returns empty array for empty string", () => {
    expect(splitIntoBlocks("")).toEqual([]);
  });

  it("trims whitespace from blocks", () => {
    const text = "  Spaced  \n\n  Also spaced  ";
    expect(splitIntoBlocks(text)).toEqual(["Spaced", "Also spaced"]);
  });

  it("filters empty blocks", () => {
    const text = "Real content\n\n\n\nMore content";
    expect(splitIntoBlocks(text)).toEqual(["Real content", "More content"]);
  });

  it("handles whitespace only string", () => {
    expect(splitIntoBlocks("   \n\t  ")).toEqual([]);
  });

  it("handles mixed double and single newlines", () => {
    const text = "First line\nStill first block\n\nSecond block";
    expect(splitIntoBlocks(text)).toEqual(["First line\nStill first block", "Second block"]);
  });

  it("handles windows style newlines", () => {
    const text = "First\r\n\r\nSecond\r\n\r\nThird";
    expect(splitIntoBlocks(text)).toEqual(["First", "Second", "Third"]);
  });

  it("handles single line text with no newlines", () => {
    expect(splitIntoBlocks("Single line text")).toEqual(["Single line text"]);
  });

  it("handles multiple spaces between newlines", () => {
    const text = "Block 1\n   \nBlock 2";
    expect(splitIntoBlocks(text)).toEqual(["Block 1", "Block 2"]);
  });
});

describe("computeDiff", () => {
  it("returns empty array for two empty strings", () => {
    expect(computeDiff("", "")).toEqual([]);
  });

  it("returns all added when source is empty", () => {
    const result = computeDiff("", "New content");
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("added");
    expect(result[0].sourceText).toBe("New content");
  });

  it("returns all removed when target is empty", () => {
    const result = computeDiff("Old content", "");
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe("removed");
    expect(result[0].sourceText).toBe("Old content");
  });

  it("returns all unchanged for identical texts", () => {
    const text = "Paragraph one.\n\nParagraph two.";
    const result = computeDiff(text, text);
    expect(result).toHaveLength(2);
    expect(result.every((b) => b.type === "unchanged")).toBe(true);
  });

  it("detects modified blocks", () => {
    const source = "The contract is valid.\n\nSection 2: Terms.";
    const target = "The contract is void.\n\nSection 2: Terms.";
    const result = computeDiff(source, target);
    const modified = result.filter((b) => b.type === "modified");
    expect(modified.length).toBeGreaterThanOrEqual(1);
    expect(modified[0].sourceText).toContain("valid");
    expect(modified[0].targetText).toContain("void");
  });

  it("detects added blocks", () => {
    const source = "Paragraph one.";
    const target = "Paragraph one.\n\nNew paragraph.";
    const result = computeDiff(source, target);
    const added = result.filter((b) => b.type === "added");
    expect(added).toHaveLength(1);
    expect(added[0].sourceText).toBe("New paragraph.");
  });

  it("detects removed blocks", () => {
    const source = "Paragraph one.\n\nRemoved paragraph.";
    const target = "Paragraph one.";
    const result = computeDiff(source, target);
    const removed = result.filter((b) => b.type === "removed");
    expect(removed).toHaveLength(1);
    expect(removed[0].sourceText).toBe("Removed paragraph.");
  });

  it("handles multi-paragraph diff with mixed changes", () => {
    const source = "Intro text.\n\nSame paragraph.\n\nOld text here.";
    const target = "Intro text modified.\n\nSame paragraph.\n\nNew text here.\n\nExtra paragraph.";
    const result = computeDiff(source, target);

    // Should have unchanged and modified blocks (consecutive remove+add merged into modified)
    const types = result.map((b) => b.type);
    expect(types).toContain("unchanged");
    expect(types).toContain("modified");

    // The last modified block should contain both "New text here" and "Extra paragraph"
    const lastModified = result.filter((b) => b.type === "modified").pop();
    expect(lastModified?.targetText).toContain("New text here");
    expect(lastModified?.targetText).toContain("Extra paragraph");
  });

  it("preserves order of blocks", () => {
    const source = "A\n\nB\n\nC";
    const target = "A\n\nB_modified\n\nC";
    const result = computeDiff(source, target);

    // First block should be unchanged "A"
    expect(result[0].type).toBe("unchanged");
    expect(result[0].sourceText).toBe("A");

    // Last block should be unchanged "C"
    const last = result[result.length - 1];
    expect(last.type).toBe("unchanged");
    expect(last.sourceText).toBe("C");
  });

  it("handles German text with umlauts", () => {
    const source = "Der Vertrag ist gültig.";
    const target = "Der Vertrag ist ungültig.";
    const result = computeDiff(source, target);
    expect(result.some((b) => b.type === "modified")).toBe(true);
  });

  it("handles French text with accents", () => {
    const source = "Le contrat est valide.";
    const target = "Le contrat est annulé.";
    const result = computeDiff(source, target);
    expect(result.some((b) => b.type === "modified")).toBe(true);
  });
});
