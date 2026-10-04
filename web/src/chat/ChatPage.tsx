import { useReducer } from 'react'
import { useParams } from 'react-router-dom'
import { ConversationList } from './ConversationList'
import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { FeatureChips } from './FeatureChips'
import { chatStreamReducer, initialStreamState } from './useChatStream'
import styles from './ChatPage.module.css'

export function ChatPage() {
  const { conversationId } = useParams()
  const [stream] = useReducer(chatStreamReducer, initialStreamState)

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <ConversationList activeId={conversationId} />
      </aside>
      <main className={styles.main}>
        <MessageList conversationId={conversationId} stream={stream} />
        <FeatureChips selected={undefined} onSelect={() => {}} />
        <Composer disabled={!conversationId} onSend={() => {}} />
      </main>
    </div>
  )
}
