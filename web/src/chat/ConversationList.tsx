export function ConversationList({ activeId }: { activeId?: string }) {
  // TODO: GET /api/conversations with TanStack Query.
  return (
    <nav aria-label="Conversations">
      <p>{activeId ? 'Conversation open' : 'No conversation selected'}</p>
    </nav>
  )
}
