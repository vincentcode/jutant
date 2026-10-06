// Typed union of the server-sent events streamed by POST /api/conversations/{id}/ask.

export interface Citation {
  kind: 'document' | 'record'
  title: string
  locator: string
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResult {
  call_id: string
  ok: boolean
  error: string | null
  citations: Citation[]
}

export interface PlaybookStep {
  order: number
  title: string
  instruction: string
  expects: 'confirm' | 'choice' | 'text' | 'none'
  choices: string[]
}

/** A step as a turn showed it: `answered` when a looked-up record answered it. */
export interface ShownStep {
  playbook_id: string
  playbook_title?: string
  answered?: string | null
  step: PlaybookStep
}

export interface Answer {
  text: string
  feature_id: string
  citations: Citation[]
}

export type StreamEvent =
  | { event: 'queued'; data: { position: number } }
  | { event: 'feature_selected'; data: { feature_id: string; switched_from?: string | null } }
  | { event: 'tool_started'; data: { call: ToolCall; label?: string | null } }
  | { event: 'tool_finished'; data: { result: ToolResult } }
  | { event: 'text_delta'; data: { text: string } }
  | { event: 'playbook_step'; data: ShownStep }
  | { event: 'completed'; data: { answer: Answer } }
  | { event: 'failed'; data: { reason: string } }
