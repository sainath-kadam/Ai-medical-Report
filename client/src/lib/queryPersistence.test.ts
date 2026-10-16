import { QueryClient } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearPersistedQueryCache, persistQueryCache, restorePersistedQueryCache } from './queryPersistence';

const KEY = 'radiolens_query_cache';

function newClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe('query cache persistence across reloads', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('a reload restores the last successful data', async () => {
    const before = newClient();
    const stop = persistQueryCache(before);
    before.setQueryData(['patients', 'list'], { items: [{ id: 'p1' }] });
    vi.advanceTimersByTime(1500);
    stop();

    const after = newClient(); // simulates the page reload
    restorePersistedQueryCache(after);

    expect(after.getQueryData(['patients', 'list'])).toEqual({ items: [{ id: 'p1' }] });
  });

  it('never persists failed queries', async () => {
    const client = newClient();
    const stop = persistQueryCache(client);
    await client.fetchQuery({ queryKey: ['bad'], queryFn: () => Promise.reject(new Error('x')) }).catch(() => {});
    client.setQueryData(['good'], 1);
    vi.advanceTimersByTime(1500);
    stop();

    const keys = JSON.parse(sessionStorage.getItem(KEY)!).state.queries.map((q: { queryKey: unknown }) => q.queryKey);
    expect(keys).toEqual([['good']]);
  });

  it('throttles writes instead of saving on every change', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const client = newClient();
    const stop = persistQueryCache(client);
    for (let i = 0; i < 20; i++) client.setQueryData(['n', i], i);
    vi.advanceTimersByTime(1500);
    stop();

    expect(setItem.mock.calls.filter(([key]) => key === KEY)).toHaveLength(1);
    setItem.mockRestore();
  });

  it('drops a cache older than a day, or from another cache version', () => {
    sessionStorage.setItem(KEY, JSON.stringify({ version: 1, savedAt: Date.now() - 25 * 3600_000, state: { queries: [], mutations: [] } }));
    restorePersistedQueryCache(newClient());
    expect(sessionStorage.getItem(KEY)).toBeNull();

    sessionStorage.setItem(KEY, JSON.stringify({ version: 999, savedAt: Date.now(), state: { queries: [], mutations: [] } }));
    restorePersistedQueryCache(newClient());
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it('ignores a corrupt entry instead of crashing the app', () => {
    sessionStorage.setItem(KEY, '{not json');
    expect(() => restorePersistedQueryCache(newClient())).not.toThrow();
  });

  it('logout clears the persisted cache', () => {
    sessionStorage.setItem(KEY, 'anything');
    clearPersistedQueryCache();
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });
});
