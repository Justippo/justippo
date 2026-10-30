import { useGDPRStore } from "../stores/useGDPRStore";

/**
 * Bridge hook — matches web's useGDPRConsent signature exactly.
 * Web: React Context with localStorage → Mobile: Zustand with AsyncStorage.
 * Property names aligned: hasConsent, grantConsent, revokeConsent.
 */
export function useGDPRConsent() {
  const { hasConsent, grantConsent, revokeConsent } = useGDPRStore();
  return { hasConsent, grantConsent, revokeConsent };
}
