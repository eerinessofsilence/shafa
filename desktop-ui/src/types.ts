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

export type TelegramPhotoSource = 'Сообщение' | 'Комментарии' | 'Два в одном';

export interface TelegramChannel {
  id: string;
  title: string;
  handle: string;
  photoSource: TelegramPhotoSource;
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
  telegramChannels: TelegramChannel[];
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
