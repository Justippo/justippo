// SPDX-License-Identifier: MIT
// DRY: Single source of truth lives in @evidenceeu/shared.
// Re-export here so existing @/lib/diff imports keep working.
export { type DiffBlock, splitIntoBlocks, computeDiff } from "@evidenceeu/shared";
