import { parseFrames } from '../api/stream'

describe('parseFrames', () => {
  it('parses complete frames and keeps the remainder', () => {
    const input =
      'event: feature_selected\ndata: {"feature_id":"policy_qa"}\n\n' +
      ': keep-alive\n\n' +
      'event: text_delta\ndata: {"text":"Hel'
    const { events, rest } = parseFrames(input)
    expect(events).toEqual([{ event: 'feature_selected', data: { feature_id: 'policy_qa' } }])
    expect(rest).toBe('event: text_delta\ndata: {"text":"Hel')
  })
})
