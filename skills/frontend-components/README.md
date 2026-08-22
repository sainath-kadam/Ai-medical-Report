# frontend-components

Two related but distinct groups: `components/common/` (pre-existing generic building
blocks — buttons, cards, form fields) and the feature-specific component folders that
compose them into actual product UI (layout chrome, patients, studies, reports,
templates, upload).

## Inventory

**`components/common/`** (one `Name/Name.tsx` + `Name.css` pair each):
`Button`, `Card`, `EmptyState`, `GoogleButton`, `Loader`, `Modal`, `StatCard`,
`StatusBadge`, `TempPasswordBanner`, `TextField` (exports both `TextField` and
`TextArea`).

**Feature folders** (each holding one or more `Name/Name.tsx` + `Name.css` pairs):
- `layout/` — `DashboardLayout` (authenticated-route page shell: Topbar + Sidebar +
  `<Outlet>`), `Sidebar` (mobile slide-in drawer), `Topbar` (desktop horizontal nav +
  account/admin dropdowns), plus `navItems.tsx` (shared nav-item source of truth, with
  its own test file).
- `patients/` — `PatientForm`.
- `reports/` — `ReportCard` (list-view summary card), `ReportViewer` (renders one report
  version using the org's template), `RequestChangesPanel` (the "ask AI to revise" form).
- `studies/` — `NewStudyForm`.
- `templates/` — `TemplateFieldsEditor`, `TemplateForm`, `TemplatePresetGallery`,
  `TemplatePreviewFrame` (live PDF preview + download button).
- `upload/` — `FileDropzone` (drag/drop or click-to-browse file picker with image preview).

## Non-obvious things

- **`components/common/` sits "below" `components/ui/` in the dependency graph, despite
  the folder split suggesting the opposite.** `ui/Table` imports `common/EmptyState`;
  feature components freely import from both `common/` and `ui/`. There's no rule that
  `common/` must stay leaf-level, but as of today nothing in `common/` imports from `ui/`
  or a feature folder — keep it that way when adding new common components.
- **`layout/navItems.tsx` is the single source of truth for navigation**, consumed by
  both `Sidebar` (mobile) and `Topbar` (desktop). Items are filtered by `roles` and
  grouped via an optional `group: 'admin'` flag (which routes them into the Topbar's
  "Admin" dropdown / Sidebar's "Admin" section instead of the inline row). The `SKIP_AUTH`
  dev flag makes `navItemsForRole` return every item when there's no logged-in user, so
  the nav still has something to show when browsing the app without a backend session.
- **Object URLs are created/revoked in a strict pattern — copy it, don't reinvent it.**
  `FileDropzone` (image preview), `useTemplatePreviewPdf` (PDF preview), and
  `TemplatePreviewFrame`'s download handler all call `URL.createObjectURL` and revoke the
  previous URL both on the next change and on unmount, so blob URLs never leak.
- **Report/template rendering is template-driven, not hardcoded.** `ReportViewer` pulls
  accent color, section order/titles, header text, and footer disclaimer from the
  report's `ReportTemplate` (falling back to a default only if no template object is
  attached) — two organizations can and do see completely different report layouts.
  Don't hardcode section names or ordering into a report/template component.
- **`TempPasswordBanner` exists because the app has no SMTP configured** (see
  `CONTRACTS.md`) — it's the *only* place a newly-issued temporary password is ever
  displayed (right after inviting a user, or a system_admin creating an org's first
  admin), which is why it leads with a "this is the only time you'll see this" warning
  rather than being a generic credentials display.
