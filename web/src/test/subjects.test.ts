import { describe, expect, it } from 'vitest'
import { shortTitle } from '../chat/ChatPage'

describe('subject chips', () => {
  it('show what a subject is about, without the feature name', () => {
    expect(shortTitle('Transaction lookup: transfer TX-0002')).toBe('transfer TX-0002')
    expect(shortTitle('Product lookup: Standard Savings (SAV-STD)')).toBe('Standard Savings (SAV-STD)')
    expect(shortTitle('Policy and procedure Q&A')).toBe('Policy and procedure Q&A')
  })
})
