import { ListChecks } from 'lucide-react'
import type { ShownStep } from '../api/events'
import { stepHeading } from './steps'

interface Props {
  shown: ShownStep
  onAnswer: (answer: string) => void
}

/** The step waiting for staff: what to do, and a button for each answer it takes. */
export function PlaybookStepCard({ shown, onAnswer }: Props) {
  const { step } = shown
  return (
    <section
      aria-label="Procedure step"
      className="max-w-[min(720px,92%)] self-start rounded-xl border border-accent bg-accent-soft px-4 py-3"
    >
      <p className="m-0 mb-0.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted">
        <ListChecks aria-hidden className="size-3.5" />
        {stepHeading(shown)}
      </p>
      <h2 className="m-0 mb-1.5 text-base font-semibold">{step.title}</h2>
      <p className="m-0 mb-2.5">{step.instruction}</p>
      <div className="flex flex-wrap items-center gap-2">
        {step.expects === 'confirm' && (
          <button type="button" className="btn" onClick={() => onAnswer('done')}>
            Done
          </button>
        )}
        {step.expects === 'choice' &&
          step.choices.map((choice) => (
            <button key={choice} type="button" className="btn capitalize" onClick={() => onAnswer(choice)}>
              {choice.replace(/_/g, ' ')}
            </button>
          ))}
        {step.expects === 'text' && <span className="text-sm text-muted">Type your answer below.</span>}
        <button type="button" className="btn-link" onClick={() => onAnswer('cancel')}>
          Stop procedure
        </button>
      </div>
    </section>
  )
}

/** A step already passed: one line, with what answered it; the instruction on demand. */
export function PlaybookStepLine({ shown }: { shown: ShownStep }) {
  const { step } = shown
  const line = 'm-0 max-w-[min(720px,92%)] self-start border-l-[3px] border-line px-2.5 py-1 text-sm text-muted'
  if (step.expects === 'none') {
    return (
      <p className={line}>
        <span className="text-fg">
          {stepHeading(shown)} · {step.title}
        </span>{' '}
        {step.instruction}
      </p>
    )
  }
  return (
    <details className={line}>
      <summary className="cursor-pointer">
        <span className="text-fg">
          {stepHeading(shown)} · {step.title}
        </span>
        {shown.answered && (
          <span className="font-semibold text-fg"> {shown.answered.replace(/_/g, ' ')} (from the record)</span>
        )}
      </summary>
      <p className="mt-1">{step.instruction}</p>
    </details>
  )
}
