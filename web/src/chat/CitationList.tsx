import type { Citation } from '../api/events'

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null
  return (
    <ul aria-label="Sources">
      {citations.map((c) => (
        <li key={`${c.kind}:${c.title}:${c.locator}`}>
          {c.title}, {c.locator}
        </li>
      ))}
    </ul>
  )
}
