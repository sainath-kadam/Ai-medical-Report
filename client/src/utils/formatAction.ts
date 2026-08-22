/** Audit-log `action` values are SCREAMING_SNAKE_CASE enum constants (e.g.
 * `AI_ANALYSIS_COMPLETED`) — this turns one into a readable label. Used by both the
 * Dashboard's "Recent activity" widget and the full Audit Logs page, which previously
 * formatted this inconsistently (one lowercased-then-CSS-capitalized it, producing "Ai
 * Analysis Completed"; the other showed the raw enum unformatted).
 */
const ALL_CAPS_WORDS = new Set(['ai']);

export function humanizeAction(action: string): string {
  return action
    .split('_')
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase();
      if (ALL_CAPS_WORDS.has(lower)) return lower.toUpperCase();
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(' ');
}
