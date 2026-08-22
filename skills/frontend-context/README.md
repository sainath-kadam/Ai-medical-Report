# frontend-context

Global React state that lives above the router: authentication/session state and the
light/dark theme. Also home to the app's small collection of standalone hooks (most of
which don't belong to `context/` themselves but are colocated here because they're
similarly app-wide, not feature-specific).

## Key files

- `client/src/context/AuthContext.tsx` — `AuthProvider`. Holds `user`, `organization`,
  `isLoading`, `isAuthenticated`, and `login`/`signup`/`loginWithGoogle`/`logout`/
  `refreshProfile`. Delegates actual HTTP calls to `api/auth.api.ts` and token
  persistence to `tokenStorage` (`api/axiosInstance.ts`).
- `client/src/context/ThemeContext.tsx` — `ThemeProvider`. Holds `theme` (`'light' |
  'dark'`) and `toggleTheme`. Persists to `localStorage['medscan_theme']` and falls back
  to `prefers-color-scheme` on first load.
- `client/src/hooks/useAuth.ts` / `useTheme.ts` — thin `useContext` wrappers; both throw
  if called outside their provider (fail fast on a missing `<AuthProvider>`/`<ThemeProvider>`
  rather than silently returning `undefined`).
- `client/src/hooks/useClickOutside.ts` — generic "close this popover/dropdown on outside
  click" hook, used by Topbar's account/admin dropdowns.
- `client/src/hooks/useAnalysisJobPolling.ts` — polls `GET /analysis/jobs/{id}` every 2s
  until a terminal status, shared by every screen that starts or resumes watching an AI
  analysis job.
- `client/src/hooks/useTemplatePreviewPdf.ts` — debounced fetch of `POST
  /templates/preview-pdf`, exposed as a revocable object URL.
- `client/src/hooks/useScrollReveal.ts` — one-shot IntersectionObserver fade-in, used only
  on the marketing Landing page (app pages intentionally don't animate content in).

## Non-obvious things

- **`refreshProfile` only logs the user out on a genuine 401.** Any other failure
  (429, 5xx, dropped connection) is treated as transient and left alone. This is
  deliberate: `axiosInstance.ts`'s response interceptor already attempts one silent
  `/auth/refresh` before a 401 ever reaches this code, so if a 401 does land here the
  refresh itself already failed. Logging out on *any* error was tried and caused
  spurious session drops during rapid navigation (found via a browser smoke test) —
  don't "simplify" this back to a catch-all.
- **`ThemeProvider` sets `data-theme` directly on `<html>`** (`document.documentElement`),
  which is what `styles/variables.css`'s `[data-theme='dark']` block key off. There is no
  CSS class involved — a component that tries to theme off a class won't work.
- **`logout()` does a hard `window.location.href = '/login'`**, not a router navigate —
  it fully reloads the app so no stale in-memory state survives. Session revocation
  (`authApi.logout`) is fire-and-forget after tokens are already cleared client-side, so
  the user is logged out locally even if that network call fails.
- Both polling/debounce hooks (`useAnalysisJobPolling`, `useTemplatePreviewPdf`) stash
  their callback/payload in a `ref` specifically so callers don't have to memoize what
  they pass in — copy that pattern rather than adding the callback to a `useCallback`
  dependency array.
