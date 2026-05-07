import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useMsal } from "@azure/msal-react";
import type { AccountInfo } from "@azure/msal-browser";

import { setUser as telemetrySetUser, clearUser as telemetryClearUser } from "../utils/telemetry";

export type AuthUser = {
  name: string;
  email: string;
};

type AuthContextValue = {
  user: AuthUser | null;
  getAuthHeaders: () => Promise<Record<string, string>>;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  getAuthHeaders: async () => ({}),
  signOut: () => {},
});

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}

/** Bridges MSAL state into a simple AuthContext. Must be inside MsalProvider. */
export function MsalAuthBridge({
  children,
  apiScopes,
}: {
  children: ReactNode;
  apiScopes: string[];
}) {
  const { instance, accounts } = useMsal();
  const account: AccountInfo | undefined = accounts[0];

  // Bind authenticated user to App Insights (opaque homeAccountId — never email).
  useEffect(() => {
    if (account?.homeAccountId) {
      telemetrySetUser(account.homeAccountId, account.tenantId);
    } else {
      telemetryClearUser();
    }
  }, [account]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: account
        ? { name: account.name ?? "", email: account.username ?? "" }
        : null,

      getAuthHeaders: async (): Promise<Record<string, string>> => {
        if (!account) return {};
        try {
          const result = await instance.acquireTokenSilent({
            scopes: apiScopes,
            account,
          });
          return { Authorization: `Bearer ${result.accessToken}` };
        } catch {
          // Silent acquisition failed — trigger interactive login
          await instance.acquireTokenRedirect({ scopes: apiScopes });
          return {};
        }
      },

      signOut: () => {
        instance.logoutRedirect({ postLogoutRedirectUri: "/" });
      },
    }),
    [instance, account, apiScopes],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

/** No-op provider for when auth is disabled (local dev). */
export function NoAuthProvider({ children }: { children: ReactNode }) {
  const value = useMemo<AuthContextValue>(
    () => ({
      user: null,
      getAuthHeaders: async () => ({}),
      signOut: () => {},
    }),
    [],
  );

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}
