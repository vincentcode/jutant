// A reducer over stream events: in-progress message, tool activity, citations and the
// current playbook step.

import type { Citation, PlaybookStep, StreamEvent, ToolCall, ToolResult } from '../api/events'

export interface ToolActivityItem {
  call: ToolCall
  result?: ToolResult
}

export interface ChatStreamState {
  status: 'idle' | 'queued' | 'streaming' | 'done' | 'failed'
  queuePosition?: number
  featureId?: string
  text: string
  tools: ToolActivityItem[]
  citations: Citation[]
  playbookStep?: { playbookId: string; step: PlaybookStep }
  error?: string
}

export const initialStreamState: ChatStreamState = { status: 'idle', text: '', tools: [], citations: [] }

export function chatStreamReducer(state: ChatStreamState, event: StreamEvent | { event: 'reset' }): ChatStreamState {
  switch (event.event) {
    case 'reset':
      return initialStreamState
    case 'queued':
      return { ...state, status: 'queued', queuePosition: event.data.position }
    case 'feature_selected':
      return { ...state, status: 'streaming', featureId: event.data.feature_id }
    case 'tool_started':
      return { ...state, status: 'streaming', tools: [...state.tools, { call: event.data.call }] }
    case 'tool_finished':
      return {
        ...state,
        tools: state.tools.map((t) =>
          t.call.id === event.data.result.call_id ? { ...t, result: event.data.result } : t,
        ),
      }
    case 'text_delta':
      return { ...state, status: 'streaming', text: state.text + event.data.text }
    case 'playbook_step':
      return { ...state, playbookStep: { playbookId: event.data.playbook_id, step: event.data.step } }
    case 'completed':
      return { ...state, status: 'done', text: event.data.answer.text, citations: event.data.answer.citations }
    case 'failed':
      return { ...state, status: 'failed', error: event.data.reason }
  }
}
