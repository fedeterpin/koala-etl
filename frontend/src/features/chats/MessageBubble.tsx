import { fmtTime } from '../../lib/format'
import { t } from '../../i18n/es'
import { MediaAttachment } from './MediaAttachment'
import type { MessageOut } from '../../lib/types'

/**
 * Burbuja estilo WhatsApp:
 * - user → izquierda, blanca
 * - bot → derecha, verde claro
 * - agent → derecha, azul claro con el nombre del agente arriba
 */
export function MessageBubble({ message }: { message: MessageOut }) {
  const from = message.message_from ?? 'user'
  const isUser = from === 'user'
  const isAgent = from === 'agent'
  const isBot = from === 'bot'
  const alignRight = isAgent || isBot

  const bubbleColor = isAgent
    ? 'bg-sky-100'
    : isBot
      ? 'bg-emerald-100'
      : 'bg-white'

  return (
    <div className={`flex ${alignRight ? 'justify-end' : 'justify-start'} px-3 py-0.5`}>
      <div
        className={`max-w-[78%] rounded-2xl px-3 py-2 shadow-sm sm:max-w-[65%] ${bubbleColor} ${
          alignRight ? 'rounded-br-sm' : 'rounded-bl-sm'
        }`}
      >
        {isAgent && (
          <p className="mb-0.5 text-xs font-semibold text-sky-700">
            {message.agent_name || message.agent_id || t.chats.agent}
          </p>
        )}

        {message.whatsapp_template_name && (
          <span className="mb-1 inline-flex items-center gap-1 rounded-full bg-violet-100 px-2 py-0.5 text-[11px] font-medium text-violet-700">
            📋 {t.chats.template}: {message.whatsapp_template_name}
          </span>
        )}

        {message.text && (
          <p className="whitespace-pre-wrap break-words text-sm text-gray-800">{message.text}</p>
        )}

        {/* Chips de botones del bot; el seleccionado, resaltado */}
        {(message.buttons.length > 0 || message.selected_button) && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {message.buttons.map((b) => (
              <span
                key={b}
                className={`rounded-full border px-2 py-0.5 text-[11px] ${
                  b === message.selected_button
                    ? 'border-primary-500 bg-primary-600 font-semibold text-white'
                    : 'border-gray-300 bg-white text-gray-600'
                }`}
              >
                {b}
              </span>
            ))}
            {message.selected_button && !message.buttons.includes(message.selected_button) && (
              <span className="rounded-full border border-primary-500 bg-primary-600 px-2 py-0.5 text-[11px] font-semibold text-white">
                ✓ {message.selected_button}
              </span>
            )}
          </div>
        )}

        {message.files.map((f) => (
          <MediaAttachment key={f.file_type} messageId={message.id} file={f} />
        ))}

        {message.location &&
          message.location.latitude != null &&
          message.location.longitude != null && (
            <a
              href={`https://www.google.com/maps?q=${message.location.latitude},${message.location.longitude}`}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary-700 hover:underline"
            >
              📍 {message.location.name || message.location.address || t.chats.openInMaps}
            </a>
          )}

        <p className="mt-0.5 text-right text-[10px] text-gray-400">{fmtTime(message.creation_time)}</p>
      </div>
    </div>
  )
}
