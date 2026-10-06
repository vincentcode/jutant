import { BookOpen, MessagesSquare, Plus, Search, Settings, type LucideIcon } from 'lucide-react'

export type PanelId = 'search' | 'conversations' | 'knowledge' | 'settings'

const ITEMS: { id: PanelId; label: string; icon: LucideIcon }[] = [
  { id: 'search', label: 'Search', icon: Search },
  { id: 'conversations', label: 'Conversations', icon: MessagesSquare },
  { id: 'knowledge', label: 'Knowledge', icon: BookOpen },
]

interface Props {
  open?: PanelId
  onToggle: (panel: PanelId) => void
  onNew: () => void
}

const ITEM =
  'flex size-10 items-center justify-center rounded-xl text-muted hover:bg-hover hover:text-fg aria-pressed:bg-accent-soft aria-pressed:text-accent'

/** The narrow rail on the left: a new conversation, and the panels that open beside it. */
export function IconRail({ open, onToggle, onNew }: Props) {
  return (
    <nav aria-label="Main" className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-bg py-3">
      <button type="button" className={ITEM} onClick={onNew} title="New conversation (Ctrl+Shift+O)" aria-label="New conversation">
        <Plus aria-hidden className="size-5" />
      </button>
      {ITEMS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          className={ITEM}
          aria-pressed={open === id}
          aria-label={label}
          title={label}
          onClick={() => onToggle(id)}
        >
          <Icon aria-hidden className="size-5" />
        </button>
      ))}
      <button
        type="button"
        className={`${ITEM} mt-auto`}
        aria-pressed={open === 'settings'}
        aria-label="Settings"
        title="Settings"
        onClick={() => onToggle('settings')}
      >
        <Settings aria-hidden className="size-5" />
      </button>
    </nav>
  )
}
