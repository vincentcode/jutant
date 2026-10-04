import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiJson } from '../api/client'

export interface Me {
  id: string
  role: string
  display_name: string
}

interface AuthState {
  me: Me | undefined
  loading: boolean
}

const AuthContext = createContext<AuthState>({ me: undefined, loading: true })

export function AuthProvider({ children }: { children: ReactNode }) {
  const { data, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: () => apiJson<Me>('/auth/me'),
    retry: false,
  })
  return <AuthContext.Provider value={{ me: data, loading: isLoading }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  return useContext(AuthContext)
}
