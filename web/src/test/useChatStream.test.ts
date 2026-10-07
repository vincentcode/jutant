import { chatStreamReducer, initialStreamState, isBusy } from '../chat/useChatStream'

describe('chatStreamReducer', () => {
  it('accumulates text and completes with citations', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'start', data: { question: 'KYC?', at: 1000 } })
    expect(state).toMatchObject({ status: 'sending', question: 'KYC?', startedAt: 1000 })
    state = chatStreamReducer(state, { event: 'text_delta', data: { text: 'Both ' } })
    state = chatStreamReducer(state, { event: 'text_delta', data: { text: 'holders.' } })
    expect(state.text).toBe('Both holders.')
    state = chatStreamReducer(state, {
      event: 'completed',
      data: {
        answer: {
          text: 'Both holders.',
          feature_id: 'policy_qa',
          citations: [{ kind: 'document', title: 'KYC Policy', locator: '4.2' }],
        },
      },
    })
    expect(state.status).toBe('done')
    expect(isBusy(state)).toBe(false)
    expect(state.citations).toHaveLength(1)
  })

  it('tracks tool activity by call id, with its label', () => {
    const call = { id: 'c1', name: 'transactions.get_status', arguments: {} }
    let state = chatStreamReducer(initialStreamState, {
      event: 'tool_started',
      data: { call, label: 'the transfer' },
    })
    expect(isBusy(state)).toBe(true)
    expect(state.tools[0]?.label).toBe('the transfer')
    state = chatStreamReducer(state, {
      event: 'tool_finished',
      data: { result: { call_id: 'c1', ok: true, error: null, citations: [] } },
    })
    expect(state.tools[0]?.result?.ok).toBe(true)
  })

  it('keeps every step a turn shows, in order', () => {
    const step = { order: 2, title: 'Check the status', instruction: '', expects: 'choice' as const, choices: [] }
    let state = chatStreamReducer(initialStreamState, {
      event: 'playbook_step',
      data: { playbook_id: 'failed_transfer', answered: 'failed', step },
    })
    state = chatStreamReducer(state, {
      event: 'playbook_step',
      data: { playbook_id: 'failed_transfer', step: { ...step, order: 3, expects: 'confirm' } },
    })
    expect(state.steps.map((s) => [s.step.order, s.answered])).toEqual([
      [2, 'failed'],
      [3, undefined],
    ])
  })

  it('keeps the failure reason, and a new question clears the last turn', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'queued', data: { position: 2 } })
    state = chatStreamReducer(state, { event: 'failed', data: { reason: 'step_limit' } })
    expect(state).toMatchObject({ status: 'failed', failure: 'step_limit' })
    state = chatStreamReducer(state, { event: 'start', data: { question: 'Again', at: 5 } })
    expect(state).toEqual({ ...initialStreamState, status: 'sending', question: 'Again', startedAt: 5 })
  })

  it('records when the question was for another feature than the quick action', () => {
    const switched = chatStreamReducer(initialStreamState, {
      event: 'feature_selected',
      data: { feature_id: 'policy_qa', switched_from: 'transaction_lookup' },
    })
    expect(switched).toMatchObject({ featureId: 'policy_qa', switchedFrom: 'transaction_lookup' })
    const kept = chatStreamReducer(initialStreamState, {
      event: 'feature_selected',
      data: { feature_id: 'policy_qa', switched_from: null },
    })
    expect(kept.switchedFrom).toBeUndefined()
  })

  it('keeps an unclear reply until the next question', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'start', data: { question: 'blue', at: 1 } })
    state = chatStreamReducer(state, {
      event: 'reply_unclear',
      data: { step_order: 2, step_title: 'Find the block reason' },
    })
    expect(state.unclear).toEqual({ stepOrder: 2, stepTitle: 'Find the block reason' })
    state = chatStreamReducer(state, { event: 'start', data: { question: 'blue', at: 2 } })
    expect(state.unclear).toBeUndefined()
  })

  it('keeps the subject question until the next question', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'start', data: { question: 'why?', at: 1 } })
    state = chatStreamReducer(state, {
      event: 'subject_unclear',
      data: { subject_id: 3, subject_title: 'Transaction lookup: transfer TX-0002' },
    })
    expect(state.subjectUnclear).toEqual({ subjectId: 3, subjectTitle: 'Transaction lookup: transfer TX-0002' })
    state = chatStreamReducer(state, { event: 'start', data: { question: 'why?', at: 2 } })
    expect(state.subjectUnclear).toBeUndefined()
  })
})
