import { chatStreamReducer, initialStreamState } from '../chat/useChatStream'

describe('chatStreamReducer', () => {
  it('accumulates text and completes with citations', () => {
    let state = chatStreamReducer(initialStreamState, { event: 'text_delta', data: { text: 'Both ' } })
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
    expect(state.citations).toHaveLength(1)
  })
})
