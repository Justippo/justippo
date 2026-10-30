import { DEMO_EMAIL, DEMO_PASSWORD } from "@evidenceeu/shared";
import { useAuthStore } from "../stores/useAuthStore";

/**
 * Bridge hook — matches web's useAuthState signature exactly.
 * Web: React Context with localStorage → Mobile: Zustand with AsyncStorage.
 * Demo credentials imported from @evidenceeu/shared (DRY).
 */
export function useAuthState() {
  const { isAuthenticated, isLoading, login, logout } = useAuthStore();
  return {
    isAuthenticated,
    isLoading,
    isMatrixAuthEnabled: false,
    login: () => login(DEMO_EMAIL, DEMO_PASSWORD),
    loginWithCredentials: (email: string, password: string) =>
      login(email, password),
    logout,
  };
}
