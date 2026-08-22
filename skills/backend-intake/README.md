# backend-intake

One endpoint, `POST /intake/parse`, backing the frontend's chat-style study intake flow
(`ChatIntake`): turns one free-text physician message into structured patient/study fields,
merges them with whatever's already been confirmed earlier in the same conversation, and
reports what's still missing plus a follow-up question to ask. This is a newer domain —
stateless and persists nothing of its own; `AnalysisService`/`ReportService` never call into
it. See CONTRACTS.md §9 for the route list.

## Key files

- `server/app/api/intake/routes.py` — the one route. `require_admin_or_doctor()`, same RBAC
  as creating a patient/study directly. No `db` dependency at all — this domain touches no
  database table.
- `server/app/services/intake_service.py` — `parse_intake(payload)`: calls
  `get_report_provider().extract_intake(kind, message, known)`, merges the result into
  `known` (`{**known, **extracted}` — new extraction wins on overlap), computes
  `missingFields` from a required-fields list, and picks a canned follow-up question for the
  first missing field (or `None` if nothing's missing).
- `server/app/schemas/intake.py` — `IntakeParseRequest`: `kind` (`"patient"` or `"study"`),
  `message` (1-2000 chars), `known: dict[str, str]` (camelCase field name -> confirmed
  value, defaults to `{}`).

## Non-obvious things

- **Nothing here is persisted, and there's no session/conversation id.** The frontend is
  responsible for resending the full `known` dict with every message; the backend is a pure
  function of `(kind, message, known)` on each call. If you're debugging a "the bot forgot
  what I told it" report, the bug is almost certainly on the frontend's state management, not
  here.
- **`_REQUIRED_FIELDS` deliberately excludes `sex`** even though `PatientCreateRequest`
  requires it — `sex` always safely defaults to `"unspecified"` (matching `PatientForm`'s own
  convention), so the chat flow never bothers asking about it. If you add a new truly-required
  field to `PatientCreateRequest`/`StudyCreate`, you need to separately add it to
  `_REQUIRED_FIELDS`/`_FOLLOW_UP_QUESTIONS` here — nothing keeps them in sync automatically.
- **The mock AI provider doesn't return placeholder text for this one method.** Every other
  method on `MockProvider` returns clearly-labeled fake content (so nobody mistakes it for a
  real AI result), but `extract_intake` is the deliberate exception: it runs an actual
  regex/keyword heuristic (`app/ai/providers/mock_provider.py`) so the chat intake flow is
  genuinely clickable end-to-end in local dev/CI without an API key, even though it never
  claims to be AI-generated.
- `merged = {**payload.known, **extracted}` means a field the AI mis-extracts on a later
  message CAN overwrite a previously-confirmed value for that same field — there's no
  "don't touch what's already confirmed" protection here; that's a frontend/UX
  responsibility if it matters.
