import type { Feature } from '../api/endpoints'
import styles from './FeatureChips.module.css'

interface Props {
  features: Feature[]
  selected?: string
  onSelect: (featureId: string | undefined) => void
}

/** Picking a feature sends it with the question and skips automatic routing. */
export function FeatureChips({ features, selected, onSelect }: Props) {
  if (features.length === 0) return null
  return (
    <div role="group" aria-label="Features" className={styles.chips}>
      <button aria-pressed={selected === undefined} onClick={() => onSelect(undefined)}>
        Automatic
      </button>
      {features.map((f) => (
        <button key={f.id} aria-pressed={selected === f.id} title={f.description} onClick={() => onSelect(f.id)}>
          {f.title}
        </button>
      ))}
    </div>
  )
}
