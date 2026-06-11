import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, registerSessionExpiredHandler, tokenStore } from './api'
import type { MeOut, TokenPair } from './types'

const SELECTED_TENANT_KEY = 'koala.selected_tenant'

interface AuthContextValue {
  user: MeOut | null
  /** true mientras se restaura la sesión inicial desde localStorage */
  initializing: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  isAdmin: boolean
  isSuperadmin: boolean
  /** Tenant seleccionado por el superadmin (persistido). */
  selectedTenant: string | null
  setSelectedTenant: (tenantId: string | null) => void
  /**
   * Parámetro `tenant_id` a agregar en TODOS los endpoints scoped
   * (metrics, chats, files, backups, etl/runs, users):
   * - superadmin → tenant seleccionado en el header
   * - usuario de tenant → undefined (el backend lo resuelve del JWT)
   */
  tenantParam: string | undefined
  /** Superadmin sin tenant elegido: las vistas scoped deben pedir selección. */
  needsTenantSelection: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeOut | null>(null)
  const [initializing, setInitializing] = useState(true)
  const [selectedTenant, setSelectedTenantState] = useState<string | null>(
    () => localStorage.getItem(SELECTED_TENANT_KEY),
  )
  const queryClient = useQueryClient()

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    queryClient.clear()
  }, [queryClient])

  useEffect(() => {
    registerSessionExpiredHandler(() => {
      setUser(null)
      queryClient.clear()
    })
  }, [queryClient])

  // Restaurar sesión al montar
  useEffect(() => {
    let cancelled = false
    async function restore() {
      if (!tokenStore.access && !tokenStore.refresh) {
        setInitializing(false)
        return
      }
      try {
        const me = await api<MeOut>('/auth/me')
        if (!cancelled) setUser(me)
      } catch {
        if (!cancelled) tokenStore.clear()
      } finally {
        if (!cancelled) setInitializing(false)
      }
    }
    restore()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const pair = await api<TokenPair>('/auth/login', {
      method: 'POST',
      body: { email, password },
      skipAuth: true,
    })
    tokenStore.set(pair.access_token, pair.refresh_token)
    // /auth/me trae tenant_name y logo_url además del usuario
    const me = await api<MeOut>('/auth/me')
    setUser(me)
  }, [])

  const setSelectedTenant = useCallback(
    (tenantId: string | null) => {
      setSelectedTenantState(tenantId)
      if (tenantId) localStorage.setItem(SELECTED_TENANT_KEY, tenantId)
      else localStorage.removeItem(SELECTED_TENANT_KEY)
      // Los datos scoped cambian por completo al cambiar de tenant
      queryClient.invalidateQueries()
    },
    [queryClient],
  )

  const isSuperadmin = user?.role === 'superadmin'
  const isAdmin = user?.role === 'superadmin' || user?.role === 'tenant_admin'

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      initializing,
      login,
      logout,
      isAdmin,
      isSuperadmin,
      selectedTenant,
      setSelectedTenant,
      tenantParam: isSuperadmin ? selectedTenant ?? undefined : undefined,
      needsTenantSelection: isSuperadmin && !selectedTenant,
    }),
    [user, initializing, login, logout, isAdmin, isSuperadmin, selectedTenant, setSelectedTenant],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
