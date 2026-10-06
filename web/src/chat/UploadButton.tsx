import { useRef, useState } from 'react'
import { LoaderCircle, Paperclip } from 'lucide-react'
import { ApiError } from '../api/client'

interface Props {
  disabled?: boolean
  onFile: (file: File) => Promise<void>
}

const ACCEPT = '.pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff'

/** Attach a document or a photo; says which file is being read, and why one could not be. */
export function UploadButton({ disabled, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [reading, setReading] = useState<string | null>(null) // the file being read
  const [error, setError] = useState<string | null>(null)

  async function choose(file: File | undefined) {
    if (!file) return
    setError(null)
    setReading(file.name)
    try {
      await onFile(file)
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === 'string' ? err.detail : 'Upload failed.')
    } finally {
      setReading(null)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <span className="relative inline-flex items-center">
      <button
        type="button"
        className="rounded-lg p-2 text-muted hover:bg-hover hover:text-fg disabled:opacity-50"
        disabled={disabled || reading !== null}
        onClick={() => input.current?.click()}
        aria-label="Attach a document"
        title="Attach a document (PDF, Word, text or photo)"
      >
        {reading ? <LoaderCircle aria-hidden className="size-5 animate-spin" /> : <Paperclip aria-hidden className="size-5" />}
      </button>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => void choose(e.target.files?.[0])} />
      {(reading || error) && (
        <span
          role={error ? 'alert' : 'status'}
          className={`absolute bottom-full left-0 mb-1 whitespace-nowrap rounded-md bg-surface px-2 py-1 text-sm shadow ${error ? 'text-danger' : 'text-muted'}`}
        >
          {error ?? `Reading ${reading}…`}
        </span>
      )}
    </span>
  )
}
