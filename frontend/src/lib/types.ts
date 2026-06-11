/**
 * Tipos espejo del contrato real del backend (backend/app/schemas + routers v1).
 */

export type Role = 'superadmin' | 'tenant_admin' | 'viewer'

export interface UserOut {
  id: number
  email: string
  full_name: string
  role: Role
  tenant_id: string | null
  is_active: boolean
  created_at?: string | null
  last_login_at?: string | null
}

export interface MeOut extends UserOut {
  tenant_name?: string | null
  logo_url?: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  user: UserOut
}

// ——— Admin ———

export interface TenantOut {
  tenant_id: string
  tenant_name: string
  created_at?: string | null
}

export interface TenantSettingsOut {
  tenant_id: string
  botmaker_client_id: string | null
  has_botmaker_credentials: boolean
  etl_schedule_cron: string | null
  etl_initial_ts: string | null
  etl_window_days: number | null
  is_etl_enabled: boolean
  logo_url: string | null
  siniestros_queue: string | null
  siniestros_button: string | null
}

export interface TenantSettingsUpdate {
  botmaker_client_id?: string
  botmaker_secret_id?: string
  botmaker_token?: string
  botmaker_refresh_token?: string
  etl_schedule_cron?: string
  etl_initial_ts?: string
  etl_window_days?: number
  is_etl_enabled?: boolean
  logo_url?: string
  siniestros_queue?: string
  siniestros_button?: string
}

export interface EtlRunOut {
  id: number
  tenant_id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'ok' | 'partial' | 'failed'
  stats: Record<string, unknown> | null
  error_summary: string | null
}

export interface Paginated<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

// ——— Métricas ———

export interface MetricsSummary {
  total_sessions: number
  unique_clients: number
  avg_first_response_min: number | null
  sessions_no_agent: number
  pct_sessions_no_agent: number
  templates_sent: number
  sessions_started_by_external: number
}

export interface PeriodRow {
  period: string
  agent_name?: string
  sessions?: number
  clients?: number
}

export interface SessionsByAgentRow {
  agent_name: string
  agent_id: string | null
  sessions: number
  clients: number
}

export interface FirstResponseRow {
  agent_name: string
  avg_minutes: number
  sessions_considered: number
}

export interface TemplatesByPeriodRow {
  period: string
  template: string
  sent: number
}

export interface ButtonSegmentationRow {
  button: string
  times_selected: number
  sessions: number
}

export interface ContactRankingRow {
  chat_id: string
  first_name: string | null
  last_name: string | null
  value: number
}

export type RankingKind = 'sessions' | 'messages' | 'external' | 'templates'

// ——— Chats ———

export interface ChatListItem {
  chat_id: string
  contact_id: string | null
  first_name: string | null
  last_name: string | null
  last_message_time: string | null
  last_message_preview: string | null
  tags: string[]
}

export type ChatListOut = Paginated<ChatListItem>

export interface ChatDetailOut {
  chat_id: string
  contact_id: string | null
  channel_id: string | null
  first_name: string | null
  last_name: string | null
  email: string | null
  country: string | null
  creation_time: string | null
  last_session_creation_time: string | null
  variables: Record<string, string | null>
  tags: string[]
}

export interface MessageFileOut {
  file_type: string
  status: string
  content_type: string | null
  size_bytes: number | null
  has_file: boolean
}

export interface MessageLocation {
  latitude?: number | null
  longitude?: number | null
  name?: string | null
  address?: string | null
}

export interface MessageOut {
  id: string
  creation_time: string | null
  message_from: string | null
  agent_id: string | null
  agent_name: string | null
  session_id: string | null
  session_creation_time: string | null
  queue_id: string | null
  whatsapp_template_name: string | null
  content_type: string | null
  text: string | null
  selected_button: string | null
  buttons: string[]
  files: MessageFileOut[]
  location: MessageLocation | null
}

export interface ChatMessagesOut {
  chat_id: string
  items: MessageOut[]
  has_more: boolean
  next_before: string | null
}

// ——— Archivos ———

export interface FileUrlOut {
  url: string
  expires_in: number
  content_type: string | null
}

export interface FailedFileItem {
  message_id: string
  file_type: string
  status: string
  original_url: string
  downloaded_at: string | null
}

export interface FailedFilesOut extends Paginated<FailedFileItem> {
  counts_by_status: Record<string, number>
  counts_by_type: Record<string, number>
}

export interface RetryRequest {
  statuses?: string[]
  file_types?: string[]
  message_ids?: string[]
  limit?: number
}

export interface RetryJobOut {
  id: number
  tenant_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  filters: Record<string, unknown> | null
  counts_before: Record<string, number> | null
  counts_after: Record<string, number> | null
  processed: number | null
  created_at: string
  finished_at: string | null
  error_summary: string | null
}

// ——— Backups ———

export interface BackupOut {
  id: number
  tenant_id: string
  type: 'full' | 'incremental'
  status: 'pending' | 'running' | 'done' | 'failed'
  size_bytes: number | null
  created_at: string
  finished_at: string | null
  expires_at: string | null
  error_summary: string | null
}

export interface BackupDownloadOut {
  url: string
  expires_in: number
}
