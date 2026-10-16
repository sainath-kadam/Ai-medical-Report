import axios from 'axios';
import { createContext, ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/auth.api';
import { tokenStorage } from '../api/axiosInstance';
import { queryClient } from '../lib/queryClient';
import { clearPersistedQueryCache } from '../lib/queryPersistence';
import { Organization, User } from '../types';

// The last /auth/me answer, so a reload with a still-valid token renders the app at once
// instead of a full-screen loader while /auth/me (on a cold backend, many seconds) runs.
// refreshProfile still re-checks in the background and corrects or clears it.
const PROFILE_KEY = 'radiolens_profile';

interface ProfileSnapshot {
  user: User;
  organization: Organization | null;
}

function readProfileSnapshot(): ProfileSnapshot | null {
  if (!tokenStorage.getAccess()) return null;
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    return raw ? (JSON.parse(raw) as ProfileSnapshot) : null;
  } catch {
    return null;
  }
}

function writeProfileSnapshot(snapshot: ProfileSnapshot | null) {
  try {
    if (snapshot) localStorage.setItem(PROFILE_KEY, JSON.stringify(snapshot));
    else localStorage.removeItem(PROFILE_KEY);
  } catch {
    // Storage blocked: the app just falls back to waiting for /auth/me on reload.
  }
}

/** Drops every trace of the previous session's data -- cached pages included -- so a
 *  different account signing in on this browser never sees it. */
function clearSessionData() {
  writeProfileSnapshot(null);
  queryClient.clear();
  clearPersistedQueryCache();
}

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
  const [snapshot] = useState(readProfileSnapshot);
  const [user, setUser] = useState<User | null>(snapshot?.user ?? null);
  const [organization, setOrganization] = useState<Organization | null>(snapshot?.organization ?? null);
  // With a snapshot there's nothing to wait for: render now, revalidate in the background.
  const [isLoading, setIsLoading] = useState(!snapshot);

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
      writeProfileSnapshot({ user: data.user, organization: data.organization });
    } catch (err) {
      // Only a genuine 401 means the session is actually invalid. Anything else (rate
      // limiting, a 5xx, a dropped connection) is transient -- axiosInstance.ts already
      // retries a 401 once via /auth/refresh before this ever throws, so if a 401 does
      // reach here the refresh attempt itself already failed. Logging the user out on a
      // 429/500/network blip would spuriously drop an active session (found via an
      // end-to-end browser smoke test hitting /auth/me during rapid navigation).
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        tokenStorage.clear();
        clearSessionData();
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
    clearSessionData();
    tokenStorage.set(data.accessToken, data.refreshToken);
    setUser(data.user);
    await refreshProfile();
  }, [refreshProfile]);

  const signup = useCallback(
    async (payload: { name: string; email: string; password: string; organizationName: string }) => {
      const data = await authApi.signup(payload);
      clearSessionData();
      tokenStorage.set(data.accessToken, data.refreshToken);
      setUser(data.user);
      await refreshProfile();
    },
    [refreshProfile]
  );

  const loginWithGoogle = useCallback(
    async (idToken: string, organizationName?: string) => {
      const data = await authApi.google({ idToken, organizationName });
      clearSessionData();
      tokenStorage.set(data.accessToken, data.refreshToken);
      setUser(data.user);
      await refreshProfile();
    },
    [refreshProfile]
  );

  const logout = useCallback(async () => {
    const refreshToken = tokenStorage.getRefresh();
    tokenStorage.clear();
    clearSessionData();
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
