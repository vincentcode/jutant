import { MessageBubble } from './MessageBubble'
import { ToolActivity } from './ToolActivity'
import { CitationList } from './CitationList'
import { PlaybookStepCard } from './PlaybookStepCard'
import type { ChatStreamState } from './useChatStream'

interface Props {
  conversationId?: string
  stream: ChatStreamState
}

export function MessageList({ stream }: Props) {
  // TODO: history from GET /api/conversations/{id}/messages.
  return (
    <section aria-live="polite">
      {stream.text && (
        <MessageBubble role="assistant" text={stream.text}>
          <ToolActivity items={stream.tools} />
          <CitationList citations={stream.citations} />
        </MessageBubble>
      )}
      {stream.playbookStep && <PlaybookStepCard step={stream.playbookStep.step} onAnswer={() => {}} />}
    </section>
  )
}
