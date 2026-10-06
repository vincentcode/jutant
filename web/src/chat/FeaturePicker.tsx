import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { ChevronDown } from 'lucide-react'
import type { Feature } from '../api/endpoints'

interface Props {
  features: Feature[]
  selected?: string
  onSelect: (featureId: string | undefined) => void
  label?: string // the button's text; by default "Ask about: <the choice>"
  pressed?: boolean // shown as chosen, when the choice is one this menu holds
}

const AUTOMATIC = {
  title: 'Automatic',
  description: 'The assistant picks the right kind of help for your question.',
}

/** Every kind of help, grouped. Picking one sends it with the question and skips automatic
 * routing. Opens upwards, from the question box. */
export function FeaturePicker({ features, selected, onSelect, label, pressed }: Props) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const current = features.find((f) => f.id === selected)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    root.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus()
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (features.length === 0) return null

  function choose(featureId: string | undefined) {
    onSelect(featureId)
    setOpen(false)
    button.current?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...(root.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])]
    const at = items.indexOf(document.activeElement as HTMLElement)
    if (event.key === 'Escape') {
      setOpen(false)
      button.current?.focus()
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      items[(at + step + items.length) % items.length]?.focus()
    }
  }

  return (
    <div className="relative w-fit" ref={root} onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        className={`chip ${pressed ? 'chip-on' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {label ?? (
          <>
            <span className="text-muted">Ask about:</span> {current?.title ?? AUTOMATIC.title}
          </>
        )}
        <ChevronDown aria-hidden className="size-3.5" />
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Kind of help"
          className="absolute bottom-[calc(100%+6px)] right-0 z-20 grid max-h-[min(60vh,460px)] w-[min(380px,calc(100vw-32px))] overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-lg"
        >
          <Item feature={AUTOMATIC} checked={!current} onChoose={() => choose(undefined)} />
          {groupBy(features).map(([group, members]) => (
            <div key={group} role="group" aria-label={group}>
              <p aria-hidden="true" className="mx-2 mb-0.5 mt-2 text-xs font-semibold uppercase tracking-wide text-muted">
                {group}
              </p>
              {members.map((f) => (
                <Item key={f.id} feature={f} checked={f.id === selected} onChoose={() => choose(f.id)} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Item({
  feature,
  checked,
  onChoose,
}: {
  feature: { title: string; description: string }
  checked: boolean
  onChoose: () => void
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      onClick={onChoose}
      className="grid w-full gap-px rounded-lg px-2.5 py-1.5 text-left hover:bg-hover focus-visible:bg-hover aria-checked:bg-accent-soft"
    >
      <span className="text-sm font-semibold">{feature.title}</span>
      <span className="text-xs text-muted">{feature.description}</span>
    </button>
  )
}

function groupBy(features: Feature[]): [string, Feature[]][] {
  const groups = new Map<string, Feature[]>()
  for (const f of features) {
    const group = f.group || 'Other'
    groups.set(group, [...(groups.get(group) ?? []), f])
  }
  return [...groups.entries()]
}
