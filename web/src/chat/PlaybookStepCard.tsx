import type { PlaybookStep } from '../api/events'
import styles from './PlaybookStepCard.module.css'

interface Props {
  step: PlaybookStep
  onAnswer: (answer: string) => void
}

export function PlaybookStepCard({ step, onAnswer }: Props) {
  return (
    <section aria-label="Procedure step" className={styles.card}>
      <h2>
        Step {step.order}: {step.title}
      </h2>
      <p>{step.instruction}</p>
      <div className={styles.actions}>
        {step.expects === 'confirm' && <button onClick={() => onAnswer('done')}>Done</button>}
        {step.expects === 'choice' &&
          step.choices.map((choice) => (
            <button key={choice} onClick={() => onAnswer(choice)}>
              {choice.replace(/_/g, ' ')}
            </button>
          ))}
        {step.expects === 'text' && <span className={styles.hint}>Type your answer below.</span>}
        {step.expects !== 'none' && (
          <button className="link" onClick={() => onAnswer('cancel')}>
            Stop procedure
          </button>
        )}
      </div>
    </section>
  )
}
