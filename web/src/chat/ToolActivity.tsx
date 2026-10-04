import type { ToolActivityItem } from './useChatStream'

export function ToolActivity({ items }: { items: ToolActivityItem[] }) {
  if (items.length === 0) return null
  return (
    <ul aria-label="Tool activity">
      {items.map(({ call, result }) => (
        <li key={call.id}>
          {call.name}: {result ? (result.ok ? 'done' : result.error) : 'running'}
        </li>
      ))}
    </ul>
  )
}
