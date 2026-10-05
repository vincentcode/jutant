import { createContext, useCallback, useContext, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/endpoints'
import type { Me } from '../api/endpoints'

interface AuthState {
  me: Me | undefined
  loading: boolean
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState>({ me: undefined, loading: true, signOut: async () => {} })

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['me'], queryFn: api.me, retry: false })

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined)
    queryClient.clear()
    window.location.assign('/login')
  }, [queryClient])

  return (
    <AuthContext.Provider value={{ me: data, loading: isLoading, signOut }}>{children}</AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  return useContext(AuthContext)
}

/** Shows its children only to a signed-in user; everyone else goes to the sign-in page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return <p className="splash">Loading…</p>
  if (!me) return <Navigate to="/login" replace />
  return children
}
