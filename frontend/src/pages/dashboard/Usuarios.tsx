import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { fmtDecimal, fmtNumber } from '../../lib/format'
import { t } from '../../i18n/es'
import { ChartCard, KpiCard } from '../../components/ui'
import {
  DateRangeFilter,
  DonutChart,
  HorizontalBars,
  StackedBars,
  TenantGate,
  errMsg,
  pivotByAgent,
  useDateRange,
} from './shared'
import type {
  FirstResponseRow,
  MetricsSummary,
  PeriodRow,
  SessionsByAgentRow,
} from '../../lib/types'

export function DashboardUsuarios() {
  const { tenantParam, needsTenantSelection } = useAuth()
  const { range, setRange, iso } = useDateRange()
  const [agent, setAgent] = useState('')

  const baseParams = useMemo(
    () => ({
      tenant_id: tenantParam,
      from: iso.from,
      to: iso.to,
    }),
    [tenantParam, iso.from, iso.to],
  )
  const params = useMemo(
    () => ({ ...baseParams, agent_id: agent || undefined }),
    [baseParams, agent],
  )
  const enabled = !needsTenantSelection

  const summary = useQuery({
    queryKey: ['metrics', 'summary', params],
    queryFn: () => api<MetricsSummary>('/metrics/summary', { params }),
    enabled,
  })
  const sessionsByMonth = useQuery({
    queryKey: ['metrics', 'sessions-by-month', params],
    queryFn: () =>
      api<{ items: PeriodRow[] }>('/metrics/sessions-by-month', {
        params: { ...params, by_agent: true },
      }),
    enabled,
  })
  // Sin filtro de agente: alimenta el selector y las tortas por agente
  const sessionsByAgent = useQuery({
    queryKey: ['metrics', 'sessions-by-agent', baseParams],
    queryFn: () =>
      api<{ items: SessionsByAgentRow[] }>('/metrics/sessions-by-agent', { params: baseParams }),
    enabled,
  })
  const clientsByMonth = useQuery({
    queryKey: ['metrics', 'clients-by-month', params],
    queryFn: () =>
      api<{ items: PeriodRow[] }>('/metrics/clients-by-month', {
        params: { ...params, by_agent: true },
      }),
    enabled,
  })
  const firstResponse = useQuery({
    queryKey: ['metrics', 'first-response-by-agent', params],
    queryFn: () =>
      api<{ items: FirstResponseRow[] }>('/metrics/first-response-by-agent', { params }),
    enabled,
  })

  const sessionsPivot = useMemo(
    () => pivotByAgent(sessionsByMonth.data?.items ?? [], 'sessions'),
    [sessionsByMonth.data],
  )
  const clientsPivot = useMemo(
    () => pivotByAgent(clientsByMonth.data?.items ?? [], 'clients'),
    [clientsByMonth.data],
  )
  const agentOptions = useMemo(
    () =>
      (sessionsByAgent.data?.items ?? []).filter(
        (r): r is SessionsByAgentRow & { agent_id: string } => r.agent_id != null,
      ),
    [sessionsByAgent.data],
  )
  const agentRows = useMemo(() => {
    const items = sessionsByAgent.data?.items ?? []
    return agent ? items.filter((r) => r.agent_id === agent) : items
  }, [sessionsByAgent.data, agent])

  const s = summary.data

  return (
    <TenantGate>
      <div className="space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{t.dashboards.usuariosTitle}</h1>
          <p className="text-sm text-gray-500">{t.dashboards.usuariosSubtitle}</p>
        </div>

        {/* Filtros globales */}
        <div className="flex flex-wrap items-end gap-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <DateRangeFilter range={range} onChange={setRange} />
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">{t.filters.agent}</label>
            <select
              value={agent}
              onChange={(e) => setAgent(e.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none"
            >
              <option value="">{t.filters.allAgents}</option>
              {agentOptions.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label={t.kpis.totalSessions}
            value={fmtNumber(s?.total_sessions)}
            loading={summary.isLoading}
          />
          <KpiCard
            label={t.kpis.uniqueClients}
            value={fmtNumber(s?.unique_clients)}
            loading={summary.isLoading}
          />
          <KpiCard
            label={t.kpis.avgFirstResponse}
            value={s?.avg_first_response_min != null ? fmtDecimal(s.avg_first_response_min) : '—'}
            loading={summary.isLoading}
          />
          <KpiCard
            label={t.kpis.pctNoAgent}
            value={s ? `${fmtDecimal(s.pct_sessions_no_agent)} %` : '—'}
            hint={s ? `${fmtNumber(s.sessions_no_agent)} ${t.charts.sessions.toLowerCase()}` : undefined}
            loading={summary.isLoading}
          />
        </div>

        {/* Gráficos */}
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <ChartCard
            title={t.charts.sessionsByMonthByAgent}
            className="xl:col-span-2"
            loading={sessionsByMonth.isLoading}
            error={errMsg(sessionsByMonth.error)}
            onRetry={() => sessionsByMonth.refetch()}
            empty={sessionsPivot.data.length === 0}
          >
            <StackedBars data={sessionsPivot.data} series={sessionsPivot.series} />
          </ChartCard>
          <ChartCard
            title={t.charts.sessionsByAgent}
            loading={sessionsByAgent.isLoading}
            error={errMsg(sessionsByAgent.error)}
            onRetry={() => sessionsByAgent.refetch()}
            empty={agentRows.length === 0}
          >
            <DonutChart
              data={agentRows.map((r) => ({ agent_name: r.agent_name, sessions: r.sessions }))}
              nameKey="agent_name"
              valueKey="sessions"
            />
          </ChartCard>
          <ChartCard
            title={t.charts.clientsByMonthByAgent}
            className="xl:col-span-2"
            loading={clientsByMonth.isLoading}
            error={errMsg(clientsByMonth.error)}
            onRetry={() => clientsByMonth.refetch()}
            empty={clientsPivot.data.length === 0}
          >
            <StackedBars data={clientsPivot.data} series={clientsPivot.series} />
          </ChartCard>
          <ChartCard
            title={t.charts.clientsByAgent}
            loading={sessionsByAgent.isLoading}
            error={errMsg(sessionsByAgent.error)}
            onRetry={() => sessionsByAgent.refetch()}
            empty={agentRows.length === 0}
          >
            <DonutChart
              data={agentRows.map((r) => ({ agent_name: r.agent_name, clients: r.clients }))}
              nameKey="agent_name"
              valueKey="clients"
            />
          </ChartCard>
          <ChartCard
            title={t.charts.firstResponseByAgent}
            className="xl:col-span-3"
            loading={firstResponse.isLoading}
            error={errMsg(firstResponse.error)}
            onRetry={() => firstResponse.refetch()}
            empty={(firstResponse.data?.items ?? []).length === 0}
          >
            <HorizontalBars
              data={(firstResponse.data?.items ?? []).map((r) => ({
                agent_name: r.agent_name,
                avg_minutes: r.avg_minutes,
              }))}
              nameKey="agent_name"
              valueKey="avg_minutes"
              name={t.charts.minutes}
            />
          </ChartCard>
        </div>
      </div>
    </TenantGate>
  )
}
