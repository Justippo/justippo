// SPDX-License-Identifier: MIT
// DRY: Single source of truth lives in @evidenceeu/shared.
// Re-export here so existing @/lib/anonymous-routes imports keep working.
export {
  PUBLIC_ONLY_ROUTES,
  AUTH_AWARE_PUBLIC_ROUTES,
  ANONYMOUS_ROUTES,
  isPublicOnlyRoute,
  isAuthAwarePublicRoute,
  shouldUseAnonymousLayout,
  isAnonymousRoute,
} from "@evidenceeu/shared";
