import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { t } from '../../i18n/es'
import { Badge, ErrorState, LoadingBlock } from '../../components/ui'
import { TenantGate, errMsg } from '../dashboard/shared'
import type { TenantSettingsOut, TenantSettingsUpdate } from '../../lib/types'

const inputClass =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="rounded-xl border border-gray-200 p-4">
      <legend className="px-2 text-sm font-semibold text-gray-700">{title}</legend>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{children}</div>
    </fieldset>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  )
}

/** ISO UTC → valor de <input type="datetime-local"> (en UTC). */
function isoToLocalInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 16)
}

function SettingsForm({ settings, tenantId }: { settings: TenantSettingsOut; tenantId: string }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    botmaker_client_id: settings.botmaker_client_id ?? '',
    botmaker_secret_id: '',
    botmaker_token: '',
    botmaker_refresh_token: '',
    etl_schedule_cron: settings.etl_schedule_cron ?? '',
    etl_window_days: settings.etl_window_days != null ? String(settings.etl_window_days) : '',
    etl_initial_ts: isoToLocalInput(settings.etl_initial_ts),
    is_etl_enabled: settings.is_etl_enabled,
    logo_url: settings.logo_url ?? '',
    siniestros_queue: settings.siniestros_queue ?? '',
    siniestros_button: settings.siniestros_button ?? '',
  })
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const body: TenantSettingsUpdate = {
        is_etl_enabled: form.is_etl_enabled,
      }
      // Campos de texto: enviar solo si tienen valor (el backend ignora None)
      if (form.botmaker_client_id) body.botmaker_client_id = form.botmaker_client_id
      // Secretos write-only: solo si se completaron
      if (form.botmaker_secret_id) body.botmaker_secret_id = form.botmaker_secret_id
      if (form.botmaker_token) body.botmaker_token = form.botmaker_token
      if (form.botmaker_refresh_token) body.botmaker_refresh_token = form.botmaker_refresh_token
      if (form.etl_schedule_cron) body.etl_schedule_cron = form.etl_schedule_cron
      if (form.etl_window_days) body.etl_window_days = parseInt(form.etl_window_days, 10)
      if (form.etl_initial_ts) {
        const d = new Date(`${form.etl_initial_ts}:00Z`)
        if (!isNaN(d.getTime())) body.etl_initial_ts = d.toISOString()
      }
      if (form.logo_url) body.logo_url = form.logo_url
      if (form.siniestros_queue) body.siniestros_queue = form.siniestros_queue
      if (form.siniestros_button) body.siniestros_button = form.siniestros_button
      return api<TenantSettingsOut>(`/tenants/${encodeURIComponent(tenantId)}/settings`, {
        method: 'PUT',
        body,
      })
    },
    onSuccess: () => {
      setSaved(true)
      setForm((f) => ({ ...f, botmaker_secret_id: '', botmaker_token: '', botmaker_refresh_token: '' }))
      queryClient.invalidateQueries({ queryKey: ['tenant-settings', tenantId] })
      setTimeout(() => setSaved(false), 4000)
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value })

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Section title={t.admin.botmakerSection}>
        <div className="sm:col-span-2 space-y-1">
          <p className="text-xs text-gray-500">{t.admin.botmakerHint}</p>
          {settings.has_botmaker_credentials ? (
            <Badge tone="green">{t.admin.credentialsLoaded}</Badge>
          ) : (
            <Badge tone="yellow">{t.admin.credentialsMissing}</Badge>
          )}
        </div>
        <Field label={t.admin.botmakerClientId}>
          <input type="text" value={form.botmaker_client_id} onChange={set('botmaker_client_id')} className={inputClass} />
        </Field>
        <Field label={`${t.admin.botmakerSecretId} ${t.common.optional}`}>
          <input type="password" autoComplete="new-password" value={form.botmaker_secret_id} onChange={set('botmaker_secret_id')} className={inputClass} />
        </Field>
        <Field label={`${t.admin.botmakerToken} ${t.common.optional}`}>
          <input type="password" autoComplete="new-password" value={form.botmaker_token} onChange={set('botmaker_token')} className={inputClass} />
        </Field>
        <Field label={`${t.admin.botmakerRefreshToken} ${t.common.optional}`}>
          <input type="password" autoComplete="new-password" value={form.botmaker_refresh_token} onChange={set('botmaker_refresh_token')} className={inputClass} />
        </Field>
      </Section>

      <Section title={t.admin.etlSection}>
        <Field label={t.admin.etlCron}>
          <input type="text" placeholder="0 3 * * *" value={form.etl_schedule_cron} onChange={set('etl_schedule_cron')} className={inputClass} />
          <p className="mt-1 text-xs text-gray-400">{t.admin.etlCronHint}</p>
        </Field>
        <Field label={t.admin.etlWindowDays}>
          <input type="number" min={1} max={31} value={form.etl_window_days} onChange={set('etl_window_days')} className={inputClass} />
        </Field>
        <Field label={`${t.admin.etlInitialTs} (UTC)`}>
          <input type="datetime-local" value={form.etl_initial_ts} onChange={set('etl_initial_ts')} className={inputClass} />
        </Field>
        <div className="flex items-end pb-2">
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <input
              type="checkbox"
              checked={form.is_etl_enabled}
              onChange={(e) => setForm({ ...form, is_etl_enabled: e.target.checked })}
              className="h-4 w-4 rounded border-gray-300 text-primary-600"
            />
            {t.admin.etlEnabled}
          </label>
        </div>
      </Section>

      <Section title={t.admin.brandingSection}>
        <Field label={t.admin.logoUrl}>
          <input type="url" value={form.logo_url} onChange={set('logo_url')} className={inputClass} />
        </Field>
        <div className="hidden sm:block" />
        <Field label={t.admin.siniestrosQueue}>
          <input type="text" value={form.siniestros_queue} onChange={set('siniestros_queue')} className={inputClass} />
        </Field>
        <Field label={t.admin.siniestrosButton}>
          <input type="text" value={form.siniestros_button} onChange={set('siniestros_button')} className={inputClass} />
        </Field>
      </Section>

      {save.isError && <p className="text-sm text-red-600">{errMsg(save.error)}</p>}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={save.isPending}
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-50"
        >
          {save.isPending ? t.common.loading : t.common.save}
        </button>
        {saved && <span className="text-sm font-medium text-emerald-600">{t.admin.settingsSaved}</span>}
      </div>
    </form>
  )
}

export function SettingsTab() {
  const { selectedTenant } = useAuth()

  const settings = useQuery({
    queryKey: ['tenant-settings', selectedTenant],
    queryFn: () =>
      api<TenantSettingsOut>(`/tenants/${encodeURIComponent(selectedTenant!)}/settings`),
    enabled: !!selectedTenant,
  })

  return (
    <TenantGate>
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
        <h2 className="mb-4 text-sm font-semibold text-gray-700">
          {t.admin.settingsFor} <code className="text-primary-700">{selectedTenant}</code>
        </h2>
        {settings.isLoading ? (
          <LoadingBlock />
        ) : settings.isError ? (
          <ErrorState message={errMsg(settings.error) ?? undefined} onRetry={() => settings.refetch()} />
        ) : settings.data ? (
          <SettingsForm
            key={selectedTenant}
            settings={settings.data}
            tenantId={selectedTenant!}
          />
        ) : null}
      </div>
    </TenantGate>
  )
}
