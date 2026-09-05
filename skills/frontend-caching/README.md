# frontend-caching

Every page's GET request goes through a TanStack Query (`@tanstack/react-query` v5) cache
instead of a bare `useEffect` fetch — added so navigating between pages (Patients ->
a patient -> back, Studies -> a study -> back, and so on) reuses the last response instead
of re-hitting the API every time, while a mutation (create/update/delete) still shows fresh
data right after. Not part of the original CONTRACTS.md spec.

## Key files

- `client/src/lib/queryClient.ts` — the one `QueryClient` instance, created in `main.tsx`'s
  `<QueryClientProvider>` and shared by the whole app for the lifetime of the tab. Global
  defaults: `staleTime: 30_000` (a query mounted again within 30s reads cache with **no**
  network request; past that, cached data renders immediately — stale-while-revalidate —
  while a background refetch silently replaces it if the server's answer changed),
  `gcTime: 5 * 60_000` (how long an unused entry survives after its last observer
  unmounts), `retry: 1`, `refetchOnWindowFocus: false` (the existing pages fail fast on a
  real error with no built-in retry; kept that instead of React Query's louder defaults).
- `client/src/lib/queryKeys.ts` — one key-factory object per domain (`patients`, `studies`,
  `reports`, `templates`, `users`, `organization`, `billing`, `auditLogs`, `dashboard`,
  `platform`). Every domain has an `all` prefix (e.g. `['patients']`) that every other key
  in it nests under — `invalidateQueries({queryKey: queryKeys.patients.all})` matches
  every list (any page/search) and every detail (any id) in one call. Mutations invalidate
  the whole domain rather than hand-picking the one key a write touched — simpler, and the
  cost is only a few extra background refetches for whatever else happens to be mounted.
- `client/src/hooks/queries/*.ts` — one file per domain (`usePatients.ts`, `useStudies.ts`,
  `useReports.ts`, `useTemplates.ts`, `useUsers.ts`, `useOrganization.ts`, `useBilling.ts`,
  `useAuditLogs.ts`, `useDashboard.ts`, `usePlatform.ts`), each exporting plain `useQuery`
  wrappers around the matching `api/*.api.ts` call — e.g. `usePatientsList(params)`,
  `usePatient(id)`. `staleTime` is set per file, shorter for data that changes during
  active work (studies: 20s, a study's job history: 10s) and longer for
  configure-once-in-a-while data (templates/users/organization: 60s).

## Non-obvious things

- **Pages still own their own mutations** — no `useMutation` wrapper. A page calls the
  `api/*.api.ts` function directly (as before), then either `queryClient.setQueryData(key,
  result)` (when the mutation's response IS the new cached value — e.g. saving a report
  edit) or `queryClient.invalidateQueries({queryKey: queryKeys.X.all})` (list-shaped
  changes: create/delete, or anything with side effects elsewhere) inside the same
  `try`/`catch` as before. This kept every page's existing error-handling/loading-state
  pattern intact instead of rewriting it around `useMutation`.
- **A mutation on one page invalidates domains it doesn't render**, on purpose. E.g.
  finalizing a report on `StudyDetail` invalidates `studies`, `reports`, AND `dashboard` —
  the Dashboard's stats/recent-reports and the ReportsList both embed a snapshot of that
  same report/study, so they'd otherwise show stale data on their next visit. Look at each
  page's `invalidate*` helper (defined at the top of the component) to see exactly what a
  given action touches.
- **`placeholderData: keepPreviousData`** (imported from `@tanstack/react-query`) is set
  on every paginated/filtered list query. Changing page or a filter shows the *previous*
  page's rows (marked `isPlaceholderData` internally, not surfaced to the UI) while the
  new one loads, instead of flashing to a full-page `Loader` — a deliberate UX
  improvement over the pre-caching behavior, not just a side effect of adding the cache.
- **`isLoading` (not `isPending`) is what pages check for the full-page `Loader`.** In
  React Query v5, `isLoading` = `isPending && isFetching` — true only on a genuine first
  fetch with nothing cached yet. A revisit within `staleTime` never sets it (data is
  already there, nothing fetching); a revisit past `staleTime` also never sets it (data is
  still there, just refetching silently in the background) — that's what makes "show the
  old page instantly, then quietly refresh if it changed" work with no extra code per page.
- **Query keys are structural, not reference-based.** A page passes a fresh params object
  to a hook every render (e.g. `{page, pageSize, search}}`); React Query hashes it
  deterministically, so this still dedupes correctly against the same `{page, pageSize,
  search}` shape from an earlier render/visit. Don't "optimize" this by memoizing the
  params object — it isn't needed and isn't the source of any caching bug if one shows up.
- **Some pages guard against a background refetch clobbering an in-progress edit.**
  `OrganizationSettings.tsx` and `Platform/OrganizationDetail.tsx` both keep a local form
  draft seeded from the query's data, but only re-seed it while nothing is unsaved
  (`isDirty`/`isFormDirty` flag) — otherwise a silent cache revalidation mid-edit would
  overwrite whatever the user just typed. Copy this pattern for any new page with an
  editable form fed by a cached query.
- **`StudyDetail.tsx` is the one page where cached queries sit alongside existing
  polling** (`useAnalysisJobPolling`, unchanged). The polling callback and every mutation
  handler call the same `invalidateStudy`/`invalidateReportRelated` helpers a plain click
  would, so an AI analysis finishing in the background refreshes the study/report/job-
  history caches exactly like a manual save does — see that file for the "resume polling
  once per study id, not on every cache refetch" guard (a `useRef`, not a dependency
  array), which is not obvious from the hook calls alone.
- **`AuthContext` (`user`/`organization`) is deliberately NOT part of this cache.** It's
  session state with its own login/logout/refresh lifecycle (`client/src/context/
  AuthContext.tsx`), fetched once via `authApi.me()` at app mount — not a per-page GET.
  `organization.access` (CONTRACTS.md §2c read-only state) rides along on it as before;
  don't route it through a query hook.
- **Not every GET was converted** — only page-level "list/detail" fetches. A few
  in-component convenience fetches stayed direct API calls where converting them added no
  cross-page cache benefit (e.g. `NewStudyForm`'s live patient search-as-you-type list).
  The one component-level fetch that WAS converted is `NewStudyForm`'s template picker
  (`useTemplatesList()`, same key the Templates settings page reads) — opening the upload
  flow after visiting Templates, or the reverse, costs zero network requests.
