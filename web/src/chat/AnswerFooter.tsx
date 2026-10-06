import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import type { Feedback, HistoryMessage } from '../api/endpoints'
import { FeedbackBar } from './FeedbackBar'

interface Props {
  message: HistoryMessage
  featureTitle?: string // the feature that answered, so a misroute shows
  onRate?: (feedback: Feedback) => Promise<void>
}

/** Under an answer: which kind of help answered it, Copy, and the rating. */
export function AnswerFooter({ message, featureTitle, onRate }: Props) {
  const [copied, setCopied] = useState<'idle' | 'done' | 'failed'>('idle')

  async function copy() {
    try {
      await navigator.clipboard.writeText(asPlainText(message))
      setCopied('done')
    } catch {
      setCopied('failed')
    }
    setTimeout(() => setCopied('idle'), 2000)
  }

  return (
    <div className="flex flex-wrap items-start gap-x-3 gap-y-1 text-xs text-muted">
      {featureTitle && <span className="pt-1.5">Answered by {featureTitle}</span>}
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-md border border-transparent px-2 py-1 hover:border-line hover:text-fg"
        onClick={() => void copy()}
      >
        {copied === 'done' ? <Check aria-hidden className="size-3.5" /> : <Copy aria-hidden className="size-3.5" />}
        {copied === 'done' ? 'Copied' : copied === 'failed' ? "Couldn't copy" : 'Copy'}
      </button>
      {onRate && (
        <div className="min-w-[220px] flex-1">
          <FeedbackBar feedback={message.feedback} onRate={onRate} />
        </div>
      )}
    </div>
  )
}

/** The answer as plain text with its sources, for pasting into a note or an email. */
export function asPlainText(message: HistoryMessage): string {
  const text = message.content
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/^\s*[-*] /gm, '• ')
    .trim()
  if (message.citations.length === 0) return text
  const sources = message.citations.map((c) => `- ${c.title}, ${c.locator}`).join('\n')
  return `${text}\n\nSources:\n${sources}`
}
