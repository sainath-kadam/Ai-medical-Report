import axios from 'axios';
import { SKIP_AUTH } from '../utils/devFlags';

const ACCESS_TOKEN_KEY = 'medscan_access_token';
const REFRESH_TOKEN_KEY = 'medscan_refresh_token';

export const tokenStorage = {
  getAccess: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  set: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  setAccess: (accessToken: string) => localStorage.setItem(ACCESS_TOKEN_KEY, accessToken),
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  timeout: 120_000, // AI analysis/report calls can legitimately take a while
});

api.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Every request that legitimately hits a 401 (expired access token) gets exactly one
// silent refresh attempt before we give up and send the user back to /login. Concurrent
// 401s while a refresh is already in flight share the same in-flight promise instead of
// each firing their own /auth/refresh call.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = tokenStorage.getRefresh();
  if (!refreshToken) return null;
  try {
    const response = await axios.post<{ success: boolean; data: { accessToken: string; refreshToken: string } }>(
      `${api.defaults.baseURL}/auth/refresh`,
      { refreshToken }
    );
    const { accessToken, refreshToken: nextRefreshToken } = response.data.data;
    tokenStorage.set(accessToken, nextRefreshToken);
    return accessToken;
  } catch {
    return null;
  }
}

// A request made with `responseType: 'blob'` (PDF downloads/previews) still deserializes
// an *error* response as a Blob, per the configured responseType -- axios doesn't know the
// error body is actually JSON. Left alone, `error.response.data` is an opaque Blob and
// every string-shaped fallback in apiErrorMessage misses, surfacing axios's raw "Request
// failed with status code 4xx" instead of the server's real message. Unwrap it here, once,
// so every call site's error handling just works.
async function unwrapBlobErrorBody(error: unknown): Promise<void> {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (!(data instanceof Blob) || !data.type.includes('json')) return;
  try {
    const parsed = JSON.parse(await data.text());
    (error as { response: { data: unknown } }).response.data = parsed;
  } catch {
    // Wasn't actually JSON (e.g. a truly binary error body) -- leave it as the Blob.
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    await unwrapBlobErrorBody(error);

    const originalRequest = error.config;
    const isAuthEndpoint = originalRequest?.url?.startsWith('/auth/');

    if (error.response?.status === 401 && !originalRequest?._retried && !isAuthEndpoint) {
      originalRequest._retried = true;
      refreshPromise = refreshPromise || refreshAccessToken();
      const newAccessToken = await refreshPromise;
      refreshPromise = null;

      if (newAccessToken) {
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      }

      tokenStorage.clear();
      if (!SKIP_AUTH && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      return error.response.data?.error?.message || error.response.data?.message || error.message || 'Something went wrong';
    }
    // No response at all means the request never completed -- offline, dropped connection,
    // CORS, or our own 120s timeout -- not something the server had a chance to describe.
    if (error.code === 'ECONNABORTED') {
      return 'The request timed out. Please check your connection and try again.';
    }
    return 'Unable to reach the server. Check your connection and try again.';
  }
  return 'Something went wrong';
}
