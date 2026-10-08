import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import type { HistoryMessage } from '../api/endpoints'
import { useTheme } from '../app/appearance'
import { AnswerFooter, asPlainText } from '../chat/AnswerFooter'
import { ConversationList } from '../chat/ConversationList'

describe('AnswerFooter', () => {
  const answer: HistoryMessage = {
    id: 'a',
    role: 'assistant',
    content: '**Failed**: the account is closed.\n- Funds returned',
    feature_id: 'transaction_lookup',
    citations: [{ kind: 'record', title: 'Transaction', locator: 'TX-0002' }],
    steps: [],
    created_at: '2026-10-01T10:00:05Z',
  }

  it('says which kind of help answered, and copies the answer with its sources', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<AnswerFooter message={answer} featureTitle="Transaction lookup" />)
    expect(screen.getByText('Answered by Transaction lookup')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }))
    await screen.findByRole('button', { name: 'Copied' })
    expect(writeText).toHaveBeenCalledWith(
      'Failed: the account is closed.\n• Funds returned\n\nSources:\n- Transaction, TX-0002',
    )
    expect(asPlainText({ ...answer, citations: [] })).not.toMatch(/Sources/)
  })
})

describe('ConversationList', () => {
  const conversations = [
    { id: 'c1', title: 'Why did TX-0002 fail?', updated_at: '2026-10-01T10:00:00Z' },
    { id: 'c2', title: 'KYC for minors', updated_at: '2026-10-01T09:00:00Z' },
  ]

  function wrapper({ children }: { children: ReactNode }) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  function serve(handler: (url: string, init?: RequestInit) => unknown) {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const body = handler(url, init)
      return new Response(body === undefined ? null : JSON.stringify(body), {
        status: body === undefined ? 204 : 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }

  afterEach(() => vi.unstubAllGlobals())

  it('searches by what was said, after typing stops', async () => {
    const fetchMock = serve((url) => (url.includes('q=closed') ? [conversations[0]] : conversations))
    render(<ConversationList />, { wrapper })
    expect(await screen.findByText('KYC for minors')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search conversations'), { target: { value: 'closed' } })
    await waitFor(() => expect(screen.queryByText('KYC for minors')).toBeNull())
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('q=closed'))).toBe(true)
  })

  it('renames and deletes a conversation, asking before deleting', async () => {
    const fetchMock = serve((_url, init) => {
      if (init?.method === 'PATCH') return { ...conversations[0], title: 'TX-0002, Mrs Mensah' }
      if (init?.method === 'DELETE') return undefined
      return conversations
    })
    render(<ConversationList />, { wrapper })
    fireEvent.click(await screen.findByRole('button', { name: 'Options for Why did TX-0002 fail?' }))
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }))
    fireEvent.change(screen.getByLabelText('Conversation name'), { target: { value: 'TX-0002, Mrs Mensah' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/conversations/c1'),
        expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ title: 'TX-0002, Mrs Mensah' }) }),
      ),
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Options for KYC for minors' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByText('Delete this conversation?')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ method: 'DELETE' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/conversations/c2'),
        expect.objectContaining({ method: 'DELETE' }),
      ),
    )
  })
})

describe('useTheme', () => {
  it('cycles automatic, light and dark, and remembers the choice', () => {
    localStorage.clear()
    const { result, unmount } = renderHook(() => useTheme())
    expect(result.current[0]).toBe('auto')
    expect(document.documentElement.dataset.theme).toBeUndefined()
    act(() => result.current[1]())
    expect(document.documentElement.dataset.theme).toBe('light')
    act(() => result.current[1]())
    expect(document.documentElement.dataset.theme).toBe('dark')
    unmount()
    expect(renderHook(() => useTheme()).result.current[0]).toBe('dark') // remembered
  })
})
