import type { ToolActivityItem } from './useChatStream'
import styles from './ToolActivity.module.css'

export function ToolActivity({ items }: { items: ToolActivityItem[] }) {
  if (items.length === 0) return null
  return (
    <ul aria-label="Tool activity" className={styles.list}>
      {items.map(({ call, result }) => (
        <li key={call.id}>
          {label(call.name)}: {result ? (result.ok ? 'done' : (result.error ?? 'failed').replace(/_/g, ' ')) : 'checking…'}
        </li>
      ))}
    </ul>
  )
}

/** `transactions.get_status` reads as "Transactions: get status". */
function label(name: string): string {
  const [server = '', tool = ''] = name.split('.')
  return `${server.charAt(0).toUpperCase()}${server.slice(1)}: ${tool.replace(/_/g, ' ')}`
}
