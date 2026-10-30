import { useState, useEffect, useCallback } from "react";
import * as AuthSession from "expo-auth-session";
import * as SecureStore from "expo-secure-store";

const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

const discovery = {
  authorizationEndpoint: `${API_BASE}/oauth/authorize`,
  tokenEndpoint: `${API_BASE}/oauth/token`,
};

interface AuthState {
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export function useMobileAuth() {
  const [state, setState] = useState<AuthState>({
    accessToken: null,
    isLoading: true,
    isAuthenticated: false,
  });

  useEffect(() => {
    SecureStore.getItemAsync("accessToken").then((token) => {
      setState({
        accessToken: token,
        isLoading: false,
        isAuthenticated: !!token,
      });
    });
  }, []);

  const signIn = useCallback(async () => {
    try {
      const redirectUri = AuthSession.makeRedirectUri({ scheme: "evidenceeu" });
      const request = new AuthSession.AuthRequest({
        clientId: "evidenceeu-mobile",
        redirectUri,
        responseType: AuthSession.ResponseType.Code,
        scopes: ["openid", "profile", "email"],
      });

      const result = await request.promptAsync(discovery);

      if (result.type === "success" && result.params.code) {
        const tokenResponse = await AuthSession.exchangeCodeAsync(
          {
            clientId: "evidenceeu-mobile",
            code: result.params.code,
            redirectUri,
            extraParams: {},
          },
          discovery,
        );

        await SecureStore.setItemAsync("accessToken", tokenResponse.accessToken);
        setState({
          accessToken: tokenResponse.accessToken,
          isLoading: false,
          isAuthenticated: true,
        });
      }
    } catch {
      setState((prev) => ({ ...prev, isLoading: false }));
    }
  }, []);

  const signOut = useCallback(async () => {
    await SecureStore.deleteItemAsync("accessToken");
    setState({ accessToken: null, isLoading: false, isAuthenticated: false });
  }, []);

  return {
    ...state,
    signIn,
    signOut,
  };
}
