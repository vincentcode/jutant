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

export function upload(conversationId: string, file: File): Promise<Upload> {
  const body = new FormData()
  body.append('file', file)
  return apiJson<Upload>(`/conversations/${conversationId}/upload`, { method: 'POST', body })
}
