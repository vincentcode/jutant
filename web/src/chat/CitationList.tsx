import { FileText } from 'lucide-react'
import type { Citation } from '../api/events'

/** The answer's source, first; the other sections a search returned behind "Also searched".
 * Search results come best first, so the first is the one most likely to have been used. */
export function CitationList({ citations }: { citations: Citation[] }) {
  const [main, ...others] = citations
  if (!main) return null
  return (
    <section aria-label="Sources" className="grid gap-1 border-t border-line pt-2 text-sm text-muted">
      <p className="m-0 flex items-start gap-1.5 text-fg">
        <FileText aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted" />
        <span>
          <span className="mr-1 font-semibold text-muted">Source</span> {describe(main)}
        </span>
      </p>
      {others.length > 0 && (
        <details>
          <summary className="w-fit cursor-pointer">Also searched ({others.length})</summary>
          <ul className="mt-1 list-disc pl-5">
            {others.map((c) => (
              <li key={`${c.kind}:${c.title}:${c.locator}`}>{describe(c)}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function describe(citation: Citation): string {
  return `${citation.title}, ${citation.locator}`
}
