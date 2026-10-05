import { chatStreamReducer, failureMessage, initialStreamState, isBusy } from '../chat/useChatStream'

describe('chatStreamReducer', () => {
  it('accumulates text and completes with citations', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'start', data: { question: 'KYC?' } })
    expect(state).toMatchObject({ status: 'sending', question: 'KYC?' })
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

  it('tracks tool activity by call id', () => {
    const call = { id: 'c1', name: 'transactions.get_status', arguments: {} }
    let state = chatStreamReducer(initialStreamState, { event: 'tool_started', data: { call } })
    expect(isBusy(state)).toBe(true)
    state = chatStreamReducer(state, {
      event: 'tool_finished',
      data: { result: { call_id: 'c1', ok: true, error: null, citations: [] } },
    })
    expect(state.tools[0]?.result?.ok).toBe(true)
  })

  it('turns failure reasons into plain language and a new question clears the last turn', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'queued', data: { position: 2 } })
    state = chatStreamReducer(state, { event: 'failed', data: { reason: 'step_limit' } })
    expect(state.error).toBe(failureMessage('step_limit'))
    expect(failureMessage('anything else')).toMatch(/went wrong/)
    state = chatStreamReducer(state, { event: 'start', data: { question: 'Again' } })
    expect(state).toEqual({ ...initialStreamState, status: 'sending', question: 'Again' })
  })
})
