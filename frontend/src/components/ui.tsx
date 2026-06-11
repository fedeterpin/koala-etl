/**
 * Componentes de UI reutilizables: Badge, Spinner, estados de carga/error/vacío,
 * KpiCard, ChartCard, Modal, ConfirmDialog, DataTable.
 */
import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { t } from '../i18n/es'

// ——— Badge ———

export type BadgeTone = 'gray' | 'green' | 'red' | 'yellow' | 'blue' | 'indigo' | 'orange'

const badgeTones: Record<BadgeTone, string> = {
  gray: 'bg-gray-100 text-gray-700',
  green: 'bg-emerald-100 text-emerald-800',
  red: 'bg-red-100 text-red-700',
  yellow: 'bg-amber-100 text-amber-800',
  blue: 'bg-sky-100 text-sky-800',
  indigo: 'bg-primary-100 text-primary-800',
  orange: 'bg-orange-100 text-orange-800',
}

export function Badge({ tone = 'gray', children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${badgeTones[tone]}`}
    >
      {children}
    </span>
  )
}

export function statusTone(status: string): BadgeTone {
  switch (status) {
    case 'ok':
    case 'done':
      return 'green'
    case 'running':
    case 'pending':
      return 'blue'
    case 'partial':
      return 'yellow'
    case 'failed':
    case 'error':
      return 'red'
    case 'forbidden':
      return 'orange'
    case 'not_found':
      return 'yellow'
    default:
      return 'gray'
  }
}

// ——— Spinner / Loading ———

export function Spinner({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg className={`animate-spin text-primary-600 ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

export function LoadingBlock({ label = t.common.loading }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-gray-500">
      <Spinner />
      <span>{label}</span>
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-gray-200 ${className}`} />
}

// ——— Error / Empty ———

export function ErrorState({
  message,
  onRetry,
}: {
  message?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-8 text-center">
      <p className="text-sm text-red-700">{message || t.common.error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
        >
          {t.common.retry}
        </button>
      )}
    </div>
  )
}

export function EmptyState({ message, icon = '🗂️' }: { message: string; icon?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <span className="text-3xl" aria-hidden>
        {icon}
      </span>
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  )
}

// ——— KpiCard ———

export function KpiCard({
  label,
  value,
  hint,
  loading,
}: {
  label: string
  value: ReactNode
  hint?: string
  loading?: boolean
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  )
}

// ——— ChartCard ———

export function ChartCard({
  title,
  children,
  loading,
  error,
  onRetry,
  empty,
  className = '',
}: {
  title: string
  children: ReactNode
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  empty?: boolean
  className?: string
}) {
  return (
    <div className={`rounded-xl border border-gray-100 bg-white p-4 shadow-sm ${className}`}>
      <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>
      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner className="h-7 w-7" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : empty ? (
        <EmptyState message={t.common.noData} icon="📊" />
      ) : (
        children
      )}
    </div>
  )
}

// ——— Modal ———

export function Modal({
  open,
  title,
  onClose,
  children,
  wide,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-gray-900/50" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        className={`relative w-full ${wide ? 'max-w-2xl' : 'max-w-md'} max-h-[90vh] overflow-y-auto rounded-xl bg-white p-5 shadow-xl`}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          <button
            onClick={onClose}
            aria-label={t.common.close}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

// ——— ConfirmDialog ———

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = t.common.confirm,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <p className="text-sm text-gray-600">{message}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          {t.common.cancel}
        </button>
        <button
          onClick={onConfirm}
          disabled={busy}
          className={`rounded-lg px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 ${
            danger ? 'bg-red-600 hover:bg-red-700' : 'bg-primary-600 hover:bg-primary-700'
          }`}
        >
          {busy ? t.common.loading : confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

// ——— DataTable ———

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  emptyMessage = t.common.noData,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  emptyMessage?: string
}) {
  if (rows.length === 0) return <EmptyState message={emptyMessage} icon="📭" />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 ${c.className ?? ''}`}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((row) => (
            <tr key={rowKey(row)} className="hover:bg-gray-50">
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-2 align-top text-gray-700 ${c.className ?? ''}`}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ——— Paginación simple ———

export function Pager({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number
  pageSize: number
  total: number
  onPage: (p: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1) return null
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-gray-600">
      <span>
        {t.common.page} {page} / {pages}
      </span>
      <div className="flex gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="rounded-lg border border-gray-300 px-3 py-1 disabled:opacity-40 hover:bg-gray-50"
        >
          {t.common.previous}
        </button>
        <button
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          className="rounded-lg border border-gray-300 px-3 py-1 disabled:opacity-40 hover:bg-gray-50"
        >
          {t.common.next}
        </button>
      </div>
    </div>
  )
}
