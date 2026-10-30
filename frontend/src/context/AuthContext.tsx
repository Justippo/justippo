"use client";

/**
 * MOBILE_GAP: Matrix OAuth PKCE uses window.location for redirect.
 * Mobile requires expo-auth-session. See ADR-019 and
 * docs/mobile/mobile-compat.md for the adaptation plan.
 */

import { createContext, useContext } from "react";
import { useAuthState } from "@/hooks/useAuthState";

interface AuthContextValue {
  readonly isAuthenticated: boolean;
  readonly isLoading: boolean;
  readonly isMatrixAuthEnabled: boolean;
  readonly login: () => void;
  readonly loginWithCredentials: (email: string, password: string, returnPath?: string) => boolean;
  readonly logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  isLoading: true,
  isMatrixAuthEnabled: false,
  login: () => {},
  loginWithCredentials: () => false,
  logout: () => Promise.resolve(),
});

interface AuthProviderProps {
  readonly children: React.ReactNode;
}

export function AuthProvider({ children }: Readonly<AuthProviderProps>) {
  const auth = useAuthState();

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
