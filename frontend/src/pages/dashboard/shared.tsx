/**
 * Piezas compartidas por los tres dashboards: filtros globales, helpers de
 * datos para Recharts y tarjeta de ranking.
 */
import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { dateInputToIso, fmtNumber, fmtPeriod, contactName } from '../../lib/format'
import { t } from '../../i18n/es'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui'
import type { ContactRankingRow, PeriodRow } from '../../lib/types'

export const CHART_COLORS = [
  '#4f46e5',
  '#0ea5e9',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#14b8a6',
  '#f97316',
  '#ec4899',
  '#64748b',
]

export function colorFor(index: number): string {
  return CHART_COLORS[index % CHART_COLORS.length]
}

export function errMsg(error: unknown): string | null {
  if (!error) return null
  if (error instanceof ApiError) return error.detail
  if (error instanceof Error) return error.message
  return t.common.error
}

// ——— Filtros globales ———

export interface DateRange {
  from: string // valor del input date (YYYY-MM-DD) o ''
  to: string
}

export function useDateRange() {
  const [range, setRange] = useState<DateRange>({ from: '', to: '' })
  const iso = useMemo(
    () => ({
      from: dateInputToIso(range.from),
      to: dateInputToIso(range.to, true),
    }),
    [range],
  )
  return { range, setRange, iso }
}

export function DateRangeFilter({
  range,
  onChange,
}: {
  range: DateRange
  onChange: (r: DateRange) => void
}) {
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-500">{t.common.from}</label>
        <input
          type="date"
          value={range.from}
          onChange={(e) => onChange({ ...range, from: e.target.value })}
          className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-500">{t.common.to}</label>
        <input
          type="date"
          value={range.to}
          onChange={(e) => onChange({ ...range, to: e.target.value })}
          className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
        />
      </div>
      {(range.from || range.to) && (
        <button
          onClick={() => onChange({ from: '', to: '' })}
          className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
        >
          {t.common.clear}
        </button>
      )}
    </div>
  )
}

export function GranularityToggle({
  value,
  onChange,
}: {
  value: 'day' | 'month'
  onChange: (g: 'day' | 'month') => void
}) {
  return (
    <div className="flex items-end">
      <div>
        <label className="mb-1 block text-xs font-medium text-gray-500">{t.filters.granularity}</label>
        <div className="flex overflow-hidden rounded-lg border border-gray-300">
          {(['day', 'month'] as const).map((g) => (
            <button
              key={g}
              onClick={() => onChange(g)}
              className={`px-3 py-1.5 text-sm ${
                value === g ? 'bg-primary-600 font-medium text-white' : 'bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {g === 'day' ? t.filters.byDay : t.filters.byMonth}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Aviso para superadmin sin tenant elegido. */
export function TenantGate({ children }: { children: React.ReactNode }) {
  const { needsTenantSelection } = useAuth()
  if (needsTenantSelection) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <EmptyState message={t.common.selectTenantPrompt} icon="🏢" />
      </div>
    )
  }
  return <>{children}</>
}

// ——— Transformaciones para Recharts ———

/**
 * Pivotea filas {period, agent_name, <valueKey>} a una fila por período con
 * una columna por agente (para barras apiladas) y devuelve la lista de series.
 */
export function pivotByAgent(
  items: PeriodRow[],
  valueKey: 'sessions' | 'clients',
): { data: Array<Record<string, string | number>>; series: string[] } {
  const byPeriod = new Map<string, Record<string, string | number>>()
  const series = new Set<string>()
  for (const row of items) {
    const agent = row.agent_name ?? t.charts.noAgent
    series.add(agent)
    let entry = byPeriod.get(row.period)
    if (!entry) {
      entry = { period: row.period }
      byPeriod.set(row.period, entry)
    }
    entry[agent] = ((entry[agent] as number) ?? 0) + (row[valueKey] ?? 0)
  }
  return {
    data: [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period))),
    series: [...series].sort(),
  }
}

/** Pivotea {period, template, sent} a fila por período con columna por template. */
export function pivotByTemplate(
  items: Array<{ period: string; template: string; sent: number }>,
): { data: Array<Record<string, string | number>>; series: string[] } {
  const byPeriod = new Map<string, Record<string, string | number>>()
  const series = new Set<string>()
  for (const row of items) {
    series.add(row.template)
    let entry = byPeriod.get(row.period)
    if (!entry) {
      entry = { period: row.period }
      byPeriod.set(row.period, entry)
    }
    entry[row.template] = ((entry[row.template] as number) ?? 0) + row.sent
  }
  return {
    data: [...byPeriod.values()].sort((a, b) => String(a.period).localeCompare(String(b.period))),
    series: [...series].sort(),
  }
}

const tooltipNumber = (value: number | string) => fmtNumber(Number(value))

// ——— Gráficos reutilizables ———

export function StackedBars({
  data,
  series,
  height = 280,
}: {
  data: Array<Record<string, string | number>>
  series: string[]
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="period" tickFormatter={fmtPeriod} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={tooltipNumber} allowDecimals={false} />
        <Tooltip formatter={tooltipNumber} labelFormatter={(l) => fmtPeriod(String(l))} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {series.map((s, i) => (
          <Bar key={s} dataKey={s} stackId="stack" fill={colorFor(i)} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

export function SimpleBars({
  data,
  dataKey,
  name,
  height = 280,
  color = CHART_COLORS[0],
}: {
  data: Array<Record<string, string | number>>
  dataKey: string
  name: string
  height?: number
  color?: string
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
        <XAxis dataKey="period" tickFormatter={fmtPeriod} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={tooltipNumber} allowDecimals={false} />
        <Tooltip formatter={tooltipNumber} labelFormatter={(l) => fmtPeriod(String(l))} />
        <Bar dataKey={dataKey} name={name} fill={color} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DonutChart({
  data,
  nameKey,
  valueKey,
  height = 280,
}: {
  data: Array<Record<string, string | number>>
  nameKey: string
  valueKey: string
  height?: number
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={nameKey}
          innerRadius="50%"
          outerRadius="80%"
          paddingAngle={2}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={colorFor(i)} />
          ))}
        </Pie>
        <Tooltip formatter={tooltipNumber} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

export function HorizontalBars({
  data,
  nameKey,
  valueKey,
  name,
  color = CHART_COLORS[1],
  height,
}: {
  data: Array<Record<string, string | number>>
  nameKey: string
  valueKey: string
  name: string
  color?: string
  height?: number
}) {
  const h = height ?? Math.max(220, data.length * 36 + 40)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={tooltipNumber} />
        <YAxis
          type="category"
          dataKey={nameKey}
          width={140}
          tick={{ fontSize: 11 }}
          interval={0}
        />
        <Tooltip formatter={tooltipNumber} />
        <Bar dataKey={valueKey} name={name} fill={color} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

// ——— Ranking de contactos ———

export function RankingCard({
  title,
  items,
  loading,
  error,
  onRetry,
}: {
  title: string
  items: ContactRankingRow[] | undefined
  loading: boolean
  error: unknown
  onRetry: () => void
}) {
  const max = Math.max(1, ...(items ?? []).map((i) => i.value))
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-gray-700">{title}</h3>
      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState message={errMsg(error) ?? undefined} onRetry={onRetry} />
      ) : !items || items.length === 0 ? (
        <EmptyState message={t.common.noData} icon="🏆" />
      ) : (
        <ul className="space-y-2">
          {items.map((row) => {
            const name = contactName(row.first_name, row.last_name)
            return (
              <li key={row.chat_id} className="text-sm">
                <div className="mb-0.5 flex items-baseline justify-between gap-2">
                  <span className="min-w-0 truncate font-medium text-gray-800">
                    {name || row.chat_id}
                    {name && <span className="ml-1 text-xs font-normal text-gray-400">{row.chat_id}</span>}
                  </span>
                  <span className="font-semibold text-gray-700">{fmtNumber(row.value)}</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-gray-100">
                  <div
                    className="h-1.5 rounded-full bg-primary-500"
                    style={{ width: `${Math.round((row.value / max) * 100)}%` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
