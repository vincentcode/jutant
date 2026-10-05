import { fireEvent, render, screen } from '@testing-library/react'
import { Composer } from '../chat/Composer'
import { FeatureChips } from '../chat/FeatureChips'
import { MessageList } from '../chat/MessageList'
import { PlaybookStepCard } from '../chat/PlaybookStepCard'
import { initialStreamState } from '../chat/useChatStream'

describe('PlaybookStepCard', () => {
  it('sends the chosen option, done, or cancel', () => {
    const onAnswer = vi.fn()
    const step = {
      order: 2,
      title: 'Find the block reason',
      instruction: 'Which reason is shown?',
      expects: 'choice' as const,
      choices: ['wrong_pin', 'fraud_hold'],
    }
    const { rerender } = render(<PlaybookStepCard step={step} onAnswer={onAnswer} />)
    fireEvent.click(screen.getByRole('button', { name: 'fraud hold' }))
    expect(onAnswer).toHaveBeenLastCalledWith('fraud_hold')

    rerender(<PlaybookStepCard step={{ ...step, expects: 'confirm', choices: [] }} onAnswer={onAnswer} />)
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
      created_at: '2026-10-01T10:00:00Z',
    },
    {
      id: '2',
      role: 'assistant' as const,
      content: 'The beneficiary account is closed.',
      feature_id: 'transaction_lookup',
      citations: [{ kind: 'record' as const, title: 'Transaction', locator: 'TX-0002' }],
      created_at: '2026-10-01T10:00:05Z',
    },
  ]

  it('shows every answer with its sources', () => {
    render(<MessageList messages={history} busy={false} onAnswerStep={() => {}} />)
    expect(screen.getByText('The beneficiary account is closed.')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Sources' })).toHaveTextContent('Transaction, TX-0002')
  })

  it('shows the question and progress while waiting, and failures in plain language', () => {
    const queued = { ...initialStreamState, status: 'queued' as const, question: 'KYC?', queuePosition: 2 }
    const { rerender } = render(<MessageList messages={[]} stream={queued} busy onAnswerStep={() => {}} />)
    expect(screen.getByText('KYC?')).toBeInTheDocument()
    expect(screen.getByText(/number 2 in line/)).toBeInTheDocument()

    const failed = { ...queued, status: 'failed' as const, error: 'The assistant is unavailable right now.' }
    rerender(<MessageList messages={[]} stream={failed} busy={false} onAnswerStep={() => {}} />)
    expect(screen.getByRole('alert')).toHaveTextContent('unavailable')
  })

  it('shows the question once when history fetched mid-answer already has it', () => {
    const asking = { ...initialStreamState, status: 'streaming' as const, question: 'Why did TX-0002 fail?' }
    render(<MessageList messages={history.slice(0, 1)} stream={asking} busy onAnswerStep={() => {}} />)
    expect(screen.getAllByText('Why did TX-0002 fail?')).toHaveLength(1)
    expect(screen.getByText('Working on it…')).toBeInTheDocument()
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

describe('FeatureChips', () => {
  it('marks the chosen feature and offers automatic routing', () => {
    const onSelect = vi.fn()
    const features = [{ id: 'policy_qa', template: 'document_qa', title: 'Policy Q&A', description: 'Policies' }]
    render(<FeatureChips features={features} selected="policy_qa" onSelect={onSelect} />)
    expect(screen.getByRole('button', { name: 'Policy Q&A' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Automatic' }))
    expect(onSelect).toHaveBeenCalledWith(undefined)
  })
})
