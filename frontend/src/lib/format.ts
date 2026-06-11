/**
 * Formato de fechas y números en es-AR (huso horario argentino, §11.8:
 * la DB guarda UTC; la conversión es solo de presentación).
 */

const TZ = 'America/Argentina/Buenos_Aires'
const LOCALE = 'es-AR'

const dateFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
})

const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

const timeFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TZ,
  hour: '2-digit',
  minute: '2-digit',
})

const dayLongFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TZ,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

const numberFmt = new Intl.NumberFormat(LOCALE)
const decimalFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 })

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  return isNaN(d.getTime()) ? null : d
}

export function fmtDate(value: string | Date | null | undefined): string {
  const d = toDate(value)
  return d ? dateFmt.format(d) : '—'
}

export function fmtDateTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  return d ? dateTimeFmt.format(d) : '—'
}

export function fmtTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  return d ? timeFmt.format(d) : '—'
}

export function fmtDayLong(value: string | Date | null | undefined): string {
  const d = toDate(value)
  return d ? dayLongFmt.format(d) : '—'
}

/** Clave de día en hora argentina (para separadores del timeline). */
export function dayKey(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return ''
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(d)
}

/** Fecha relativa corta para la lista de chats: hora si es hoy, día si es esta semana, fecha si no. */
export function fmtRelative(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return ''
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const oneDay = 24 * 60 * 60 * 1000
  if (dayKey(d) === dayKey(now)) return timeFmt.format(d)
  if (diffMs < 7 * oneDay) {
    return new Intl.DateTimeFormat(LOCALE, { timeZone: TZ, weekday: 'short' }).format(d)
  }
  return dateFmt.format(d)
}

export function fmtNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return numberFmt.format(value)
}

export function fmtDecimal(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return decimalFmt.format(value)
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = ''
  for (const u of units) {
    value /= 1024
    unit = u
    if (value < 1024) break
  }
  return `${decimalFmt.format(value)} ${unit}`
}

/** Duración legible entre dos timestamps. */
export function fmtDuration(start: string | null, end: string | null): string {
  const a = toDate(start)
  const b = toDate(end)
  if (!a || !b) return '—'
  const secs = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000))
  if (secs < 60) return `${secs} s`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min ${secs % 60} s`
  return `${Math.floor(mins / 60)} h ${mins % 60} min`
}

/** "2025-03" / "2025-03-15" → etiqueta amigable para ejes. */
export function fmtPeriod(period: string): string {
  if (/^\d{4}-\d{2}$/.test(period)) {
    const [y, m] = period.split('-')
    const months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
    return `${months[parseInt(m, 10) - 1]} ${y}`
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) {
    const [, m, d] = period.split('-')
    return `${d}/${m}`
  }
  return period
}

/**
 * Convierte un valor de <input type="date"> a ISO UTC interpretándolo como
 * inicio (o fin) del día en hora argentina (-03:00).
 */
export function dateInputToIso(value: string, endOfDay = false): string | undefined {
  if (!value) return undefined
  const suffix = endOfDay ? 'T23:59:59-03:00' : 'T00:00:00-03:00'
  const d = new Date(`${value}${suffix}`)
  return isNaN(d.getTime()) ? undefined : d.toISOString()
}

export function contactName(first: string | null | undefined, last: string | null | undefined): string {
  const name = [first, last].filter(Boolean).join(' ').trim()
  return name || ''
}
