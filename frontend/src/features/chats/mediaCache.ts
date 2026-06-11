/**
 * Cache en memoria de URLs prefirmadas de archivos.
 * Las URLs expiran (~5 min): se guarda el vencimiento y se renueva al expirar.
 */
import { api } from '../../lib/api'
import type { FileUrlOut } from '../../lib/types'

interface CachedUrl {
  url: string
  contentType: string | null
  expiresAt: number // epoch ms
}

const cache = new Map<string, CachedUrl>()
const inflight = new Map<string, Promise<CachedUrl>>()

const EXPIRY_BUFFER_MS = 20_000

export async function getFileUrl(
  messageId: string,
  fileType: string,
  tenantParam: string | undefined,
): Promise<CachedUrl> {
  const key = `${tenantParam ?? ''}:${messageId}:${fileType}`
  const cached = cache.get(key)
  if (cached && cached.expiresAt > Date.now()) return cached

  let pending = inflight.get(key)
  if (!pending) {
    pending = api<FileUrlOut>(
      `/files/${encodeURIComponent(messageId)}/${encodeURIComponent(fileType)}/url`,
      { params: { tenant_id: tenantParam } },
    )
      .then((res) => {
        const entry: CachedUrl = {
          url: res.url,
          contentType: res.content_type,
          expiresAt: Date.now() + Math.max(30, res.expires_in) * 1000 - EXPIRY_BUFFER_MS,
        }
        cache.set(key, entry)
        return entry
      })
      .finally(() => {
        inflight.delete(key)
      })
    inflight.set(key, pending)
  }
  return pending
}
