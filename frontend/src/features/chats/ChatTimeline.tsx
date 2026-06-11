import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { contactName, dayKey, fmtDayLong } from '../../lib/format'
import { t } from '../../i18n/es'
import { EmptyState, ErrorState, LoadingBlock, Spinner } from '../../components/ui'
import { ContactDrawer } from './ContactDrawer'
import { MessageBubble } from './MessageBubble'
import type { ChatListItem, ChatMessagesOut, MessageOut } from '../../lib/types'

type TimelineEntry =
  | { kind: 'date'; key: string; label: string }
  | { kind: 'session'; key: string; queue: string | null }
  | { kind: 'message'; key: string; message: MessageOut }

function buildTimeline(messages: MessageOut[]): TimelineEntry[] {
  const entries: TimelineEntry[] = []
  let lastDay = ''
  let lastSession: string | null | undefined
  for (const m of messages) {
    const day = dayKey(m.creation_time)
    if (day && day !== lastDay) {
      entries.push({ kind: 'date', key: `d-${day}`, label: fmtDayLong(m.creation_time) })
      lastDay = day
    }
    if (m.session_id && m.session_id !== lastSession) {
      entries.push({ kind: 'session', key: `s-${m.session_id}-${m.id}`, queue: m.queue_id })
      lastSession = m.session_id
    }
    entries.push({ kind: 'message', key: m.id, message: m })
  }
  return entries
}

export function ChatTimeline({ chat }: { chat: ChatListItem }) {
  const { tenantParam } = useAuth()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const prevHeightRef = useRef<number | null>(null)
  const lastChatRef = useRef<string | null>(null)

  const query = useInfiniteQuery({
    queryKey: ['chat-messages', chat.chat_id, tenantParam],
    queryFn: ({ pageParam }) =>
      api<ChatMessagesOut>(`/chats/${encodeURIComponent(chat.chat_id)}/messages`, {
        params: {
          tenant_id: tenantParam,
          before: pageParam ?? undefined,
          limit: 50,
        },
      }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => (last.has_more ? last.next_before : null),
  })

  // Mensajes en orden ascendente: las páginas llegan de la más nueva a la más vieja
  const messages = useMemo(() => {
    const pages = query.data?.pages ?? []
    return [...pages].reverse().flatMap((p) => p.items)
  }, [query.data])

  const timeline = useMemo(() => buildTimeline(messages), [messages])

  // Scroll: al fondo en la carga inicial / cambio de chat; mantener posición al cargar viejos
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (lastChatRef.current !== chat.chat_id) {
      if (messages.length > 0) {
        el.scrollTop = el.scrollHeight
        lastChatRef.current = chat.chat_id
      }
      return
    }
    if (prevHeightRef.current !== null) {
      el.scrollTop += el.scrollHeight - prevHeightRef.current
      prevHeightRef.current = null
    }
  }, [messages, chat.chat_id])

  const loadOlder = () => {
    prevHeightRef.current = scrollRef.current?.scrollHeight ?? null
    query.fetchNextPage()
  }

  const name = contactName(chat.first_name, chat.last_name)

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col">
      {/* Header del chat → abre detalle del contacto */}
      <button
        onClick={() => setDrawerOpen(true)}
        title={t.chats.viewContact}
        className="flex items-center gap-3 border-b border-gray-200 bg-white px-4 py-3 text-left hover:bg-gray-50"
      >
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary-100 text-base font-semibold text-primary-700">
          {(name || chat.chat_id).slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-gray-900">{name || chat.chat_id}</p>
          <p className="truncate text-xs text-gray-400">
            {name ? chat.chat_id : t.chats.viewContact}
          </p>
        </div>
      </button>

      {/* Timeline */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto bg-[#ece5dd] py-3"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(0,0,0,0.04) 1px, transparent 0)',
          backgroundSize: '18px 18px',
        }}
      >
        {query.isLoading ? (
          <LoadingBlock />
        ) : query.isError ? (
          <div className="px-4">
            <ErrorState onRetry={() => query.refetch()} />
          </div>
        ) : messages.length === 0 ? (
          <EmptyState message={t.chats.noMessages} icon="💬" />
        ) : (
          <>
            {query.hasNextPage && (
              <div className="mb-2 flex justify-center">
                <button
                  onClick={loadOlder}
                  disabled={query.isFetchingNextPage}
                  className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-1.5 text-xs font-medium text-gray-600 shadow hover:bg-gray-50 disabled:opacity-60"
                >
                  {query.isFetchingNextPage && <Spinner className="h-3 w-3" />}
                  {t.chats.loadOlder}
                </button>
              </div>
            )}
            {timeline.map((entry) => {
              if (entry.kind === 'date') {
                return (
                  <div key={entry.key} className="sticky top-1 z-10 my-2 flex justify-center">
                    <span className="rounded-full bg-white/95 px-3 py-1 text-[11px] font-medium text-gray-500 shadow">
                      {entry.label}
                    </span>
                  </div>
                )
              }
              if (entry.kind === 'session') {
                return (
                  <div key={entry.key} className="my-3 flex items-center gap-2 px-4">
                    <div className="h-px flex-1 bg-gray-400/40" />
                    <span className="rounded-full border border-gray-300 bg-gray-50 px-3 py-0.5 text-[11px] text-gray-500">
                      {t.chats.sessionStarted}
                      {entry.queue ? ` — ${t.chats.queue}: ${entry.queue}` : ''}
                    </span>
                    <div className="h-px flex-1 bg-gray-400/40" />
                  </div>
                )
              }
              return <MessageBubble key={entry.key} message={entry.message} />
            })}
          </>
        )}
      </div>

      {drawerOpen && <ContactDrawer chatId={chat.chat_id} onClose={() => setDrawerOpen(false)} />}
    </div>
  )
}
