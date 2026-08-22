# frontend-routes

The full client-side route table and the two guard components every protected route is
wrapped in. Three files total, all short — read them directly rather than guessing.

## Key files

- `client/src/routes/AppRoutes.tsx` — the entire route table. `/`, `/login`, `/signup`,
  `/forgot-password` are public; everything else nests under `<ProtectedRoute>` +
  `<DashboardLayout>`. `/templates`, `/users`, `/organization`, `/audit-logs` are further
  wrapped in `<RoleRoute roles={['org_admin']}>`; `/platform/organizations` in
  `<RoleRoute roles={['system_admin']}>`. Unmatched paths hit `/404` (`NotFound`).
- `client/src/routes/ProtectedRoute.tsx` — redirects to `/login` if not authenticated
  (renders a full-page `Loader` while auth is still resolving); otherwise renders `<Outlet>`.
- `client/src/routes/RoleRoute.tsx` — nested under `ProtectedRoute`, so auth is already
  resolved by the time it runs; redirects to `/dashboard` if the current user's role isn't
  in the allowed list.

## Non-obvious things

- **Two inline components inside `AppRoutes.tsx` do real routing logic, not just the
  `<Routes>` table**: `RootGate` (used for `/`) shows the public `Landing` page only while
  logged out — once authenticated it redirects to `/dashboard` instead of rendering both at
  the same path — and `Home` (used for `/dashboard`) sends `system_admin` straight to
  `/platform/organizations` instead of rendering `Dashboard`, because `system_admin` has no
  `organization_id` and Dashboard's data calls would just 403.
- **`SKIP_AUTH` (from `client/src/utils/devFlags.ts`) bypasses both guards entirely** —
  `ProtectedRoute` and `RoleRoute` both short-circuit to `<Outlet>` immediately when it's
  set, skipping the auth/role check altogether. This is a dev-only escape hatch; don't
  assume either guard is actually enforcing anything without checking that flag's value.
- **Role gating is coarse-grained, not per-page**: `RoleRoute` wraps a whole `<Route>`
  subtree (e.g. all four org_admin-only pages share one `RoleRoute` block), so a new
  org_admin-only page just needs adding inside the existing block, not a new guard.
