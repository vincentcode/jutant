import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Composer } from '../chat/Composer'
import { FeedbackBar } from '../chat/FeedbackBar'
import { MessageList } from '../chat/MessageList'
import { PlaybookStepCard } from '../chat/PlaybookStepCard'
import { initialStreamState } from '../chat/useChatStream'

const STEP = {
  order: 2,
  title: 'Find the block reason',
  instruction: 'Which reason is shown?',
  expects: 'choice' as const,
  choices: ['wrong_pin', 'fraud_hold'],
}

function stored(order: number, title: string, extra: Record<string, unknown> = {}) {
  return {
    playbook_id: 'failed_transfer',
    playbook_title: 'Failed transfer',
    order,
    title,
    instruction: `Instruction ${order}.`,
    expects: 'confirm' as const,
    choices: [],
    ...extra,
  }
}

describe('PlaybookStepCard', () => {
  it('shows where staff are, and sends the chosen option, done, or cancel', () => {
    const onAnswer = vi.fn()
    const shown = { playbook_id: 'blocked_card', playbook_title: 'Blocked card', step: STEP }
    const { rerender } = render(<PlaybookStepCard shown={shown} onAnswer={onAnswer} />)
    expect(screen.getByText('Blocked card · Step 2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'fraud hold' }))
    expect(onAnswer).toHaveBeenLastCalledWith('fraud_hold')

    rerender(
      <PlaybookStepCard shown={{ ...shown, step: { ...STEP, expects: 'confirm', choices: [] } }} onAnswer={onAnswer} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onAnswer).toHaveBeenLastCalledWith('done')
    fireEvent.click(screen.getByRole('button', { name: 'Stop procedure' }))
    expect(onAnswer).toHaveBeenLastCalledWith('cancel')
  })
})

describe('MessageList', () => {
  const history = [
    {
      id: '1',
      role: 'user' as const,
      content: 'Why did TX-0002 fail?',
      citations: [],
      steps: [],
      created_at: '2026-10-01T10:00:00Z',
    },
    {
      id: '2',
      role: 'assistant' as const,
      content: '**Failed**: the beneficiary account is closed.',
      feature_id: 'transaction_lookup',
      citations: [
        { kind: 'record' as const, title: 'Transaction', locator: 'TX-0002' },
        { kind: 'document' as const, title: 'Error codes', locator: 'E51' },
      ],
      steps: [],
      created_at: '2026-10-01T10:00:05Z',
    },
  ]
  const none = () => {}

  it('renders formatting in answers, and shows the main source first', () => {
    render(<MessageList messages={history} busy={false} onAnswerStep={none} />)
    expect(screen.getByText('Failed').tagName).toBe('STRONG')
    const sources = screen.getByRole('region', { name: 'Sources' })
    expect(sources).toHaveTextContent('Source Transaction, TX-0002')
    expect(screen.getByText('Also searched (1)')).toBeInTheDocument()
  })

  it('never runs or loads anything an answer contains', () => {
    const risky = {
      ...history[1]!,
      content: 'Hi <img src=x onerror="alert(1)"> ![x](http://evil/x.png) <script>alert(2)</script> [link](javascript:alert(3))',
    }
    const { container } = render(<MessageList messages={[risky]} busy={false} onAnswerStep={none} />)
    expect(container.querySelector('img, script')).toBeNull()
    expect(container.querySelector('a')?.getAttribute('href') ?? '').not.toMatch(/javascript/)
  })

  it('shows earlier procedure steps as lines and the waiting one as a card, after a reload too', () => {
    const turn = {
      ...history[1]!,
      content: '',
      steps: [
        stored(2, 'Check the status', { expects: 'choice', choices: ['failed'], answered: 'failed' }),
        stored(3, 'Explain the failure'),
      ],
    }
    render(<MessageList messages={[history[0]!, turn]} busy={false} onAnswerStep={none} />)
    expect(screen.getByText('failed (from the record)', { exact: false })).toBeInTheDocument()
    const card = screen.getByRole('region', { name: 'Procedure step' })
    expect(card).toHaveTextContent('Failed transfer · Step 3')
    expect(card).toHaveTextContent('Explain the failure')
    expect(screen.getAllByText(/Explain the failure/)).toHaveLength(1) // shown once
  })

  it('shows the stage while waiting, and failures as the reply', () => {
    const queued = { ...initialStreamState, status: 'queued' as const, question: 'KYC?', queuePosition: 2 }
    const { rerender } = render(<MessageList messages={[]} stream={queued} busy onAnswerStep={none} />)
    expect(screen.getByText('KYC?')).toBeInTheDocument()
    expect(screen.getByText(/number 2 in line/)).toBeInTheDocument()

    const refused = {
      call: { id: 'c1', name: 'transactions.list', arguments: { account_number: '0099887766' } },
      label: "the account's transactions",
      result: { call_id: 'c1', ok: false, error: 'denied', citations: [] },
    }
    const failed = { ...queued, status: 'failed' as const, failure: 'denied', tools: [refused] }
    rerender(<MessageList messages={[]} stream={failed} busy={false} onAnswerStep={none} />)
    expect(screen.getByRole('alert')).toHaveTextContent(
      "You don't have access to the account's transactions 0099887766.",
    )
  })

  it('shows the question once when history fetched mid-answer already has it', () => {
    const asking = { ...initialStreamState, status: 'streaming' as const, question: 'Why did TX-0002 fail?' }
    render(<MessageList messages={history.slice(0, 1)} stream={asking} busy onAnswerStep={none} />)
    expect(screen.getAllByText('Why did TX-0002 fail?')).toHaveLength(1)
    expect(screen.getByText('Finding the right help…')).toBeInTheDocument()
  })
})

describe('Composer', () => {
  const props = { onStop: vi.fn(), onAttach: vi.fn(), onDetach: vi.fn() }

  it('sends on Enter and clears the box; Shift+Enter does not send', () => {
    const onSend = vi.fn()
    render(<Composer busy={false} onSend={onSend} {...props} />)
    const box = screen.getByLabelText('Ask a question')
    fireEvent.change(box, { target: { value: '  KYC for joint accounts?  ' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('KYC for joint accounts?')
    expect(box).toHaveValue('')
  })

  it('offers Stop while an answer is coming', () => {
    const onStop = vi.fn()
    render(<Composer busy onSend={vi.fn()} {...props} onStop={onStop} />)
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(onStop).toHaveBeenCalled()
  })
})

describe('FeedbackBar', () => {
  it('saves a thumbs-up at once', async () => {
    const onRate = vi.fn().mockResolvedValue(undefined)
    render(<FeedbackBar onRate={onRate} />)
    fireEvent.click(screen.getByRole('button', { name: 'Helpful' }))
    expect(onRate).toHaveBeenCalledWith({ rating: 'up', reason: null, comment: '' })
    expect(await screen.findByText('Thanks.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Helpful' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('saves a thumbs-down at once, then what was wrong', async () => {
    const onRate = vi.fn().mockResolvedValue(undefined)
    render(<FeedbackBar onRate={onRate} />)
    fireEvent.click(screen.getByRole('button', { name: 'Not helpful' }))
    expect(onRate).toHaveBeenLastCalledWith({ rating: 'down', reason: null, comment: '' })

    fireEvent.click(await screen.findByLabelText('Wrong source'))
    fireEvent.change(screen.getByLabelText('Anything else (optional)'), {
      target: { value: ' Cites E91, not E12 ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() =>
      expect(onRate).toHaveBeenLastCalledWith({ rating: 'down', reason: 'wrong_source', comment: 'Cites E91, not E12' }),
    )
    expect(await screen.findByText("Thanks, we'll look at this.")).toBeInTheDocument()
  })

  it('shows an earlier rating, and says so when saving fails', async () => {
    const onRate = vi.fn().mockRejectedValue(new Error('offline'))
    render(<FeedbackBar feedback={{ rating: 'down', reason: 'too_slow', comment: '' }} onRate={onRate} />)
    expect(screen.getByRole('button', { name: 'Not helpful' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Helpful' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't save your rating")
  })

  it('appears under answers only, when rating is possible', () => {
    const messages = [
      { id: 'q', role: 'user' as const, content: 'KYC?', citations: [], steps: [], created_at: '2026-10-01T10:00:00Z' },
      { id: 'a', role: 'assistant' as const, content: 'Two IDs.', citations: [], steps: [], created_at: '2026-10-01T10:00:05Z' },
    ]
    const { rerender } = render(<MessageList messages={messages} busy={false} onAnswerStep={() => {}} />)
    expect(screen.queryByRole('group', { name: 'Rate this answer' })).toBeNull()
    rerender(<MessageList messages={messages} busy={false} onAnswerStep={() => {}} onRate={vi.fn()} />)
    expect(screen.getAllByRole('group', { name: 'Rate this answer' })).toHaveLength(1)
  })
})
