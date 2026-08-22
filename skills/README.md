# skills/

One folder per backend domain / frontend area — the fast path for working on a specific
module without reading `CLAUDE.md`, root `README.md`, or `CONTRACTS.md` in full first.
Each folder has a `README.md` (what the module does, key files, non-obvious gotchas) and
a `skill.json` (machine-readable: `name`, `domain`, `description`, `paths`).
`index.json` in this folder catalogs all of them in one place.

**Working on something? Find the matching skill below, read its `README.md`, then go to
the code.** If a skill's `README.md` cites a `CONTRACTS.md` section, that's the place to
check the exact wire shape before changing a route/schema.

## Backend (`server/app/`)

| Skill | Covers |
|---|---|
| `backend-auth` | Signup, login, Google OAuth, tokens, JWT/RBAC primitives |
| `backend-users` | Org user roster: invite/list/update/delete |
| `backend-organizations` | Read/update the current org (the tenant itself) |
| `backend-core` | Config, error contract, logging, trial gate, rate limiting |
| `backend-patients` | Patient CRUD + a patient's studies |
| `backend-studies` | Study CRUD + the combined intake flow |
| `backend-uploads` | File attach + signed-URL download |
| `backend-intake` | Stateless chat-style intake field extraction |
| `backend-analysis` | Triggers/tracks the in-request AI-analysis pipeline |
| `backend-reports` | Report edit/change-request/regenerate/finalize/PDF |
| `backend-templates` | Report-template branding/sections/preview |
| `backend-ai` | The imaging-analysis + report-generation provider abstraction |
| `backend-database` | SQLAlchemy models, engine/session, camelCase<->snake_case |
| `backend-repositories` | `BaseRepository`'s shared CRUD/org-scoping convention |
| `backend-storage` | Signed-URL file storage abstraction (local/S3/Firebase) |
| `backend-platform` | `system_admin` role + onboarding new organizations |
| `backend-billing` | Trial gating + Stripe checkout/webhook |
| `backend-dashboard` | Stats + recent-activity rollups |
| `backend-audit-logs` | The audit trail every mutation writes to |
| `backend-notifications` | In-app notifications (create/list/mark-read) |

## Frontend (`client/src/`)

| Skill | Covers |
|---|---|
| `frontend-pages` | Route screens, the loading/error/empty/content pattern |
| `frontend-routes` | Route table, `ProtectedRoute`/`RoleRoute` guards |
| `frontend-api` | `*.api.ts` modules, `axiosInstance.ts`, `types/index.ts` |
| `frontend-context` | `AuthContext`/`ThemeContext` + shared hooks |
| `frontend-ui-components` | Generic primitives: Table, Pagination, Select, Tabs, Toast |
| `frontend-components` | `common/` + feature component folders (patients/studies/…) |
| `frontend-styles` | Design tokens, light/dark theme, base reset |

Note: there's deliberately no skill for the outer `client/` or `server/` folder as a
whole — every skill maps to one specific module, not a top-level umbrella.
