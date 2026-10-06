import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteConversation, renameConversation, searchConversations, type Conversation } from '../api/endpoints'
import { MoreHorizontal } from 'lucide-react'

/** Staff's conversations, latest first: search them, open one, rename or delete it. */
export function ConversationList({
  activeId,
  focusSearch = false,
  limit,
}: {
  activeId?: string
  focusSearch?: boolean // opened to search: the cursor starts in the search box
  limit?: number // show only the latest few, without search (the home screen)
}) {
  const [typed, setTyped] = useState('')
  const search = useDebounced(typed.trim(), 300)
  const { data, isLoading } = useQuery({
    queryKey: ['conversations', search],
    queryFn: () => searchConversations(search),
  })
  const shown = limit ? data?.slice(0, limit) : data

  return (
    <nav aria-label={limit ? 'Recent conversations' : 'Conversations'} className="grid gap-2">
      {!limit && (
        <input
          type="search"
          aria-label="Search conversations"
          placeholder="Search conversations"
          value={typed}
          autoFocus={focusSearch}
          onChange={(e) => setTyped(e.target.value)}
          className="field w-full py-1.5 text-sm"
        />
      )}
      {isLoading && <p className="px-2 text-sm text-muted">Loading…</p>}
      {shown?.length === 0 && (
        <p className="px-2 text-sm text-muted">{search ? `Nothing matches “${search}”.` : 'No conversations yet.'}</p>
      )}
      <ul className="m-0 grid list-none gap-0.5 p-0">
        {shown?.map((c) => (
          <ConversationItem key={c.id} conversation={c} active={c.id === activeId} />
        ))}
      </ul>
    </nav>
  )
}

function ConversationItem({ conversation, active }: { conversation: Conversation; active: boolean }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'view' | 'menu' | 'rename' | 'confirm'>('view')
  const [title, setTitle] = useState(conversation.title)
  const [problem, setProblem] = useState<string | null>(null)
  const name = conversation.title || 'New conversation'

  async function rename(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    try {
      await renameConversation(conversation.id, title.trim())
      await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      setMode('view')
    } catch {
      setProblem("Couldn't rename it. Try again.")
    }
  }

  async function remove() {
    try {
      await deleteConversation(conversation.id)
      await queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (active) navigate('/chat')
    } catch {
      setProblem("Couldn't delete it. Try again.")
      setMode('view')
    }
  }

  if (mode === 'rename') {
    return (
      <li>
        <form className="flex items-center gap-1.5 px-1.5 py-1" onSubmit={(e) => void rename(e)}>
          <input
            aria-label="Conversation name"
            value={title}
            maxLength={120}
            autoFocus
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && setMode('view')}
            className="field min-w-0 flex-1 px-2 py-1 text-sm"
          />
          <button type="submit" className="btn px-2.5 py-1 text-sm">
            Save
          </button>
          <button type="button" className="btn-link text-sm" onClick={() => setMode('view')}>
            Cancel
          </button>
        </form>
        {problem && (
          <p role="alert" className="mx-2.5 text-xs text-danger">
            {problem}
          </p>
        )}
      </li>
    )
  }

  return (
    <li className="group relative">
      <Link
        to={`/chat/${conversation.id}`}
        className={`grid gap-0.5 rounded-lg px-2.5 py-2 pr-9 text-fg no-underline hover:bg-hover ${active ? 'bg-accent-soft' : ''}`}
      >
        <span className="truncate text-sm">{name}</span>
        <time dateTime={conversation.updated_at} className="text-xs text-muted">
          {when(conversation.updated_at)}
        </time>
      </Link>
      {mode === 'confirm' ? (
        <div className="flex flex-wrap items-center gap-2 px-2.5 pb-2 pt-1 text-sm" role="group" aria-label={`Delete ${name}?`}>
          <span>Delete this conversation?</span>
          <button
            type="button"
            className="rounded-md bg-danger px-2.5 py-0.5 text-white"
            onClick={() => void remove()}
          >
            Delete
          </button>
          <button type="button" className="btn-link" onClick={() => setMode('view')}>
            Keep
          </button>
        </div>
      ) : (
        <div className="absolute right-1.5 top-1.5">
          <button
            type="button"
            className="rounded-md p-1 text-muted opacity-0 hover:bg-hover focus-visible:opacity-100 group-hover:opacity-100 aria-expanded:opacity-100 [@media(hover:none)]:opacity-100"
            aria-label={`Options for ${name}`}
            aria-expanded={mode === 'menu'}
            onClick={() => setMode(mode === 'menu' ? 'view' : 'menu')}
          >
            <MoreHorizontal aria-hidden className="size-4" />
          </button>
          {mode === 'menu' && (
            <div className="absolute right-0 z-10 grid gap-1.5 rounded-lg border border-line bg-surface px-3 py-2 shadow-lg">
              <button type="button" className="btn-link text-sm" onClick={() => setMode('rename')}>
                Rename
              </button>
              <button type="button" className="btn-link text-sm" onClick={() => setMode('confirm')}>
                Delete
              </button>
            </div>
          )}
        </div>
      )}
      {problem && (
        <p role="alert" className="mx-2.5 text-xs text-danger">
          {problem}
        </p>
      )}
    </li>
  )
}

function useDebounced(value: string, ms: number): string {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

function when(iso: string): string {
  const date = new Date(iso)
  const today = new Date().toDateString() === date.toDateString()
  return today
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString([], { day: 'numeric', month: 'short' })
}
