// SPDX-License-Identifier: MIT
/**
 * Tolgee instance — DRY singleton.
 *
 * staticData is bundled at build time (imported JSON objects), so translations
 * are available synchronously on first render — eliminating the "Loading…"
 * flash from the TolgeeProvider fallback. For a small, fixed MVP locale set
 * (en/de/fr) bundling all three is negligible (~13 KB raw) and is the
 * Tolgee-recommended approach for making translations available for initial render.
 *
 * The DRY principle: this file is the ONLY place where Tolgee is configured.
 * Every component imports useT() from @/hooks/useT — never @tolgee/react directly.
 */
import en from "../locales/en.json";
import de from "../locales/de.json";
import fr from "../locales/fr.json";
import { Tolgee, DevTools, FormatSimple, type TolgeeStaticDataProp } from "@tolgee/web";
import { DEFAULT_APP_LANGUAGE, type AppLanguage } from "@/lib/interface-language";

/**
 * Build-time translation bundle. Shared by both the Tolgee instance init and
 * the TolgeeProvider `ssr` prop (initial server render — eliminates the
 * "Loading…" flash). DRY: defined once.
 *
 * JSON.parse/stringify ensures these are plain objects with Object.prototype,
 * preventing "Cannot convert object to primitive value" from Next.js's
 * dev-mode console.assert when it tries to String() ES module namespace objects.
 */
export const staticData: TolgeeStaticDataProp = {
  en: JSON.parse(JSON.stringify(en)),
  de: JSON.parse(JSON.stringify(de)),
  fr: JSON.parse(JSON.stringify(fr)),
};

const baseTolgeeConfig = {
  defaultLanguage: "en",
  availableLanguages: ["en", "de", "fr"],
  fallbackLanguage: "en",
};

interface TolgeeEnvironment {
  readonly nodeEnv: string;
  readonly apiKey?: string;
  readonly apiUrl?: string;
  readonly liveEnabled?: boolean;
}

/**
 * Live Tolgee access is a development-only editing aid. Production uses the
 * committed locale bundle so first render is deterministic and no platform
 * API key or translation request is exposed to the browser.
 *
 * Live mode is opt-in via NEXT_PUBLIC_TOLGEE_LIVE=true — merely having an API
 * key present in .env.local does NOT switch dev into remote mode. This prevents
 * a stray key from forcing every dev render through the network (which shows
 * raw keys while the fetch is in flight or if it fails). Contributors who want
 * in-context editing set the flag explicitly.
 */
export function buildTolgeeConfig({
  nodeEnv,
  apiKey,
  apiUrl = "https://app.tolgee.io",
  liveEnabled = false,
}: TolgeeEnvironment) {
  if (nodeEnv === "production" || !apiKey || !liveEnabled) {
    return baseTolgeeConfig;
  }

  return { ...baseTolgeeConfig, apiKey, apiUrl };
}

const tolgeeEnvironment: TolgeeEnvironment =
  process.env.NODE_ENV === "production"
    ? { nodeEnv: "production" }
    : {
        nodeEnv: process.env.NODE_ENV,
        apiKey: process.env.NEXT_PUBLIC_TOLGEE_API_KEY,
        apiUrl: process.env.NEXT_PUBLIC_TOLGEE_API_URL,
        liveEnabled: process.env.NEXT_PUBLIC_TOLGEE_LIVE === "true",
      };

export const tolgeeConfig = buildTolgeeConfig(tolgeeEnvironment);

export function createTolgeeInstance(language: AppLanguage = DEFAULT_APP_LANGUAGE) {
  const tolgee = Tolgee().use(FormatSimple());

  // DevTools enables in-context translation editing — only load it when a
  // Tolgee API key is configured. Without a key it is a no-op and the
  // console.assert crash (FastTextEncoding + null-prototype) is already
  // handled by the patch in instrumentation-client.ts.
  if (tolgeeEnvironment.nodeEnv !== "production" && tolgeeEnvironment.apiKey) {
    tolgee.use(DevTools());
  }

  return tolgee.init({
    ...tolgeeConfig,
    language,
    staticData,
  });
}
