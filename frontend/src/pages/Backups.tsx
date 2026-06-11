import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtBytes, fmtDateTime } from '../lib/format'
import { t } from '../i18n/es'
import {
  Badge,
  DataTable,
  ErrorState,
  LoadingBlock,
  Spinner,
  statusTone,
} from '../components/ui'
import type { Column } from '../components/ui'
import { TenantGate, errMsg } from './dashboard/shared'
import type { BackupDownloadOut, BackupOut } from '../lib/types'

function DownloadButton({ backup }: { backup: BackupOut }) {
  const { tenantParam } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  async function download() {
    setBusy(true)
    setError(false)
    try {
      const res = await api<BackupDownloadOut>(`/backups/${backup.id}/download`, {
        params: { tenant_id: tenantParam },
      })
      window.open(res.url, '_blank', 'noopener')
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  if (backup.status !== 'done') return null
  return (
    <button
      onClick={download}
      disabled={busy}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50 ${
        error ? 'bg-red-600 hover:bg-red-700' : 'bg-primary-600 hover:bg-primary-700'
      }`}
    >
      {busy && <Spinner className="h-3 w-3 text-white" />}
      ⬇ {error ? t.common.retry : t.common.download}
    </button>
  )
}

export function BackupsPage() {
  const { tenantParam, needsTenantSelection } = useAuth()
  const queryClient = useQueryClient()

  const backups = useQuery({
    queryKey: ['backups', tenantParam],
    queryFn: () => api<BackupOut[]>('/backups', { params: { tenant_id: tenantParam, limit: 50 } }),
    enabled: !needsTenantSelection,
    // Poll cada 5 s mientras haya jobs en curso
    refetchInterval: (q) =>
      (q.state.data ?? []).some((b) => b.status === 'pending' || b.status === 'running')
        ? 5000
        : false,
  })

  const create = useMutation({
    mutationFn: (type: 'full' | 'incremental') =>
      api<BackupOut>('/backups', {
        method: 'POST',
        params: { tenant_id: tenantParam },
        body: { type },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backups'] }),
  })

  const createError =
    create.error instanceof ApiError && create.error.status === 409
      ? t.backups.inProgressError
      : errMsg(create.error)

  const hasActive = (backups.data ?? []).some(
    (b) => b.status === 'pending' || b.status === 'running',
  )

  const columns: Column<BackupOut>[] = [
    { key: 'id', header: 'ID', render: (b) => `#${b.id}` },
    {
      key: 'type',
      header: t.common.type,
      render: (b) => (b.type === 'full' ? t.backups.typeFull : t.backups.typeIncremental),
    },
    {
      key: 'status',
      header: t.common.status,
      render: (b) => (
        <span className="inline-flex items-center gap-1.5">
          <Badge tone={statusTone(b.status)}>{t.backups.statusLabels[b.status] ?? b.status}</Badge>
          {(b.status === 'pending' || b.status === 'running') && <Spinner className="h-3 w-3" />}
        </span>
      ),
    },
    { key: 'size', header: t.backups.size, render: (b) => fmtBytes(b.size_bytes) },
    { key: 'created', header: t.backups.requested, render: (b) => fmtDateTime(b.created_at) },
    { key: 'finished', header: t.backups.finished, render: (b) => fmtDateTime(b.finished_at) },
    { key: 'expires', header: t.backups.expires, render: (b) => fmtDateTime(b.expires_at) },
    {
      key: 'actions',
      header: t.common.actions,
      render: (b) =>
        b.status === 'failed' && b.error_summary ? (
          <span className="text-xs text-red-600">{b.error_summary}</span>
        ) : (
          <DownloadButton backup={b} />
        ),
    },
  ]

  return (
    <TenantGate>
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{t.backups.title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-gray-500">{t.backups.explainer}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <button
            onClick={() => create.mutate('full')}
            disabled={create.isPending || hasActive}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {create.isPending && <Spinner className="h-4 w-4 text-white" />}
            📦 {t.backups.createFull}
          </button>
          <button
            onClick={() => create.mutate('incremental')}
            disabled={create.isPending || hasActive}
            className="inline-flex items-center gap-2 rounded-lg border border-primary-600 px-4 py-2 text-sm font-semibold text-primary-700 hover:bg-primary-50 disabled:opacity-50"
          >
            {t.backups.createIncremental}
          </button>
          {createError && <span className="text-sm text-red-600">{createError}</span>}
        </div>

        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          {backups.isLoading ? (
            <LoadingBlock />
          ) : backups.isError ? (
            <ErrorState
              message={errMsg(backups.error) ?? undefined}
              onRetry={() => backups.refetch()}
            />
          ) : (
            <DataTable
              columns={columns}
              rows={backups.data ?? []}
              rowKey={(b) => b.id}
              emptyMessage={t.backups.noBackups}
            />
          )}
        </div>
      </div>
    </TenantGate>
  )
}
