// SPDX-License-Identifier: MIT
// DRY: Single source of truth lives in @evidenceeu/shared.
// Re-export here so existing @/lib/language-codes imports keep working.
export {
  formatLanguageCode,
  getLanguageLabel,
  formatLanguagePair,
  TARGET_LANGUAGE_OPTIONS,
  getDefaultTargetLanguage,
} from "@evidenceeu/shared";
