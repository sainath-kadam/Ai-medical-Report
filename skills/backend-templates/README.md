# backend-templates

Owns `report_templates`: an organization's branding (header/logo/accent color/footer
disclaimer) and the ordered list of sections an AI-generated report's body is structured
into. See CONTRACTS.md §4 (table shapes), §9 (route list), §12 (cross-domain entry point
used by signup).

## Key files

- `server/app/api/templates/routes.py` — list/get open to any authenticated org member;
  create/update/delete/logo-upload restricted to `org_admin`; `POST /preview-pdf` is open
  to any member (nothing is persisted, it just renders a sample PDF from a draft payload).
- `server/app/services/template_service.py` — CRUD, `upload_logo`, `render_preview_pdf`,
  and `ensure_default_template` (called once from the signup flow).
- `server/app/repositories/template_repository.py` — `BaseRepository` CRUD plus
  `get_default` and `unset_other_defaults`.
- `server/app/schemas/template.py` — request bodies (`TemplateCreate`/`TemplateUpdate`
  and their nested header/style/doctorInfo/section/footer schemas); responses are always
  plain dicts.

## Non-obvious things

- **`logoKey` is a storage key the client never gets to set freely.**
  `TemplateService._sanitize_logo_key` silently nulls out any `header.logoKey` that
  doesn't start with `template_logo/{organization_id}/` (the prefix this org's own
  `POST /templates/logo` endpoint issues) — without this check, any authenticated user
  could point a template at another org's (or another storage category's) key and have
  the server fetch and embed those bytes into a downloadable PDF. It fails silently
  (drops to `None`, doesn't raise) so a stale/tampered value never blocks a save.
- **Only one template per org can be `isDefault=true` at a time**, enforced by
  `TemplateRepository.unset_other_defaults`, called from both `create_template` (when
  `is_default=True`) and `update_template`. `delete_template` refuses to delete the
  current default (`CANNOT_DELETE_DEFAULT_TEMPLATE`) — you have to set another template
  as default first.
- `ensure_default_template` (called from the signup flow, not from this domain's own
  routes) MUST stay idempotent — it returns the org's existing default if one already
  exists rather than ever creating a second one. The seeded default deliberately does
  NOT include "impression"/"recommendations" as sections — those are dedicated top-level
  fields on `GeneratedContent` (`app/ai/base.py`), always rendered as their own blocks by
  both the frontend and `pdf_service.py`; adding them as sections too would duplicate
  that block in every rendered report.
- `render_preview_pdf` is stateless by design (unlike `get_pdf_bytes` in
  `backend-reports`, nothing here is cached) since it's rendering a still-being-edited
  draft payload that changes on every keystroke; it fabricates a sample
  patient/study/content via `_sample_report_data` since no real report exists yet.
