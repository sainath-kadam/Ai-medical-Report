/** Local-dev-only escape hatches. Never rely on these in a real deployment — they exist
 * purely so a developer can click through every page's layout without a backend session
 * (e.g. to eyeball a UI change) while a real fix/flow is still being worked out.
 *
 * `VITE_SKIP_AUTH=true` (client/.env) disables both route-level auth gating
 * (`routes/ProtectedRoute.tsx`, `routes/RoleRoute.tsx`) and the axios 401 redirect
 * (`api/axiosInstance.ts`). Pages still call the real API with no
 * token, so anything that fetches data will show its normal loading/empty/error state
 * (401s), not populated content — this only stops the app from bouncing you back to
 * `/login`. To see the app with real data, sign up/log in normally instead.
 */
export const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === 'true';
