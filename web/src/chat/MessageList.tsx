import { useEffect, useRef } from 'react'
import type { HistoryMessage } from '../api/endpoints'
import { MessageBubble } from './MessageBubble'
import { ToolActivity } from './ToolActivity'
import { CitationList } from './CitationList'
import { PlaybookStepCard } from './PlaybookStepCard'
import type { ChatStreamState } from './useChatStream'
import styles from './MessageList.module.css'

interface Props {
  messages: HistoryMessage[]
  stream?: ChatStreamState
  busy: boolean
  onAnswerStep: (answer: string) => void
}

export function MessageList({ messages, stream, busy, onAnswerStep }: Props) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length, stream?.text, stream?.status, stream?.tools.length])

  const empty = messages.length === 0 && (!stream || stream.status === 'idle')
  // The server stores the question when the turn starts, so history fetched mid-answer (on
  // returning to the window, say) already ends with it; show it once, not again from the stream.
  const last = messages[messages.length - 1]
  const questionInHistory =
    stream !== undefined && last?.role === 'user' && last.content === stream.question

  return (
    <section className={styles.list} aria-live="polite">
      {empty && (
        <p className={styles.welcome}>
          Ask about a policy, a transaction, a product or a procedure. Answers show their sources.
        </p>
      )}
      {messages.map((m) => (
        <MessageBubble key={m.id} role={m.role} text={m.content}>
          {m.role === 'assistant' && <CitationList citations={m.citations} />}
        </MessageBubble>
      ))}
      {stream && busy && (
        <>
          {!questionInHistory && <MessageBubble role="user" text={stream.question ?? ''} />}
          <MessageBubble role="assistant" text={stream.text} pending>
            {!stream.text && <p className={styles.status}>{statusLine(stream)}</p>}
            <ToolActivity items={stream.tools} />
          </MessageBubble>
        </>
      )}
      {stream?.status === 'failed' && (
        <p role="alert" className={styles.error}>
          {stream.error}
        </p>
      )}
      {stream?.status === 'stopped' && <p className={styles.status}>Stopped.</p>}
      {stream?.playbookStep && !busy && stream.status === 'done' && (
        <PlaybookStepCard step={stream.playbookStep.step} onAnswer={onAnswerStep} />
      )}
      <div ref={end} />
    </section>
  )
}

function statusLine(stream: ChatStreamState): string {
  if (stream.status === 'queued') return `Waiting for the assistant: you are number ${stream.queuePosition} in line.`
  return 'Working on it…'
}
