import { useState, type FormEvent } from 'react'
import { UploadButton } from './UploadButton'

interface Props {
  disabled?: boolean
  onSend: (text: string) => void
}

export function Composer({ disabled, onSend }: Props) {
  const [text, setText] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  return (
    <form onSubmit={submit}>
      <UploadButton onUploaded={() => {}} />
      <input
        aria-label="Ask a question"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
      />
      <button type="submit" disabled={disabled}>
        Ask
      </button>
    </form>
  )
}
