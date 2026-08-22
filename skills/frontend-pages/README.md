# frontend-pages

One folder per route under `client/src/pages/` — the top-level screen components wired up
in `client/src/routes/AppRoutes.tsx`. Each page owns its own data fetching (via
`client/src/api/*.api.ts`), local UI state, and a colocated `<PageName>.css`.

## Folder inventory

- `Dashboard/` — landing screen after login; stats + recent reports, or an inline "new
  study" upload flow toggled by state (not a separate route).
- `Patients/` — `Patients.tsx` (searchable/paginated list + create/edit modals) and
  `PatientDetail.tsx`.
- `Studies/` — `Studies.tsx` (list) and `StudyDetail.tsx` (the big one — see below).
- `ReportsList/` and `ReportDetail/` — `ReportDetail.tsx` is a thin redirect, not a real
  page (see below).
- `Users/`, `AuditLogs/`, `OrganizationSettings/`, `Templates/` — org_admin-only screens
  (gated by `RoleRoute` in `client/src/routes/`).
- `Billing/`, `Settings/`, `Profile/` — account-level screens, any authenticated role.
- `Platform/CreateOrganization.tsx` — system_admin-only; the one screen that creates a new
  org + its first org_admin rather than operating inside an existing org.
- `Landing/` — public marketing page shown only when logged out (see `RootGate` in
  `AppRoutes.tsx`).
- `auth/Login/`, `auth/Signup/`, `auth/ForgotPassword/` — unauthenticated auth flows.
- `NotFound/` — catch-all for `/404` and any unmatched path.

## The shared pattern

Every list/detail page follows the same shape: `isLoading` state shows a `Loader`, a
caught error (via `apiErrorMessage` from `client/src/api/axiosInstance.ts`) shows an inline
error string, an empty result shows `EmptyState` (with a call-to-action where one makes
sense), and only then does the real content render. Pages don't use React Query or SWR —
just `useState`/`useEffect`/`useCallback` calling the api modules directly.

## Non-obvious things

- **`ReportDetail.tsx` is not a real page.** `/reports/:id` used to duplicate patient/study/
  report data that `StudyDetail.tsx` also showed; now `StudyDetail`'s "Report" tab
  (`?tab=report`) is the only place a report is viewed/edited/finalized. `ReportDetail.tsx`
  just resolves the report's `studyId` and issues a `<Navigate>` there, so old
  `/reports/{id}` links (from `ReportCard`, notifications, etc.) keep working.
- **`StudyDetail.tsx` has no `GET /studies/{id}/report` endpoint to call** (a known backend
  gap — see `CONTRACTS.md`), so it locates a study's report indirectly: list reports by
  `patientId` and find the one whose `studyId` matches, client-side.
- **`Dashboard.tsx`'s upload flow is a mode, not a route.** `?startUpload=1&patientId=...`
  in the URL (set by `PatientDetail`'s "new study for this patient" link) flips Dashboard
  into showing `NewStudyForm` inline instead of the normal stats/reports view; closing it
  clears those query params rather than navigating away.
- **`Home()` inside `AppRoutes.tsx`, not anything in `Dashboard/`, decides that
  `system_admin` never sees the Dashboard** — it redirects straight to
  `/platform/organizations` because a system_admin has no `organization_id` and every
  Dashboard data call would just 403. Keep that redirect in mind if you ever see a
  system_admin unexpectedly skip past this page.
