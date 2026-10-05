import type { Citation } from '../api/events'
import styles from './CitationList.module.css'

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null
  return (
    <div className={styles.sources}>
      <span>Sources</span>
      <ul aria-label="Sources">
        {citations.map((c) => (
          <li key={`${c.kind}:${c.title}:${c.locator}`}>
            {c.title}, {c.locator}
          </li>
        ))}
      </ul>
    </div>
  )
}
