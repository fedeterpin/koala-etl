import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { fmtDate } from '../../lib/format'
import { t } from '../../i18n/es'
import { DataTable, ErrorState, LoadingBlock, Modal } from '../../components/ui'
import type { Column } from '../../components/ui'
import { errMsg } from '../dashboard/shared'
import type { TenantOut } from '../../lib/types'

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500'

function TenantFormModal({
  open,
  onClose,
  editing,
}: {
  open: boolean
  onClose: () => void
  editing: TenantOut | null
}) {
  const queryClient = useQueryClient()
  const [tenantId, setTenantId] = useState(editing?.tenant_id ?? '')
  const [tenantName, setTenantName] = useState(editing?.tenant_name ?? '')

  const save = useMutation({
    mutationFn: async () => {
      if (editing) {
        return api<TenantOut>(`/tenants/${encodeURIComponent(editing.tenant_id)}`, {
          method: 'PATCH',
          body: { tenant_name: tenantName },
        })
      }
      return api<TenantOut>('/tenants', {
        method: 'POST',
        body: { tenant_id: tenantId, tenant_name: tenantName },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenants'] })
      onClose()
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  return (
    <Modal open={open} title={editing ? t.admin.editTenant : t.admin.newTenant} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t.admin.tenantId}</label>
          <input
            type="text"
            required
            pattern="[A-Za-z0-9_-]+"
            maxLength={50}
            disabled={!!editing}
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className={`${inputClass} disabled:bg-gray-100 disabled:text-gray-500`}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">{t.admin.tenantName}</label>
          <input
            type="text"
            required
            maxLength={255}
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            className={inputClass}
          />
        </div>
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

export function TenantsTab() {
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<TenantOut | null>(null)

  const tenants = useQuery({
    queryKey: ['tenants'],
    queryFn: () => api<TenantOut[]>('/tenants'),
  })

  const columns: Column<TenantOut>[] = [
    { key: 'id', header: t.admin.tenantId, render: (tn) => <code className="text-xs">{tn.tenant_id}</code> },
    { key: 'name', header: t.admin.tenantName, render: (tn) => tn.tenant_name },
    { key: 'created', header: t.admin.createdAt, render: (tn) => fmtDate(tn.created_at) },
    {
      key: 'actions',
      header: t.common.actions,
      render: (tn) => (
        <button
          onClick={() => {
            setEditing(tn)
            setModalOpen(true)
          }}
          className="text-xs font-medium text-primary-700 hover:underline"
        >
          {t.common.edit}
        </button>
      ),
    },
  ]

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">{t.admin.tabTenants}</h2>
        <button
          onClick={() => {
            setEditing(null)
            setModalOpen(true)
          }}
          className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-700"
        >
          + {t.admin.newTenant}
        </button>
      </div>
      {tenants.isLoading ? (
        <LoadingBlock />
      ) : tenants.isError ? (
        <ErrorState message={errMsg(tenants.error) ?? undefined} onRetry={() => tenants.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          rows={tenants.data ?? []}
          rowKey={(tn) => tn.tenant_id}
          emptyMessage={t.admin.noTenants}
        />
      )}
      {modalOpen && (
        <TenantFormModal
          key={editing?.tenant_id ?? 'new'}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
          editing={editing}
        />
      )}
    </div>
  )
}
