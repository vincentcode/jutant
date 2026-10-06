import { CircleAlert, CircleCheck, LoaderCircle } from 'lucide-react'
import type { ToolActivityItem } from './useChatStream'
import { toolLine } from './wording'

const MARKS = {
  running: <LoaderCircle aria-hidden className="size-3.5 animate-spin" />,
  done: <CircleCheck aria-hidden className="size-3.5 text-accent" />,
  problem: <CircleAlert aria-hidden className="size-3.5" />,
}

/** What the assistant is looking up, in staff's words: "Checking the transfer TX-0002…". */
export function ToolActivity({ items }: { items: ToolActivityItem[] }) {
  if (items.length === 0) return null
  return (
    <ul aria-label="What the assistant checked" className="m-0 grid list-none gap-0.5 p-0 text-sm text-muted">
      {items.map((item) => {
        const { text, state } = toolLine(item)
        return (
          <li key={item.call.id} className={`flex items-center gap-1.5 ${state === 'problem' ? 'text-danger' : ''}`}>
            {MARKS[state]}
            {text}
          </li>
        )
      })}
    </ul>
  )
}
