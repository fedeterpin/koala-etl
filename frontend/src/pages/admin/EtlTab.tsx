import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { fmtDateTime, fmtDuration } from '../../lib/format'
import { t } from '../../i18n/es'
import {
  Badge,
  DataTable,
  ErrorState,
  LoadingBlock,
  Pager,
  statusTone,
} from '../../components/ui'
import type { Column } from '../../components/ui'
import { TenantGate, errMsg } from '../dashboard/shared'
import type { EtlRunOut, Paginated } from '../../lib/types'

function StatsCell({ run }: { run: EtlRunOut }) {
  const [open, setOpen] = useState(false)
  if (!run.stats || Object.keys(run.stats).length === 0) return <span>—</span>
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-medium text-primary-700 hover:underline"
      >
        {open ? t.common.close : t.admin.viewStats}
      </button>
      {open && (
        <pre className="mt-1 max-h-48 max-w-md overflow-auto rounded-lg bg-gray-900 p-2 text-[11px] leading-snug text-gray-100">
          {JSON.stringify(run.stats, null, 2)}
        </pre>
      )}
    </div>
  )
}

export function EtlTab() {
  const { tenantParam, needsTenantSelection } = useAuth()
  const [page, setPage] = useState(1)

  const runs = useQuery({
    queryKey: ['etl-runs', tenantParam, page],
    queryFn: () =>
      api<Paginated<EtlRunOut>>('/etl/runs', {
        params: { tenant_id: tenantParam, page, page_size: 20 },
      }),
    enabled: !needsTenantSelection,
  })

  const columns: Column<EtlRunOut>[] = [
    { key: 'id', header: 'ID', render: (r) => `#${r.id}` },
    {
      key: 'status',
      header: t.common.status,
      render: (r) => <Badge tone={statusTone(r.status)}>{t.admin.runStatus[r.status] ?? r.status}</Badge>,
    },
    { key: 'started', header: t.admin.started, render: (r) => fmtDateTime(r.started_at) },
    {
      key: 'duration',
      header: t.admin.duration,
      render: (r) => fmtDuration(r.started_at, r.finished_at),
    },
    { key: 'stats', header: t.admin.stats, render: (r) => <StatsCell run={r} /> },
    {
      key: 'error',
      header: t.admin.errorSummary,
      render: (r) =>
        r.error_summary ? (
          <span className="block max-w-xs truncate text-xs text-red-600" title={r.error_summary}>
            {r.error_summary}
          </span>
        ) : (
          '—'
        ),
    },
  ]

  return (
    <TenantGate>
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-gray-700">{t.admin.etlRunsTitle}</h2>
        {runs.isLoading ? (
          <LoadingBlock />
        ) : runs.isError ? (
          <ErrorState message={errMsg(runs.error) ?? undefined} onRetry={() => runs.refetch()} />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={runs.data?.items ?? []}
              rowKey={(r) => r.id}
              emptyMessage={t.admin.noRuns}
            />
            <Pager
              page={page}
              pageSize={runs.data?.page_size ?? 20}
              total={runs.data?.total ?? 0}
              onPage={setPage}
            />
          </>
        )}
      </div>
    </TenantGate>
  )
}
