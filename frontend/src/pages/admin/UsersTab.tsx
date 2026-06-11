import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { fmtDateTime } from '../../lib/format'
import { t } from '../../i18n/es'
import {
  Badge,
  ConfirmDialog,
  DataTable,
  ErrorState,
  LoadingBlock,
  Modal,
} from '../../components/ui'
import type { Column } from '../../components/ui'
import { TenantGate, errMsg } from '../dashboard/shared'
import type { UserOut } from '../../lib/types'

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500'

interface UserFormState {
  email: string
  full_name: string
  password: string
  role: 'viewer' | 'tenant_admin'
  is_active: boolean
}

function UserFormModal({
  open,
  onClose,
  editing,
}: {
  open: boolean
  onClose: () => void
  editing: UserOut | null
}) {
  const { tenantParam, isSuperadmin } = useAuth()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<UserFormState>(() => ({
    email: editing?.email ?? '',
    full_name: editing?.full_name ?? '',
    password: '',
    role: editing?.role === 'tenant_admin' ? 'tenant_admin' : 'viewer',
    is_active: editing?.is_active ?? true,
  }))

  const save = useMutation({
    mutationFn: async () => {
      if (editing) {
        return api<UserOut>(`/users/${editing.id}`, {
          method: 'PATCH',
          body: {
            full_name: form.full_name,
            role: form.role,
            is_active: form.is_active,
            ...(form.password ? { password: form.password } : {}),
          },
        })
      }
      return api<UserOut>('/users', {
        method: 'POST',
        body: {
          email: form.email,
          full_name: form.full_name,
          password: form.password,
          role: form.role,
          // superadmin crea usuarios en el tenant seleccionado en el header
          ...(isSuperadmin ? { tenant_id: tenantParam } : {}),
        },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      onClose()
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  return (
    <Modal open={open} title={editing ? t.admin.editUser : t.admin.newUser} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {!editing && (
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">{t.admin.email}</label>
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className={inputClass}
            />
          </div>
        )}
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t.admin.fullName}</label>
          <input
            type="text"
            required
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            className={inputClass}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {editing ? t.admin.passwordKeep : t.admin.password}
          </label>
          <input
            type="password"
            required={!editing}
            minLength={8}
            autoComplete="new-password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className={inputClass}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t.admin.role}</label>
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as 'viewer' | 'tenant_admin' })}
            className={inputClass}
          >
            <option value="viewer">{t.roles.viewer}</option>
            <option value="tenant_admin">{t.roles.tenant_admin}</option>
          </select>
        </div>
        {editing && (
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="h-4 w-4 rounded border-gray-300 text-primary-600"
            />
            {t.common.active}
          </label>
        )}
        {save.isError && <p className="text-sm text-red-600">{errMsg(save.error)}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            {t.common.cancel}
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {save.isPending ? t.common.loading : t.common.save}
          </button>
        </div>
      </form>
    </Modal>
  )
}

export function UsersTab() {
  const { tenantParam, needsTenantSelection, user: me } = useAuth()
  const queryClient = useQueryClient()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<UserOut | null>(null)
  const [toDeactivate, setToDeactivate] = useState<UserOut | null>(null)

  const users = useQuery({
    queryKey: ['users', tenantParam],
    queryFn: () => api<UserOut[]>('/users', { params: { tenant_id: tenantParam } }),
    enabled: !needsTenantSelection,
  })

  const deactivate = useMutation({
    mutationFn: (id: number) => api<void>(`/users/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setToDeactivate(null)
    },
  })

  const columns: Column<UserOut>[] = [
    { key: 'email', header: t.admin.email, render: (u) => u.email },
    { key: 'name', header: t.admin.fullName, render: (u) => u.full_name },
    {
      key: 'role',
      header: t.admin.role,
      render: (u) => (
        <Badge tone={u.role === 'tenant_admin' ? 'indigo' : u.role === 'superadmin' ? 'red' : 'gray'}>
          {t.roles[u.role] ?? u.role}
        </Badge>
      ),
    },
    {
      key: 'active',
      header: t.common.status,
      render: (u) => (
        <Badge tone={u.is_active ? 'green' : 'gray'}>
          {u.is_active ? t.common.active : t.common.inactive}
        </Badge>
      ),
    },
    { key: 'last_login', header: t.admin.lastLogin, render: (u) => fmtDateTime(u.last_login_at) },
    {
      key: 'actions',
      header: t.common.actions,
      render: (u) => (
        <div className="flex gap-2">
          <button
            onClick={() => {
              setEditing(u)
              setModalOpen(true)
            }}
            className="text-xs font-medium text-primary-700 hover:underline"
          >
            {t.common.edit}
          </button>
          {u.is_active && u.id !== me?.id && (
            <button
              onClick={() => setToDeactivate(u)}
              className="text-xs font-medium text-red-600 hover:underline"
            >
              {t.admin.deactivate}
            </button>
          )}
        </div>
      ),
    },
  ]

  return (
    <TenantGate>
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">{t.admin.tabUsers}</h2>
          <button
            onClick={() => {
              setEditing(null)
              setModalOpen(true)
            }}
            className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-700"
          >
            + {t.admin.newUser}
          </button>
        </div>
        {users.isLoading ? (
          <LoadingBlock />
        ) : users.isError ? (
          <ErrorState message={errMsg(users.error) ?? undefined} onRetry={() => users.refetch()} />
        ) : (
          <DataTable
            columns={columns}
            rows={users.data ?? []}
            rowKey={(u) => u.id}
            emptyMessage={t.admin.noUsers}
          />
        )}
      </div>

      {modalOpen && (
        <UserFormModal
          key={editing?.id ?? 'new'}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          editing={editing}
        />
      )}

      <ConfirmDialog
        open={toDeactivate !== null}
        title={t.admin.deactivateConfirmTitle}
        message={`${t.admin.deactivateConfirm} (${toDeactivate?.email ?? ''})`}
        confirmLabel={t.admin.deactivate}
        danger
        busy={deactivate.isPending}
        onConfirm={() => toDeactivate && deactivate.mutate(toDeactivate.id)}
        onCancel={() => setToDeactivate(null)}
      />
    </TenantGate>
  )
}
