import { QueryClient } from '@tanstack/react-query';

// One shared cache for the whole app (created in main.tsx's <QueryClientProvider>, not per
// component) -- this is what lets navigating Patients -> Studies -> back to Patients reuse
// the last response instead of refetching, as long as it's still "fresh" (see each
// hooks/queries/*.ts file's staleTime). Defaults here are the fallback for any query that
// doesn't set its own staleTime; per-domain hooks override it where a shorter or longer
// window makes sense (e.g. an in-progress analysis job's own list is cached only briefly).
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // "Fresh" window: a query re-mounted (e.g. by navigating back to a page) within this
      // many ms reads straight from cache with NO network request. Past it, the cached
      // value is shown immediately (stale-while-revalidate) while a background refetch
      // silently replaces it if the server's answer actually changed -- exactly the "show
      // older values while it refetches" behavior asked for, not an extra loading spinner.
      staleTime: 30_000,
      // How long an unused cache entry (no mounted component reading it) is kept before
      // being garbage-collected -- long enough that a quick round trip between pages
      // still hits cache even after every observer of it has unmounted.
      gcTime: 5 * 60_000,
      // The existing pages fail fast on a real error (no built-in retry today) -- keep
      // that behavior rather than React Query's default of 3 silent retries, which would
      // make a genuine 4xx/5xx take several extra seconds to surface.
      retry: 1,
      // Switching browser tabs/windows shouldn't fire a wave of background requests across
      // every mounted query -- normal navigation (mount/unmount) already revalidates stale
      // data, which covers what this app needs.
      refetchOnWindowFocus: false,
    },
  },
});
