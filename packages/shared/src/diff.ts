// SPDX-License-Identifier: MIT
/**
 * Block-level diff engine using Myers algorithm.
 *
 * Pure TypeScript — no external dependencies.
 * Splits text into paragraphs (double-newline delimited) and computes
 * the minimal edit script (LCS-based) between the two arrays.
 *
 * Output format matches DiffBlock from DocumentComparison component (DRY).
 */

export interface DiffBlock {
  type: "unchanged" | "added" | "removed" | "modified";
  sourceText: string;
  targetText?: string;
}

/**
 * Split text into blocks at paragraph boundaries (double newline).
 * Falls back to single newline if no double newlines exist.
 */
export function splitIntoBlocks(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const blocks = trimmed.split(/\n\s*\n/);
  if (blocks.length === 1 && trimmed.includes("\n")) {
    return trimmed.split("\n").filter((b) => b.trim().length > 0);
  }
  return blocks.map((b) => b.trim()).filter((b) => b.length > 0);
}

/**
 * Compute Longest Common Subsequence (LCS) table for two string arrays.
 * Returns a 2D table where table[i][j] = length of LCS of a[0..i-1] and b[0..j-1].
 */
function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  const table: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        table[i][j] = table[i - 1][j - 1] + 1;
      } else {
        table[i][j] = Math.max(table[i - 1][j], table[i][j - 1]);
      }
    }
  }
  return table;
}

/**
 * Backtrack through LCS table to produce a diff.
 * Consecutive remove+add pairs are merged into "modified" blocks.
 */
function backtrack(table: number[][], a: string[], b: string[]): DiffBlock[] {
  const raw: DiffBlock[] = [];
  let i = a.length;
  let j = b.length;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      raw.push({ type: "unchanged", sourceText: a[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || table[i][j - 1] >= table[i - 1][j])) {
      raw.push({ type: "added", sourceText: b[j - 1] });
      j--;
    } else {
      raw.push({ type: "removed", sourceText: a[i - 1] });
      i--;
    }
  }

  raw.reverse();

  const merged: DiffBlock[] = [];
  let k = 0;
  while (k < raw.length) {
    if (raw[k].type === "removed") {
      const removedTexts: string[] = [raw[k].sourceText];
      let next = k + 1;
      while (next < raw.length && raw[next].type === "removed") {
        removedTexts.push(raw[next].sourceText);
        next++;
      }
      if (next < raw.length && raw[next].type === "added") {
        const addedTexts: string[] = [raw[next].sourceText];
        let next2 = next + 1;
        while (next2 < raw.length && raw[next2].type === "added") {
          addedTexts.push(raw[next2].sourceText);
          next2++;
        }
        merged.push({
          type: "modified",
          sourceText: removedTexts.join("\n\n"),
          targetText: addedTexts.join("\n\n"),
        });
        k = next2;
      } else {
        for (const t of removedTexts) {
          merged.push({ type: "removed", sourceText: t });
        }
        k = next;
      }
    } else if (raw[k].type === "added") {
      merged.push({ type: "added", sourceText: raw[k].sourceText, targetText: raw[k].sourceText });
      k++;
    } else {
      merged.push(raw[k]);
      k++;
    }
  }

  return merged;
}

/**
 * Compute block-level diff between two texts.
 *
 * @param sourceText - Original document text
 * @param targetText - Modified/translated document text
 * @returns Array of DiffBlock describing the changes
 */
export function computeDiff(sourceText: string, targetText: string): DiffBlock[] {
  const sourceBlocks = splitIntoBlocks(sourceText);
  const targetBlocks = splitIntoBlocks(targetText);

  if (sourceBlocks.length === 0 && targetBlocks.length === 0) {
    return [];
  }
  if (sourceBlocks.length === 0) {
    return targetBlocks.map((t) => ({ type: "added" as const, sourceText: t, targetText: t }));
  }
  if (targetBlocks.length === 0) {
    return sourceBlocks.map((t) => ({ type: "removed" as const, sourceText: t }));
  }

  const table = lcsTable(sourceBlocks, targetBlocks);
  return backtrack(table, sourceBlocks, targetBlocks);
}