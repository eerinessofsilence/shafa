export type PageId =
  | 'dashboard'
  | 'accounts'
  | 'parsing'
  | 'stats'
  | 'settings';

export type StatusTone = 'success' | 'warning' | 'info' | 'danger' | 'neutral';

export type MetricAccent = 'teal' | 'amber' | 'blue' | 'rose';

export interface DesktopShellInfo {
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
  open_browser: boolean;
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

export interface ApiAccountCreate {
  name: string;
  phone: string;
  path: string;
  open_browser: boolean;
  timer_minutes: number;
  channel_links: string[];
  branch?: string;
}

export interface ApiAccountUpdate {
  name?: string;
  path?: string;
  open_browser?: boolean;
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
  path: string;
  branch: string;
  browser: string;
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
