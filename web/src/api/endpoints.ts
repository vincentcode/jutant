// The REST calls, typed from the API's OpenAPI document (schema.d.ts). Asking a question is a
// stream, in stream.ts.

import { apiFetch, apiJson } from './client'
import type { components } from './schema'

type Schemas = components['schemas']
export type Me = Schemas['Me']
export type Feature = Schemas['FeatureOut']
export type Conversation = Schemas['ConversationOut']
export type HistoryMessage = Schemas['MessageOut']
export type Upload = Schemas['UploadOut']

export const login = (username: string, password: string) =>
  apiJson<Me>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })

export const logout = () => apiFetch('/auth/logout', { method: 'POST' })

export const me = () => apiJson<Me>('/auth/me')

export const features = () => apiJson<Feature[]>('/features')

export const conversations = () => apiJson<Conversation[]>('/conversations')

export const startConversation = () => apiJson<Conversation>('/conversations', { method: 'POST' })

export const history = (conversationId: string) =>
  apiJson<HistoryMessage[]>(`/conversations/${conversationId}/messages`)

/** The subjects open in a conversation, current first, for staff to return to. */
export type Subject = Schemas['SubjectOut']
export const subjects = (conversationId: string) =>
  apiJson<Subject[]>(`/conversations/${conversationId}/subjects`)

/** The procedure in progress and the step it waits on, or null. */
export type Procedure = Schemas['ProcedureOut']
export const procedure = (conversationId: string) =>
  apiJson<Procedure | null>(`/conversations/${conversationId}/procedure`)

export function upload(conversationId: string, file: File): Promise<Upload> {
  const body = new FormData()
  body.append('file', file)
  return apiJson<Upload>(`/conversations/${conversationId}/upload`, { method: 'POST', body })
}

export type Feedback = Schemas['FeedbackOut']
export type FeedbackReason = NonNullable<Schemas['FeedbackIn']['reason']>

export const rateAnswer = (
  conversationId: string,
  messageId: string,
  feedback: Schemas['FeedbackIn'],
) =>
  apiJson<Feedback>(`/conversations/${conversationId}/messages/${messageId}/feedback`, {
    method: 'PUT',
    body: JSON.stringify(feedback),
  })

export type AppInfo = Schemas['AppOut']
export const appInfo = () => apiJson<AppInfo>('/app')

export const searchConversations = (q: string) =>
  apiJson<Conversation[]>(`/conversations${q ? `?q=${encodeURIComponent(q)}` : ''}`)

export const renameConversation = (conversationId: string, title: string) =>
  apiJson<Conversation>(`/conversations/${conversationId}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  })

export const deleteConversation = (conversationId: string) =>
  apiFetch(`/conversations/${conversationId}`, { method: 'DELETE' })

export type Home = Schemas['HomeOut']
export type HomeCard = Schemas['HomeCardOut']
export type QuickAction = Schemas['QuickActionOut']
export type LibraryDocument = Schemas['DocumentOut']

export const home = () => apiJson<Home>('/home')

export const documents = (q: string, type = '') => {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (type) params.set('type', type)
  const query = params.toString()
  return apiJson<LibraryDocument[]>(`/documents${query ? `?${query}` : ''}`)
}
