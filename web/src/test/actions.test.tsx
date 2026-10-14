import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Proposal } from '../api/events'
import { ActionCard } from '../chat/ActionCard'
import { placeProposals } from '../chat/MessageList'
import { chatStreamReducer, initialStreamState } from '../chat/useChatStream'

const NOW = Date.parse('2026-10-13T12:00:00Z')

function proposal(changes: Partial<Proposal> = {}): Proposal {
  return {
    id: 'p1',
    action_id: 'leave_request',
    title: 'Leave request',
    icon: 'calendar',
    summary: 'Annual leave, 10-14 Nov 2026',
    fields: [
      { label: 'From', value: 'Mon 10 Nov 2026' },
      { label: 'Days', value: '5' },
    ],
    notes: ['Balance after this: 9 of 21 days'],
    warnings: ['14 Nov is half a day at Head Office'],
    status: 'proposed',
    reference: '',
    outcome: '',
    expires_at: '2026-10-13T12:10:00Z',
    created_at: '2026-10-13T12:00:00Z',
    ...changes,
  }
}

const noop = () => Promise.resolve()

describe('ActionCard', () => {
  it('shows exactly what will be sent, and sends only when asked', async () => {
    const onSend = vi.fn(noop)
    render(<ActionCard proposal={proposal()} onSend={onSend} onChange={noop} onCancel={noop} now={NOW} />)
    expect(screen.getByText('Leave request · not sent yet')).toBeInTheDocument()
    expect(screen.getByText('Mon 10 Nov 2026')).toBeInTheDocument()
    expect(screen.getByText('Balance after this: 9 of 21 days')).toBeInTheDocument()
    expect(screen.getByText('14 Nov is half a day at Head Office')).toBeInTheDocument()
    expect(onSend).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Send request' }))
    await waitFor(() => expect(onSend).toHaveBeenCalledOnce())
  })

  it('once sent, shows the reference and no buttons', () => {
    render(
      <ActionCard
        proposal={proposal({ status: 'sent', reference: 'LV-2026-00318', outcome: 'Waiting for Ama Mensah' })}
        onSend={noop}
        onChange={noop}
        onCancel={noop}
        now={NOW}
      />,
    )
    expect(screen.getByText('Leave request · sent')).toBeInTheDocument()
    expect(screen.getByText('LV-2026-00318')).toBeInTheDocument()
    expect(screen.getByText(/Waiting for Ama Mensah/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('a card past its time cannot be sent', () => {
    render(
      <ActionCard proposal={proposal()} onSend={noop} onChange={noop} onCancel={noop} now={NOW + 11 * 60_000} />,
    )
    expect(screen.getByText('Leave request · not sent: it waited too long')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send request' })).not.toBeInTheDocument()
  })

  it('says why, when sending did not work', async () => {
    const onSend = vi.fn(() => Promise.reject(new Error('This request has already been sent.')))
    render(<ActionCard proposal={proposal()} onSend={onSend} onChange={noop} onCancel={noop} now={NOW} />)
    fireEvent.click(screen.getByRole('button', { name: 'Send request' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already been sent')
  })

  it('a system that did not answer leaves the card to send again, saying so', () => {
    render(
      <ActionCard
        proposal={proposal({ outcome: 'The system did not answer, so nothing was sent.' })}
        onSend={noop}
        onChange={noop}
        onCancel={noop}
        now={NOW}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('nothing was sent')
    expect(screen.getByRole('button', { name: 'Send request' })).toBeEnabled()
  })
})

describe('placing cards', () => {
  const message = (id: string, role: 'user' | 'assistant', at: string) => ({
    id,
    role,
    content: id,
    citations: [],
    steps: [],
    created_at: at,
  })

  it('puts a card under the answer of the turn that proposed it, or at the end', () => {
    const messages = [
      message('q1', 'user', '2026-10-13T11:59:58Z'),
      message('a1', 'assistant', '2026-10-13T12:00:01Z'),
    ]
    const later = proposal({ id: 'p2', created_at: '2026-10-13T12:05:00Z' })
    const { after, trailing } = placeProposals(messages, [proposal(), later])
    expect(after.get('a1')?.map((p) => p.id)).toEqual(['p1'])
    expect(trailing.map((p) => p.id)).toEqual(['p2'])
  })
})

describe('the stream', () => {
  it('keeps the requests a turn proposed', () => {
    const state = chatStreamReducer(initialStreamState, { event: 'action_proposed', data: proposal() })
    expect(state.proposals.map((p) => p.id)).toEqual(['p1'])
  })
})
