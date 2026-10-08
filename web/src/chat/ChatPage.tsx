import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CircleUserRound, ListChecks, X } from 'lucide-react'
import * as api from '../api/endpoints'
import type { Upload } from '../api/endpoints'
import type { Choice } from '../api/events'
import type { ReplyAs } from '../api/stream'
import { useAppInfo, useTheme } from '../app/appearance'
import { useAuth } from '../auth/AuthProvider'
import { HomeScreen } from '../home/HomeScreen'
import { IconRail, type PanelId } from '../shell/IconRail'
import { KnowledgePanel } from '../shell/KnowledgePanel'
import { SettingsPanel } from '../shell/SettingsPanel'
import { ConversationList } from './ConversationList'
import { MessageList } from './MessageList'
import { Composer } from './Composer'
import { isBusy, useChatStream } from './useChatStream'

const PANEL_TITLES: Record<PanelId, string> = {
  search: 'Search',
  conversations: 'Conversations',
  knowledge: 'Knowledge',
  settings: 'Settings',
}

export function ChatPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { me, signOut } = useAuth()
  const app = useAppInfo()
  const [theme, , setTheme] = useTheme()
  const [featureId, setFeatureId] = useState<string | undefined>()
  const [hint, setHint] = useState<string | undefined>()
  const [attachment, setAttachment] = useState<Upload | undefined>()
  const [streamFor, setStreamFor] = useState<string | undefined>()
  const [panel, setPanel] = useState<PanelId | undefined>()

  const features = useQuery({ queryKey: ['features'], queryFn: api.features })
  const home = useQuery({ queryKey: ['home'], queryFn: api.home })
  const featureTitles = useMemo(
    () => Object.fromEntries((features.data ?? []).map((f) => [f.id, f.title])),
    [features.data],
  )
  const history = useQuery({
    queryKey: ['history', conversationId],
    queryFn: () => api.history(conversationId!),
    enabled: Boolean(conversationId),
  })
  // A procedure paused while staff ask other things, to offer Resume and Stop.
  const procedure = useQuery({
    queryKey: ['procedure', conversationId],
    queryFn: () => api.procedure(conversationId!),
    enabled: Boolean(conversationId),
  })

  const onSettled = useCallback(
    (id: string) => {
      void queryClient.invalidateQueries({ queryKey: ['history', id] })
      void queryClient.invalidateQueries({ queryKey: ['conversations'] })
      void queryClient.invalidateQueries({ queryKey: ['procedure', id] })
    },
    [queryClient],
  )
  const { state, send, stop, reset } = useChatStream(onSettled)
  const busy = isBusy(state)

  // Opening another conversation leaves the turn in progress behind, and closes a panel that
  // covers the page on a phone.
  useEffect(() => {
    if (streamFor !== conversationId) {
      reset()
      setAttachment(undefined)
    }
    if (window.matchMedia?.('(max-width: 767px)').matches) setPanel(undefined)
  }, [conversationId]) // eslint-disable-line react-hooks/exhaustive-deps

  const startNew = useCallback(() => {
    navigate('/chat')
    setFeatureId(undefined)
    setHint(undefined)
    setTimeout(() => document.getElementById('question')?.focus())
  }, [navigate])

  // Ctrl+Shift+O (⌘⇧O on a Mac): a new conversation, from anywhere.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'o') {
        event.preventDefault()
        startNew()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [startNew])

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId
    const created = await api.startConversation()
    void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    setStreamFor(created.id)
    navigate(`/chat/${created.id}`)
    return created.id
  }

  // The quick action is a preference: the server keeps to it unless the question is clearly
  // for another feature. With a file attached, the chosen feature reads it, whatever the words.
  // During a procedure, `replyAs` says what the message is (an answer clicked on the step card,
  // Resume, Stop...), so the server does not need to read it.
  async function ask(
    text: string,
    feature = featureId,
    replyAs?: ReplyAs,
    subjectId?: number,
    picked?: number,
  ) {
    const id = await ensureConversation()
    setStreamFor(id)
    const said = { reply_as: replyAs, subject_id: subjectId, picked }
    setFeatureId(undefined) // a card's or an upload's kind of help is for this message only
    setHint(undefined)
    void send(
      id,
      attachment
        ? { text, feature_id: feature, upload_id: attachment.upload_id, ...said }
        : { text, preferred_feature_id: feature, ...said },
      picked !== undefined, // sent again after a pick: already shown
    )
  }

  /** Staff picked what a message is, when the assistant could not tell: it is sent again
   * saying so. When the assistant had asked them in words what they need ("How can I help?"),
   * there is nothing to send again: the kind of help picked starts, and asks what they need. */
  async function pick(text: string, choice: Choice, picked: number) {
    if (state.clarifyReason === 'talk' && choice.kind === 'feature') {
      const id = await ensureConversation()
      setStreamFor(id)
      void send(id, { text: choice.title, feature_id: choice.feature_id ?? undefined, reply_as: 'start', picked })
      return
    }
    switch (choice.kind) {
      case 'answer':
        return ask(text, undefined, 'answer', undefined, picked)
      case 'subject':
        return ask(text, undefined, 'continue', choice.subject_id ?? undefined, picked)
      case 'resume':
        return ask('Resume the procedure', undefined, 'resume', undefined, picked)
      case 'new':
        return ask(text, undefined, 'question', undefined, picked)
      case 'feature': {
        const id = await ensureConversation()
        setStreamFor(id)
        void send(id, { text, feature_id: choice.feature_id ?? undefined, reply_as: 'question', picked }, true)
      }
    }
  }

  /** Ask in a new conversation, whatever is open (a document summary from Knowledge). The
   * feature applies to this question only: a follow-up is routed afresh, not summarised again. */
  async function askInNew(text: string, feature: string) {
    const created = await api.startConversation()
    void queryClient.invalidateQueries({ queryKey: ['conversations'] })
    setStreamFor(created.id)
    setFeatureId(undefined)
    setHint(undefined)
    navigate(`/chat/${created.id}`)
    void send(created.id, { text, feature_id: feature })
  }

  async function rate(messageId: string, feedback: api.Feedback): Promise<void> {
    if (!conversationId) return
    const saved = await api.rateAnswer(conversationId, messageId, feedback)
    queryClient.setQueryData<api.HistoryMessage[]>(['history', conversationId], (messages) =>
      messages?.map((m) => (m.id === messageId ? { ...m, feedback: saved } : m)),
    )
  }

  async function attach(file: File): Promise<void> {
    const id = await ensureConversation()
    const uploaded = await api.upload(id, file)
    setAttachment(uploaded)
    const extraction = features.data?.find((f) => f.template === 'document_extraction')
    if (extraction) setFeatureId(extraction.id)
  }

  function chooseFeature(id: string | undefined) {
    setFeatureId(id)
    const example = features.data?.find((f) => f.id === id)?.examples[0]
    setHint(example ? `For example: ${example}` : undefined)
  }

  const summariser = features.data?.find((f) => f.template === 'document_extraction')
  const firstName = me?.display_name.split(' ')[0]

  const composer = (
    <Composer
      busy={busy}
      attachment={attachment}
      onSend={(text) => void ask(text)}
      onStop={stop}
      onAttach={attach}
      onDetach={() => setAttachment(undefined)}
      placeholder={hint}
    />
  )

  return (
    <div className="flex h-dvh">
      <a href="#question" className="skip-link">
        Skip to the question box
      </a>
      <IconRail open={panel} onToggle={(p) => setPanel(panel === p ? undefined : p)} onNew={startNew} />

      {panel && (
        <aside
          aria-label={PANEL_TITLES[panel]}
          className="fixed inset-y-0 left-14 right-0 z-30 flex flex-col border-r border-line bg-bg md:static md:z-auto md:w-80 md:shrink-0"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <h2 className="text-sm font-semibold">{PANEL_TITLES[panel]}</h2>
            <button
              type="button"
              className="rounded-md p-1 text-muted hover:bg-hover"
              aria-label="Close panel"
              onClick={() => setPanel(undefined)}
            >
              <X aria-hidden className="size-4" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {(panel === 'search' || panel === 'conversations') && (
              <div className="p-3">
                <ConversationList key={panel} activeId={conversationId} focusSearch={panel === 'search'} />
              </div>
            )}
            {panel === 'knowledge' && (
              <KnowledgePanel
                onSummarise={
                  summariser &&
                  ((doc) => void askInNew(`Summarise "${doc.title}"`, summariser.id))
                }
              />
            )}
            {panel === 'settings' && (
              <SettingsPanel me={me} theme={theme} onTheme={setTheme} onSignOut={() => void signOut()} />
            )}
          </div>
        </aside>
      )}

      <main className="flex min-w-0 flex-1 flex-col bg-surface">
        <header className="grid grid-cols-[1fr_auto_1fr] items-center border-b border-line px-4 py-2.5">
          <span />
          <span className="font-semibold text-accent">{app.name}</span>
          <button
            type="button"
            className="justify-self-end rounded-full p-1 text-muted hover:bg-hover hover:text-fg"
            aria-label={`Your account: ${me?.display_name ?? ''}`}
            title={me ? `${me.display_name} · ${me.role.replace(/_/g, ' ')}` : undefined}
            onClick={() => setPanel(panel === 'settings' ? undefined : 'settings')}
          >
            <CircleUserRound aria-hidden className="size-6" />
          </button>
        </header>

        {conversationId ? (
          <>
            <MessageList
              messages={history.data ?? []}
              stream={streamFor === conversationId ? state : undefined}
              busy={busy}
              onAnswerStep={(answer) => void ask(answer, undefined, 'answer')}
              onRate={rate}
              featureTitles={featureTitles}
            />
            {streamFor === conversationId && state.choices?.length && state.question && !busy ? (
              <Picker
                choices={state.choices}
                onPick={(choice, picked) => void pick(state.question!, choice, picked)}
              />
            ) : null}
            {procedure.data?.paused && !busy && (
              <PausedProcedure
                procedure={procedure.data}
                onResume={() => void ask('Resume the procedure', undefined, 'resume')}
                onStop={() => void ask('Stop the procedure', undefined, 'stop')}
              />
            )}
            {streamFor === conversationId && state.switchedFrom && state.featureId && (
              <p role="status" className="mx-auto mb-1 w-full max-w-3xl px-5 text-xs text-muted">
                Switched from {featureTitles[state.switchedFrom] ?? 'the card you chose'} to{' '}
                {featureTitles[state.featureId] ?? 'another kind of help'}: the question was about that.
              </p>
            )}
            <div className="mx-auto w-full max-w-3xl px-4 pb-4">{composer}</div>
          </>
        ) : (
          <HomeScreen
            firstName={firstName}
            cards={home.data?.cards ?? []}
            onCard={(card) => {
              chooseFeature(card.feature_id)
              document.getElementById('question')?.focus()
            }}
            composer={composer}
          />
        )}
      </main>
    </div>
  )
}

/** A procedure waiting on its step while staff ask other things. */
function PausedProcedure({
  procedure,
  onResume,
  onStop,
}: {
  procedure: api.Procedure
  onResume: () => void
  onStop: () => void
}) {
  return (
    <div
      role="status"
      className="mx-auto mb-2 flex w-full max-w-3xl flex-wrap items-center gap-2 rounded-xl border border-line bg-accent-soft px-4 py-2 text-sm"
    >
      <ListChecks aria-hidden className="size-4 text-accent" />
      <span className="flex-1">
        <strong className="font-semibold">{procedure.playbook_title}</strong> · paused at step{' '}
        {procedure.step_order} ({procedure.step_title})
      </span>
      <button type="button" className="btn px-3 py-1 text-sm" onClick={onResume}>
        Resume
      </button>
      <button type="button" className="btn-link text-sm" onClick={onStop}>
        Stop
      </button>
    </div>
  )
}

/** The assistant could not tell what staff's message is: the open subjects, the waiting step and
 * the kinds of help, to pick from. A pick sends the message again saying which. */
function Picker({
  choices,
  onPick,
}: {
  choices: Choice[]
  onPick: (choice: Choice, picked: number) => void
}) {
  return (
    <div
      role="group"
      aria-label="What is this about?"
      className="mx-auto mb-2 flex w-full max-w-3xl flex-wrap items-center gap-2 px-5 text-sm"
    >
      {choices.map((choice, picked) => (
        <button
          key={`${choice.kind}:${choice.subject_id ?? choice.feature_id ?? choice.title}`}
          type="button"
          className="chip"
          onClick={() => onPick(choice, picked)}
        >
          {choice.title}
        </button>
      ))}
    </div>
  )
}
