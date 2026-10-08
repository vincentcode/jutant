import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Feedback, HistoryMessage } from '../api/endpoints'
import { AnswerFooter } from './AnswerFooter'
import { MessageBubble } from './MessageBubble'
import { ToolActivity } from './ToolActivity'
import { CitationList } from './CitationList'
import { PlaybookStepCard, PlaybookStepLine } from './PlaybookStepCard'
import { currentStep, fromHistory } from './steps'
import { isBusy, type ChatStreamState } from './useChatStream'
import { elapsed, failureText, stageLine } from './wording'

interface Props {
  messages: HistoryMessage[]
  stream?: ChatStreamState
  busy: boolean
  onAnswerStep: (answer: string) => void
  onRate?: (messageId: string, feedback: Feedback) => Promise<void>
  featureTitles?: Record<string, string> // feature id -> title, for "Answered by…"
  welcome?: ReactNode // the first screen, before anything is asked
}

export function MessageList({
  messages,
  stream,
  busy,
  onAnswerStep,
  onRate,
  featureTitles = {},
  welcome,
}: Props) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' })
  }, [messages.length, stream?.text, stream?.status, stream?.tools.length])

  const empty = messages.length === 0 && (!stream || stream.status === 'idle')
  // The server stores the question when the turn starts, so history fetched mid-answer (on
  // returning to the window, say) already ends with it; show it once, not again from the stream.
  const last = messages[messages.length - 1]
  // A message sent again after a pick in "What is this about?" is already in history too.
  const questionInHistory =
    stream !== undefined &&
    (stream.repeat || (last?.role === 'user' && last.content === stream.question))
  const current = currentStep(messages, stream, busy)

  return (
    <section className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
      <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-3.5 px-4 py-5">
      {empty &&
        (welcome ?? (
          <p className="m-auto max-w-md text-center text-muted">
            Ask about a policy, a transaction, a product or a procedure. Answers show their sources.
          </p>
        ))}
      {messages.map((m) => (
        <HistoryEntry
          key={m.id}
          message={m}
          hideLastStep={current?.messageId === m.id}
          featureTitle={m.feature_id ? featureTitles[m.feature_id] : undefined}
          onRate={onRate && ((feedback) => onRate(m.id, feedback))}
        />
      ))}
      {stream && busy && (
        <>
          {!questionInHistory && <MessageBubble role="user" text={stream.question ?? ''} />}
          <MessageBubble role="assistant" text={stream.text} pending>
            <Progress stream={stream} />
            <ToolActivity items={stream.tools} />
          </MessageBubble>
        </>
      )}
      {stream?.status === 'failed' && (
        <MessageBubble role="assistant" text="">
          <div role="alert" className="rounded border-l-[3px] border-danger bg-danger-soft px-2.5 py-2">
            {failureText(stream)}
          </div>
          <ToolActivity items={stream.tools} />
        </MessageBubble>
      )}
      {stream?.status === 'stopped' && <p className="m-0 italic text-muted">Stopped. Ask again when you're ready.</p>}
      {current && <PlaybookStepCard shown={current.shown} onAnswer={onAnswerStep} />}
      <div ref={end} />
      </div>
    </section>
  )
}

/** One stored message: the text, then any procedure steps the turn showed, as lines. The step
 * still waiting for staff is left to the card at the end. */
function HistoryEntry({
  message,
  hideLastStep,
  featureTitle,
  onRate,
}: {
  message: HistoryMessage
  hideLastStep: boolean
  featureTitle?: string
  onRate?: (feedback: Feedback) => Promise<void>
}) {
  const steps = (hideLastStep ? message.steps.slice(0, -1) : message.steps).map(fromHistory)
  const answer = message.role === 'assistant'
  return (
    <>
      {(message.content || !answer) && (
        <MessageBubble role={message.role} text={message.content} at={message.created_at}>
          {answer && <CitationList citations={message.citations} />}
          {answer && <AnswerFooter message={message} featureTitle={featureTitle} onRate={onRate} />}
        </MessageBubble>
      )}
      {steps.map((shown) => (
        <PlaybookStepLine key={`${shown.playbook_id}:${shown.step.order}`} shown={shown} />
      ))}
    </>
  )
}

/** The stage of the turn in progress, and how long it has taken once that is noticeable. */
function Progress({ stream }: { stream: ChatStreamState }) {
  const seconds = useSecondsSince(stream.startedAt, isBusy(stream))
  const stage = stageLine(stream)
  const took = elapsed(seconds)
  if (!stage && !took) return null
  return (
    <p className="m-0 italic text-muted">
      {stage}
      {stage && took && ' · '}
      {took && <span className="not-italic tabular-nums">{took}</span>}
    </p>
  )
}

function useSecondsSince(start: number | undefined, running: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [running])
  return start ? Math.max(0, Math.floor((now - start) / 1000)) : 0
}
