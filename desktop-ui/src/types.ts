export type PageId =
  | 'dashboard'
  | 'accounts'
  | 'templates'
  | 'parsing'
  | 'logs'
  | 'settings';

export type StatusTone = 'success' | 'warning' | 'info' | 'danger' | 'neutral';

export type DashboardRangePreset =
  | 'all'
  | 'week'
  | 'month'
  | 'quarter'
  | 'custom';
export type MetricAccent = 'teal' | 'amber' | 'blue' | 'rose';
export type MetricKind =
  | 'accounts'
  | 'active'
  | 'items'
  | 'errors'
  | 'deactivated';

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
}

export interface Metric {
  kind: MetricKind;
  label: string;
  value: string;
  unit?: string;
  accent: MetricAccent;
}

export interface ChartPoint {
  date: string;
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
export type ApiProxyScheme = 'http' | 'https' | 'socks5';
export type ApiProxyStatus =
  | 'unknown'
  | 'healthy'
  | 'degraded'
  | 'failing'
  | 'disabled';

export interface ApiResolvedTelegramChannel {
  channel_id: number;
  title: string;
  alias: string;
}

export type ChannelTemplateType = 'clothes' | 'shoes';

export interface ApiChannelTemplateSummary {
  id: string;
  account_id?: string | null;
  name: string;
  type: ChannelTemplateType;
  links: string[];
  resolved_channels: ApiResolvedTelegramChannel[];
  created_at?: string;
  updated_at?: string;
}

export interface ApiChannelTemplateRead extends ApiChannelTemplateSummary {
  account_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApiProxySummary {
  id: string;
  name: string;
  scheme: ApiProxyScheme;
  status: ApiProxyStatus;
  assigned_accounts_count: number;
  max_accounts: number;
  enabled: boolean;
}

export interface ApiProxyRead {
  id: string;
  name: string;
  scheme: ApiProxyScheme;
  host: string;
  port: number;
  username: string;
  password: string;
  max_accounts: number;
  enabled: boolean;
  notes: string;
  status: ApiProxyStatus;
  assigned_accounts_count: number;
  total_requests: number;
  total_failures: number;
  consecutive_failures: number;
  last_used_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApiAccountRead {
  id: string;
  name: string;
  phone: string;
  path: string;
  branch: string;
  timer_minutes: number;
  markup_amount: number | null;
  channel_links: string[];
  proxy_id: string | null;
  status: ApiAccountStatus;
  last_run: string | null;
  errors: number;
  shafa_session_exists: boolean;
  telegram_session_exists: boolean;
  api_credentials_configured: boolean;
  created_at: string | null;
  updated_at: string | null;
  channel_templates: ApiChannelTemplateSummary[];
  proxy_summary: ApiProxySummary | null;
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

export interface ApiDashboardSharedDeactivationAccount {
  account_id: string;
  account_name: string | null;
  deactivated_success_count: number;
  not_found_treated_as_done_count: number;
  total_done_count: number;
  failed_count: number;
  pending_count: number;
  retry_scheduled_count: number;
}

export interface ApiDashboardRecentSharedDeactivation {
  account_id: string;
  account_name: string | null;
  telegram_product_key: string;
  channel_id: number | null;
  message_id: number | null;
  product_title: string | null;
  shafa_product_id: string;
  status: string;
  completed_at: string | null;
  reason: string | null;
  last_error: string | null;
}

export interface ApiDashboardSharedDeactivationSummary {
  total_deactivated_products: number;
  deactivated_success_count: number;
  not_found_treated_as_done_count: number;
  total_done_count: number;
  per_account: ApiDashboardSharedDeactivationAccount[];
  recent: ApiDashboardRecentSharedDeactivation[];
}

export interface ApiDashboardSummary {
  generated_at: string;
  range_start: string;
  range_end: string;
  total_accounts: number;
  active_accounts: number;
  ready_accounts: number;
  attention_accounts: number;
  item_successes_in_range: number;
  error_events_in_range: number;
  latest_run_account_name: string | null;
  latest_run_at: string | null;
  top_error_account_name: string | null;
  top_error_account_errors: number;
  series: ApiDashboardSeriesPoint[];
  shared_deactivation: ApiDashboardSharedDeactivationSummary;
}

export interface ApiAccountCreate {
  name: string;
  phone: string;
  path: string;
  timer_minutes: number;
  markup_amount?: number | null;
  channel_links: string[];
  proxy_id?: string | null;
  branch?: string;
}

export interface ApiAccountUpdate {
  name?: string;
  path?: string;
  timer_minutes?: number;
  markup_amount?: number | null;
  channel_links?: string[];
  proxy_id?: string | null;
}

export interface ApiProxyCreate {
  name: string;
  scheme: ApiProxyScheme;
  host: string;
  port: number;
  username?: string;
  password?: string;
  max_accounts?: number;
  enabled?: boolean;
  notes?: string;
}

export interface ApiProxyUpdate {
  name?: string;
  scheme?: ApiProxyScheme;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  max_accounts?: number;
  enabled?: boolean;
  notes?: string;
}

export interface ApiChannelTemplateCreate {
  name: string;
  type?: ChannelTemplateType;
  links: string[];
}

export interface ApiChannelTemplateUpdate {
  name?: string;
  type?: ChannelTemplateType;
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
  email: string;
  phone: string;
  message: string;
}

export interface AccountRow {
  id: string;
  name: string;
  phone?: string;
  path: string;
  branch: string;
  timer: string;
  markup: string;
  proxyId: string;
  proxySummary?: ApiProxySummary | null;
  errors: string;
  statusLabel: string;
  statusTone: StatusTone;
  shafaSessionExists?: boolean;
  telegramSessionExists?: boolean;
  telegramChannels: TelegramChannel[];
  channelTemplates?: ApiChannelTemplateSummary[];
}
