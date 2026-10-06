import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, FileText, Square, X } from 'lucide-react'
import type { Feature, QuickAction, Upload } from '../api/endpoints'
import { FeaturePicker } from './FeaturePicker'
import { UploadButton } from './UploadButton'

interface Props {
  busy: boolean
  attachment?: Upload
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (file: File) => Promise<void>
  onDetach: () => void
  features?: Feature[] // every kind of help, for "More"
  quickActions?: QuickAction[] // the pack's chips in the box
  selected?: string
  onSelect?: (featureId: string | undefined) => void
  placeholder?: string
}

/** The question box: the question, an attachment, Send (or Stop while an answer is coming),
 * and the quick actions that pick a kind of help. */
export function Composer({
  busy,
  attachment,
  onSend,
  onStop,
  onAttach,
  onDetach,
  features = [],
  quickActions = [],
  selected,
  onSelect,
  placeholder = 'Ask anything about customers, payments or policies…',
}: Props) {
  const [text, setText] = useState('')
  const quick = new Set(quickActions.map((a) => a.feature_id))
  const other = features.find((f) => f.id === selected && !quick.has(f.id))

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (busy || !text.trim()) return
    onSend(text.trim())
    setText('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      className="grid gap-2 rounded-2xl border border-line bg-surface p-2.5 shadow-sm focus-within:border-accent"
      onSubmit={submit}
    >
      {attachment && (
        <div className="flex items-center gap-2 rounded-lg bg-hover px-2.5 py-1.5 text-sm text-muted">
          <FileText aria-hidden className="size-4 shrink-0" />
          <span className="min-w-0 flex-1">
            {attachment.filename} ({attachment.characters.toLocaleString()} characters read
            {attachment.note ? `; ${attachment.note}` : ''})
          </span>
          <button
            type="button"
            className="rounded p-0.5 hover:bg-surface"
            onClick={onDetach}
            aria-label="Remove attachment"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>
      )}
      <div className="flex items-end gap-1.5">
        <UploadButton disabled={busy} onFile={onAttach} />
        <textarea
          id="question"
          aria-label="Ask a question"
          placeholder={placeholder}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={4000}
          className="max-h-40 min-h-10 flex-1 resize-none border-0 bg-transparent px-1 py-2 outline-none focus-visible:outline-none"
        />
        {busy ? (
          <button type="button" className="btn rounded-full p-2" onClick={onStop} aria-label="Stop">
            <Square aria-hidden className="size-4 fill-current" />
          </button>
        ) : (
          <button type="submit" className="btn rounded-full p-2" disabled={!text.trim()} aria-label="Ask">
            <ArrowUp aria-hidden className="size-4" />
          </button>
        )}
      </div>
      {onSelect && features.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-2" role="group" aria-label="Quick actions">
          <span className="text-xs text-muted">Quick actions:</span>
          <button type="button" className="chip" aria-pressed={selected === undefined} onClick={() => onSelect(undefined)}>
            Automatic
          </button>
          {quickActions.map((a) => (
            <button
              key={a.feature_id}
              type="button"
              className="chip"
              aria-pressed={selected === a.feature_id}
              onClick={() => onSelect(selected === a.feature_id ? undefined : a.feature_id)}
            >
              {a.label}
            </button>
          ))}
          <FeaturePicker
            features={features}
            selected={selected}
            onSelect={onSelect}
            label={other?.title ?? 'More'}
            pressed={other !== undefined}
          />
        </div>
      )}
    </form>
  )
}
