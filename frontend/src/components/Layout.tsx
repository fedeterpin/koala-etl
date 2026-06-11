import { useState } from 'react'
import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { t } from '../i18n/es'
import type { TenantOut } from '../lib/types'
import { LoadingBlock } from './ui'

function navClass({ isActive }: { isActive: boolean }) {
  return `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-primary-700 text-white'
      : 'text-primary-100 hover:bg-primary-800 hover:text-white'
  }`
}

function TenantSelector() {
  const { selectedTenant, setSelectedTenant } = useAuth()
  const { data: tenants } = useQuery({
    queryKey: ['tenants'],
    queryFn: () => api<TenantOut[]>('/tenants'),
  })
  return (
    <select
      aria-label={t.header.tenantSelector}
      value={selectedTenant ?? ''}
      onChange={(e) => setSelectedTenant(e.target.value || null)}
      className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 focus:border-primary-500 focus:outline-none"
    >
      <option value="">{t.header.noTenantSelected}</option>
      {(tenants ?? []).map((tn) => (
        <option key={tn.tenant_id} value={tn.tenant_id}>
          {tn.tenant_name}
        </option>
      ))}
    </select>
  )
}

export function Layout() {
  const { user, logout, isAdmin, isSuperadmin } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-gray-100">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 transform bg-primary-900 transition-transform md:static md:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex h-16 items-center gap-2 px-4 text-white">
          <span className="text-2xl" aria-hidden>
            🐨
          </span>
          <div>
            <p className="text-lg font-bold leading-tight">{t.brand.name}</p>
            <p className="text-[10px] text-primary-300">{t.brand.tagline}</p>
          </div>
        </div>
        <nav className="space-y-1 px-3 py-2">
          <p className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-primary-400">
            {t.nav.dashboards}
          </p>
          <NavLink to="/dashboard/usuarios" className={navClass} onClick={() => setSidebarOpen(false)}>
            👤 {t.nav.dashUsuarios}
          </NavLink>
          <NavLink to="/dashboard/clientes" className={navClass} onClick={() => setSidebarOpen(false)}>
            👥 {t.nav.dashClientes}
          </NavLink>
          <NavLink to="/dashboard/siniestros" className={navClass} onClick={() => setSidebarOpen(false)}>
            🚗 {t.nav.dashSiniestros}
          </NavLink>
          <p className="px-3 pt-3 text-[10px] font-semibold uppercase tracking-wider text-primary-400">
            {t.brand.name}
          </p>
          <NavLink to="/conversaciones" className={navClass} onClick={() => setSidebarOpen(false)}>
            💬 {t.nav.conversations}
          </NavLink>
          {isAdmin && (
            <>
              <NavLink to="/descargas-fallidas" className={navClass} onClick={() => setSidebarOpen(false)}>
                ⚠️ {t.nav.failedDownloads}
              </NavLink>
              <NavLink to="/backups" className={navClass} onClick={() => setSidebarOpen(false)}>
                📦 {t.nav.backups}
              </NavLink>
              <NavLink to="/admin" className={navClass} onClick={() => setSidebarOpen(false)}>
                ⚙️ {t.nav.admin}
              </NavLink>
            </>
          )}
        </nav>
      </aside>
      {sidebarOpen && (
        <div className="fixed inset-0 z-30 bg-gray-900/40 md:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Contenido */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-gray-200 bg-white px-4 shadow-sm">
          <button
            className="rounded-md p-2 text-gray-500 hover:bg-gray-100 md:hidden"
            onClick={() => setSidebarOpen((v) => !v)}
            aria-label="Menú"
          >
            ☰
          </button>
          <div className="flex min-w-0 items-center gap-2">
            {user?.logo_url && (
              <img src={user.logo_url} alt="" className="h-8 w-8 rounded object-contain" />
            )}
            <span className="truncate text-sm font-semibold text-gray-800">
              {isSuperadmin ? t.header.superadmin : user?.tenant_name ?? ''}
            </span>
          </div>
          {isSuperadmin && (
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-gray-500 sm:inline">{t.header.tenantSelector}:</span>
              <TenantSelector />
            </div>
          )}
          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-gray-800">{user?.full_name}</p>
              <p className="text-xs text-gray-400">{t.roles[user?.role ?? ''] ?? user?.role}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              {t.nav.logout}
            </button>
          </div>
        </header>
        <main className="min-w-0 flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** Ruta protegida: requiere sesión. */
export function RequireAuth() {
  const { user, initializing } = useAuth()
  const location = useLocation()
  if (initializing) return <LoadingBlock />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

/** Guard por rol: viewer no accede a fallidas/backups/admin. */
export function RequireAdmin() {
  const { isAdmin } = useAuth()
  if (!isAdmin) return <Navigate to="/dashboard/usuarios" replace />
  return <Outlet />
}
