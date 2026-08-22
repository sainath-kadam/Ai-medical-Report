import axios from 'axios';
import { createContext, ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/auth.api';
import { tokenStorage } from '../api/axiosInstance';
import { Organization, User } from '../types';

interface AuthContextValue {
  user: User | null;
  organization: Organization | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (payload: { name: string; email: string; password: string; organizationName: string }) => Promise<void>;
  loginWithGoogle: (idToken: string, organizationName?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

// eslint-disable-next-line react-refresh/only-export-components
export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    if (!tokenStorage.getAccess()) {
      setUser(null);
      setOrganization(null);
      setIsLoading(false);
      return;
    }
    try {
      const data = await authApi.me();
      setUser(data.user);
      setOrganization(data.organization);
    } catch (err) {
      // Only a genuine 401 means the session is actually invalid. Anything else (rate
      // limiting, a 5xx, a dropped connection) is transient -- axiosInstance.ts already
      // retries a 401 once via /auth/refresh before this ever throws, so if a 401 does
      // reach here the refresh attempt itself already failed. Logging the user out on a
      // 429/500/network blip would spuriously drop an active session (found via an
      // end-to-end browser smoke test hitting /auth/me during rapid navigation).
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        tokenStorage.clear();
        setUser(null);
        setOrganization(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login({ email, password });
    tokenStorage.set(data.accessToken, data.refreshToken);
    setUser(data.user);
    await refreshProfile();
  }, [refreshProfile]);

  const signup = useCallback(
    async (payload: { name: string; email: string; password: string; organizationName: string }) => {
      const data = await authApi.signup(payload);
      tokenStorage.set(data.accessToken, data.refreshToken);
      setUser(data.user);
      await refreshProfile();
    },
    [refreshProfile]
  );

  const loginWithGoogle = useCallback(
    async (idToken: string, organizationName?: string) => {
      const data = await authApi.google({ idToken, organizationName });
      tokenStorage.set(data.accessToken, data.refreshToken);
      setUser(data.user);
      await refreshProfile();
    },
    [refreshProfile]
  );

  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefresh();
    tokenStorage.clear();
    setUser(null);
    setOrganization(null);
    if (refreshToken) {
      // Best-effort session revocation — the client is already logged out locally either way.
      authApi.logout(refreshToken).catch(() => {});
    }
    window.location.href = '/login';
  }, []);

  const value = useMemo(
    () => ({ user, organization, isLoading, isAuthenticated: !!user, login, signup, loginWithGoogle, logout, refreshProfile }),
    [user, organization, isLoading, login, signup, loginWithGoogle, logout, refreshProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
