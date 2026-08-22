/** A doctor's `name` field commonly includes a title ("Dr. Ava Chen") since nothing
 * splits that out at signup/invite time. Naively taking `name.split(' ')[0]` or
 * `name.charAt(0)` then reads as "Dr." / "D" instead of the actual first name — this
 * strips a small set of common titles first so greetings and avatar initials use the
 * person's actual name.
 */
const TITLES = new Set(['dr', 'dr.', 'mr', 'mr.', 'mrs', 'mrs.', 'ms', 'ms.', 'prof', 'prof.', 'miss']);

function nameWithoutTitle(fullName: string): string[] {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length > 1 && TITLES.has(parts[0].toLowerCase())) {
    return parts.slice(1);
  }
  return parts;
}

export function getFirstName(fullName: string): string {
  const [first] = nameWithoutTitle(fullName);
  return first ?? fullName.trim();
}

export function getInitial(fullName: string | undefined | null): string {
  if (!fullName) return '?';
  const first = getFirstName(fullName);
  return first ? first.charAt(0).toUpperCase() : '?';
}
