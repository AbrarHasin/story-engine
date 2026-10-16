/**
 * Normalise agent bullets for display.
 *
 * The backend sends a list of strings, but older stories (and replies cut off
 * at the token cap) can carry the model's raw JSON array as one bullet, e.g.
 * '["Fact one", "Fact two", "Fact thr'. Expand those into their complete items.
 */
const JSON_STRING = /"(?:[^"\\]|\\.)*"/g

function expandJsonArray(text: string): string[] | null {
  const body = text.trim()
  if (!body.startsWith('[')) return null
  try {
    const parsed: unknown = JSON.parse(body)
    if (Array.isArray(parsed)) return parsed.map(String)
  } catch {
    // unterminated array: keep its complete string items below
  }
  const items: string[] = []
  for (const m of body.matchAll(JSON_STRING)) {
    try {
      items.push(String(JSON.parse(m[0])))
    } catch {
      // skip a malformed item
    }
  }
  return items.length ? items : null
}

export function normalizeBullets(bullets: readonly string[]): string[] {
  return bullets
    .flatMap(b => expandJsonArray(b) ?? [b])
    .map(b => b.trim())
    .filter(Boolean)
}

/** Bullets stored in the DB as newline-joined text. */
export function bulletsFromText(content: string): string[] {
  return normalizeBullets(content.split('\n'))
}
