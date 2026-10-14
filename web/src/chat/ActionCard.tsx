import { useState } from 'react'
import { CircleCheck, CircleX, Send, TriangleAlert } from 'lucide-react'
import type { Proposal } from '../api/events'

interface Props {
  proposal: Proposal
  onSend: () => Promise<void>
  onChange: () => Promise<void>
  onCancel: () => Promise<void>
  now?: number // for tests
}

const HEADING: Record<Proposal['status'], string> = {
  proposed: 'not sent yet',
  sending: 'sending…',
  sent: 'sent',
  failed: 'not sent',
  cancelled: 'cancelled',
  expired: 'not sent: it waited too long',
}

/** A request the assistant proposed. Nothing is sent until staff press Send; the server sends
 * exactly what the card shows. Once decided, the card stays as a record of what happened. */
export function ActionCard({ proposal, onSend, onChange, onCancel, now = Date.now() }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const expired = proposal.status === 'proposed' && Date.parse(proposal.expires_at) <= now
  const status = expired ? 'expired' : proposal.status
  const open = status === 'proposed'
  const sent = status === 'sent'

  async function act(run: () => Promise<void>) {
    setBusy(true)
    setError(undefined)
    try {
      await run()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That did not work. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section
      aria-label={`${proposal.title}: ${HEADING[status]}`}
      className={`max-w-[min(720px,92%)] self-start rounded-xl border px-4 py-3 ${
        open ? 'border-accent bg-accent-soft' : 'border-line bg-surface'
      }`}
    >
      <p className="m-0 mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted">
        {sent ? (
          <CircleCheck aria-hidden className="size-3.5 text-accent" />
        ) : open ? (
          <Send aria-hidden className="size-3.5" />
        ) : (
          <CircleX aria-hidden className="size-3.5" />
        )}
        {proposal.title} · {HEADING[status]}
      </p>
      {sent && proposal.reference && (
        <p className="m-0 mb-1 font-semibold">
          {proposal.reference}
          {proposal.outcome && <span className="font-normal text-muted"> · {proposal.outcome}</span>}
        </p>
      )}
      {proposal.summary && <h2 className="m-0 mb-1.5 text-base font-semibold">{proposal.summary}</h2>}
      {proposal.fields.length > 0 && (
        <dl className="m-0 mb-2 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5">
          {proposal.fields.map((f) => (
            <div key={f.label} className="contents">
              <dt className="text-muted">{f.label}</dt>
              <dd className="m-0">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {open &&
        proposal.notes.map((note) => (
          <p key={note} className="m-0 mb-1 text-sm">
            {note}
          </p>
        ))}
      {open &&
        proposal.warnings.map((warning) => (
          <p key={warning} className="m-0 mb-1 flex items-start gap-1.5 text-sm">
            <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0 text-danger" />
            {warning}
          </p>
        ))}
      {!sent && proposal.outcome && (
        <p role="status" className="m-0 mb-1 text-sm">
          {proposal.outcome}
        </p>
      )}
      {error && (
        <p role="alert" className="m-0 mb-1 rounded border-l-[3px] border-danger bg-danger-soft px-2 py-1 text-sm">
          {error}
        </p>
      )}
      {open && (
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <button type="button" className="btn" disabled={busy} onClick={() => void act(onSend)}>
            <Send aria-hidden className="size-4" />
            Send request
          </button>
          <button type="button" className="btn-link" disabled={busy} onClick={() => void act(onChange)}>
            Change
          </button>
          <button type="button" className="btn-link" disabled={busy} onClick={() => void act(onCancel)}>
            Cancel
          </button>
        </div>
      )}
      {open && (
        <p className="m-0 mt-2 text-xs text-muted">
          Not sent until you press Send. Expires at{' '}
          {new Date(proposal.expires_at).toLocaleTimeString([], { timeStyle: 'short' })}.
        </p>
      )}
    </section>
  )
}
