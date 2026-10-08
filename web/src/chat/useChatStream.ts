// The turn in progress: a reducer over the stream's events (the answer so far, tool activity,
// citations, the playbook steps shown) and a hook that runs the stream and can stop it.

import { useCallback, useReducer, useRef } from 'react'
import { ApiError } from '../api/client'
import type { Choice, Citation, ShownStep, StreamEvent, ToolCall, ToolResult } from '../api/events'
import { ask, type AskBody } from '../api/stream'

export interface ToolActivityItem {
  call: ToolCall
  label?: string | null // what the tool looks at, in staff's words, from the pack
  result?: ToolResult
}

export interface ChatStreamState {
  status: 'idle' | 'sending' | 'queued' | 'streaming' | 'done' | 'failed' | 'stopped'
  question?: string
  repeat?: boolean // the question sent again after a pick: already shown, not shown twice
  startedAt?: number // when the question was sent, for the time shown while waiting
  queuePosition?: number
  featureId?: string
  switchedFrom?: string // the quick action staff had chosen, when the question was for another feature
  choices?: Choice[] // the assistant could not tell what the message is: staff pick one
  clarifyReason?: string // why it asked: `talk` when the assistant talked, the kinds of help offered with it
  text: string
  tools: ToolActivityItem[]
  citations: Citation[]
  steps: ShownStep[]
  failure?: string // the reason the turn failed (`denied`, `model_unavailable`...)
  error?: string // a message for failures outside the stream (connection, HTTP)
}

export type ChatAction =
  | StreamEvent
  | { event: 'start'; data: { question: string; at: number; repeat?: boolean } }
  | { event: 'error'; data: { message: string } }
  | { event: 'stopped' }
  | { event: 'reset' }

export const initialStreamState: ChatStreamState = {
  status: 'idle',
  text: '',
  tools: [],
  citations: [],
  steps: [],
}

export function chatStreamReducer(state: ChatStreamState, action: ChatAction): ChatStreamState {
  switch (action.event) {
    case 'reset':
      return initialStreamState
    case 'start':
      return {
        ...initialStreamState,
        status: 'sending',
        question: action.data.question,
        startedAt: action.data.at,
        repeat: action.data.repeat,
      }
    case 'queued':
      return { ...state, status: 'queued', queuePosition: action.data.position }
    case 'feature_selected':
      return {
        ...state,
        status: 'streaming',
        featureId: action.data.feature_id,
        switchedFrom: action.data.switched_from ?? undefined,
      }
    case 'clarify':
      return { ...state, choices: action.data.choices, clarifyReason: action.data.reason }
    case 'tool_started':
      return {
        ...state,
        status: 'streaming',
        tools: [...state.tools, { call: action.data.call, label: action.data.label }],
      }
    case 'tool_finished':
      return {
        ...state,
        tools: state.tools.map((t) =>
          t.call.id === action.data.result.call_id ? { ...t, result: action.data.result } : t,
        ),
      }
    case 'text_delta':
      return { ...state, status: 'streaming', text: state.text + action.data.text }
    case 'playbook_step':
      return { ...state, steps: [...state.steps, action.data] }
    case 'completed':
      return { ...state, status: 'done', text: action.data.answer.text, citations: action.data.answer.citations }
    case 'failed':
      return { ...state, status: 'failed', failure: action.data.reason }
    case 'error':
      return { ...state, status: 'failed', error: action.data.message }
    case 'stopped':
      return { ...state, status: 'stopped' }
  }
}

export function isBusy(state: ChatStreamState): boolean {
  return state.status === 'sending' || state.status === 'queued' || state.status === 'streaming'
}

/** Runs one turn at a time. `onSettled` is called with the turn's conversation when it ends,
 * however it ends. */
export function useChatStream(onSettled: (conversationId: string) => void) {
  const [state, dispatch] = useReducer(chatStreamReducer, initialStreamState)
  const controller = useRef<AbortController | null>(null)

  const send = useCallback(
    async (conversationId: string, body: AskBody, repeat = false) => {
      controller.current?.abort()
      const current = new AbortController()
      controller.current = current
      dispatch({ event: 'start', data: { question: body.text, at: Date.now(), repeat } })
      try {
        for await (const event of ask(conversationId, body, current.signal)) dispatch(event)
      } catch (error) {
        if (current.signal.aborted) dispatch({ event: 'stopped' })
        else if (error instanceof ApiError && error.status === 403) {
          dispatch({ event: 'failed', data: { reason: 'denied' } })
        } else dispatch({ event: 'error', data: { message: errorMessage(error) } })
      } finally {
        onSettled(conversationId)
      }
    },
    [onSettled],
  )

  const stop = useCallback(() => controller.current?.abort(), [])
  const reset = useCallback(() => dispatch({ event: 'reset' }), [])
  return { state, send, stop, reset }
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === 'string') return error.detail
  return 'The connection was lost. Check your network, then ask again.'
}
