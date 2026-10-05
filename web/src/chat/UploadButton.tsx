import { useRef, useState } from 'react'
import { ApiError } from '../api/client'
import styles from './UploadButton.module.css'

interface Props {
  disabled?: boolean
  onFile: (file: File) => Promise<void>
}

const ACCEPT = '.pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff'

export function UploadButton({ disabled, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'uploading'>('idle')
  const [error, setError] = useState<string | null>(null)

  async function choose(file: File | undefined) {
    if (!file) return
    setError(null)
    setState('uploading')
    try {
      await onFile(file)
    } catch (err) {
      setError(err instanceof ApiError && typeof err.detail === 'string' ? err.detail : 'Upload failed.')
    } finally {
      setState('idle')
      if (input.current) input.current.value = ''
    }
  }

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        disabled={disabled || state === 'uploading'}
        onClick={() => input.current?.click()}
        aria-label="Attach a document"
        title="Attach a document (PDF, Word, text or photo)"
      >
        {state === 'uploading' ? '…' : '📎'}
      </button>
      <input ref={input} type="file" accept={ACCEPT} hidden onChange={(e) => void choose(e.target.files?.[0])} />
      {error && (
        <span role="alert" className={styles.error}>
          {error}
        </span>
      )}
    </span>
  )
}
