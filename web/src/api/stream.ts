// `ask` is a POST, so EventSource cannot be used. Read the body as a stream and parse
// server-sent event frames ourselves.

import { API_BASE, ApiError } from './client'
import type { StreamEvent } from './events'

/** A step answer clicked on its card, staff's reply to "your answer or a new question?", a
 * paused procedure's Resume and Stop, or a subject chip clicked to return to it. */
export type ReplyAs = 'answer' | 'question' | 'resume' | 'stop' | 'return' | 'continue'

export interface AskBody {
  text: string
  feature_id?: string // used whatever the question
  preferred_feature_id?: string // staff's quick action: used unless the question is clearly for another
  reply_as?: ReplyAs // during a procedure: what staff say the message is, so it is not read
  subject_id?: number // with reply_as 'return' or 'continue': the subject staff chose
  upload_id?: string
}

/** Parse complete SSE frames from `buffer`. Returns the events and the unparsed remainder. */
export function parseFrames(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = []
  const frames = buffer.split(/\r?\n\r?\n/)
  const rest = frames.pop() ?? ''
  for (const frame of frames) {
    let name = 'message'
    const data: string[] = []
    for (const line of frame.split(/\r?\n/)) {
      if (line.startsWith(':')) continue // keep-alive comment
      if (line.startsWith('event:')) name = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length === 0) continue
    events.push({ event: name, data: JSON.parse(data.join('\n')) } as StreamEvent)
  }
  return { events, rest }
}

export async function* ask(
  conversationId: string,
  body: AskBody,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}/ask`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (response.status === 401) window.location.assign('/login')
  if (!response.ok || !response.body) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : body
    throw new ApiError(response.status, detail)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = parseFrames(buffer + value)
    buffer = parsed.rest
    yield* parsed.events
  }
}
