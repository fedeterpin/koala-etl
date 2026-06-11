import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateInputToIso, fmtDateTime, fmtNumber } from '../lib/format'
import { t } from '../i18n/es'
import {
  Badge,
  DataTable,
  ErrorState,
  LoadingBlock,
  Pager,
  Spinner,
  statusTone,
} from '../components/ui'
import type { Column } from '../components/ui'
import { DateRangeFilter, TenantGate, errMsg } from './dashboard/shared'
import type { DateRange } from './dashboard/shared'
import type { FailedFileItem, FailedFilesOut, RetryJobOut } from '../lib/types'

const RETRYABLE = ['forbidden', 'not_found', 'error']
const HIDDEN_STATUSES = new Set(['ok', 'skipped'])

function statusLabel(s: string): string {
  return t.failed.statusLabels[s] ?? s
}

function CountsRow({ label, counts }: { label: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      {entries.length === 0 ? (
        <p className="text-sm text-gray-400">{t.common.noData}</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {entries.map(([key, count]) => (
            <div key={key} className="flex items-center gap-2">
              <Badge tone={statusTone(key)}>{statusLabel(key)}</Badge>
              <span className="text-lg font-semibold text-gray-800">{fmtNumber(count)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Estado del job de reintento en curso (poll cada 3 s hasta done/failed). */
function ActiveJobBanner({ jobId, onFinished }: { jobId: number; onFinished: () => void }) {
  const { tenantParam } = useAuth()
  const job = useQuery({
    queryKey: ['retry-job', jobId, tenantParam],
    queryFn: () =>
      api<RetryJobOut>(`/files/retry-jobs/${jobId}`, { params: { tenant_id: tenantParam } }),
    refetchInterval: (q) => {
      const st = q.state.data?.status
      return st === 'done' || st === 'failed' ? false : 3000
    },
  })
  const data = job.data
  const finished = data?.status === 'done' || data?.status === 'failed'

  // refrescar tabla cuando finaliza
  const queryClient = useQueryClient()
  useEffect(() => {
    if (finished) {
      queryClient.invalidateQueries({ queryKey: ['failed-files'] })
      queryClient.invalidateQueries({ queryKey: ['retry-jobs'] })
      onFinished()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished])

  return (
    <div
      className={`rounded-xl border p-4 text-sm ${
        data?.status === 'failed'
          ? 'border-red-200 bg-red-50 text-red-700'
          : data?.status === 'done'
            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
            : 'border-sky-200 bg-sky-50 text-sky-800'
      }`}
    >
      <div className="flex items-center gap-2 font-medium">
        {!finished && <Spinner className="h-4 w-4" />}
        {data?.status === 'done'
          ? t.failed.retryDone
          : data?.status === 'failed'
            ? t.failed.retryFailed
            : t.failed.retryStarted}
        {data?.processed != null && (
          <span className="font-normal">
            ({fmtNumber(data.processed)} {t.failed.processed})
          </span>
        )}
      </div>
      {data?.counts_before && data?.counts_after && (
        <div className="mt-2 flex flex-wrap gap-4">
          <span className="text-xs font-medium uppercase text-gray-500">{t.failed.beforeAfter}:</span>
          {RETRYABLE.map((s) => {
            const before = data.counts_before?.[s] ?? 0
            const after = data.counts_after?.[s] ?? 0
            return (
              <span key={s} className="text-xs">
                <Badge tone={statusTone(s)}>{statusLabel(s)}</Badge>{' '}
                <span className="font-semibold">
                  {fmtNumber(before)} → {fmtNumber(after)}
                </span>
              </span>
            )
          })}
        </div>
      )}
      {data?.error_summary && <p className="mt-1 text-xs">{data.error_summary}</p>}
    </div>
  )
}

export function DescargasFallidasPage() {
  const { tenantParam, needsTenantSelection } = useAuth()
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [range, setRange] = useState<DateRange>({ from: '', to: '' })
  const [page, setPage] = useState(1)
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const queryClient = useQueryClient()

  const params = useMemo(
    () => ({
      tenant_id: tenantParam,
      status: statusFilter || undefined,
      file_type: typeFilter || undefined,
      from: dateInputToIso(range.from),
      to: dateInputToIso(range.to, true),
      page,
      page_size: 50,
    }),
    [tenantParam, statusFilter, typeFilter, range, page],
  )

  const failed = useQuery({
    queryKey: ['failed-files', params],
    queryFn: () => api<FailedFilesOut>('/files/failed', { params }),
    enabled: !needsTenantSelection,
  })

  const jobs = useQuery({
    queryKey: ['retry-jobs', tenantParam],
    queryFn: () =>
      api<RetryJobOut[]>('/files/retry-jobs', { params: { tenant_id: tenantParam, limit: 10 } }),
    enabled: !needsTenantSelection,
  })

  const retryAll = useMutation({
    mutationFn: () =>
      api<RetryJobOut>('/files/retry', {
        method: 'POST',
        params: { tenant_id: tenantParam },
        body: {
          statuses: statusFilter ? [statusFilter] : RETRYABLE,
          file_types: typeFilter ? [typeFilter] : undefined,
          limit: 2000,
        },
      }),
    onSuccess: (job) => {
      setActiveJobId(job.id)
      queryClient.invalidateQueries({ queryKey: ['retry-jobs'] })
    },
  })

  const countsByStatus = useMemo(() => {
    const all = failed.data?.counts_by_status ?? {}
    return Object.fromEntries(Object.entries(all).filter(([s]) => !HIDDEN_STATUSES.has(s)))
  }, [failed.data])

  const typeOptions = useMemo(
    () => Object.keys(failed.data?.counts_by_type ?? {}).sort(),
    [failed.data],
  )

  const columns: Column<FailedFileItem>[] = [
    { key: 'message_id', header: t.failed.messageId, render: (r) => <code className="text-xs">{r.message_id}</code> },
    { key: 'file_type', header: t.failed.fileType, render: (r) => r.file_type },
    {
      key: 'status',
      header: t.common.status,
      render: (r) => <Badge tone={statusTone(r.status)}>{statusLabel(r.status)}</Badge>,
    },
    {
      key: 'url',
      header: t.failed.originalUrl,
      render: (r) => (
        <span className="block max-w-xs truncate text-xs text-gray-400" title={r.original_url}>
          {r.original_url}
        </span>
      ),
    },
    { key: 'date', header: t.failed.downloadedAt, render: (r) => fmtDateTime(r.downloaded_at) },
  ]

  return (
    <TenantGate>
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{t.failed.title}</h1>
          <p className="text-sm text-gray-500">{t.failed.subtitle}</p>
        </div>

        {/* Resumen */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CountsRow label={t.failed.byStatus} counts={countsByStatus} />
          <CountsRow label={t.failed.byType} counts={failed.data?.counts_by_type ?? {}} />
        </div>

        {/* Job activo */}
        {activeJobId !== null && (
          <ActiveJobBanner jobId={activeJobId} onFinished={() => undefined} />
        )}
        {retryAll.isError && <ErrorState message={errMsg(retryAll.error) ?? undefined} />}

        {/* Filtros + acción */}
        <div className="flex flex-wrap items-end gap-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">{t.failed.filterStatus}</label>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
            >
              <option value="">{t.common.all}</option>
              {RETRYABLE.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">{t.failed.filterType}</label>
            <select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
            >
              <option value="">{t.common.all}</option>
              {typeOptions.map((ty) => (
                <option key={ty} value={ty}>
                  {ty}
                </option>
              ))}
            </select>
          </div>
          <DateRangeFilter
            range={range}
            onChange={(r) => {
              setRange(r)
              setPage(1)
            }}
          />
          <button
            onClick={() => retryAll.mutate()}
            disabled={retryAll.isPending || (failed.data?.total ?? 0) === 0}
            className="ml-auto inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {retryAll.isPending && <Spinner className="h-4 w-4 text-white" />}
            {retryAll.isPending ? t.failed.retrying : t.failed.retryFiltered}
          </button>
        </div>

        {/* Tabla */}
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          {failed.isLoading ? (
            <LoadingBlock />
          ) : failed.isError ? (
            <ErrorState message={errMsg(failed.error) ?? undefined} onRetry={() => failed.refetch()} />
          ) : (
            <>
              <p className="mb-2 text-xs text-gray-500">
                {t.common.total}: {fmtNumber(failed.data?.total ?? 0)}
              </p>
              <DataTable
                columns={columns}
                rows={failed.data?.items ?? []}
                rowKey={(r) => `${r.message_id}-${r.file_type}`}
                emptyMessage={t.failed.noFailed}
              />
              <Pager
                page={page}
                pageSize={failed.data?.page_size ?? 50}
                total={failed.data?.total ?? 0}
                onPage={setPage}
              />
            </>
          )}
        </div>

        {/* Jobs recientes */}
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-sm font-semibold text-gray-700">{t.failed.recentJobs}</h2>
          {jobs.isLoading ? (
            <LoadingBlock />
          ) : (
            <DataTable
              columns={[
                { key: 'id', header: 'ID', render: (j: RetryJobOut) => `#${j.id}` },
                {
                  key: 'status',
                  header: t.common.status,
                  render: (j) => (
                    <Badge tone={statusTone(j.status)}>{t.failed.jobStatus[j.status] ?? j.status}</Badge>
                  ),
                },
                {
                  key: 'processed',
                  header: t.failed.processed,
                  render: (j) => (j.processed != null ? fmtNumber(j.processed) : '—'),
                },
                { key: 'created', header: t.common.date, render: (j) => fmtDateTime(j.created_at) },
                {
                  key: 'result',
                  header: t.failed.beforeAfter,
                  render: (j) =>
                    j.counts_before && j.counts_after ? (
                      <span className="text-xs">
                        {RETRYABLE.filter(
                          (s) => (j.counts_before?.[s] ?? 0) > 0 || (j.counts_after?.[s] ?? 0) > 0,
                        )
                          .map(
                            (s) =>
                              `${statusLabel(s)}: ${fmtNumber(j.counts_before?.[s] ?? 0)} → ${fmtNumber(j.counts_after?.[s] ?? 0)}`,
                          )
                          .join(' · ') || '—'}
                      </span>
                    ) : (
                      j.error_summary ?? '—'
                    ),
                },
              ]}
              rows={jobs.data ?? []}
              rowKey={(j) => j.id}
            />
          )}
        </div>
      </div>
    </TenantGate>
  )
}
