# frontend-api

The HTTP layer between pages/components and the FastAPI backend: one `*.api.ts` module per
backend domain, a shared axios instance, and `client/src/types/index.ts` — the frontend
half of the wire contract described in `CONTRACTS.md`.

## Key files

- `client/src/api/axiosInstance.ts` — the shared `api` axios instance (baseURL from
  `VITE_API_URL`, 120s timeout to tolerate slow AI calls), token storage helpers
  (`tokenStorage`), and `apiErrorMessage(error)` — every page's catch block calls this to
  turn an axios error into a display string.
- `client/src/api/auth.api.ts`, `patient.api.ts`, `study.api.ts`, `report.api.ts`,
  `template.api.ts`, `user.api.ts`, `organization.api.ts`, `billing.api.ts`,
  `dashboard.api.ts`, `auditLog.api.ts`, `platform.api.ts` — one object per domain, each
  method a thin `api.get/post/patch/delete(...).then((r) => r.data.data)` that unwraps the
  `{success, data}` envelope and returns the typed payload.
- `client/src/types/index.ts` — every wire entity (`User`, `Organization`, `Patient`,
  `Study`, `StudyFile`, `AnalysisJob`, `Report`/`ReportVersion`/`GeneratedReportContent`,
  `ReportTemplate`, `AuditLog`, `DashboardStats`, `Paginated<T>`, etc.) plus the string-union
  types (`UserRole`, `Modality`, `StudyStatus`, `AnalysisJobStatus`, `ReportStatus`, `Sex`).
  Every entity uses `id: string`, never `_id` or a numeric id.

## Non-obvious things

- **Automatic silent token refresh lives entirely in `axiosInstance.ts`'s response
  interceptor.** A 401 on any non-`/auth/*` request triggers exactly one refresh attempt
  (via `POST /auth/refresh`), and concurrent 401s share one in-flight `refreshPromise`
  rather than each firing their own refresh call. If refresh fails, tokens are cleared and
  the browser is hard-redirected to `/login` — this bypasses React Router entirely.
- **Blob-typed error responses are unwrapped before `apiErrorMessage` ever sees them.**
  Requests made with `responseType: 'blob'` (PDF download/preview) still deserialize an
  *error* body as a Blob per axios's configured responseType, not JSON — the response
  interceptor's `unwrapBlobErrorBody` detects a JSON-typed Blob and parses it back into the
  object every call site expects. Without this, PDF-download error handling would silently
  show axios's generic "Request failed with status code 4xx" instead of the server's actual
  message.
- **Some endpoints return the paginated envelope but the api module flattens it.**
  E.g. `patientApi.getStudies` and `studyApi.getJobsForStudy` unwrap `Paginated<T>` down to
  a plain array (`.data.items`) because no current caller needs pagination for those lists —
  don't assume every api method's return shape matches its backend route's raw response.
- **`reportApi.requestChanges` and `studyApi.runAnalysis` return only a `jobId`**, not the
  updated resource — callers must poll `GET /analysis/jobs/{jobId}` (see
  `useAnalysisJobPolling` and `StudyDetail.tsx`) to find out when it's done, even though the
  backend runs both synchronously in-request with no real background worker.
