import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface GDPRState {
  hasConsent: boolean;
  grantConsent: () => void;
  revokeConsent: () => void;
}

export const useGDPRStore = create<GDPRState>()(
  persist(
    (set) => ({
      hasConsent: false,

      grantConsent: () => set({ hasConsent: true }),
      revokeConsent: () => set({ hasConsent: false }),
    }),
    {
      name: "gdpr-consent",
      storage: createJSONStorage(() => AsyncStorage),
    },
  ),
);
