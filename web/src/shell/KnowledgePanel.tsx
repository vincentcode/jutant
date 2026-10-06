import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, Sparkles } from 'lucide-react'
import { documents, type LibraryDocument } from '../api/endpoints'

interface Props {
  onSummarise?: (doc: LibraryDocument) => void // absent if the role cannot summarise
}

/** The documents this staff member's role may read, grouped by type, with search. Opening one
 * asks the assistant to summarise it (which checks access again). */
export function KnowledgePanel({ onSummarise }: Props) {
  const [typed, setTyped] = useState('')
  const [search, setSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => setSearch(typed.trim()), 300)
    return () => clearTimeout(timer)
  }, [typed])
  const { data, isLoading } = useQuery({ queryKey: ['documents', search], queryFn: () => documents(search) })

  const groups = new Map<string, LibraryDocument[]>()
  for (const doc of data ?? []) groups.set(doc.doc_type, [...(groups.get(doc.doc_type) ?? []), doc])

  return (
    <div className="grid gap-3 p-3">
      <h2 className="px-1 text-sm font-semibold">Knowledge</h2>
      <input
        type="search"
        aria-label="Search documents"
        placeholder="Search documents"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        className="field w-full py-1.5 text-sm"
      />
      {isLoading && <p className="px-1 text-sm text-muted">Loading…</p>}
      {data?.length === 0 && (
        <p className="px-1 text-sm text-muted">{search ? `No document matches “${search}”.` : 'No documents yet.'}</p>
      )}
      {[...groups.entries()].map(([type, docs]) => (
        <section key={type} aria-label={plural(type)} className="grid gap-1">
          <h3 className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">{plural(type)}</h3>
          <ul className="grid gap-0.5">
            {docs.map((doc) => (
              <li key={doc.id} className="group flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-hover">
                <FileText aria-hidden className="size-4 shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate text-sm" title={doc.title}>
                  {doc.title}
                </span>
                {onSummarise && (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-accent hover:bg-accent-soft"
                    onClick={() => onSummarise(doc)}
                    aria-label={`Summarise ${doc.title}`}
                  >
                    <Sparkles aria-hidden className="size-3.5" />
                    Summarise
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function plural(type: string): string {
  const word = type.replace(/_/g, ' ')
  const label = word.endsWith('y') ? `${word.slice(0, -1)}ies` : `${word}s`
  return label.charAt(0).toUpperCase() + label.slice(1)
}
