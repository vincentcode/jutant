import type { ReactNode } from 'react'
import { Markdown } from './Markdown'

interface Props {
  role: 'user' | 'assistant'
  text: string
  pending?: boolean
  at?: string // when it was sent, shown on hover
  children?: ReactNode
}

const LOOK = {
  user: 'self-end bg-accent text-on-accent',
  assistant: 'self-start border border-line bg-surface',
}

/** Staff's own words are shown as typed; the assistant's are rendered as formatted text. */
export function MessageBubble({ role, text, pending, at, children }: Props) {
  return (
    <article
      className={`grid max-w-[min(720px,92%)] gap-2 rounded-xl px-3.5 py-2.5 ${LOOK[role]}`}
      data-role={role}
      aria-busy={pending || undefined}
      title={at ? new Date(at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : undefined}
    >
      {text &&
        (role === 'assistant' ? (
          <Markdown text={text} />
        ) : (
          <p className="m-0 whitespace-pre-wrap break-words">{text}</p>
        ))}
      {children}
    </article>
  )
}
