import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import { fmtBytes } from '../../lib/format'
import { t } from '../../i18n/es'
import { Spinner } from '../../components/ui'
import { getFileUrl } from './mediaCache'
import type { MessageFileOut, RetryJobOut } from '../../lib/types'

function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/80 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <img src={src} alt={t.chats.imageAlt} className="max-h-full max-w-full rounded-lg shadow-2xl" />
      <button
        className="absolute right-4 top-4 rounded-full bg-white/10 px-3 py-1.5 text-white hover:bg-white/20"
        onClick={onClose}
        aria-label={t.common.close}
      >
        ✕
      </button>
    </div>
  )
}

/** Archivo no descargado: aviso gris + reintento para admins. */
function FailedFile({ messageId, file }: { messageId: string; file: MessageFileOut }) {
  const { isAdmin, tenantParam } = useAuth()
  const retry = useMutation({
    mutationFn: () =>
      api<RetryJobOut>('/files/retry', {
        method: 'POST',
        params: { tenant_id: tenantParam },
        body: { message_ids: [messageId], statuses: [file.status] },
      }),
  })

  return (
    <div className="mt-1 flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-100 px-3 py-2 text-xs text-gray-500">
      <span aria-hidden>📎</span>
      <span>
        {t.chats.fileNotDownloaded} ({file.status})
      </span>
      {isAdmin &&
        (retry.isSuccess ? (
          <span className="font-medium text-emerald-600">{t.chats.retryQueued}</span>
        ) : (
          <button
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
            className="font-medium text-primary-600 hover:underline disabled:opacity-50"
          >
            {retry.isPending ? t.common.loading : t.chats.retryDownload}
          </button>
        ))}
    </div>
  )
}

export function MediaAttachment({
  messageId,
  file,
}: {
  messageId: string
  file: MessageFileOut
}) {
  const { tenantParam } = useAuth()
  const [url, setUrl] = useState<string | null>(null)
  const [contentType, setContentType] = useState<string | null>(file.content_type)
  const [error, setError] = useState(false)
  const [lightbox, setLightbox] = useState(false)

  useEffect(() => {
    if (!file.has_file) return
    let cancelled = false
    getFileUrl(messageId, file.file_type, tenantParam)
      .then((res) => {
        if (cancelled) return
        setUrl(res.url)
        if (res.contentType) setContentType(res.contentType)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [messageId, file.file_type, file.has_file, tenantParam])

  if (!file.has_file) return <FailedFile messageId={messageId} file={file} />

  if (error) {
    return (
      <div className="mt-1 rounded-lg border border-gray-200 bg-gray-100 px-3 py-2 text-xs text-gray-500">
        {t.chats.mediaLoadError}
      </div>
    )
  }

  if (!url) {
    return (
      <div className="mt-1 flex h-16 w-40 items-center justify-center rounded-lg bg-gray-100">
        <Spinner className="h-4 w-4" />
      </div>
    )
  }

  const ct = contentType ?? ''
  if (ct.startsWith('image/')) {
    return (
      <>
        <button onClick={() => setLightbox(true)} className="mt-1 block">
          <img
            src={url}
            alt={t.chats.imageAlt}
            loading="lazy"
            className="max-h-48 max-w-full cursor-zoom-in rounded-lg object-cover shadow-sm"
          />
        </button>
        {lightbox && <Lightbox src={url} onClose={() => setLightbox(false)} />}
      </>
    )
  }
  if (ct.startsWith('audio/')) {
    return <audio controls src={url} className="mt-1 max-w-full" preload="none" />
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="mt-1 inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-primary-700 hover:bg-primary-50"
    >
      <span aria-hidden>📄</span>
      {t.chats.downloadFile} ({file.file_type}
      {file.size_bytes ? `, ${fmtBytes(file.size_bytes)}` : ''})
    </a>
  )
}
