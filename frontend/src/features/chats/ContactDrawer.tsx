import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { contactName, fmtDateTime } from '../../lib/format'
import { t } from '../../i18n/es'
import { Badge, ErrorState, LoadingBlock } from '../../components/ui'
import type { ChatDetailOut } from '../../lib/types'

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</p>
      <p className="text-sm text-gray-800">{value || '—'}</p>
    </div>
  )
}

export function ContactDrawer({ chatId, onClose }: { chatId: string; onClose: () => void }) {
  const { tenantParam } = useAuth()
  const detail = useQuery({
    queryKey: ['chat-detail', chatId, tenantParam],
    queryFn: () =>
      api<ChatDetailOut>(`/chats/${encodeURIComponent(chatId)}`, {
        params: { tenant_id: tenantParam },
      }),
  })
  const d = detail.data

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-gray-900/40" onClick={onClose} aria-hidden />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
          <h2 className="text-base font-semibold text-gray-900">{t.chats.contactDetail}</h2>
          <button
            onClick={onClose}
            aria-label={t.common.close}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {detail.isLoading ? (
            <LoadingBlock />
          ) : detail.isError ? (
            <ErrorState onRetry={() => detail.refetch()} />
          ) : d ? (
            <div className="space-y-4">
              <Field label={t.chats.contactName} value={contactName(d.first_name, d.last_name)} />
              <Field label={t.chats.contactPhone} value={d.contact_id || d.chat_id} />
              <Field label={t.chats.contactEmail} value={d.email ?? ''} />
              <Field label={t.chats.contactCountry} value={d.country ?? ''} />
              <Field label={t.chats.contactCreated} value={fmtDateTime(d.creation_time)} />
              <Field label={t.chats.contactLastSession} value={fmtDateTime(d.last_session_creation_time)} />

              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
                  {t.chats.tags}
                </p>
                {d.tags.length === 0 ? (
                  <p className="text-sm text-gray-400">{t.chats.noTags}</p>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {d.tags.map((tag) => (
                      <Badge key={tag} tone="indigo">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
                  {t.chats.variables}
                </p>
                {Object.keys(d.variables).length === 0 ? (
                  <p className="text-sm text-gray-400">{t.chats.noVariables}</p>
                ) : (
                  <dl className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                    {Object.entries(d.variables).map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2 px-3 py-1.5 text-sm">
                        <dt className="text-gray-500">{k}</dt>
                        <dd className="text-right font-medium text-gray-800">{v ?? '—'}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  )
}
