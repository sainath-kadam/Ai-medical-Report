# frontend-styles

The design-token system every component CSS file draws from, plus the global reset.
Two files, both short.

## Key files

- `client/src/styles/variables.css` — all design tokens on `:root`: brand colors,
  surfaces, text, status colors, elevation shadows, an overlay scrim, radii, an 8px-based
  spacing scale, font stacks, and layout constants (topbar height, sidebar width, content
  max-width). A `[data-theme='dark']` block redefines the color/shadow tokens (not
  spacing/radius/fonts/layout) for dark mode — toggled by `ThemeContext` setting
  `data-theme` on `<html>` (see `frontend-context` skill).
- `client/src/styles/base.css` — global reset (`box-sizing: border-box` everywhere),
  base element styles (body font/background/color from tokens), a visible
  `:focus-visible` ring, and scrollbar styling. Deliberately minimal — component files
  own their own presentation.

## Non-obvious things

- **The file's own header comment states the rule: no component should hard-code a hex
  color or pixel radius — always read from a `--color-*`/`--radius-*` variable.** This
  isn't just style guidance; violating it silently breaks dark mode, because tokens
  *flip* between themes rather than just getting darker. Two real bugs from doing this
  are still visible in the codebase's history:
  - `--color-text-muted` (used widely for hints/labels/timestamps) used to be a light
    gray with only ~2.6:1 contrast against `--color-bg` in light mode — well under WCAG
    AA's 4.5:1 for body text. It's now `#5b6b80`.
  - `components/common/Button/Button.css`'s `.btn--secondary` used to hardcode `color:
    white` against `background: var(--color-accent)`. That looked fine in light mode
    (accent is a mid-tone blue) but broke in dark mode, where `--color-accent` flips to a
    *bright* light-blue (`#6d9bff`) — white-on-bright-blue has poor contrast. It's now
    `color: var(--color-text-on-primary)`, which itself flips appropriately (white in
    light mode, a dark near-black in dark mode) instead of being pinned to one literal
    value.
  Treat any new hardcoded color in component CSS as a likely dark-mode bug, not just a
  style nit.
- **`--color-overlay` (the Modal/Sidebar backdrop scrim) is the one color token that does
  NOT flip between themes** — it's the same fixed `rgba(15, 23, 32, 0.5)` in both, by
  design: it's a dimming scrim over content, not a themed surface, so it should look the
  same regardless of theme.
- Dark mode is a real clinical feature here, not decoration — radiology reading rooms are
  often kept dim, so keeping report text legible without a glaring white panel matters
  (see the comment above the `[data-theme='dark']` block).
