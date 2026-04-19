export type PageId =
  | 'dashboard'
  | 'accounts'
  | 'parsing'
  | 'logs'
  | 'settings';

export type StatusTone = 'success' | 'warning' | 'info' | 'danger' | 'neutral';

export type MetricAccent = 'teal' | 'amber' | 'blue' | 'rose';

export interface DesktopShellInfo {
  apiBaseUrl: string;
  platform: string;
  electronVersion: string;
  chromeVersion: string;
  cwd: string;
}

export interface NavItem {
  id: PageId;
  label: string;
  caption: string;
}

export interface Metric {
  label: string;
  value: string;
  accent: MetricAccent;
}

export interface ChartPoint {
  label: string;
  items: number;
  errors: number;
}

export interface TelegramChannel {
  id: string;
  title: string;
  handle: string;
  photoSource?: string;
  channelId?: number;
  alias?: string;
}

export type ApiAccountStatus = 'started' | 'stopped';

export interface ApiResolvedTelegramChannel {
  channel_id: number;
  title: string;
  alias: string;
}

export interface ApiChannelTemplateSummary {
  id: string;
  name: string;
  links: string[];
  resolved_channels: ApiResolvedTelegramChannel[];
}

export interface ApiAccountRead {
  id: string;
  name: string;
  phone: string;
  path: string;
  branch: string;
  timer_minutes: number;
  channel_links: string[];
  status: ApiAccountStatus;
  last_run: string | null;
  errors: number;
  shafa_session_exists: boolean;
  telegram_session_exists: boolean;
  api_credentials_configured: boolean;
  created_at: string | null;
  updated_at: string | null;
  channel_templates: ApiChannelTemplateSummary[];
  extra: Record<string, unknown>;
}

export interface ApiAccountLogEntryRead {
  index: number;
  account_id: string;
  timestamp: string;
  level: string;
  message: string;
}

export interface ApiDashboardSeriesPoint {
  date: string;
  items: number;
  errors: number;
}

export interface ApiDashboardSummary {
  generated_at: string;
  total_accounts: number;
  active_accounts: number;
  ready_accounts: number;
  attention_accounts: number;
  item_successes_last_7_days: number;
  error_events_last_7_days: number;
  latest_run_account_name: string | null;
  latest_run_at: string | null;
  top_error_account_name: string | null;
  top_error_account_errors: number;
  series: ApiDashboardSeriesPoint[];
}

export interface ApiAccountCreate {
  name: string;
  phone: string;
  path: string;
  timer_minutes: number;
  channel_links: string[];
  branch?: string;
}

export interface ApiAccountUpdate {
  name?: string;
  path?: string;
  timer_minutes?: number;
  channel_links?: string[];
}

export interface ApiChannelTemplateCreate {
  name: string;
  links: string[];
}

export interface ApiChannelTemplateUpdate {
  name?: string;
  links?: string[];
}

export interface ApiTelegramPhoneRequest {
  phone: string;
}

export interface ApiTelegramCodeRequest {
  code: string;
}

export interface ApiTelegramPasswordRequest {
  password: string;
}

export interface ApiTelegramSessionCopyRequest {
  source_account_id: string;
}

export interface ApiTelegramAuthStatus {
  account_id: string;
  connected: boolean;
  has_api_credentials: boolean;
  current_step: string;
  next_step: string | null;
  phone_number: string;
  message: string;
}

export interface ApiShafaCookieInput {
  name: string;
  value: string;
  domain?: string;
  path?: string;
  expires?: number | null;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: string | null;
}

export interface ApiShafaStorageStateRequest {
  cookies?: ApiShafaCookieInput[];
  origins?: Array<Record<string, unknown>>;
  storage_state?: Record<string, unknown> | null;
}

export interface ApiShafaAuthStatus {
  account_id: string;
  connected: boolean;
  cookies_count: number;
  message: string;
}

export interface AccountRow {
  id: string;
  name: string;
  phone?: string;
  path: string;
  branch: string;
  timer: string;
  errors: string;
  statusLabel: string;
  statusTone: StatusTone;
  shafaSessionExists?: boolean;
  telegramSessionExists?: boolean;
  telegramChannels: TelegramChannel[];
  channelTemplates?: ApiChannelTemplateSummary[];
}

export interface StatusItem {
  label: string;
  value: string;
  badge: string;
  tone: StatusTone;
}

export interface AlertItem {
  title: string;
  copy: string;
  tone: StatusTone;
}

export interface NoteItem {
  title: string;
  copy: string;
}

export interface SettingToggle {
  label: string;
  copy: string;
  enabled: boolean;
}

export interface ParserQueueItem {
  title: string;
  copy: string;
  badge: string;
  tone: StatusTone;
}

export interface ParserResult {
  id: string;
  title: string;
  price: string;
  meta: string;
}

export interface LogRecordItem {
  time: string;
  account: string;
  level: string;
  tone: StatusTone;
  message: string;
}

export interface SettingsField {
  label: string;
  value: string;
}

export interface SettingsGroup {
  title: string;
  subtitle: string;
  fields: SettingsField[];
}
