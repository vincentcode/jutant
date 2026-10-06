import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import type { Feedback, FeedbackReason } from '../api/endpoints'

const REASONS: { id: FeedbackReason; label: string }[] = [
  { id: 'wrong_answer', label: 'Wrong answer' },
  { id: 'wrong_source', label: 'Wrong source' },
  { id: 'wrong_feature', label: 'Wrong kind of help' },
  { id: 'too_slow', label: 'Too slow' },
  { id: 'other', label: 'Other' },
]

const THUMB =
  'rounded-md border border-transparent p-1 text-muted hover:border-line hover:text-fg aria-pressed:border-accent aria-pressed:bg-accent-soft aria-pressed:text-accent disabled:opacity-50'

interface Props {
  feedback?: Feedback | null // the staff member's earlier rating, if any
  onRate: (feedback: Feedback) => Promise<void>
}

/** 👍 / 👎 under an answer. A thumbs-down is saved at once, then asks what was wrong. */
export function FeedbackBar({ feedback, onRate }: Props) {
  const [rating, setRating] = useState(feedback?.rating)
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState<FeedbackReason | undefined>(feedback?.reason ?? undefined)
  const [comment, setComment] = useState(feedback?.comment ?? '')
  const [state, setState] = useState<'idle' | 'saving' | 'thanks' | 'error'>('idle')

  async function save(next: Feedback, then: 'thanks' | 'idle' = 'thanks') {
    setState('saving')
    try {
      await onRate(next)
      setRating(next.rating)
      setState(then)
    } catch {
      setState('error')
    }
  }

  function thumbsDown() {
    setAsking(true)
    void save({ rating: 'down', reason: reason ?? null, comment }, 'idle')
  }

  async function sendDetails() {
    await save({ rating: 'down', reason: reason ?? null, comment: comment.trim() })
    setAsking(false)
  }

  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-1" role="group" aria-label="Rate this answer">
        <button
          type="button"
          className={THUMB}
          aria-label="Helpful"
          aria-pressed={rating === 'up'}
          disabled={state === 'saving'}
          onClick={() => {
            setAsking(false)
            void save({ rating: 'up', reason: null, comment: '' })
          }}
        >
          <ThumbsUp aria-hidden className="size-4" />
        </button>
        <button
          type="button"
          className={THUMB}
          aria-label="Not helpful"
          aria-pressed={rating === 'down'}
          disabled={state === 'saving'}
          onClick={thumbsDown}
        >
          <ThumbsDown aria-hidden className="size-4" />
        </button>
        {state === 'thanks' && (
          <span className="ml-1.5 text-sm text-muted">
            {rating === 'down' ? "Thanks, we'll look at this." : 'Thanks.'}
          </span>
        )}
        {state === 'error' && (
          <span role="alert" className="ml-1.5 text-sm text-danger">
            Couldn't save your rating. Try again.
          </span>
        )}
      </div>
      {asking && (
        <form
          className="grid gap-2 rounded-lg border border-line bg-bg p-2.5"
          onSubmit={(event) => {
            event.preventDefault()
            void sendDetails()
          }}
        >
          <fieldset className="m-0 flex flex-wrap gap-1.5 border-0 p-0">
            <legend className="mb-1.5 text-sm font-semibold">What was wrong?</legend>
            {REASONS.map((r) => (
              <label
                key={r.id}
                className="inline-flex cursor-pointer items-center gap-1 rounded-full border border-line px-2.5 py-0.5 text-sm has-checked:border-accent has-checked:bg-accent-soft"
              >
                <input
                  type="radio"
                  name="reason"
                  value={r.id}
                  checked={reason === r.id}
                  onChange={() => setReason(r.id)}
                  className="m-0"
                />
                {r.label}
              </label>
            ))}
          </fieldset>
          <textarea
            aria-label="Anything else (optional)"
            placeholder="Anything else? (optional)"
            rows={2}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="field w-full resize-y"
          />
          <div className="flex items-center gap-2.5">
            <button type="submit" className="btn" disabled={state === 'saving'}>
              Send
            </button>
            <button type="button" className="btn-link" onClick={() => setAsking(false)}>
              Close
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
