import type { ReactNode } from 'react'
import styles from './MessageBubble.module.css'

interface Props {
  role: 'user' | 'assistant'
  text: string
  pending?: boolean
  children?: ReactNode
}

export function MessageBubble({ role, text, pending, children }: Props) {
  return (
    <article className={`${styles.bubble} ${styles[role]}`} data-role={role} aria-busy={pending || undefined}>
      {text && <p className={styles.text}>{text}</p>}
      {children}
    </article>
  )
}
