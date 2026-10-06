// Playbook steps as the conversation shows them: the step waiting for staff as a card, every
// earlier step as one line. Steps come from the history (kept with each answer, so a reload
// shows them) and from the turn just streamed (before the history has caught up).

import type { HistoryMessage } from '../api/endpoints'
import type { ShownStep } from '../api/events'
import type { ChatStreamState } from './useChatStream'

export function fromHistory(step: HistoryMessage['steps'][number]): ShownStep {
  return {
    playbook_id: step.playbook_id,
    playbook_title: step.playbook_title,
    answered: step.answered,
    step: {
      order: step.order,
      title: step.title,
      instruction: step.instruction,
      expects: step.expects,
      choices: step.choices ?? [],
    },
  }
}

/** A step waits for staff if it needs a reply and no record answered it. */
export function waitsForStaff(shown: ShownStep): boolean {
  return shown.step.expects !== 'none' && !shown.answered
}

/** The step staff should act on now: the last step of the latest answer, if it waits for
 * them. The turn just finished wins over the history, which may not have caught up yet. */
export function currentStep(
  messages: HistoryMessage[],
  stream: ChatStreamState | undefined,
  busy: boolean,
): { shown: ShownStep; messageId?: string } | undefined {
  if (busy) return undefined
  if (stream?.status === 'done') {
    const last = stream.steps[stream.steps.length - 1]
    return last && waitsForStaff(last) ? { shown: last } : undefined
  }
  const latest = messages[messages.length - 1]
  const stored = latest?.role === 'assistant' ? latest.steps[latest.steps.length - 1] : undefined
  if (!latest || !stored) return undefined
  const last = fromHistory(stored)
  return waitsForStaff(last) ? { shown: last, messageId: latest.id } : undefined
}

export function stepHeading(shown: ShownStep): string {
  const where = shown.playbook_title ? `${shown.playbook_title} · ` : ''
  return `${where}Step ${shown.step.order}`
}
