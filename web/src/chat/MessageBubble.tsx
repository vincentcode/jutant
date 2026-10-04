import type { ReactNode } from 'react'

interface Props {
  role: 'user' | 'assistant'
  text: string
  children?: ReactNode
}

export function MessageBubble({ role, text, children }: Props) {
  return (
    <article data-role={role}>
      <p>{text}</p>
      {children}
    </article>
  )
}
