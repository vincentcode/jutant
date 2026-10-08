import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, FileText, Square, X } from 'lucide-react'
import type { Upload } from '../api/endpoints'
import { UploadButton } from './UploadButton'

interface Props {
  busy: boolean
  attachment?: Upload
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (file: File) => Promise<void>
  onDetach: () => void
  placeholder?: string
}

/** The question box: the question, an attachment, and Send (or Stop while an answer is
 * coming). Staff do not pick a kind of help here: the assistant works it out, and asks when it
 * cannot tell. */
export function Composer({
  busy,
  attachment,
  onSend,
  onStop,
  onAttach,
  onDetach,
  placeholder = 'Ask anything about customers, payments or policies…',
}: Props) {
  const [text, setText] = useState('')

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
    </form>
  )
}
