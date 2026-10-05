import { useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Upload } from '../api/endpoints'
import { UploadButton } from './UploadButton'
import styles from './Composer.module.css'

interface Props {
  busy: boolean
  attachment?: Upload
  onSend: (text: string) => void
  onStop: () => void
  onAttach: (file: File) => Promise<void>
  onDetach: () => void
}

export function Composer({ busy, attachment, onSend, onStop, onAttach, onDetach }: Props) {
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
    <form className={styles.composer} onSubmit={submit}>
      {attachment && (
        <div className={styles.attachment}>
          <span>
            📎 {attachment.filename} ({attachment.characters.toLocaleString()} characters read)
          </span>
          <button type="button" className="link" onClick={onDetach} aria-label="Remove attachment">
            Remove
          </button>
        </div>
      )}
      <div className={styles.row}>
        <UploadButton disabled={busy} onFile={onAttach} />
        <textarea
          aria-label="Ask a question"
          placeholder="Ask a question…"
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={4000}
        />
        {busy ? (
          <button type="button" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={!text.trim()}>
            Ask
          </button>
        )}
      </div>
    </form>
  )
}
