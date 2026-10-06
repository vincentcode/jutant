import { initialStreamState, type ChatStreamState, type ToolActivityItem } from '../chat/useChatStream'
import { elapsed, failureText, stageLine, toolLine } from '../chat/wording'

function tool(name: string, args: Record<string, unknown>, label?: string, error?: string | null): ToolActivityItem {
  const item: ToolActivityItem = { call: { id: name, name, arguments: args }, label }
  if (error !== undefined) item.result = { call_id: name, ok: error === null, error, citations: [] }
  return item
}

describe('tool activity', () => {
  it('reads as what was checked, with the record staff named', () => {
    const transfer = (error?: string | null) =>
      tool('transactions.get_status', { reference: 'TX-0002' }, 'the transfer', error)
    expect(toolLine(transfer())).toEqual({ text: 'Checking the transfer TX-0002…', state: 'running' })
    expect(toolLine(transfer(null))).toEqual({ text: 'Checked the transfer TX-0002', state: 'done' })
    expect(toolLine(transfer('denied')).text).toBe('Not allowed: the transfer TX-0002')
    expect(toolLine(transfer('not_found')).text).toBe('Not found: the transfer TX-0002')
    expect(toolLine(transfer('upstream_error')).text).toBe("No answer from the bank's system: the transfer TX-0002")
  })

  it('leaves out a value that is a whole question, and never shows a tool name raw', () => {
    const search = tool('documents.search', { query: 'What ID do joint holders need?' }, "the bank's documents")
    expect(toolLine(search).text).toBe("Checking the bank's documents…")
    expect(toolLine(tool('transactions.get_status', {})).text).toBe('Checking transactions (get status)…')
  })
})

describe('waiting', () => {
  const streaming = (patch: Partial<ChatStreamState>): ChatStreamState => ({
    ...initialStreamState,
    status: 'streaming',
    ...patch,
  })

  it('says which stage the turn is at', () => {
    expect(stageLine({ ...initialStreamState, status: 'queued', queuePosition: 3 })).toMatch(/number 3 in line/)
    expect(stageLine(streaming({}))).toBe('Finding the right help…')
    expect(stageLine(streaming({ featureId: 'transaction_lookup', tools: [tool('t.x', {})] }))).toBeUndefined()
    expect(stageLine(streaming({ featureId: 'transaction_lookup', tools: [tool('t.x', {}, 'x', null)] }))).toBe(
      'Writing the answer…',
    )
    expect(stageLine(streaming({ featureId: 'policy_qa', text: 'Both' }))).toBeUndefined()
  })

  it('shows the time taken once it is noticeable', () => {
    expect(elapsed(9)).toBeUndefined()
    expect(elapsed(45)).toBe('45 s')
    expect(elapsed(125)).toBe('2 min 05 s')
  })
})

describe('failures', () => {
  const failed = (patch: Partial<ChatStreamState>): ChatStreamState => ({
    ...initialStreamState,
    status: 'failed',
    ...patch,
  })

  it('names what was refused', () => {
    const refused = tool('transactions.list', { account_number: '0099887766' }, "the account's transactions", 'denied')
    expect(failureText(failed({ failure: 'denied', tools: [refused] }))).toBe(
      "You don't have access to the account's transactions 0099887766. It is outside what your role and branch can see.",
    )
    expect(failureText(failed({ failure: 'denied' }))).toMatch(/outside what your role can use/)
  })

  it('says what happened and what to do, without codes', () => {
    for (const reason of ['model_unavailable', 'tool_failed', 'step_limit', 'something_new']) {
      const text = failureText(failed({ failure: reason }))
      expect(text).not.toMatch(/_/)
      expect(text).toMatch(/again|Try/)
    }
  })
})
