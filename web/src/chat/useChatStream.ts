// The turn in progress: a reducer over the stream's events (the answer so far, tool activity,
// citations, the current playbook step) and a hook that runs the stream and can stop it.

import { useCallback, useReducer, useRef } from 'react'
import { ApiError } from '../api/client'
import type { Citation, PlaybookStep, StreamEvent, ToolCall, ToolResult } from '../api/events'
import { ask, type AskBody } from '../api/stream'

export interface ToolActivityItem {
  call: ToolCall
  result?: ToolResult
}

export interface ChatStreamState {
  status: 'idle' | 'sending' | 'queued' | 'streaming' | 'done' | 'failed' | 'stopped'
  question?: string
  queuePosition?: number
  featureId?: string
  text: string
  tools: ToolActivityItem[]
  citations: Citation[]
  playbookStep?: { playbookId: string; step: PlaybookStep }
  error?: string
}

export type ChatAction =
  | StreamEvent
  | { event: 'start'; data: { question: string } }
  | { event: 'error'; data: { message: string } }
  | { event: 'stopped' }
  | { event: 'reset' }

export const initialStreamState: ChatStreamState = { status: 'idle', text: '', tools: [], citations: [] }

export function chatStreamReducer(state: ChatStreamState, action: ChatAction): ChatStreamState {
  switch (action.event) {
    case 'reset':
      return initialStreamState
    case 'start':
      return { ...initialStreamState, status: 'sending', question: action.data.question }
    case 'queued':
      return { ...state, status: 'queued', queuePosition: action.data.position }
    case 'feature_selected':
      return { ...state, status: 'streaming', featureId: action.data.feature_id }
    case 'tool_started':
      return { ...state, status: 'streaming', tools: [...state.tools, { call: action.data.call }] }
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
      return { ...state, playbookStep: { playbookId: action.data.playbook_id, step: action.data.step } }
    case 'completed':
      return { ...state, status: 'done', text: action.data.answer.text, citations: action.data.answer.citations }
    case 'failed':
      return { ...state, status: 'failed', error: failureMessage(action.data.reason) }
    case 'error':
      return { ...state, status: 'failed', error: action.data.message }
    case 'stopped':
      return { ...state, status: 'stopped' }
  }
}

const FAILURES: Record<string, string> = {
  step_limit: "I couldn't finish that within the steps allowed. Try a more specific question.",
  tool_failed: "A system I needed didn't respond properly. Please try again.",
  model_unavailable: 'The assistant is unavailable right now. Please try again shortly.',
  denied: "You don't have access to that.",
}

export function failureMessage(reason: string): string {
  return FAILURES[reason] ?? 'Something went wrong. Please try again.'
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
    async (conversationId: string, body: AskBody) => {
      controller.current?.abort()
      const current = new AbortController()
      controller.current = current
      dispatch({ event: 'start', data: { question: body.text } })
      try {
        for await (const event of ask(conversationId, body, current.signal)) dispatch(event)
      } catch (error) {
        if (current.signal.aborted) dispatch({ event: 'stopped' })
        else dispatch({ event: 'error', data: { message: errorMessage(error) } })
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
  if (error instanceof ApiError) {
    if (error.status === 403) return failureMessage('denied')
    if (typeof error.detail === 'string') return error.detail
  }
  return 'The connection was lost. Please try again.'
}
