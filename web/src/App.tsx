import { Navigate, Route, Routes } from 'react-router-dom'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/AuthProvider'
import { ChatPage } from './chat/ChatPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/chat/:conversationId?"
        element={
          <RequireAuth>
            <ChatPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  )
}
