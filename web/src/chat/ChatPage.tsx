import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/endpoints'
import type { Upload } from '../api/endpoints'
import { useAuth } from '../auth/AuthProvider'
import { ConversationList } from './ConversationList'
import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { FeatureChips } from './FeatureChips'
import { isBusy, useChatStream } from './useChatStream'
import styles from './ChatPage.module.css'

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { me, signOut } = useAuth()
  const [featureId, setFeatureId] = useState<string | undefined>()
  const [attachment, setAttachment] = useState<Upload | undefined>()
  const [streamFor, setStreamFor] = useState<string | undefined>()
  const [menuOpen, setMenuOpen] = useState(false)

  const features = useQuery({ queryKey: ['features'], queryFn: api.features })
  const history = useQuery({
    queryKey: ['history', conversationId],
    queryFn: () => api.history(conversationId!),
    enabled: Boolean(conversationId),
  })

  const onSettled = useCallback(
    (id: string) => {
      void queryClient.invalidateQueries({ queryKey: ['history', id] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    },
    [queryClient],
  )
  const { state, send, stop, reset } = useChatStream(onSettled)
  const busy = isBusy(state)

  // Opening another conversation leaves the turn in progress behind.
  useEffect(() => {
    if (streamFor !== conversationId) {
      reset()
      setAttachment(undefined)
    }
    setMenuOpen(false)
  }, [conversationId]) // eslint-disable-line react-hooks/exhaustive-deps

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId
    const created = await api.startConversation()
    void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    setStreamFor(created.id)
    navigate(`/chat/${created.id}`)
    return created.id
  }

  async function ask(text: string) {
    const id = await ensureConversation()
    setStreamFor(id)
    void send(id, { text, feature_id: featureId, upload_id: attachment?.upload_id })
  }

  async function attach(file: File): Promise<void> {
    const id = await ensureConversation()
    const uploaded = await api.upload(id, file)
    setAttachment(uploaded)
    const extraction = features.data?.find((f) => f.template === 'document_extraction')
    if (extraction) setFeatureId(extraction.id)
  }

  return (
    <div className={styles.layout}>
      <aside className={`${styles.sidebar} ${menuOpen ? styles.open : ''}`}>
        <ConversationList activeId={conversationId} />
      </aside>
      <main className={styles.main}>
        <header className={styles.header}>
          <button className={styles.menu} onClick={() => setMenuOpen(!menuOpen)} aria-label="Conversations">
            ☰
          </button>
          <span className={styles.title}>Staff Assistant</span>
          <span className={styles.user}>
            {me?.display_name} · {me?.role.replace(/_/g, ' ')}
          </span>
          <button className="link" onClick={() => void signOut()}>
            Sign out
          </button>
        </header>
        <MessageList
          messages={conversationId ? (history.data ?? []) : []}
          stream={streamFor === conversationId ? state : undefined}
          busy={busy}
          onAnswerStep={(answer) => void ask(answer)}
        />
        <div className={styles.bottom}>
          <FeatureChips features={features.data ?? []} selected={featureId} onSelect={setFeatureId} />
          <Composer
            busy={busy}
            attachment={attachment}
            onSend={(text) => void ask(text)}
            onStop={stop}
            onAttach={attach}
            onDetach={() => setAttachment(undefined)}
          />
        </div>
      </main>
    </div>
  )
}
