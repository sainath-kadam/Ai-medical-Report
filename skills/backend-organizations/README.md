# backend-organizations

Reading and updating the current user's own organization record. See CONTRACTS.md §9
(route list).

## Key files

- `server/app/api/organizations/routes.py` — `GET /organizations/me` (any authenticated
  role) and `PATCH /organizations/me` (`org_admin` only). Both work off
  `current_user.organization_id`; there is no way for a client to target another org.
- `server/app/services/organization_service.py` — `get_by_id` / `update`; assumes the caller
  is already authorized (RBAC is enforced by the router) and just needs an `organization_id`
  plus the acting user's id for the audit trail.
- `server/app/repositories/organization_repository.py` — `update` (by row id) and
  `find_by_stripe_customer_id` (used by `billing_service.py`'s Stripe webhook handler to map
  a webhook event back to an org).
- `server/app/schemas/organization.py` — `OrganizationUpdateRequest`, a fully-optional
  partial-update body.

## Non-obvious things

- **An organization IS the tenant boundary, not a tenant-scoped resource.** Unlike every
  other domain, there's deliberately no list/create/delete here — only "read my org" /
  "update my org". `OrganizationRepository` therefore looks up and updates rows by their own
  `id` only (never filtered by an `organizationId` column), reusing `BaseRepository.insert`/
  `find_by_id` as-is and adding a plain (non-`_scoped`) `update`.
- **Both routes wrap the response as `{"organization": ...}`**, matching the sibling
  `GET /auth/me` shape (`{user, organization}`) that the frontend's `organization.api.ts`
  already assumes (`.then((r) => r.data.data.organization)`). Don't flatten this wrapper —
  it's intentional API-shape parity, not leftover cruft.
- **`PATCH` is a true partial update**: the router calls
  `body.model_dump(by_alias=True, exclude_unset=True)` so fields the client omits are left
  untouched rather than overwritten with `null`. `OrganizationService.update` still validates
  the org exists (and no-ops back to `get_by_id`) even when the resulting update dict is
  empty, rather than silently doing nothing.
- Audit log metadata for `ORGANIZATION_UPDATED` records only the *field names* changed
  (`sorted(update.keys())`), never the new values — org branding/contact fields are
  PHI-adjacent enough that even audit logs shouldn't carry their content (spec §30/§31).
