# backend-notifications

In-app notifications for a user (report finalized, permission changed, etc.): create, list
(paginated), mark one read, mark all read. CONTRACTS.md §4, §8, §11, §12.

## Key files

- `server/app/services/notification_service.py` — `NotificationService`: `create`,
  `list_for_user`, `mark_read`, `mark_all_read`.
- `server/app/repositories/notification_repository.py` — plain `BaseRepository` subclass
  for the `notifications` table, plus the two hand-rolled mutations `mark_read`/
  `mark_all_read`.
- `server/app/api/notifications/routes.py` — `GET /notifications`, `PATCH /notifications/
  {id}/read`, `PATCH /notifications/read-all`.

## Non-obvious things

- **Email/SMS delivery is intentionally not implemented.** `NotificationService.create`
  writes the row and then only does `logger.info(...)` (logging ids/enums, never title/body
  text — spec §31) at a clearly marked "SEAM" comment. Every notification is in-app only,
  polled via `GET /notifications`; wiring a real provider (SES/SendGrid, Twilio) later means
  filling in that one call site, not restructuring this module.
- **`mark_read`/`mark_all_read` live in the repository, not built from
  `BaseRepository.update_scoped`**, because neither fits that helper: `mark_read` is
  conditional (a no-op if already read, `None` if the notification doesn't belong to
  `user_id`) and returns a single dict, while `mark_all_read` is a bulk `UPDATE` with no
  single row to return. `NotificationService` still never touches SQLAlchemy directly
  itself — it delegates to these two methods.
- **Every route is scoped to the current user within their own organization** — there is no
  way for a caller to read or mark another user's notifications, and no route ever accepts
  a client-supplied organization id or user id.
- **`notifications` has no `updatedAt` column**, so `BaseRepository.insert` (which only
  stamps `updatedAt` when the table has that column) is safe to call directly in `create`
  without special-casing, the same pattern used in `backend-audit-logs`.
