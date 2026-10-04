// `ask` is a POST, so EventSource cannot be used. Read the body as a stream and parse
// server-sent event frames ourselves.

import { API_BASE, ApiError } from './client'
import type { StreamEvent } from './events'

export interface AskBody {
  text: string
  feature_id?: string
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
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, await response.text().catch(() => null))
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
