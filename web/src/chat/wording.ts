// What staff read about a turn in progress or a turn that failed: in their words, never tool
// names or error codes. Pure functions, so the wording is tested in one place.

import type { ChatStreamState, ToolActivityItem } from './useChatStream'

/** What a tool looks at: the pack's label ("the transfer"), or a readable fallback. */
export function toolSubject(item: ToolActivityItem): string {
  if (item.label) return item.label
  const [server = '', tool = ''] = item.call.name.split('.')
  return `${server} (${tool.replace(/_/g, ' ')})`
}

/** The record a call was about, when it is an identifier staff would recognise (a reference,
 * an account or customer number), not a whole question. */
export function toolValue(item: ToolActivityItem): string | undefined {
  for (const value of Object.values(item.call.arguments)) {
    if (typeof value === 'string' && /^[\w-]{3,20}$/.test(value)) return value
  }
  return undefined
}

function subjectWithValue(item: ToolActivityItem): string {
  const value = toolValue(item)
  return value ? `${toolSubject(item)} ${value}` : toolSubject(item)
}

export function toolLine(item: ToolActivityItem): { text: string; state: 'running' | 'done' | 'problem' } {
  const subject = subjectWithValue(item)
  if (!item.result) return { text: `Checking ${subject}…`, state: 'running' }
  if (item.result.ok) return { text: `Checked ${subject}`, state: 'done' }
  const problems: Record<string, string> = {
    denied: `Not allowed: ${subject}`,
    not_found: `Not found: ${subject}`,
    upstream_error: `No answer from the bank's system: ${subject}`,
    invalid_arguments: `Couldn't check ${subject}`,
  }
  return { text: problems[item.result.error ?? ''] ?? `Couldn't check ${subject}`, state: 'problem' }
}

/** The stage of a turn in progress, when no tool line already says it. */
export function stageLine(state: ChatStreamState): string | undefined {
  if (state.status === 'queued') {
    return `Waiting for the assistant: you are number ${state.queuePosition} in line.`
  }
  if (!state.featureId) return 'Finding the right help…'
  if (state.tools.some((t) => !t.result)) return undefined // the tool line says what is happening
  if (state.text) return undefined
  return 'Writing the answer…'
}

/** "45 s", "2 min 05 s": shown once a turn has taken 10 seconds. */
export function elapsed(seconds: number): string | undefined {
  if (seconds < 10) return undefined
  if (seconds < 60) return `${seconds} s`
  return `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`
}

/** A failed turn, as the assistant's reply: what happened, and what to do. */
export function failureText(state: ChatStreamState): string {
  if (state.error) return state.error
  const refused = [...state.tools].reverse().find((t) => t.result?.error === 'denied')
  switch (state.failure) {
    case 'denied':
      return refused
        ? `You don't have access to ${subjectWithValue(refused)}. It is outside what your role and branch can see.`
        : "You don't have access to that. It is outside what your role can use."
    case 'model_unavailable':
      return "I can't answer right now: the assistant's model isn't responding. Try again in a few minutes. Procedures and your conversations still work."
    case 'tool_failed':
      return "A system I needed didn't answer properly, so I stopped rather than guess. Try again in a minute."
    case 'step_limit':
      return "I couldn't finish that in the steps allowed. Try asking more specifically, for example with a reference or an account number."
    default:
      return 'Something went wrong on our side. Please ask again.'
  }
}
