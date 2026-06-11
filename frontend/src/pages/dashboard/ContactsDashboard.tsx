/**
 * Dashboard compartido por las vistas "Clientes" (context=general) y
 * "Siniestros" (context=siniestros, con granularidad día/mes conmutable).
 */
import { useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ApiError, api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { fmtNumber } from '../../lib/format'
import { t } from '../../i18n/es'
import { ChartCard, EmptyState, KpiCard } from '../../components/ui'
import {
  DateRangeFilter,
  GranularityToggle,
  HorizontalBars,
  RankingCard,
  SimpleBars,
  StackedBars,
  TenantGate,
  errMsg,
  pivotByTemplate,
  useDateRange,
} from './shared'
import type {
  ButtonSegmentationRow,
  ContactRankingRow,
  MetricsSummary,
  PeriodRow,
  RankingKind,
  TemplatesByPeriodRow,
} from '../../lib/types'

const RANKING_KINDS: Array<{ kind: RankingKind; title: string }> = [
  { kind: 'sessions', title: t.rankings.sessions },
  { kind: 'messages', title: t.rankings.messages },
  { kind: 'external', title: t.rankings.external },
  { kind: 'templates', title: t.rankings.templates },
]

export function ContactsDashboard({
  context,
  title,
  subtitle,
  withGranularity = false,
}: {
  context: 'general' | 'siniestros'
  title: string
  subtitle: string
  withGranularity?: boolean
}) {
  const { tenantParam, needsTenantSelection } = useAuth()
  const { range, setRange, iso } = useDateRange()
  const [granularity, setGranularity] = useState<'day' | 'month'>('month')
  const effectiveGranularity = withGranularity ? granularity : 'month'

  const params = useMemo(
    () => ({
      tenant_id: tenantParam,
      from: iso.from,
      to: iso.to,
      context,
    }),
    [tenantParam, iso.from, iso.to, context],
  )
  const enabled = !needsTenantSelection

  const summary = useQuery({
    queryKey: ['metrics', 'summary', params],
    queryFn: () => api<MetricsSummary>('/metrics/summary', { params }),
    enabled,
    retry: false,
  })

  // context=siniestros sin configurar → 400 del backend: aviso amigable
  const notConfigured =
    context === 'siniestros' &&
    summary.error instanceof ApiError &&
    summary.error.status === 400

  const chartsEnabled = enabled && !notConfigured

  const sessionsByPeriod = useQuery({
    queryKey: ['metrics', 'sessions-by-month', params, effectiveGranularity],
    queryFn: () =>
      api<{ items: PeriodRow[] }>('/metrics/sessions-by-month', {
        params: { ...params, granularity: effectiveGranularity },
      }),
    enabled: chartsEnabled,
  })
  const clientsByPeriod = useQuery({
    queryKey: ['metrics', 'clients-by-month', params, effectiveGranularity],
    queryFn: () =>
      api<{ items: PeriodRow[] }>('/metrics/clients-by-month', {
        params: { ...params, granularity: effectiveGranularity },
      }),
    enabled: chartsEnabled,
  })
  const buttons = useQuery({
    queryKey: ['metrics', 'button-segmentation', params],
    queryFn: () =>
      api<{ items: ButtonSegmentationRow[] }>('/metrics/button-segmentation', { params }),
    enabled: chartsEnabled,
  })
  const templates = useQuery({
    queryKey: ['metrics', 'templates-by-month', params, effectiveGranularity],
    queryFn: () =>
      api<{ items: TemplatesByPeriodRow[] }>('/metrics/templates-by-month', {
        params: { ...params, granularity: effectiveGranularity },
      }),
    enabled: chartsEnabled,
  })
  const rankings = useQueries({
    queries: RANKING_KINDS.map(({ kind }) => ({
      queryKey: ['metrics', 'contact-rankings', params, kind],
      queryFn: () =>
        api<{ kind: RankingKind; items: ContactRankingRow[] }>('/metrics/contact-rankings', {
          params: { ...params, kind, limit: 10 },
        }),
      enabled: chartsEnabled,
    })),
  })

  const templatesPivot = useMemo(
    () => pivotByTemplate(templates.data?.items ?? []),
    [templates.data],
  )

  const s = summary.data
  const periodLabel = effectiveGranularity === 'day' ? t.charts.sessionsByDay : t.charts.sessionsByMonth
  const clientsLabel = effectiveGranularity === 'day' ? t.charts.clientsByDay : t.charts.clientsByMonth
  const templatesLabel =
    effectiveGranularity === 'day' ? t.charts.templatesByDay : t.charts.templatesByMonth

  return (
    <TenantGate>
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{title}</h1>
          <p className="text-sm text-gray-500">{subtitle}</p>
        </div>

        <div className="flex flex-wrap items-end gap-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <DateRangeFilter range={range} onChange={setRange} />
          {withGranularity && <GranularityToggle value={granularity} onChange={setGranularity} />}
        </div>

        {notConfigured ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-6">
            <EmptyState message={t.dashboards.siniestrosNotConfigured} icon="⚙️" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard
                label={t.kpis.totalSessions}
                value={fmtNumber(s?.total_sessions)}
                loading={summary.isLoading}
              />
              <KpiCard
                label={t.kpis.startedByExternal}
                value={fmtNumber(s?.sessions_started_by_external)}
                loading={summary.isLoading}
              />
              <KpiCard
                label={t.kpis.templatesSent}
                value={fmtNumber(s?.templates_sent)}
                loading={summary.isLoading}
              />
              <KpiCard
                label={t.kpis.sessionsNoAgent}
                value={fmtNumber(s?.sessions_no_agent)}
                loading={summary.isLoading}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <ChartCard
                title={periodLabel}
                loading={sessionsByPeriod.isLoading}
                error={errMsg(sessionsByPeriod.error)}
                onRetry={() => sessionsByPeriod.refetch()}
                empty={(sessionsByPeriod.data?.items ?? []).length === 0}
              >
                <SimpleBars
                  data={(sessionsByPeriod.data?.items ?? []).map((r) => ({
                    period: r.period,
                    sessions: r.sessions ?? 0,
                  }))}
                  dataKey="sessions"
                  name={t.charts.sessions}
                />
              </ChartCard>
              <ChartCard
                title={clientsLabel}
                loading={clientsByPeriod.isLoading}
                error={errMsg(clientsByPeriod.error)}
                onRetry={() => clientsByPeriod.refetch()}
                empty={(clientsByPeriod.data?.items ?? []).length === 0}
              >
                <SimpleBars
                  data={(clientsByPeriod.data?.items ?? []).map((r) => ({
                    period: r.period,
                    clients: r.clients ?? 0,
                  }))}
                  dataKey="clients"
                  name={t.charts.clients}
                  color="#0ea5e9"
                />
              </ChartCard>
              <ChartCard
                title={t.charts.buttonSegmentation}
                loading={buttons.isLoading}
                error={errMsg(buttons.error)}
                onRetry={() => buttons.refetch()}
                empty={(buttons.data?.items ?? []).length === 0}
              >
                <HorizontalBars
                  data={(buttons.data?.items ?? []).map((r) => ({
                    button: r.button,
                    sessions: r.sessions,
                  }))}
                  nameKey="button"
                  valueKey="sessions"
                  name={t.charts.sessions}
                  color="#10b981"
                />
              </ChartCard>
              <ChartCard
                title={templatesLabel}
                loading={templates.isLoading}
                error={errMsg(templates.error)}
                onRetry={() => templates.refetch()}
                empty={templatesPivot.data.length === 0}
              >
                <StackedBars data={templatesPivot.data} series={templatesPivot.series} />
              </ChartCard>
            </div>

            <h2 className="pt-2 text-base font-semibold text-gray-800">{t.rankings.title}</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {RANKING_KINDS.map(({ kind, title: rTitle }, i) => (
                <RankingCard
                  key={kind}
                  title={rTitle}
                  items={rankings[i].data?.items}
                  loading={rankings[i].isLoading}
                  error={rankings[i].error}
                  onRetry={() => rankings[i].refetch()}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </TenantGate>
  )
}
