import { useMemo, useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useDebounce } from '../lib/useDebounce'
import { contactName, fmtRelative } from '../lib/format'
import { t } from '../i18n/es'
import { Badge, EmptyState, ErrorState, LoadingBlock, Spinner } from '../components/ui'
import { TenantGate, errMsg } from './dashboard/shared'
import { ChatTimeline } from '../features/chats/ChatTimeline'
import type { ChatListItem, ChatListOut } from '../lib/types'

function ChatListRow({
  chat,
  selected,
  onSelect,
}: {
  chat: ChatListItem
  selected: boolean
  onSelect: () => void
}) {
  const name = contactName(chat.first_name, chat.last_name)
  return (
    <button
      onClick={onSelect}
      className={`flex w-full flex-col gap-0.5 border-b border-gray-100 px-3 py-2.5 text-left transition-colors ${
        selected ? 'bg-primary-50' : 'hover:bg-gray-50'
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate text-sm font-semibold text-gray-900">
          {name || chat.chat_id}
        </span>
        <span className="shrink-0 text-[11px] text-gray-400">
          {fmtRelative(chat.last_message_time)}
        </span>
      </div>
      {name && <span className="truncate text-xs text-gray-400">{chat.chat_id}</span>}
      {chat.last_message_preview && (
        <span className="truncate text-xs text-gray-500">{chat.last_message_preview}</span>
      )}
      {chat.tags.length > 0 && (
        <span className="mt-0.5 flex flex-wrap gap-1">
          {chat.tags.slice(0, 3).map((tag) => (
            <Badge key={tag} tone="indigo">
              {tag}
            </Badge>
          ))}
          {chat.tags.length > 3 && <Badge tone="gray">+{chat.tags.length - 3}</Badge>}
        </span>
      )}
    </button>
  )
}

export function ConversacionesPage() {
  const { tenantParam, needsTenantSelection } = useAuth()
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)
  const [selected, setSelected] = useState<ChatListItem | null>(null)

  const chatsQuery = useInfiniteQuery({
    queryKey: ['chats', debouncedSearch, tenantParam],
    queryFn: ({ pageParam }) =>
      api<ChatListOut>('/chats', {
        params: {
          tenant_id: tenantParam,
          search: debouncedSearch || undefined,
          page: pageParam,
          page_size: 30,
        },
      }),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : null,
    enabled: !needsTenantSelection,
  })

  const chats = useMemo(
    () => (chatsQuery.data?.pages ?? []).flatMap((p) => p.items),
    [chatsQuery.data],
  )

  return (
    <TenantGate>
      <div className="flex h-[calc(100vh-8.5rem)] overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        {/* Lista de chats */}
        <div
          className={`flex w-full flex-col border-r border-gray-200 sm:w-80 sm:shrink-0 ${
            selected ? 'hidden sm:flex' : 'flex'
          }`}
        >
          <div className="border-b border-gray-200 p-3">
            <h1 className="mb-2 text-base font-bold text-gray-900">{t.chats.title}</h1>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t.chats.searchPlaceholder}
              className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />
          </div>
          <div className="flex-1 overflow-y-auto">
            {chatsQuery.isLoading ? (
              <LoadingBlock />
            ) : chatsQuery.isError ? (
              <div className="p-3">
                <ErrorState
                  message={errMsg(chatsQuery.error) ?? undefined}
                  onRetry={() => chatsQuery.refetch()}
                />
              </div>
            ) : chats.length === 0 ? (
              <EmptyState message={t.chats.noChats} icon="🔍" />
            ) : (
              <>
                {chats.map((c) => (
                  <ChatListRow
                    key={c.chat_id}
                    chat={c}
                    selected={selected?.chat_id === c.chat_id}
                    onSelect={() => setSelected(c)}
                  />
                ))}
                {chatsQuery.hasNextPage && (
                  <div className="flex justify-center p-3">
                    <button
                      onClick={() => chatsQuery.fetchNextPage()}
                      disabled={chatsQuery.isFetchingNextPage}
                      className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-60"
                    >
                      {chatsQuery.isFetchingNextPage && <Spinner className="h-4 w-4" />}
                      {t.common.loadMore}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Timeline */}
        <div className={`min-w-0 flex-1 ${selected ? 'flex' : 'hidden sm:flex'} flex-col`}>
          {selected ? (
            <>
              <button
                onClick={() => setSelected(null)}
                className="border-b border-gray-200 px-3 py-1.5 text-left text-xs font-medium text-primary-700 sm:hidden"
              >
                ← {t.chats.title}
              </button>
              <ChatTimeline key={selected.chat_id} chat={selected} />
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center bg-gray-50">
              <EmptyState message={t.chats.selectChat} icon="💬" />
            </div>
          )}
        </div>
      </div>
    </TenantGate>
  )
}
