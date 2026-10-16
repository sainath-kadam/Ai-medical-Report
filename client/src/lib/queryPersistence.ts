import { dehydrate, hydrate, QueryClient } from '@tanstack/react-query';

// Survives a page reload so every page renders its last-known data instantly and then
// revalidates in the background (the same stale-while-revalidate behavior as navigating
// between pages), instead of a reload starting from an empty cache and waiting on the API.
//
// sessionStorage, not localStorage, on purpose: the cache holds patient data, and
// sessionStorage is scoped to this one tab and wiped when the tab closes -- a reload keeps
// it, a closed browser doesn't. `clearPersistedQueryCache` also wipes it on logout.
const STORAGE_KEY = 'radiolens_query_cache';
// Bumped whenever a cached response shape changes in a way old data would break.
const CACHE_VERSION = 1;
// Anything older than this is dropped at startup rather than shown.
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const WRITE_THROTTLE_MS = 1000;

interface PersistedCache {
  version: number;
  savedAt: number;
  state: ReturnType<typeof dehydrate>;
}

export function restorePersistedQueryCache(client: QueryClient): void {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const persisted = JSON.parse(raw) as PersistedCache;
    if (persisted.version !== CACHE_VERSION || Date.now() - persisted.savedAt > MAX_AGE_MS) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }
    hydrate(client, persisted.state);
  } catch {
    // Corrupt entry or storage blocked (private mode): just start with an empty cache.
  }
}

/** Writes the cache to sessionStorage (throttled) whenever it changes. Returns an
 *  unsubscribe function. Only successful queries are persisted -- never errors or
 *  in-flight fetches. */
export function persistQueryCache(client: QueryClient): () => void {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const write = () => {
    timer = null;
    try {
      const persisted: PersistedCache = {
        version: CACHE_VERSION,
        savedAt: Date.now(),
        state: dehydrate(client, { shouldDehydrateQuery: (query) => query.state.status === 'success' }),
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    } catch {
      // Quota exceeded or storage blocked: persistence is a convenience, never an error.
    }
  };

  const unsubscribe = client.getQueryCache().subscribe(() => {
    if (timer === null) timer = setTimeout(write, WRITE_THROTTLE_MS);
  });

  return () => {
    unsubscribe();
    if (timer !== null) clearTimeout(timer);
  };
}

export function clearPersistedQueryCache(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage blocked: nothing was persisted in the first place.
  }
}
