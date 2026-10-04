import type { PlaybookStep } from '../api/events'

interface Props {
  step: PlaybookStep
  onAnswer: (answer: string) => void
}

export function PlaybookStepCard({ step, onAnswer }: Props) {
  return (
    <section aria-label="Playbook step">
      <h2>
        Step {step.order}: {step.title}
      </h2>
      <p>{step.instruction}</p>
      {step.expects === 'confirm' && <button onClick={() => onAnswer('confirm')}>Done</button>}
      {step.expects === 'choice' &&
        step.choices.map((choice) => (
          <button key={choice} onClick={() => onAnswer(choice)}>
            {choice.replace(/_/g, ' ')}
          </button>
        ))}
    </section>
  )
}
