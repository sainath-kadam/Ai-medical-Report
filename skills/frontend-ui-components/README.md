# frontend-ui-components

Generic, domain-agnostic UI primitives — the kind of components that would look the same
in a completely different app. Distinct from `components/common/` (also generic, but
that folder predates this one and holds things like `Button`/`Card`/`TextField`) and
from the feature folders (`components/patients/`, `components/reports/`, etc.), which are
domain-specific.

## Inventory

- `Pagination/` — page-number strip with ellipsis collapsing for large page counts.
  Renders nothing (`return null`) when `totalPages <= 1`.
- `Select/` — styled `<select>` wrapper with `label`/`error`/`hint` and a custom chevron
  icon; forwards its ref like a native select.
- `Table/` — generic `Table<T>` driven by a `columns` array (`key`, `header`, optional
  `render`/`width`) and a `rowKey` extractor. Renders `EmptyState` (from
  `components/common/EmptyState`) when `rows` is empty, and makes rows keyboard-activatable
  (`Enter`/`Space`) whenever `onRowClick` is passed.
- `Tabs/` — a pure tab *strip*; it has no opinion on panel content. The caller owns which
  `activeKey` is selected and what renders below it.
- `Toast/` — `ToastProvider` + `useToast()`. Toasts are portaled to `document.body`,
  auto-dismiss after 4000ms, and come in `success`/`error`/`info` variants.

Each subfolder is `Name/Name.tsx` + colocated `Name.css` — no shared index/barrel file.

## Non-obvious things

- **`ToastProvider` must wrap the app once, near the root** (it's mounted in `main.tsx`
  alongside `AuthProvider`/`ThemeProvider`) — `useToast()` throws if called without an
  ancestor provider, same fail-fast pattern as `useAuth`/`useTheme`.
- **This folder depends on `components/common/`, not the other way around** — `Table`
  imports `EmptyState` from `../../common/EmptyState/EmptyState`. Don't assume `ui/` sits
  strictly "below" `common/` in the dependency graph just because of naming/folder order.
- `Select`/`TextField`(in `common/`)-style components derive `id` from `label` when no
  explicit `id` prop is given (`label.toLowerCase().replace(/\s+/g, '-')`) purely so
  `<label htmlFor>` has something to point at — pass an explicit `id` if two fields on the
  same page could ever share a label text.
