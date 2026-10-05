import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { conversations } from '../api/endpoints'
import styles from './ConversationList.module.css'

export function ConversationList({ activeId }: { activeId?: string }) {
  const { data, isLoading } = useQuery({ queryKey: ['conversations'], queryFn: conversations })

  return (
    <nav aria-label="Conversations" className={styles.list}>
      <Link to="/chat" className={styles.new}>
        + New conversation
      </Link>
      {isLoading && <p className={styles.empty}>Loading…</p>}
      {data?.length === 0 && <p className={styles.empty}>No conversations yet.</p>}
      <ul>
        {data?.map((c) => (
          <li key={c.id}>
            <Link to={`/chat/${c.id}`} className={c.id === activeId ? styles.active : undefined}>
              <span>{c.title || 'New conversation'}</span>
              <time dateTime={c.updated_at}>{when(c.updated_at)}</time>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function when(iso: string): string {
  const date = new Date(iso)
  const today = new Date().toDateString() === date.toDateString()
  return today
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString([], { day: 'numeric', month: 'short' })
}
