# EvidenceEU Mobile Compatibility Guide

This document is the single source of truth for the mobile migration.

## Platform Compatibility Table

| Hook / Lib File | Platform Rating | Notes |
|---|---|---|
| `useSearch.ts` | `@platform web mobile:adapter` | SSE streaming needs fetch-event-source |
| `useChatSSE.ts` | `@platform web mobile:adapter` | SSE streaming needs fetch-event-source |
| `useTranslate.ts` | `@platform web mobile:adapter` | DOM File API -> expo-document-picker |
| `useUpload.ts` | `@platform web mobile:adapter` | DOM File API -> expo-document-picker |
| `useSearchView.ts` | `@platform web mobile` | Pure React state |
| `useChatView.ts` | `@platform web mobile` | Pure React state |
| `useTranslationView.ts` | `@platform web mobile` | Pure React state |
| `useUploadView.ts` | `@platform web mobile` | Pure React state |
| `useSettingsView.ts` | `@platform web mobile` | Pure React state |
| `useDashboard.ts` | `@platform web mobile` | Pure React state |
| `useAuthState.ts` | `@platform web mobile:adapter` | Storage adapter needed |
| `useHealthCheck.ts` | `@platform web mobile` | Pure fetch utility |
| `useFileValidation.ts` | `@platform web mobile:adapter` | DOM File type -> RN file |
| `useT.ts` | `@platform web mobile:adapter` | Tolgee web -> Tolgee RN |
| `useTolgeeClient.ts` | `@platform web mobile:adapter` | Tolgee web -> Tolgee RN |
| `useAnalytics.ts` | `@platform web mobile:adapter` | PostHog web -> PostHog RN |
| `useDatadogInit.ts` | `@platform web` | Browser-only analytics |
| `useIsClient.ts` | `@platform web` | SSR safety, not needed in RN |
| `usePrefersReducedMotion.ts` | `@platform web mobile:adapter` | Window.matchMedia -> RN API |
| `useScrollReveal.ts` | `@platform web` | IntersectionObserver |
| `useDragAndDrop.ts` | `@platform web mobile:adapter` | HTML drag/drop -> RN gesture |
| `useJourneyState.ts` | `@platform web mobile` | Pure state machine |
| `usePrimaryNavigation.ts` | `@platform web mobile:adapter` | Next.js router -> Expo Router |
| `useSidebarState.ts` | `@platform web` | Desktop-only UI state |
| `diff.ts` | `@platform web mobile` | Pure TypeScript algorithm |
| `language-codes.ts` | `@platform web mobile` | Pure utility functions |
| `anonymous-routes.ts` | `@platform web mobile` | Pure route logic |
| `AuthContext.tsx` | `@platform web mobile:adapter` | PKCE -> expo-auth-session |
| `GDPRConsentContext.tsx` | `@platform web mobile:adapter` | localStorage -> AsyncStorage |
| `OfflineModeContext.tsx` | `@platform web mobile:adapter` | Service Worker -> RN offline |
| `types/index.ts` | `@platform web mobile` | Pure TypeScript types |

## Known Gaps

### 1. SSE Streaming (estimate: M)

**Problem:** `EventSource` is not available in React Native.

**Web:** Uses native `EventSource` API for SSE streaming in `useSearchSSE.ts` and `useChatSSE.ts`.

**Mobile solution:** Use `@microsoft/fetch-event-source` which is a fetch-based polyfill.

**Implementation:**
```typescript
// Mobile adapter for SSE
import { fetchEventSource } from "@microsoft/fetch-event-source/fetch";

export async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  await fetchEventSource(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    onmessage(ev) {
      onEvent(ev.event, JSON.parse(ev.data));
    },
  });
}
```

**Files to update:** `useSearchSSE.ts`, `useChatSSE.ts`

### 2. File Upload (estimate: M)

**Problem:** DOM `<input type="file">` and `File` API not available in RN.

**Web:** Uses HTML file input and DOM File objects.

**Mobile solution:** Use `expo-document-picker` to select files, `expo-file-system` to read them.

**Implementation:**
```typescript
import * as DocumentPicker from "expo-document-picker";
import * as FileSystem from "expo-file-system";

export async function pickAndReadFile(): Promise<{ name: string; content: string; type: string }> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ["application/pdf", "image/*"],
    copyToCacheDirectory: true,
  });

  if (!result.canceled && result.assets[0]) {
    const asset = result.assets[0];
    const content = await FileSystem.readAsStringAsync(asset.uri);
    return {
      name: asset.name,
      content,
      type: asset.mimeType ?? "application/octet-stream",
    };
  }

  throw new Error("No file selected");
}
```

**Files to update:** `useUpload.ts`, `useFileValidation.ts`

### 3. Matrix OAuth PKCE (estimate: L)

**Problem:** `window.location` redirect not available in RN.

**Web:** Full PKCE flow using browser redirects.

**Mobile solution:** Use `expo-auth-session` which handles native OAuth flows.

**Implementation:**
```typescript
import * as AuthSession from "expo-auth-session";

const redirectUri = AuthSession.makeRedirectUri({
  path: "auth/callback",
  scheme: "evidenceeu",
});

const result = await AuthSession.startAsync({
  authUrl: `${MATRIX_HOMESERVER}/_matrix/client/v3/login/sso/redirect/oidc-oidc?redirectUri=${encodeURIComponent(redirectUri)}`,
  returnUrl: redirectUri,
});
```

**Files to update:** `AuthContext.tsx`, `useAuthState.ts`

### 4. Tolgee I18n (estimate: S)

**Problem:** `@tolgee/react` is web-only.

**Web:** Uses `@tolgee/react` + `@tolgee/web`.

**Mobile solution:** Use `@tolgee/react-native` with shared key constants from `@evidenceeu/shared`.

**Implementation:**
```typescript
// Mobile-specific Tolgee setup
import { Tolgee, DevTools, ReactNativeFormatter } from "@tolgee/react-native";

const tolgee = Tolgee()
  .use(DevTools())
  .use(ReactNativeFormatter())
  .init({
    apiUrl: process.env.EXPO_PUBLIC_TOLGEE_API_URL,
    apiKey: process.env.EXPO_PUBLIC_TOLGEE_API_KEY,
    language: "en",
  });
```

**Files to update:** New `mobile/src/lib/i18n.ts`

### 5. PostHog Analytics (estimate: S)

**Problem:** `posthog-js` is browser-only.

**Web:** Uses `posthog-js` with browser APIs.

**Mobile solution:** Use `posthog-react-native` with same event names/properties.

**Implementation:**
```typescript
import PostHog from "posthog-react-native";

export const posthog = new PostHog("YOUR_API_KEY", {
  host: "https://us.i.posthog.com",
});
```

**Files to update:** `useAnalytics.ts` -> adapter pattern

### 6. GDPR Consent Storage (estimate: S)

**Problem:** `localStorage` not available in RN.

**Web:** Uses `localStorage` and cookies for consent persistence.

**Mobile solution:** Use `expo-secure-store` for encrypted consent storage.

**Implementation:**
```typescript
import * as SecureStore from "expo-secure-store";

export async function setConsent(key: string, value: boolean): Promise<void> {
  await SecureStore.setItemAsync(`consent_${key}`, JSON.stringify(value));
}

export async function getConsent(key: string): Promise<boolean | null> {
  const value = await SecureStore.getItemAsync(`consent_${key}`);
  return value !== null ? JSON.parse(value) : null;
}
```

**Files to update:** `GDPRConsentContext.tsx` -> adapter pattern

### 7. Design Tokens / CSS (estimate: L)

**Problem:** CSS custom properties and Tailwind not available in RN.

**Web:** Uses `tokens.css` with CSS custom properties + Tailwind.

**Mobile solution:** Two options:
  - **NativeWind** (Tailwind for RN) - closest to web patterns
  - **React Native StyleSheet** - native approach, tokens as JS constants

**Recommendation:** Start with StyleSheet + JS token constants. Migrate to NativeWind later if team prefers.

**Implementation:**
```typescript
// packages/shared/src/tokens.ts
export const colors = {
  primary: "#005796",
  onPrimary: "#ffffff",
  primaryContainer: "#1b5e9e",
  error: "#da2130",
  warning: "#8b4a0b",
  success: "#467a39",
  surface: "#faf9f8",
  onSurface: "#1a1c1c",
} as const;

export const spacing = {
  xs: 8,
  sm: 12,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;
```

**Files to create:** `packages/shared/src/tokens.ts`

## Packages Already Shared

`@evidenceeu/shared` currently exports:

- `types.ts` — All core TypeScript interfaces
- `diff.ts` — Block-level diff engine (Myers algorithm)
- `language-codes.ts` — EN/DE/FR language utilities
- `anonymous-routes.ts` — Route access control
- `i18n-keys.ts` — Centralised translation key constants

## EAS Build Setup Steps

1. Install EAS CLI: `npm install -g eas-cli`
2. Login: `eas login`
3. Init project: `eas init` in `apps/mobile/`
4. Configure builds: edit `eas.json`
5. Build development: `eas build --profile development`
6. Build preview: `eas build --profile preview`
7. Build production: `eas build --profile production`

## Estimated Effort Per Gap

| Gap | Effort | Priority | Sprint |
|---|---|---|---|
| SSE Streaming (fetch-event-source) | M (3-5 days) | High | 1 |
| File Upload (expo-document-picker) | M (3-5 days) | High | 1 |
| Matrix OAuth PKCE | L (5-8 days) | High | 2 |
| Tolgee I18n (RN adapter) | S (1-2 days) | Medium | 2 |
| PostHog Analytics (RN SDK) | S (1-2 days) | Medium | 2 |
| GDPR Consent (AsyncStorage) | S (1-2 days) | Medium | 2 |
| Design Tokens (StyleSheet) | L (5-8 days) | Low | 3 |
| Navigation (Expo Router) | M (3-5 days) | High | 1 |
| Offline Mode (RN adapter) | L (5-8 days) | Low | 4 |

