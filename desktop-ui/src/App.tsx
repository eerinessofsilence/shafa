import {
  buildAccountLogsWebSocketUrl,
  createAccount as createAccountRequest,
  deleteAccount as deleteAccountRequest,
  getAccount as getAccountRequest,
  listAccountLogs,
  listAccounts,
  startAccount as startAccountRequest,
  stopAccount as stopAccountRequest,
  updateAccount as updateAccountRequest,
} from './api/accounts';
import {
  copyTelegramSession,
  getShafaAuthStatus,
  getTelegramAuthStatus,
  logoutShafa,
  logoutTelegram,
  requestTelegramCode,
  saveShafaStorageState,
  startShafaBrowserLogin,
  submitTelegramCode,
  submitTelegramPassword,
} from './api/auth';
import {
  createChannelTemplate as createChannelTemplateRequest,
  deleteChannelTemplate as deleteChannelTemplateRequest,
  updateChannelTemplate as updateChannelTemplateRequest,
} from './api/channelTemplates';
import { getDashboardSummary } from './api/dashboard';
import { LineChart } from './components/LineChart';
import { MetricCard } from './components/MetricCard';
import { PageHeader } from './components/PageHeader';
import { Panel } from './components/Panel';
import { StatusPill } from './components/StatusPill';
import { navItems } from './data/mockData';
import type {
  AccountRow,
  ApiAccountCreate,
  ApiAccountLogEntryRead,
  ApiAccountRead,
  ApiChannelTemplateSummary,
  ApiDashboardSummary,
  ApiShafaAuthStatus,
  ApiShafaStorageStateRequest,
  ApiTelegramAuthStatus,
  ApiAccountUpdate,
  ChartPoint,
  DashboardRangePreset,
  Metric,
  PageId,
  StatusTone,
  TelegramChannel,
} from './types';
import {
  cardTitleClassName,
  cx,
  fieldLabelClassName,
  getButtonClassName,
  pageTitleClassName,
  sectionTitleClassName,
  type ButtonSize,
  type ButtonTone,
  type ButtonVariant,
} from './ui';
import {
  BarChart3,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileJson,
  FolderOpen,
  Info,
  LayoutGrid,
  Link2,
  LoaderCircle,
  LockKeyhole,
  LogIn,
  LogOut,
  Mail,
  Moon,
  PencilLine,
  Phone,
  Plus,
  Power,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  Trash2,
  Upload,
  TriangleAlert,
  User,
  Users,
  SunMedium,
  X,
  SlidersHorizontal,
  EllipsisVertical,
} from 'lucide-react';
import {
  type ChangeEvent,
  type ComponentPropsWithoutRef,
  type FormEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react';

const defaultTimerMinutes = 5;
const minimumTimerMinutes = 1;
const maximumTimerMinutes = 1440;
const productName = 'Shafa Control';
const accountControlClassName =
  'h-[42px] w-full rounded-[8px] border border-border bg-foreground px-4 text-[15px] text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10';
const telegramDraftInitialState = {
  handle: '',
};
const navItemIcons: Record<PageId, ReactNode> = {
  dashboard: <LayoutGrid className="h-4 w-4" />,
  accounts: <Users className="h-4 w-4" />,
  parsing: <Power className="h-4 w-4" />,
  logs: <BarChart3 className="h-4 w-4" />,
  settings: <Settings className="h-4 w-4" />,
};

type TelegramChannelDraft = Pick<TelegramChannel, 'handle'>;
type ActionTone = ButtonTone;
type AccountEditableField = 'name' | 'path' | 'timer';
type AccountDraft = Pick<AccountRow, AccountEditableField>;
type AccountSortField = 'name' | 'timer' | 'channels' | 'status' | 'errors';
type AccountSortDirection = 'asc' | 'desc';
type AccountBulkActionId = 'open' | 'close' | 'delete';
type PaginationEllipsisKey = 'left' | 'right';
type TablePageSize = (typeof accountPageSizeOptions)[number];
type PaginationItem =
  | { type: 'page'; value: number }
  | { type: 'ellipsis'; key: PaginationEllipsisKey };

const accountTableHeaders: Array<{
  id: AccountSortField;
  label: string;
}> = [
  { id: 'name', label: 'Имя' },
  { id: 'timer', label: 'Таймер' },
  { id: 'channels', label: 'Каналы' },
  { id: 'status', label: 'Статус' },
  { id: 'errors', label: 'Ошибки' },
];
const joinDisplayPath = (basePath: string, relativePath: string) => {
  const normalizedBasePath = basePath.trim().replace(/[\\/]+$/, '');

  if (!normalizedBasePath) {
    return '';
  }

  const separator = normalizedBasePath.includes('\\') ? '\\' : '/';
  const normalizedRelativePath = relativePath.replace(/^[\\/]+/, '');
  return `${normalizedBasePath}${separator}${normalizedRelativePath}`;
};
const legacyDefaultAccountProjectPath =
  '/Users/eeri/coding/python/projects/scripts/shafa';
const legacyDefaultAccountsDirectory = joinDisplayPath(
  legacyDefaultAccountProjectPath,
  'accounts',
);
const legacyDefaultLogsDirectory = joinDisplayPath(
  legacyDefaultAccountProjectPath,
  'runtime/logs',
);
const defaultAccountProjectPath = window.desktopShell?.cwd?.trim() ?? '';
const defaultAccountsDirectory = joinDisplayPath(defaultAccountProjectPath, 'accounts');
const defaultLogsDirectory = joinDisplayPath(defaultAccountProjectPath, 'runtime/logs');
const defaultChannelTemplateName = 'default';
const accountDraftInitialState: AccountDraft = {
  name: '',
  path: defaultAccountProjectPath,
  timer: `${defaultTimerMinutes} мин`,
};
const accountPageSizeOptions = [5, 10, 20, 50] as const;
const tablePaginationSelectClassName =
  'h-9 min-w-[4.75rem] appearance-none rounded-lg border border-border/18 bg-foreground/86 px-3 pr-8 text-[13px] font-medium text-text outline-none transition hover:border-border/34 hover:bg-foreground focus:border-info/30 focus:ring-2 focus:ring-info/12';
const tablePaginationButtonClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/18 bg-foreground/86 text-[13px] font-medium tabular-nums text-text-muted outline-none transition hover:border-border/34 hover:bg-foreground hover:text-text focus:border-info/30 focus:ring-2 focus:ring-info/12 disabled:pointer-events-none disabled:opacity-50';
const tablePaginationIconButtonClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/18 bg-foreground/86 text-text-muted outline-none transition hover:border-border/34 hover:bg-foreground hover:text-text focus:border-info/30 focus:ring-2 focus:ring-info/12 disabled:pointer-events-none disabled:opacity-50';
const tablePaginationCurrentPageClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/24 bg-secondary/72 text-[13px] font-semibold tabular-nums text-text shadow-[0_1px_0_rgba(255,255,255,0.03)]';
const tablePaginationJumpTriggerClassName = tablePaginationButtonClassName;
const tablePaginationJumpPopoverClassName =
  'absolute bottom-[calc(100%+8px)] left-1/2 z-20 flex w-36 -translate-x-1/2 flex-col gap-1.5 rounded-lg border border-border/18 bg-foreground p-2 shadow-[0_18px_40px_rgba(15,23,42,0.14)]';
const tablePaginationJumpInputClassName =
  'number-input-no-spin h-8 w-full rounded-md border border-border/18 bg-secondary/75 px-2.5 text-[13px] font-medium text-text outline-none transition hover:border-border/42 focus:border-info/42 focus:ring-2 focus:ring-info/16';
const allLogAccountsValue = '__all_accounts__';
const allLogLevelsValue = 'ALL';
const logLevelOptions = [
  { label: 'Все уровни', value: allLogLevelsValue },
  { label: 'Успех', value: 'SUCCESS' },
  { label: 'Только ошибки', value: 'ERROR' },
  { label: 'Предупреждения', value: 'WARNING' },
  { label: 'Инфо', value: 'INFO' },
  { label: 'Debug', value: 'DEBUG' },
] as const;
const logFilterSelectClassName =
  'h-[42px] min-w-[220px] appearance-none rounded-[8px] border border-border bg-foreground px-4 pr-11 text-[15px] font-normal text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10';
const logTableDesktopGridClassName =
  'xl:grid-cols-[minmax(180px,1.1fr)_minmax(128px,0.7fr)_minmax(0,2.55fr)_minmax(108px,0.6fr)]';
const logLevelBadgeClassNames: Record<StatusTone, string> = {
  success: 'border-success/12.5 bg-success/10 text-success',
  warning: 'border-warning/12.5 bg-warning/10 text-warning',
  info: 'border-info/12.5 bg-info/10 text-info',
  danger: 'border-error/12.5 bg-error/10 text-error',
  neutral: 'border-border/12.5 bg-foreground/75 text-text-muted',
};
const accountLogTimestampFormatter = new Intl.DateTimeFormat('en-US', {
  day: '2-digit',
  hour: 'numeric',
  hour12: true,
  minute: '2-digit',
  month: 'short',
  year: 'numeric',
});
const dashboardWeekdayLabelFormatter = new Intl.DateTimeFormat('ru-RU', {
  weekday: 'short',
});
const dashboardDateLabelFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
});
const accountPanelTimestampFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  hour: '2-digit',
  hour12: false,
  minute: '2-digit',
  month: 'short',
  year: 'numeric',
});
const settingsStorageKey = 'shafa.desktop.settings.v1';
const themeStorageKey = 'shafa.desktop.theme.v1';
const settingsFieldClassName =
  'h-[42px] w-full rounded-[8px] border border-border bg-foreground px-4 text-[15px] font-normal text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10';
const settingsTextAreaClassName =
  'h-[42px] w-full rounded-[8px] border border-border bg-foreground px-4 text-[13px] font-normal text-text-soft outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10';
const settingsPageClassName =
  "min-h-screen bg-background text-text antialiased transition-colors duration-200 [font-family:'Inter','Avenir_Next','Segoe_UI','Helvetica_Neue',sans-serif]";
const settingsPanelClassName =
  'rounded-[12px] border border-border bg-foreground px-6 py-6';
const settingsSubtleCardClassName = 'rounded-[8px] bg-secondary p-4';
const settingsToggleCardClassName =
  'rounded-[8px] border border-border bg-foreground p-4 transition-colors duration-200 hover:bg-secondary';
const settingsLabelClassName =
  'text-[12px] font-semibold uppercase tracking-[0.05em] text-text-subtle';
const settingsDescriptionClassName = 'text-[11px] text-text-muted/75';
const dashboardRangeOptions: Array<{
  id: DashboardRangePreset;
  label: string;
}> = [
  { id: 'all', label: 'Все дни' },
  { id: 'week', label: 'Неделя' },
  { id: 'month', label: 'Месяц' },
  { id: 'quarter', label: '3 мес.' },
  { id: 'custom', label: 'Кастом' },
];

type ThemeMode = 'dark' | 'light';

type InterfaceLanguage = 'ru' | 'uk' | 'en';
type DateTimeFormatId = 'ru-24' | 'uk-24' | 'en-12' | 'iso';

interface AppPreferences {
  interfaceLanguage: InterfaceLanguage;
  dateTimeFormat: DateTimeFormatId;
  autoRefreshSeconds: number;
  httpRetries: number;
  httpRetryDelaySeconds: number;
  httpRetryJitterEnabled: boolean;
  persistRawJson: boolean;
  accountsDirectory: string;
  logsDirectory: string;
}

const interfaceLanguageOptions = [
  { label: 'English', value: 'en' },
  { label: 'Russian', value: 'ru' },
  { label: 'Ukrainian', value: 'uk' },
] as const;

const dateTimeFormatOptions = [
  { label: 'Английский 12ч', preview: '21 Apr 2026, 2:35 PM', value: 'en-12' },
  { label: 'Русский 24ч', preview: '21 апр 2026, 14:35', value: 'ru-24' },
  { label: 'ISO', preview: '2026-04-21 14:35', value: 'iso' },
] as const;

const settingsSectionItems = [
  { id: 'interface', icon: SlidersHorizontal, label: 'Время и часовой пояс' },
  { id: 'http-retry', icon: RefreshCw, label: 'Повторы HTTP' },
  { id: 'working-paths', icon: FolderOpen, label: 'Рабочие пути' },
] as const;

function createDefaultAppPreferences(): AppPreferences {
  return {
    interfaceLanguage: 'ru',
    dateTimeFormat: 'ru-24',
    autoRefreshSeconds: 30,
    httpRetries: 3,
    httpRetryDelaySeconds: 5,
    httpRetryJitterEnabled: true,
    persistRawJson: false,
    accountsDirectory: defaultAccountsDirectory,
    logsDirectory: defaultLogsDirectory,
  };
}

interface AccountLogEntry {
  id: string;
  index: number;
  accountId: string;
  accountName: string;
  timestamp: string;
  level: string;
  tone: StatusTone;
  message: string;
}

function formatTimerLabel(minutes: number) {
  return `${minutes} мин`;
}

function extractTimerMinutes(value: string) {
  const digits = value.replace(/[^\d]/g, '');

  if (!digits) {
    return null;
  }

  const parsedValue = Number.parseInt(digits, 10);

  return Number.isFinite(parsedValue) ? parsedValue : null;
}

function isTimerValueValid(value: string) {
  const parsedValue = extractTimerMinutes(value);

  return (
    parsedValue !== null &&
    parsedValue >= minimumTimerMinutes &&
    parsedValue <= maximumTimerMinutes
  );
}

function clampTimerMinutes(value: number) {
  return Math.min(maximumTimerMinutes, Math.max(minimumTimerMinutes, value));
}

function parseTimerLabel(value: string) {
  const parsedValue = extractTimerMinutes(value);

  if (parsedValue === null || parsedValue < minimumTimerMinutes) {
    return defaultTimerMinutes;
  }

  return Math.min(parsedValue, maximumTimerMinutes);
}

function formatDateInputValue(value: Date) {
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, '0'),
    String(value.getDate()).padStart(2, '0'),
  ].join('-');
}

function createDefaultDashboardCustomRange() {
  const today = new Date();
  const rangeStart = new Date(today);
  rangeStart.setDate(today.getDate() - 6);

  return {
    start: formatDateInputValue(rangeStart),
    end: formatDateInputValue(today),
  };
}

function getDashboardPresetDays(
  preset: Exclude<DashboardRangePreset, 'all' | 'custom'>,
) {
  switch (preset) {
    case 'week':
      return 7;
    case 'month':
      return 30;
    case 'quarter':
      return 90;
  }
}

function formatDashboardSeriesLabel(
  value: string,
  preset: DashboardRangePreset,
) {
  const normalizedValue = value.trim();

  if (!normalizedValue) {
    return '—';
  }

  const parsedValue = new Date(`${normalizedValue}T00:00:00`);

  if (Number.isNaN(parsedValue.getTime())) {
    return normalizedValue;
  }

  const formattedValue =
    preset === 'week'
      ? dashboardWeekdayLabelFormatter.format(parsedValue).replace('.', '')
      : dashboardDateLabelFormatter.format(parsedValue).replace('.', '');

  return formattedValue.charAt(0).toUpperCase() + formattedValue.slice(1);
}

function formatDashboardMetricWindowLabel(preset: DashboardRangePreset) {
  switch (preset) {
    case 'all':
      return 'за все дни';
    case 'week':
      return 'за неделю';
    case 'month':
      return 'за месяц';
    case 'quarter':
      return 'за 3 месяца';
    case 'custom':
      return 'за период';
  }
}

function formatDashboardRunTimestamp(value: string | null) {
  if (!value) {
    return 'Запусков пока не было';
  }

  const parsedValue = new Date(value);

  if (Number.isNaN(parsedValue.getTime())) {
    return 'Запусков пока не было';
  }

  return formatAccountPanelDateTime(parsedValue);
}

function formatAccountDateTime(value: string | null | undefined) {
  if (!value) {
    return 'Не найдено';
  }

  const parsedValue = new Date(value);

  if (Number.isNaN(parsedValue.getTime())) {
    return 'Не найдено';
  }

  return formatAccountPanelDateTime(parsedValue);
}

function formatAccountPanelDateTime(value: Date) {
  const parts = accountPanelTimestampFormatter.formatToParts(value);
  const day = parts.find((part) => part.type === 'day')?.value;
  const month = parts.find((part) => part.type === 'month')?.value;
  const year = parts.find((part) => part.type === 'year')?.value;
  const hour = parts.find((part) => part.type === 'hour')?.value;
  const minute = parts.find((part) => part.type === 'minute')?.value;

  if (!day || !month || !year || !hour || !minute) {
    return accountPanelTimestampFormatter.format(value);
  }

  return `${day} ${month} ${year}, ${hour}:${minute}`;
}

function formatAccountTextValue(value: string | null | undefined) {
  const normalizedValue = String(value ?? '').trim();
  return normalizedValue || 'Не найдено';
}

function parseIntegerSetting(
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
) {
  const parsedValue =
    typeof value === 'number'
      ? value
      : Number.parseInt(String(value ?? '').trim(), 10);

  if (!Number.isFinite(parsedValue)) {
    return fallback;
  }

  return Math.min(maximum, Math.max(minimum, Math.round(parsedValue)));
}

function parseFloatSetting(
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
) {
  const parsedValue =
    typeof value === 'number'
      ? value
      : Number.parseFloat(
          String(value ?? '')
            .trim()
            .replace(',', '.'),
        );

  if (!Number.isFinite(parsedValue)) {
    return fallback;
  }

  return Math.min(maximum, Math.max(minimum, parsedValue));
}

function parseTextSetting(value: unknown, fallback: string) {
  const normalizedValue = typeof value === 'string' ? value.trim() : '';
  return normalizedValue || fallback;
}

function migrateLegacyWorkingPath(
  value: string,
  legacyPath: string,
  nextDefaultPath: string,
) {
  if (!nextDefaultPath || nextDefaultPath === legacyPath) {
    return value;
  }

  return value === legacyPath ? nextDefaultPath : value;
}

function normalizeAppPreferences(value: unknown): AppPreferences {
  const defaults = createDefaultAppPreferences();

  if (!value || typeof value !== 'object') {
    return defaults;
  }

  const payload = value as Record<string, unknown>;
  const interfaceLanguage = interfaceLanguageOptions.some(
    (option) => option.value === payload.interfaceLanguage,
  )
    ? (payload.interfaceLanguage as InterfaceLanguage)
    : defaults.interfaceLanguage;
  const dateTimeFormat = dateTimeFormatOptions.some(
    (option) => option.value === payload.dateTimeFormat,
  )
    ? (payload.dateTimeFormat as DateTimeFormatId)
    : defaults.dateTimeFormat;

  return {
    interfaceLanguage,
    dateTimeFormat,
    autoRefreshSeconds: parseIntegerSetting(
      payload.autoRefreshSeconds,
      defaults.autoRefreshSeconds,
      5,
      3600,
    ),
    httpRetries: parseIntegerSetting(
      payload.httpRetries,
      defaults.httpRetries,
      0,
      5,
    ),
    httpRetryDelaySeconds: parseFloatSetting(
      payload.httpRetryDelaySeconds,
      defaults.httpRetryDelaySeconds,
      0.1,
      30,
    ),
    httpRetryJitterEnabled:
      typeof payload.httpRetryJitterEnabled === 'boolean'
        ? payload.httpRetryJitterEnabled
        : defaults.httpRetryJitterEnabled,
    persistRawJson:
      typeof payload.persistRawJson === 'boolean'
        ? payload.persistRawJson
        : defaults.persistRawJson,
    accountsDirectory: migrateLegacyWorkingPath(
      parseTextSetting(payload.accountsDirectory, defaults.accountsDirectory),
      legacyDefaultAccountsDirectory,
      defaults.accountsDirectory,
    ),
    logsDirectory: migrateLegacyWorkingPath(
      parseTextSetting(payload.logsDirectory, defaults.logsDirectory),
      legacyDefaultLogsDirectory,
      defaults.logsDirectory,
    ),
  };
}

function normalizeThemeMode(value: unknown): ThemeMode {
  return value === 'light' ? 'light' : 'dark';
}

function loadStoredAppPreferences() {
  if (typeof window === 'undefined') {
    return createDefaultAppPreferences();
  }

  try {
    const rawValue = window.localStorage.getItem(settingsStorageKey);
    if (!rawValue) {
      return createDefaultAppPreferences();
    }

    return normalizeAppPreferences(JSON.parse(rawValue));
  } catch {
    return createDefaultAppPreferences();
  }
}

function loadStoredThemeMode() {
  if (typeof window === 'undefined') {
    return normalizeThemeMode(null);
  }

  try {
    return normalizeThemeMode(window.localStorage.getItem(themeStorageKey));
  } catch {
    return normalizeThemeMode(null);
  }
}

function getInitialActivePage(): PageId {
  if (typeof window === 'undefined') {
    return 'dashboard';
  }

  const hashPage = window.location.hash.replace(/^#/, '') as PageId;
  return navItems.some((item) => item.id === hashPage) ? hashPage : 'dashboard';
}

function buildPaginationItems(
  currentPage: number,
  totalPages: number,
): PaginationItem[] {
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, index) => ({
      type: 'page' as const,
      value: index + 1,
    }));
  }

  if (currentPage <= 3) {
    return [
      { type: 'page', value: 1 },
      { type: 'page', value: 2 },
      { type: 'page', value: 3 },
      { type: 'ellipsis', key: 'right' },
      { type: 'page', value: totalPages },
    ];
  }

  if (currentPage >= totalPages - 2) {
    return [
      { type: 'page', value: 1 },
      { type: 'ellipsis', key: 'left' },
      { type: 'page', value: totalPages - 2 },
      { type: 'page', value: totalPages - 1 },
      { type: 'page', value: totalPages },
    ];
  }

  return [
    { type: 'page', value: 1 },
    { type: 'ellipsis', key: 'left' },
    { type: 'page', value: currentPage - 1 },
    { type: 'page', value: currentPage },
    { type: 'page', value: currentPage + 1 },
    { type: 'ellipsis', key: 'right' },
    { type: 'page', value: totalPages },
  ];
}

interface TablePaginationFooterProps {
  currentPage: number;
  itemsPerPage: TablePageSize;
  itemCountLabel: string;
  nextPageAriaLabel: string;
  onItemsPerPageChange: (value: TablePageSize) => void;
  onPageChange: (page: number) => void;
  previousPageAriaLabel: string;
  totalItems: number;
  totalPages: number;
  visibleRangeEnd: number;
  visibleRangeStart: number;
}

function TablePaginationFooter({
  currentPage,
  itemsPerPage,
  itemCountLabel,
  nextPageAriaLabel,
  onItemsPerPageChange,
  onPageChange,
  previousPageAriaLabel,
  totalItems,
  totalPages,
  visibleRangeEnd,
  visibleRangeStart,
}: TablePaginationFooterProps) {
  const paginationItems = buildPaginationItems(currentPage, totalPages);
  const [activeJumpKey, setActiveJumpKey] =
    useState<PaginationEllipsisKey | null>(null);
  const [jumpPageValue, setJumpPageValue] = useState('');
  const jumpInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!activeJumpKey) {
      return;
    }

    jumpInputRef.current?.focus();
    jumpInputRef.current?.select();
  }, [activeJumpKey]);

  useEffect(() => {
    setActiveJumpKey(null);
    setJumpPageValue('');
  }, [currentPage, totalPages]);

  const closeJumpPicker = () => {
    setActiveJumpKey(null);
    setJumpPageValue('');
  };

  const toggleJumpPicker = (key: PaginationEllipsisKey) => {
    if (activeJumpKey === key) {
      closeJumpPicker();
      return;
    }

    setActiveJumpKey(key);
    setJumpPageValue('');
  };

  const handleJumpSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const parsedPage = Number.parseInt(jumpPageValue, 10);

    if (!Number.isFinite(parsedPage)) {
      jumpInputRef.current?.focus();
      return;
    }

    onPageChange(Math.min(totalPages, Math.max(1, parsedPage)));
    closeJumpPicker();
  };

  return (
    <div className="flex items-center justify-between gap-3 border-t border-border/25 px-5 py-3.5">
      <p className="text-[13px] text-text-muted">
        Показано{' '}
        {visibleRangeStart === 0 ? 0 : `${visibleRangeStart}-${visibleRangeEnd}`}{' '}
        из {totalItems} {itemCountLabel}
      </p>

      <div className="flex items-center gap-2.5">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] text-text-muted">На странице</span>
          <div className="relative">
            <select
              aria-label={`Количество ${itemCountLabel} на странице`}
              className={tablePaginationSelectClassName}
              value={String(itemsPerPage)}
              onChange={(event) =>
                onItemsPerPageChange(Number(event.target.value) as TablePageSize)
              }
            >
              {accountPageSizeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute top-1/2 right-2.5 h-3.5 w-3.5 -translate-y-1/2 text-text-muted" />
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            aria-label={previousPageAriaLabel}
            className={tablePaginationIconButtonClassName}
            disabled={currentPage === 1}
            type="button"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>

          {paginationItems.map((item, index) =>
            item.type === 'ellipsis' ? (
              <div
                key={`${item.key}-${index}`}
                className="relative"
                onBlurCapture={(event) => {
                  const nextTarget = event.relatedTarget;

                  if (
                    !(nextTarget instanceof Node) ||
                    !event.currentTarget.contains(nextTarget)
                  ) {
                    closeJumpPicker();
                  }
                }}
              >
                <button
                  aria-expanded={activeJumpKey === item.key}
                  aria-haspopup="dialog"
                  aria-label="Перейти к странице"
                  className={tablePaginationJumpTriggerClassName}
                  type="button"
                  onClick={() => toggleJumpPicker(item.key)}
                >
                  …
                </button>

                {activeJumpKey === item.key ? (
                  <form
                    className={tablePaginationJumpPopoverClassName}
                    onSubmit={handleJumpSubmit}
                  >
                    <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
                      Номер страницы
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        ref={jumpInputRef}
                        className={tablePaginationJumpInputClassName}
                        inputMode="numeric"
                        max={totalPages}
                        min={1}
                        placeholder={`1-${totalPages}`}
                        type="number"
                        value={jumpPageValue}
                        onChange={(event) =>
                          setJumpPageValue(event.target.value)
                        }
                        onKeyDown={(event) => {
                          if (event.key === 'Escape') {
                            closeJumpPicker();
                          }
                        }}
                      />
                      <button
                        className={getButtonClassName({
                          tone: 'info',
                          variant: 'solid',
                          size: 'sm',
                          className: 'h-8 rounded-md px-2.5 text-xs',
                        })}
                        type="submit"
                      >
                        OK
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
            ) : item.value === currentPage ? (
              <span
                key={item.value}
                aria-current="page"
                className={tablePaginationCurrentPageClassName}
              >
                {item.value}
              </span>
            ) : (
              <button
                key={item.value}
                aria-label={`Страница ${item.value}`}
                className={tablePaginationButtonClassName}
                type="button"
                onClick={() => onPageChange(item.value)}
              >
                {item.value}
              </button>
            ),
          )}

          <button
            aria-label={nextPageAriaLabel}
            className={tablePaginationIconButtonClassName}
            disabled={currentPage === totalPages}
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function getBrowseLabel(label: string) {
  return `Выбрать путь для поля «${label.toLowerCase()}»`;
}

function extractAccountExtraText(
  extra: Record<string, unknown>,
  keys: string[],
  validator?: (value: string) => boolean,
) {
  for (const key of keys) {
    const nextValue = extra[key];

    if (typeof nextValue !== 'string') {
      continue;
    }

    const normalizedValue = nextValue.trim();

    if (!normalizedValue) {
      continue;
    }

    if (!validator || validator(normalizedValue)) {
      return normalizedValue;
    }
  }

  return '';
}

function isLikelyEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/i.test(value.trim());
}

function createEmptyDashboardSeries(
  preset: DashboardRangePreset,
  customRange?: { end: string; start: string },
): ChartPoint[] {
  const today = new Date();
  const resolvedPreset =
    preset === 'all' || preset === 'custom' ? 'week' : preset;
  const rangeEnd = new Date(
    `${preset === 'custom' ? (customRange?.end ?? formatDateInputValue(today)) : formatDateInputValue(today)}T00:00:00`,
  );
  const rangeStart =
    preset === 'custom' && customRange
      ? new Date(`${customRange.start}T00:00:00`)
      : (() => {
          const nextStart = new Date(rangeEnd);
          nextStart.setDate(
            rangeEnd.getDate() - (getDashboardPresetDays(resolvedPreset) - 1),
          );
          return nextStart;
        })();
  const daysCount = Math.max(
    1,
    Math.round(
      (rangeEnd.getTime() - rangeStart.getTime()) / (24 * 60 * 60 * 1000),
    ) + 1,
  );

  return Array.from({ length: daysCount }, (_, index) => {
    const pointDate = new Date(rangeStart);
    pointDate.setDate(rangeStart.getDate() + index);
    const pointDateLabel = formatDateInputValue(pointDate);

    return {
      date: pointDateLabel,
      label: formatDashboardSeriesLabel(pointDateLabel, preset),
      items: 0,
      errors: 0,
    };
  });
}

function createDashboardMetrics(
  summary: ApiDashboardSummary | null,
  preset: DashboardRangePreset,
): Metric[] {
  const rangeLabel = formatDashboardMetricWindowLabel(preset);

  return [
    {
      kind: 'accounts',
      label: 'Всего аккаунтов',
      value: summary ? String(summary.total_accounts) : '—',
      unit: 'шт.',
      accent: 'teal',
    },
    {
      kind: 'active',
      label: 'Активные сейчас',
      value: summary ? String(summary.active_accounts) : '—',
      unit: 'онлайн',
      accent: 'amber',
    },
    {
      kind: 'items',
      label: `Товаров ${rangeLabel}`,
      value: summary ? String(summary.item_successes_in_range) : '—',
      unit: 'ед.',
      accent: 'blue',
    },
    {
      kind: 'errors',
      label: `Ошибок ${rangeLabel}`,
      value: summary ? String(summary.error_events_in_range) : '—',
      unit: 'лог.',
      accent: 'rose',
    },
  ];
}

function createDashboardSeries(
  summary: ApiDashboardSummary | null,
  preset: DashboardRangePreset,
  customRange?: { end: string; start: string },
): ChartPoint[] {
  if (!summary || summary.series.length === 0) {
    return createEmptyDashboardSeries(preset, customRange);
  }

  return summary.series.map((point) => ({
    date: point.date,
    label: formatDashboardSeriesLabel(point.date, preset),
    items: point.items,
    errors: point.errors,
  }));
}

function getAccountStatusMeta(
  status: ApiAccountRead['status'],
): Pick<AccountRow, 'statusLabel' | 'statusTone'> {
  return status === 'started'
    ? { statusLabel: 'started', statusTone: 'success' }
    : { statusLabel: 'stopped', statusTone: 'neutral' };
}

function getPrimaryChannelTemplate(
  templates: ApiChannelTemplateSummary[],
): ApiChannelTemplateSummary | null {
  return (
    templates.find(
      (template) => template.name === defaultChannelTemplateName,
    ) ??
    templates[0] ??
    null
  );
}

function mapLinksToTelegramChannels(
  accountId: string,
  links: string[],
  template: ApiChannelTemplateSummary | null,
): TelegramChannel[] {
  const resolvedChannels = template?.resolved_channels ?? [];

  return links.map((link, index) => {
    const resolvedChannel = resolvedChannels[index];

    return {
      id: `${template?.id ?? accountId}-channel-${index}`,
      title: resolvedChannel?.title || formatChannelTitle(link),
      handle: link,
      channelId: resolvedChannel?.channel_id,
      alias: resolvedChannel?.alias,
    };
  });
}

function mapApiAccountToRow(account: ApiAccountRead): AccountRow {
  const { statusLabel, statusTone } = getAccountStatusMeta(account.status);
  const primaryChannelTemplate = getPrimaryChannelTemplate(
    account.channel_templates,
  );
  const channelLinks = primaryChannelTemplate?.links.length
    ? primaryChannelTemplate.links
    : account.channel_links;

  return {
    id: account.id,
    name: account.name,
    phone: account.phone,
    path: account.path,
    branch: account.branch || 'main',
    timer: formatTimerLabel(account.timer_minutes),
    errors: String(account.errors),
    statusLabel,
    statusTone,
    shafaSessionExists: account.shafa_session_exists,
    telegramSessionExists: account.telegram_session_exists,
    telegramChannels: mapLinksToTelegramChannels(
      account.id,
      channelLinks,
      primaryChannelTemplate,
    ),
    channelTemplates: account.channel_templates,
  };
}

function createAccountCreatePayload(draft: AccountDraft): ApiAccountCreate {
  return {
    name: draft.name.trim(),
    phone: '',
    path: draft.path.trim(),
    timer_minutes: parseTimerLabel(draft.timer),
    channel_links: [],
  };
}

function createAccountUpdatePayload(draft: AccountDraft): ApiAccountUpdate {
  return {
    name: draft.name.trim(),
    path: draft.path.trim(),
    timer_minutes: parseTimerLabel(draft.timer),
  };
}

function formatApiError(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function joinUniqueMessages(messages: string[]) {
  const seen = new Set<string>();
  const uniqueMessages: string[] = [];

  for (const message of messages) {
    const normalizedMessage = message.trim();

    if (!normalizedMessage || seen.has(normalizedMessage)) {
      continue;
    }

    seen.add(normalizedMessage);
    uniqueMessages.push(normalizedMessage);
  }

  return uniqueMessages.join(' ');
}

function getAccountLogTone(level: string): StatusTone {
  switch (level.toUpperCase()) {
    case 'SUCCESS':
    case 'OK':
      return 'success';
    case 'ERROR':
    case 'CRITICAL':
      return 'danger';
    case 'WARNING':
      return 'warning';
    case 'INFO':
      return 'info';
    default:
      return 'neutral';
  }
}

function mapApiAccountLogEntryToEntry(
  entry: ApiAccountLogEntryRead,
  accountName = entry.account_id,
): AccountLogEntry {
  const normalizedLevel = entry.level.toUpperCase();

  return {
    id: `${entry.account_id}:${entry.index}`,
    index: entry.index,
    accountId: entry.account_id,
    accountName,
    timestamp: entry.timestamp,
    level: normalizedLevel,
    message: entry.message,
    tone: getAccountLogTone(normalizedLevel),
  };
}

function formatAccountLogTimestamp(timestamp: string) {
  const parsedTimestamp = new Date(timestamp);

  if (Number.isNaN(parsedTimestamp.getTime())) {
    return timestamp;
  }

  const parts = accountLogTimestampFormatter.formatToParts(parsedTimestamp);
  const day = parts.find((part) => part.type === 'day')?.value;
  const month = parts.find((part) => part.type === 'month')?.value;
  const year = parts.find((part) => part.type === 'year')?.value;
  const hour = parts.find((part) => part.type === 'hour')?.value;
  const minute = parts.find((part) => part.type === 'minute')?.value;
  const dayPeriod = parts.find((part) => part.type === 'dayPeriod')?.value;

  if (!day || !month || !year || !hour || !minute || !dayPeriod) {
    return accountLogTimestampFormatter.format(parsedTimestamp);
  }

  return `${day} ${month} ${year}, ${hour}:${minute} ${dayPeriod.toUpperCase()}`;
}

function getAccountLogTimestampValue(timestamp: string) {
  const parsedTimestamp = Date.parse(timestamp);

  return Number.isNaN(parsedTimestamp) ? 0 : parsedTimestamp;
}

function mergeAndSortAccountLogEntries(entries: AccountLogEntry[]) {
  const entryMap = new Map<string, AccountLogEntry>();

  entries.forEach((entry) => {
    entryMap.set(entry.id, entry);
  });

  return [...entryMap.values()]
    .sort((leftEntry, rightEntry) => {
      const timestampDifference =
        getAccountLogTimestampValue(rightEntry.timestamp) -
        getAccountLogTimestampValue(leftEntry.timestamp);

      if (timestampDifference !== 0) {
        return timestampDifference;
      }

      return rightEntry.index - leftEntry.index;
    })
    .slice(0, 120);
}

function resolveAccountLogError(
  failures: Array<{ accountName: string; error: unknown }>,
  fallback: string,
) {
  if (failures.length === 0) {
    return '';
  }

  if (failures.length === 1) {
    return `${failures[0].accountName}: ${formatApiError(
      failures[0].error,
      fallback,
    )}`;
  }

  return `Не удалось загрузить логи для ${failures.length} аккаунтов.`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseShafaImportInput(value: string): ApiShafaStorageStateRequest {
  const parsed = JSON.parse(value) as unknown;

  if (Array.isArray(parsed)) {
    return { cookies: parsed };
  }

  if (isRecord(parsed)) {
    if (isRecord(parsed.storage_state)) {
      return { storage_state: parsed.storage_state };
    }

    if (Array.isArray(parsed.cookies)) {
      return { storage_state: parsed };
    }
  }

  throw new Error(
    'Ожидается JSON storage state Playwright или массив cookies для Shafa.',
  );
}

function getTelegramStepMeta(status: ApiTelegramAuthStatus | null): {
  label: string;
  tone: StatusTone;
} {
  if (!status) {
    return { label: 'загрузка', tone: 'neutral' };
  }

  if (status.connected) {
    return { label: 'подключен', tone: 'success' };
  }

  switch (status.current_step) {
    case 'WAIT_CODE':
      return { label: 'ждёт код', tone: 'info' };
    case 'WAIT_PASSWORD':
      return { label: 'ждёт пароль', tone: 'warning' };
    case 'FAILED':
      return { label: 'ошибка', tone: 'danger' };
    case 'WAIT_PHONE':
      return { label: 'код запрошен', tone: 'info' };
    case 'INIT':
      return { label: 'не начат', tone: 'neutral' };
    case 'SUCCESS':
      return { label: 'подключен', tone: 'success' };
    default:
      return { label: status.current_step.toLowerCase(), tone: 'neutral' };
  }
}

function getShafaStatusMeta(status: ApiShafaAuthStatus | null): {
  label: string;
  tone: StatusTone;
} {
  if (!status) {
    return { label: 'загрузка', tone: 'neutral' };
  }

  return status.connected
    ? { label: 'подключен', tone: 'success' }
    : { label: 'не подключен', tone: 'warning' };
}

function getAccountSortValue(account: AccountRow, field: AccountSortField) {
  switch (field) {
    case 'name':
      return account.name;
    case 'timer':
      return Number.parseInt(account.timer, 10) || 0;
    case 'channels':
      return account.telegramChannels.length;
    case 'status':
      return account.statusLabel;
    case 'errors':
      return Number.parseInt(account.errors, 10) || 0;
  }
}

function normalizeTelegramHandle(value: string) {
  const cleanedValue = value
    .trim()
    .replace(/^https?:\/\/(www\.)?/i, '')
    .replace(/^telegram\.me\//i, 't.me/')
    .replace(/^@/, 't.me/')
    .replace(/[?#].*$/, '')
    .replace(/\/+$/, '');

  if (!cleanedValue) {
    return '';
  }

  if (cleanedValue.startsWith('t.me/')) {
    return cleanedValue;
  }

  return `t.me/${cleanedValue.replace(/^\/+/, '')}`;
}

function formatChannelTitle(handle: string) {
  const slug = normalizeTelegramHandle(handle)
    .replace(/^t\.me\//, '')
    .replace(/[_-]+/g, ' ')
    .trim();

  if (!slug) {
    return 'Новый канал';
  }

  return slug.replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}

function formatChannelBadge(handle: string) {
  const normalizedHandle = normalizeTelegramHandle(handle);

  if (!normalizedHandle) {
    return '@new_channel';
  }

  return `@${normalizedHandle.replace(/^t\.me\//, '')}`;
}

function normalizeTelegramLinks(links: string[]) {
  const uniqueLinks = new Set<string>();

  links.forEach((link) => {
    const normalizedHandle = normalizeTelegramHandle(link);

    if (normalizedHandle) {
      uniqueLinks.add(`https://${normalizedHandle}`);
    }
  });

  return [...uniqueLinks];
}

function getAccountDraftFromRow(account: AccountRow): AccountDraft {
  return {
    name: account.name,
    path: account.path,
    timer: account.timer,
  };
}

function isAccountDraftValid(draft: AccountDraft) {
  return Boolean(draft.name.trim()) && isTimerValueValid(draft.timer);
}

function formatAccountCount(count: number) {
  const lastDigit = count % 10;
  const lastTwoDigits = count % 100;

  if (lastDigit === 1 && lastTwoDigits !== 11) {
    return `${count} аккаунт`;
  }

  if (
    lastDigit >= 2 &&
    lastDigit <= 4 &&
    (lastTwoDigits < 12 || lastTwoDigits > 14)
  ) {
    return `${count} аккаунта`;
  }

  return `${count} аккаунтов`;
}

function App() {
  const [activePage, setActivePage] = useState<PageId>(getInitialActivePage);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() =>
    loadStoredThemeMode(),
  );
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [isAccountsLoading, setIsAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState('');
  const [isAccountMutationPending, setIsAccountMutationPending] =
    useState(false);
  const [appPreferences, setAppPreferences] = useState<AppPreferences>(() =>
    loadStoredAppPreferences(),
  );
  const [settingsDraft, setSettingsDraft] = useState<AppPreferences>(() =>
    loadStoredAppPreferences(),
  );
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [accountsItemsPerPage, setAccountsItemsPerPage] =
    useState<TablePageSize>(accountPageSizeOptions[0]);
  const [accountsCurrentPage, setAccountsCurrentPage] = useState(1);
  const [logsItemsPerPage, setLogsItemsPerPage] =
    useState<TablePageSize>(accountPageSizeOptions[0]);
  const [logsCurrentPage, setLogsCurrentPage] = useState(1);

  useEffect(() => {
    if (
      selectedAccountId &&
      !accounts.some((account) => account.id === selectedAccountId)
    ) {
      setSelectedAccountId('');
    }
  }, [accounts, selectedAccountId]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        settingsStorageKey,
        JSON.stringify(appPreferences),
      );
    } catch {
      return;
    }
  }, [appPreferences]);

  useEffect(() => {
    setSettingsDraft(appPreferences);
  }, [appPreferences]);

  useEffect(() => {
    const rootElement = document.documentElement;
    rootElement.dataset.theme = themeMode;

    try {
      window.localStorage.setItem(themeStorageKey, themeMode);
    } catch {
      return;
    }
  }, [themeMode]);

  const loadAccounts = async () => {
    setAccountsError('');
    setIsAccountsLoading(true);

    try {
      const nextAccounts = await listAccounts();
      setAccounts(nextAccounts.map(mapApiAccountToRow));
    } catch (error) {
      setAccountsError(
        formatApiError(error, 'Не удалось загрузить аккаунты из API.'),
      );
    } finally {
      setIsAccountsLoading(false);
    }
  };

  useEffect(() => {
    if (activePage !== 'accounts' && activePage !== 'logs') {
      return;
    }

    void loadAccounts();
    const intervalId = window.setInterval(
      () => void loadAccounts(),
      appPreferences.autoRefreshSeconds * 1000,
    );

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activePage, appPreferences.autoRefreshSeconds]);

  const handleCreateAccount = async (draft: AccountDraft) => {
    setIsAccountMutationPending(true);

    try {
      const nextAccount = await createAccountRequest(
        createAccountCreatePayload(draft),
      );
      await loadAccounts();
      setSelectedAccountId(nextAccount.id);
    } finally {
      setIsAccountMutationPending(false);
    }
  };

  const handleSaveAccount = async (accountId: string, draft: AccountDraft) => {
    setIsAccountMutationPending(true);

    try {
      await updateAccountRequest(accountId, createAccountUpdatePayload(draft));
      await loadAccounts();
      setSelectedAccountId(accountId);
    } finally {
      setIsAccountMutationPending(false);
    }
  };

  const handleSyncAccountChannels = async (
    accountId: string,
    channelLinks: string[],
  ) => {
    setIsAccountMutationPending(true);

    try {
      await updateAccountRequest(accountId, {
        channel_links: normalizeTelegramLinks(channelLinks),
      });
      await loadAccounts();
      setSelectedAccountId(accountId);
    } finally {
      setIsAccountMutationPending(false);
    }
  };

  const handleUpdatePreference = (
    field: keyof AppPreferences,
    value: string | number | boolean,
  ) => {
    setSettingsDraft(
      (currentPreferences) =>
        ({
          ...currentPreferences,
          [field]: value,
        }) as AppPreferences,
    );
  };

  const handleSavePreferences = () => {
    setAppPreferences(settingsDraft);
  };

  const handleResetPreferences = () => {
    const nextDefaults = createDefaultAppPreferences();
    setAppPreferences(nextDefaults);
    setSettingsDraft(nextDefaults);
  };

  const handleToggleTheme = () => {
    setThemeMode((currentTheme) =>
      currentTheme === 'dark' ? 'light' : 'dark',
    );
  };

  const handleBulkAccountAction = async (
    action: AccountBulkActionId,
    accountIds: string[],
  ) => {
    if (accountIds.length === 0) {
      return '';
    }

    const accountRequests =
      action === 'open'
        ? accountIds.map((accountId) => startAccountRequest(accountId))
        : action === 'close'
          ? accountIds.map((accountId) => stopAccountRequest(accountId))
          : accountIds.map((accountId) => deleteAccountRequest(accountId));

    setIsAccountMutationPending(true);

    try {
      const results = await Promise.allSettled(accountRequests);
      const successCount = results.filter(
        (result) => result.status === 'fulfilled',
      ).length;
      const failureCount = results.length - successCount;

      await loadAccounts();

      if (action === 'open' && successCount > 0 && accountIds[0]) {
        setSelectedAccountId(accountIds[0]);
      }

      if (successCount === 0) {
        return `Не удалось выполнить действие для ${formatAccountCount(failureCount)}.`;
      }

      const actionVerb =
        action === 'open'
          ? 'Открыто'
          : action === 'close'
            ? 'Остановлено'
            : 'Удалено';
      const successMessage = `${actionVerb} ${formatAccountCount(successCount)}.`;

      return failureCount > 0
        ? `${successMessage} Ошибок: ${failureCount}.`
        : successMessage;
    } finally {
      setIsAccountMutationPending(false);
    }
  };

  if (activePage === 'settings') {
    const hasUnsavedChanges =
      JSON.stringify(settingsDraft) !== JSON.stringify(appPreferences);

    return (
      <SettingsPage
        hasUnsavedChanges={hasUnsavedChanges}
        onChangePreference={handleUpdatePreference}
        onNavigateToPage={setActivePage}
        onResetPreferences={handleResetPreferences}
        onSavePreferences={handleSavePreferences}
        onToggleTheme={handleToggleTheme}
        preferences={settingsDraft}
        themeMode={themeMode}
      />
    );
  }

  return (
    <div className={settingsPageClassName}>
      <div className="grid min-h-screen xl:grid-cols-[280px_minmax(0,1fr)]">
        <AppSidebar
          activePage={activePage}
          onNavigate={setActivePage}
          onToggleTheme={handleToggleTheme}
          themeMode={themeMode}
        />

        <main className="min-w-0 bg-background">
          <section className="min-h-screen overflow-auto">
            <div className="mx-auto max-w-265 py-10 px-7.5">
              {activePage === 'dashboard' && <DashboardPage />}
              {activePage === 'accounts' && (
                <AccountsPage
                  accounts={accounts}
                  currentPage={accountsCurrentPage}
                  isLoading={isAccountsLoading}
                  isMutationPending={isAccountMutationPending}
                  itemsPerPage={accountsItemsPerPage}
                  loadError={accountsError}
                  onBulkAction={handleBulkAccountAction}
                  onCreateAccount={handleCreateAccount}
                  onCurrentPageChange={setAccountsCurrentPage}
                  onItemsPerPageChange={setAccountsItemsPerPage}
                  onReload={loadAccounts}
                  onSelectAccount={setSelectedAccountId}
                  onSyncAccountChannels={handleSyncAccountChannels}
                  onUpdateAccount={handleSaveAccount}
                />
              )}
              {activePage === 'logs' && (
                <LogsPage
                  accounts={accounts}
                  accountsError={accountsError}
                  currentPage={logsCurrentPage}
                  isAccountsLoading={isAccountsLoading}
                  itemsPerPage={logsItemsPerPage}
                  onCurrentPageChange={setLogsCurrentPage}
                  onItemsPerPageChange={setLogsItemsPerPage}
                  onReloadAccounts={loadAccounts}
                />
              )}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

interface ActionButtonProps extends ComponentPropsWithoutRef<'button'> {
  children?: ReactNode;
  icon?: ReactNode;
  tone?: ActionTone;
  size?: ButtonSize;
  variant?: ButtonVariant;
  align?: 'center' | 'left';
  fullWidth?: boolean;
}

function ActionButton({
  children,
  icon,
  tone = 'neutral',
  size = 'md',
  variant = 'soft',
  align = 'center',
  fullWidth = false,
  className,
  type = 'button',
  ...props
}: ActionButtonProps) {
  return (
    <button
      className={getButtonClassName({
        tone,
        variant,
        size,
        align,
        fullWidth,
        className,
      })}
      type={type}
      {...props}
    >
      {icon}
      {children}
    </button>
  );
}

interface TelegramChannelCardProps {
  channel: TelegramChannel;
  action?: ReactNode;
  compact?: boolean;
}

function TelegramChannelCard({
  channel,
  action,
  compact = false,
}: TelegramChannelCardProps) {
  const normalizedHandle = normalizeTelegramHandle(channel.handle);
  const channelUrl = normalizedHandle ? `https://${normalizedHandle}` : '';
  const isClickable = compact && !action && Boolean(channelUrl);
  const cardClassName = cx(
    'border',
    compact
      ? cx(
          'block w-full px-3.5 py-3 sm:w-fit sm:max-w-[36rem]',
          isClickable
            ? 'cursor-pointer rounded-2xl border-border/22 bg-foreground/92 transition-[transform,border-color,background-color] duration-150 hover:border-info/32 hover:bg-foreground active:scale-[0.985] focus-visible:border-info/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info/18'
            : 'rounded-2xl border-border/20 bg-foreground/92',
        )
      : 'rounded-xl border-border/25 bg-secondary/50 p-2.5 shadow-[0_18px_48px_rgba(15,23,42,0.04)]',
  );
  const content = (
    <div
      className={cx(
        'flex items-center justify-between',
        compact ? 'gap-3' : 'gap-4',
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <img
          alt=""
          className={cx(
            'shrink-0 rounded-full',
            compact
              ? 'h-9 w-9'
              : 'h-10 w-10 shadow-[0_6px_18px_rgba(19,120,198,0.2)]',
          )}
          src="/tg_logo.png"
        />
        <div className="min-w-0">
          <h5
            className={cx(
              'truncate font-semibold tracking-tight text-text',
              compact ? 'text-[15px] leading-5' : 'text-[18px] leading-6',
            )}
          >
            {channel.title}
          </h5>
          <p
            className={cx(
              'truncate text-text-muted',
              compact ? 'mt-0.5 text-[13px]' : 'text-sm',
            )}
          >
            {formatChannelBadge(channel.handle)}
          </p>
        </div>
      </div>

      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );

  return isClickable ? (
    <a
      aria-label={`Открыть Telegram-канал ${channel.title}`}
      className={cardClassName}
      href={channelUrl}
      rel="noreferrer"
      target="_blank"
    >
      {content}
    </a>
  ) : (
    <article className={cardClassName}>{content}</article>
  );
}

interface AppSidebarProps {
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  onToggleTheme: () => void;
  themeMode: ThemeMode;
}

function AppSidebar({
  activePage,
  onNavigate,
  onToggleTheme,
  themeMode,
}: AppSidebarProps) {
  const isDarkTheme = themeMode === 'dark';

  return (
    <aside className="min-h-screen w-full border-r border-border-soft bg-sidebar p-5">
      <div className="sticky top-7.5 flex min-h-[calc(100vh-60px)] flex-col justify-between gap-6">
        <div className="space-y-4">
          <h1 className="relative text-4xl font-semibold leading-none tracking-[-0.05em] text-info">
            {productName}
          </h1>

          <nav className="flex flex-col gap-2.5">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-left transition-all duration-200 ${
                  activePage === item.id
                    ? 'border border-info/45 bg-sidebar-card-active text-text shadow-[0_1px_2px_rgba(15,23,42,0.02)]'
                    : 'border border-transparent bg-sidebar-card text-text-soft hover:border-border hover:bg-sidebar-card-hover'
                }`}
                onClick={() => onNavigate(item.id)}
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors duration-200 ${
                    activePage === item.id
                      ? 'bg-info/12 text-info'
                      : 'bg-sidebar-icon text-text-faint'
                  }`}
                >
                  {navItemIcons[item.id]}
                </span>
                <span className="font-medium">{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <button
          aria-checked={isDarkTheme}
          className="flex w-full cursor-pointer items-center justify-between gap-3 rounded-2xl border border-border bg-sidebar-card/50 px-4 py-3 text-left transition-all duration-200 hover:border-border-strong hover:bg-sidebar-card-hover focus:ring-2 focus:ring-info/15"
          role="switch"
          type="button"
          onClick={onToggleTheme}
        >
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sidebar-icon text-info">
              {isDarkTheme ? (
                <Moon className="h-5 w-5" />
              ) : (
                <SunMedium className="h-5 w-5" />
              )}
            </span>
            <div>
              <p className="text-[15px] font-semibold text-text">Тёмная тема</p>
              <p className="text-sm text-text-muted">
                {isDarkTheme ? 'Включена' : 'Выключена'}
              </p>
            </div>
          </div>
          <ToggleSwitch checked={isDarkTheme} />
        </button>
      </div>
    </aside>
  );
}

interface ToggleSwitchProps {
  checked: boolean;
}

function ToggleSwitch({ checked }: ToggleSwitchProps) {
  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex h-6 w-11 shrink-0 rounded-full transition-all duration-200 ${
        checked ? 'bg-info' : 'bg-switch-off'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-foreground shadow-[0_2px_5px_rgba(15,23,42,0.22)] transition-transform duration-200 ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </span>
  );
}

const accountStatusBadgeClassNames: Record<StatusTone, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-info/15 text-info',
  info: 'bg-info/15 text-info',
  danger: 'bg-error/15 text-error',
  neutral: 'bg-secondary text-text-muted',
};

function AccountStatusBadge({
  tone,
  children,
}: {
  tone: StatusTone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${accountStatusBadgeClassNames[tone]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {children}
    </span>
  );
}

interface SelectionCheckboxProps {
  checked: boolean;
  indeterminate?: boolean;
  onToggle: () => void;
  label: string;
}

function SelectionCheckbox({
  checked,
  indeterminate = false,
  onToggle,
  label,
}: SelectionCheckboxProps) {
  const isActive = checked || indeterminate;

  return (
    <button
      aria-checked={indeterminate ? 'mixed' : checked}
      aria-label={label}
      className={`flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border-2 outline-none transition-all duration-200 focus-visible:ring-4 focus-visible:ring-info/18 focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
        isActive
          ? 'border-info bg-info text-foreground shadow-[0_8px_16px_rgba(25,25,25,0.1)]'
          : 'border-border bg-foreground text-transparent hover:border-info/50 hover:bg-foreground hover:shadow-[0_4px_8px_rgba(50,50,50,0.1)]'
      }`}
      role="checkbox"
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
    >
      {checked ? (
        <Check className="h-4 w-4" strokeWidth={3} />
      ) : indeterminate ? (
        <span className="h-0.75 w-3 rounded-full bg-current" />
      ) : null}
    </button>
  );
}

type BulkActionTone = 'success' | 'neutral' | 'danger';

interface BulkActionButtonProps {
  children: ReactNode;
  icon: ReactNode;
  tone?: BulkActionTone;
  disabled?: boolean;
  className?: string;
  onClick: () => void;
}

function BulkActionButton({
  children,
  icon,
  tone = 'neutral',
  disabled = false,
  className,
  onClick,
}: BulkActionButtonProps) {
  return (
    <button
      className={getButtonClassName({
        tone,
        variant: tone === 'success' ? 'solid' : 'ghost',
        size: 'sm',
        className,
      })}
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {icon}
      {children}
    </button>
  );
}

interface DashboardRangePickerProps {
  customRange: {
    end: string;
    start: string;
  };
  isLoading: boolean;
  preset: DashboardRangePreset;
  onApplyCustomRange: () => void;
  onCustomRangeChange: (field: 'end' | 'start', value: string) => void;
  onPresetChange: (preset: DashboardRangePreset) => void;
}

function DashboardRangePicker({
  customRange,
  isLoading,
  preset,
  onApplyCustomRange,
  onCustomRangeChange,
  onPresetChange,
}: DashboardRangePickerProps) {
  const isCustomActive = preset === 'custom';
  const isCustomRangeValid =
    Boolean(customRange.start) &&
    Boolean(customRange.end) &&
    customRange.start <= customRange.end;

  return (
    <div className="flex w-full flex-wrap items-center justify-start gap-3 sm:w-auto sm:justify-end">
      <div className="flex flex-wrap items-center gap-1 rounded-2xl border border-border bg-foreground p-1.5 shadow-[0_10px_24px_rgba(15,23,42,0.06)]">
        {dashboardRangeOptions.map((option) => {
          const isActive = option.id === preset;

          return (
            <button
              key={option.id}
              className={cx(
                'h-10 rounded-xl px-3.5 text-[14px] font-medium transition-colors duration-150',
                isActive
                  ? 'bg-info text-white'
                  : 'text-text-muted hover:bg-secondary hover:text-text',
              )}
              disabled={isLoading}
              type="button"
              onClick={() => onPresetChange(option.id)}
            >
              {option.label}
            </button>
          );
        })}
      </div>

      {isCustomActive ? (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-border bg-foreground px-3 py-2 shadow-[0_10px_24px_rgba(15,23,42,0.06)]">
          <input
            className="h-10 rounded-[10px] border border-border bg-background px-3 text-[14px] text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10"
            max={customRange.end || undefined}
            type="date"
            value={customRange.start}
            onChange={(event) =>
              onCustomRangeChange('start', event.target.value)
            }
          />
          <span className="text-text-faint">-</span>
          <input
            className="h-10 rounded-[10px] border border-border bg-background px-3 text-[14px] text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10"
            min={customRange.start || undefined}
            type="date"
            value={customRange.end}
            onChange={(event) => onCustomRangeChange('end', event.target.value)}
          />
          <button
            className={getButtonClassName({
              tone: 'info',
              size: 'sm',
            })}
            disabled={isLoading || !isCustomRangeValid}
            type="button"
            onClick={onApplyCustomRange}
          >
            Применить
          </button>
        </div>
      ) : null}
    </div>
  );
}

function DashboardPage() {
  const [summary, setSummary] = useState<ApiDashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const defaultCustomRange = createDefaultDashboardCustomRange();
  const [dashboardRangePreset, setDashboardRangePreset] =
    useState<DashboardRangePreset>('all');
  const [customRangeDraft, setCustomRangeDraft] = useState(defaultCustomRange);
  const [appliedCustomRange, setAppliedCustomRange] =
    useState(defaultCustomRange);
  const dashboardMetrics = createDashboardMetrics(
    summary,
    dashboardRangePreset,
  );
  const dashboardSeries = createDashboardSeries(
    summary,
    dashboardRangePreset,
    appliedCustomRange,
  );
  const shouldShowEmptyAccounts =
    Boolean(summary) && (summary?.total_accounts ?? 0) === 0 && !isLoading;

  const loadDashboard = async (
    preset: DashboardRangePreset,
    customRange: { end: string; start: string },
  ) => {
    setIsLoading(true);
    setLoadError('');

    try {
      setSummary(
        await getDashboardSummary({
          period: preset,
          dateFrom: preset === 'custom' ? customRange.start : undefined,
          dateTo: preset === 'custom' ? customRange.end : undefined,
        }),
      );
    } catch (error) {
      setLoadError(
        formatApiError(error, 'Не удалось загрузить сводку дэшборда из API.'),
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard(dashboardRangePreset, appliedCustomRange);
  }, [appliedCustomRange, dashboardRangePreset]);

  const handleApplyCustomRange = () => {
    if (
      !customRangeDraft.start ||
      !customRangeDraft.end ||
      customRangeDraft.start > customRangeDraft.end
    ) {
      setLoadError('Укажи корректный диапазон дат для дэшборда.');
      return;
    }

    setAppliedCustomRange(customRangeDraft);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" />

      {loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          <span>{loadError}</span>
          <button
            className={getButtonClassName({
              tone: 'danger',
              size: 'sm',
            })}
            disabled={isLoading}
            type="button"
            onClick={() =>
              void loadDashboard(dashboardRangePreset, appliedCustomRange)
            }
          >
            Повторить
          </button>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-6">
        <Panel
          title="Главная статистика"
          actions={
            <DashboardRangePicker
              customRange={customRangeDraft}
              isLoading={isLoading}
              preset={dashboardRangePreset}
              onApplyCustomRange={handleApplyCustomRange}
              onCustomRangeChange={(field, value) =>
                setCustomRangeDraft((previousValue) => ({
                  ...previousValue,
                  [field]: value,
                }))
              }
              onPresetChange={(preset) => setDashboardRangePreset(preset)}
            />
          }
        >
          {shouldShowEmptyAccounts ? (
            <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
              <strong className="block text-text">Аккаунтов пока нет</strong>
              <p className="mt-2 leading-6 text-text-muted">
                После добавления аккаунтов здесь появится график публикаций и
                ошибок.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <LineChart data={dashboardSeries} height={260} />
              <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[15px] text-text-muted">
                <span className="inline-flex items-center gap-2">
                  <i className="h-2.5 w-2.5 rounded-full bg-[#45b99a]" />
                  Товары
                </span>
                <span className="inline-flex items-center gap-2">
                  <i className="h-2.5 w-2.5 rounded-full bg-[#ef6b7c]" />
                  Ошибки
                </span>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

interface AccountsPageProps {
  accounts: AccountRow[];
  currentPage: number;
  isLoading: boolean;
  isMutationPending: boolean;
  itemsPerPage: TablePageSize;
  loadError: string;
  onBulkAction: (
    action: AccountBulkActionId,
    accountIds: string[],
  ) => Promise<string>;
  onCreateAccount: (draft: AccountDraft) => Promise<void>;
  onCurrentPageChange: (page: number) => void;
  onItemsPerPageChange: (value: TablePageSize) => void;
  onReload: () => Promise<void>;
  onSelectAccount: (accountId: string) => void;
  onSyncAccountChannels: (
    accountId: string,
    channelLinks: string[],
  ) => Promise<void>;
  onUpdateAccount: (accountId: string, draft: AccountDraft) => Promise<void>;
}

function AccountsPage({
  accounts,
  currentPage,
  isLoading,
  isMutationPending,
  itemsPerPage,
  loadError,
  onBulkAction,
  onCreateAccount,
  onCurrentPageChange,
  onItemsPerPageChange,
  onReload,
  onSelectAccount,
  onSyncAccountChannels,
  onUpdateAccount,
}: AccountsPageProps) {
  const [sortState, setSortState] = useState<{
    field: AccountSortField;
    direction: AccountSortDirection;
  } | null>(null);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [bulkFeedback, setBulkFeedback] = useState('');
  const [infoAccountId, setInfoAccountId] = useState<string | null>(null);
  const [isInfoDialogOpen, setIsInfoDialogOpen] = useState(false);
  const [detailsAccountId, setDetailsAccountId] = useState<string | null>(null);
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);
  const [deleteTargetAccountId, setDeleteTargetAccountId] = useState<
    string | null
  >(null);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const detailsAccount = detailsAccountId
    ? (accounts.find((account) => account.id === detailsAccountId) ?? null)
    : null;
  const infoAccount = infoAccountId
    ? (accounts.find((account) => account.id === infoAccountId) ?? null)
    : null;
  const deleteTargetAccount = deleteTargetAccountId
    ? (accounts.find((account) => account.id === deleteTargetAccountId) ?? null)
    : null;
  const selectedAccounts = accounts.filter((account) =>
    selectedAccountIds.includes(account.id),
  );
  const deleteDialogAccounts = deleteTargetAccount
    ? [deleteTargetAccount]
    : selectedAccounts;
  const shouldShowCloseAction =
    selectedAccounts.length > 0 &&
    selectedAccounts.every((account) => account.statusLabel !== 'stopped');
  const visibleAccounts = accounts;
  const sortedAccounts = [...visibleAccounts].sort(
    (leftAccount, rightAccount) => {
      if (!sortState) {
        return 0;
      }

      const leftValue = getAccountSortValue(leftAccount, sortState.field);
      const rightValue = getAccountSortValue(rightAccount, sortState.field);
      const comparison =
        typeof leftValue === 'number' && typeof rightValue === 'number'
          ? leftValue - rightValue
          : String(leftValue).localeCompare(String(rightValue), 'ru', {
              sensitivity: 'base',
              numeric: true,
            });

      return sortState.direction === 'asc' ? comparison : -comparison;
    },
  );
  const totalPages = Math.max(
    1,
    Math.ceil(sortedAccounts.length / itemsPerPage),
  );
  const paginatedAccounts = sortedAccounts.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage,
  );
  const visibleAccountIds = paginatedAccounts.map((account) => account.id);
  const allAccountIds = accounts.map((account) => account.id);
  const allAccountSignature = allAccountIds.join('|');
  const selectedVisibleCount = selectedAccountIds.filter((accountId) =>
    visibleAccountIds.includes(accountId),
  ).length;
  const isAllVisibleSelected =
    visibleAccountIds.length > 0 &&
    selectedVisibleCount === visibleAccountIds.length;
  const isPartiallyVisibleSelected =
    selectedVisibleCount > 0 && !isAllVisibleSelected;
  const visibleRangeStart =
    paginatedAccounts.length === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const visibleRangeEnd =
    (currentPage - 1) * itemsPerPage + paginatedAccounts.length;

  const handleSortHeaderClick = (field: AccountSortField) => {
    setSortState((currentSortState) => {
      if (!currentSortState || currentSortState.field !== field) {
        return { field, direction: 'asc' };
      }

      if (currentSortState.direction === 'asc') {
        return {
          field,
          direction: 'desc',
        };
      }

      return null;
    });
  };

  const toggleAccountSelection = (accountId: string) => {
    setSelectedAccountIds((currentSelection) =>
      currentSelection.includes(accountId)
        ? currentSelection.filter((selectedId) => selectedId !== accountId)
        : [...currentSelection, accountId],
    );
  };

  const openAccountInfo = (accountId: string) => {
    setInfoAccountId(accountId);
    onSelectAccount(accountId);
    setIsInfoDialogOpen(true);
  };

  const toggleAllVisibleAccounts = () => {
    const visibleIdSet = new Set(visibleAccountIds);

    setSelectedAccountIds((currentSelection) => {
      if (selectedVisibleCount > 0) {
        return currentSelection.filter(
          (selectedId) => !visibleIdSet.has(selectedId),
        );
      }

      const nextSelection = new Set([
        ...currentSelection,
        ...visibleAccountIds,
      ]);

      return accounts
        .map((account) => account.id)
        .filter((accountId) => nextSelection.has(accountId));
    });
  };

  const runBulkAction = async (action: AccountBulkActionId) => {
    if (selectedAccountIds.length === 0 || isMutationPending) {
      return;
    }

    try {
      const message = await onBulkAction(action, selectedAccountIds);

      if (message) {
        setBulkFeedback(message);
      }

      if (action === 'delete') {
        setSelectedAccountIds([]);
        return;
      }

      if (action === 'open' && selectedAccountIds[0]) {
        onSelectAccount(selectedAccountIds[0]);
      }
    } catch (error) {
      setBulkFeedback(
        formatApiError(error, 'Не удалось выполнить действие над аккаунтами.'),
      );
    }
  };

  const openAccountDetails = (accountId: string) => {
    setDetailsAccountId(accountId);
    onSelectAccount(accountId);
    setIsDetailsDialogOpen(true);
  };

  const openDeleteAccountsDialog = (accountId?: string) => {
    setDeleteTargetAccountId(accountId ?? null);
    setIsDeleteDialogOpen(true);
  };

  useEffect(() => {
    if (currentPage <= totalPages) {
      return;
    }

    onCurrentPageChange(totalPages);
  }, [currentPage, onCurrentPageChange, totalPages]);

  useEffect(() => {
    const accountIdSet = new Set(allAccountIds);

    setSelectedAccountIds((currentSelection) => {
      const nextSelection = currentSelection.filter((accountId) =>
        accountIdSet.has(accountId),
      );

      return nextSelection.length === currentSelection.length
        ? currentSelection
        : nextSelection;
    });
  }, [allAccountSignature]);

  useEffect(() => {
    if (!bulkFeedback) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setBulkFeedback('');
    }, 3200);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [bulkFeedback]);

  useEffect(() => {
    if (!infoAccount && isInfoDialogOpen) {
      setInfoAccountId(null);
      setIsInfoDialogOpen(false);
    }
  }, [infoAccount, isInfoDialogOpen]);

  useEffect(() => {
    if (!detailsAccount && isDetailsDialogOpen) {
      setDetailsAccountId(null);
      setIsDetailsDialogOpen(false);
    }
  }, [detailsAccount, isDetailsDialogOpen]);

  useEffect(() => {
    if (isDeleteDialogOpen && deleteDialogAccounts.length === 0) {
      setDeleteTargetAccountId(null);
      setIsDeleteDialogOpen(false);
    }
  }, [deleteDialogAccounts.length, isDeleteDialogOpen]);

  return (
    <div className="space-y-6">
      <PageHeader title="Аккаунты" />

      {loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          <span>{loadError}</span>
          <button
            className={getButtonClassName({
              tone: 'danger',
              size: 'sm',
            })}
            disabled={isLoading || isMutationPending}
            type="button"
            onClick={() => void onReload()}
          >
            Повторить
          </button>
        </div>
      ) : null}

      {bulkFeedback ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/70 px-4 py-3 text-sm text-text">
          {bulkFeedback}
        </div>
      ) : null}

      {isMutationPending ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/60 px-4 py-3 text-sm text-text-muted">
          Синхронизация с API...
        </div>
      ) : null}

      <div className="flex flex-col gap-6">
        <Panel
          title="Каталог аккаунтов"
          actions={
            <div className="flex items-center justify-between gap-4 rounded-[20px] border border-border/25 bg-secondary/95 p-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <BulkActionButton
                  disabled={
                    selectedAccountIds.length === 0 || isMutationPending
                  }
                  icon={
                    shouldShowCloseAction ? (
                      <X className="h-4 w-4" />
                    ) : (
                      <FolderOpen className="h-4 w-4" />
                    )
                  }
                  tone={shouldShowCloseAction ? 'danger' : 'success'}
                  onClick={() =>
                    void runBulkAction(shouldShowCloseAction ? 'close' : 'open')
                  }
                >
                  {shouldShowCloseAction ? 'Остановить' : 'Запустить'}
                </BulkActionButton>
                <button
                  aria-label="Удалить отмеченные аккаунты"
                  className={getButtonClassName({
                    tone: 'danger',
                    size: 'icon-sm',
                  })}
                  disabled={
                    selectedAccountIds.length === 0 || isMutationPending
                  }
                  type="button"
                  onClick={() => openDeleteAccountsDialog()}
                >
                  <Trash2 className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Добавить аккаунт"
                  className={getButtonClassName({
                    tone: 'info',
                    variant: 'solid',
                    size: 'icon-sm',
                  })}
                  disabled={isMutationPending}
                  type="button"
                  onClick={() => setIsCreateDialogOpen(true)}
                >
                  <Plus className="h-4.5 w-4.5" />
                </button>
              </div>
            </div>
          }
        >
          <div className="overflow-hidden bg-secondary/50 border border-border/25 rounded-2xl">
            <div className="overflow-x-auto px-5 py-3">
              <table className="w-full border-separate [border-spacing:0_10px]">
                <thead>
                  <tr>
                    <th className="border-b border-border/25 px-4 pb-3 text-left">
                      <SelectionCheckbox
                        checked={isAllVisibleSelected}
                        indeterminate={isPartiallyVisibleSelected}
                        label="Выбрать все видимые аккаунты"
                        onToggle={toggleAllVisibleAccounts}
                      />
                    </th>
                    {accountTableHeaders.map((header) => (
                      <th
                        key={header.id}
                        aria-sort={
                          sortState?.field === header.id
                            ? sortState.direction === 'asc'
                              ? 'ascending'
                              : 'descending'
                            : 'none'
                        }
                        className="px-4 pb-3 text-left border-b border-border/25 text-xs font-medium uppercase tracking-wide text-text-muted"
                      >
                        <button
                          className={`inline-flex cursor-pointer items-center uppercase gap-1.5 transition-colors duration-200 ${
                            sortState?.field === header.id
                              ? 'text-info'
                              : 'hover:text-text'
                          }`}
                          type="button"
                          onClick={() => handleSortHeaderClick(header.id)}
                        >
                          {header.label}
                          <ChevronDown
                            className={`h-4 w-4 transition-all duration-200 ${
                              sortState?.field === header.id
                                ? `opacity-100 ${
                                    sortState.direction === 'asc'
                                      ? 'rotate-180'
                                      : ''
                                  }`
                                : 'opacity-35'
                            }`}
                          />
                        </button>
                      </th>
                    ))}
                    <th className="w-16 border-b border-border/20 px-4 pb-2 text-right">
                      <span className="sr-only">Действия</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading && accounts.length === 0 ? (
                    <tr>
                      <td colSpan={accountTableHeaders.length + 2}>
                        <div className="rounded-2xl border border-dashed border-border/20 bg-secondary/45 px-6 py-10 text-center">
                          <strong className="block text-base text-text">
                            Загружаем аккаунты
                          </strong>
                          <p className="mt-2 text-sm leading-6 text-text-muted">
                            Получаем данные со страницы API.
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : sortedAccounts.length === 0 ? (
                    <tr>
                      <td colSpan={accountTableHeaders.length + 2}>
                        <div className="rounded-2xl border border-dashed border-border/20 bg-secondary/45 px-6 py-10 text-center">
                          <strong className="block text-base text-text">
                            Пока нет аккаунтов
                          </strong>
                          <p className="mt-2 text-sm leading-6 text-text-muted">
                            Добавь новый аккаунт, чтобы снова заполнить каталог.
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    paginatedAccounts.map((account) => {
                      const isChecked = selectedAccountIds.includes(account.id);
                      const rowSurfaceClassName = isChecked
                        ? 'bg-info/8'
                        : 'group-hover:bg-secondary/50';
                      const rowCellClassName = `px-4 py-4 align-middle transition-colors duration-200 ${rowSurfaceClassName}`;
                      const hasErrors = Number(account.errors) > 0;

                      return (
                        <tr
                          key={account.id}
                          className="group cursor-pointer text-sm"
                          onClick={() => openAccountInfo(account.id)}
                        >
                          <td
                            className={`${rowCellClassName} w-16 rounded-l-2xl`}
                            onClick={(event) => {
                              event.stopPropagation();
                              toggleAccountSelection(account.id);
                            }}
                          >
                            <SelectionCheckbox
                              checked={isChecked}
                              label={`Выбрать аккаунт ${account.name}`}
                              onToggle={() =>
                                toggleAccountSelection(account.id)
                              }
                            />
                          </td>
                          <td className={rowCellClassName}>
                            <div className="flex items-center text-md font-medium text-text gap-3">
                              {account.name}
                            </div>
                          </td>
                          <td className={rowCellClassName}>
                            <div className="flex items-center gap-2 text-text">
                              <Clock3 className="h-4 w-4 text-info/50" />
                              <span>{account.timer}</span>
                            </div>
                          </td>
                          <td className={rowCellClassName}>
                            <span className="inline-flex min-w-8 items-center justify-center rounded-full bg-info/5 p-1.5 text-sm font-semibold text-info">
                              {account.telegramChannels.length}
                            </span>
                          </td>
                          <td className={rowCellClassName}>
                            <AccountStatusBadge tone={account.statusTone}>
                              {account.statusLabel}
                            </AccountStatusBadge>
                          </td>
                          <td className={rowCellClassName}>
                            <span
                              className={
                                hasErrors
                                  ? 'font-semibold text-error'
                                  : 'text-text-muted'
                              }
                            >
                              {account.errors}
                            </span>
                          </td>
                          <td
                            className={`${rowCellClassName} w-16 rounded-r-2xl`}
                            onClick={(event) => {
                              event.stopPropagation();
                            }}
                          >
                            <div className="flex justify-end">
                              <AccountRowActionMenu
                                account={account}
                                disabled={isMutationPending}
                                onDelete={openDeleteAccountsDialog}
                                onEdit={openAccountDetails}
                              />
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <TablePaginationFooter
              currentPage={currentPage}
              itemsPerPage={itemsPerPage}
              itemCountLabel="аккаунтов"
              nextPageAriaLabel="Следующая страница"
              previousPageAriaLabel="Предыдущая страница"
              totalItems={accounts.length}
              totalPages={totalPages}
              visibleRangeEnd={visibleRangeEnd}
              visibleRangeStart={visibleRangeStart}
              onItemsPerPageChange={(value) => {
                onItemsPerPageChange(value);
                onCurrentPageChange(1);
              }}
              onPageChange={onCurrentPageChange}
            />
          </div>
        </Panel>
      </div>

      <AccountDetailsDialog
        account={detailsAccount}
        accounts={accounts}
        isOpen={isDetailsDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => {
          setIsDetailsDialogOpen(false);
          setDetailsAccountId(null);
        }}
        onReloadAccounts={onReload}
        onSyncAccountChannels={onSyncAccountChannels}
        onUpdateAccount={onUpdateAccount}
      />
      <AccountInfoDialog
        accountId={infoAccountId}
        fallbackAccount={infoAccount}
        isOpen={isInfoDialogOpen}
        onClose={() => {
          setIsInfoDialogOpen(false);
          setInfoAccountId(null);
        }}
      />
      <CreateAccountDialog
        isOpen={isCreateDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => setIsCreateDialogOpen(false)}
        onCreateAccount={onCreateAccount}
      />
      <DeleteAccountsDialog
        accounts={deleteDialogAccounts}
        isOpen={isDeleteDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => {
          setIsDeleteDialogOpen(false);
          setDeleteTargetAccountId(null);
        }}
        onConfirm={async () => {
          if (deleteTargetAccountId) {
            await onBulkAction('delete', [deleteTargetAccountId]);
            setDeleteTargetAccountId(null);
          } else {
            await runBulkAction('delete');
          }
          setIsDeleteDialogOpen(false);
        }}
        onRemoveAccount={(accountId) =>
          setSelectedAccountIds((currentSelection) =>
            currentSelection.filter((selectedId) => selectedId !== accountId),
          )
        }
      />
    </div>
  );
}

interface AccountDialogShellProps {
  children: ReactNode;
  closeLabel: string;
  isOpen: boolean;
  onClose: () => void;
  statusBadge?: ReactNode;
  title: string;
}

function AccountDialogShell({
  children,
  closeLabel,
  isOpen,
  onClose,
  statusBadge,
  title,
}: AccountDialogShellProps) {
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/55 px-10 backdrop-blur-sm"
      role="dialog"
      onClick={onClose}
    >
      <div
        className="max-h-[calc(100vh-64px)] w-full max-w-250 overflow-y-auto rounded-[30px] border border-border/20 bg-foreground p-5 shadow-[0_30px_90px_rgba(15,23,42,0.2)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-col gap-4 border-b border-border/25 pb-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <h3 className={pageTitleClassName}>{title}</h3>
              {statusBadge}
            </div>
          </div>

          <button
            aria-label={closeLabel}
            className={getButtonClassName({
              tone: 'info',
              variant: 'solid',
              size: 'icon-sm',
              className: 'rounded-xl',
            })}
            type="button"
            onClick={onClose}
          >
            <X className="h-5 w-5 stroke-[2.6]" />
          </button>
        </div>

        {children}
      </div>
    </div>
  );
}

interface AccountRowActionMenuProps {
  account: AccountRow;
  disabled: boolean;
  onDelete: (accountId: string) => void;
  onEdit: (accountId: string) => void;
}

function AccountRowActionMenu({
  account,
  disabled,
  onDelete,
  onEdit,
}: AccountRowActionMenuProps) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    if (disabled) {
      setIsOpen(false);
    }
  }, [disabled]);

  return (
    <div
      className="relative"
      onClick={(event) => event.stopPropagation()}
      onMouseEnter={() => {
        if (!disabled) {
          setIsOpen(true);
        }
      }}
      onMouseLeave={() => setIsOpen(false)}
      onFocusCapture={() => {
        if (!disabled) {
          setIsOpen(true);
        }
      }}
      onBlurCapture={(event) => {
        const nextTarget = event.relatedTarget;

        if (
          !(nextTarget instanceof Node) ||
          !event.currentTarget.contains(nextTarget)
        ) {
          setIsOpen(false);
        }
      }}
    >
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={`Действия для аккаунта ${account.name}`}
        className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-text-muted transition-colors duration-200 hover:bg-foreground hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled}
        type="button"
      >
        <EllipsisVertical className="h-4.5 w-4.5" />
      </button>

      {isOpen ? (
        <div className="absolute top-full right-0 z-20 pt-2">
          <div
            className="w-52 rounded-2xl border border-border/20 bg-foreground p-1.5 shadow-[0_18px_40px_rgba(15,23,42,0.14)]"
            role="menu"
          >
            <button
              className={getButtonClassName({
                size: 'row',
                variant: 'ghost',
                fullWidth: true,
                align: 'left',
                className: 'px-3',
              })}
              role="menuitem"
              type="button"
              onClick={() => {
                setIsOpen(false);
                onEdit(account.id);
              }}
            >
              <PencilLine className="h-4 w-4" />
              Редактировать
            </button>
            <button
              className={getButtonClassName({
                tone: 'danger',
                size: 'row',
                variant: 'ghost',
                fullWidth: true,
                align: 'left',
                className: 'px-3',
              })}
              role="menuitem"
              type="button"
              onClick={() => {
                setIsOpen(false);
                onDelete(account.id);
              }}
            >
              <Trash2 className="h-4 w-4" />
              Удалить
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

interface AccountInfoDialogProps {
  accountId: string | null;
  fallbackAccount: AccountRow | null;
  isOpen: boolean;
  onClose: () => void;
}

function AccountInfoDialog({
  accountId,
  fallbackAccount,
  isOpen,
  onClose,
}: AccountInfoDialogProps) {
  const [account, setAccount] = useState<ApiAccountRead | null>(null);
  const [telegramStatus, setTelegramStatus] =
    useState<ApiTelegramAuthStatus | null>(null);
  const [shafaStatus, setShafaStatus] = useState<ApiShafaAuthStatus | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen || !accountId) {
      setAccount(null);
      setTelegramStatus(null);
      setShafaStatus(null);
      setLoadError('');
      setIsLoading(false);
      return;
    }

    let isCancelled = false;

    setIsLoading(true);
    setLoadError('');
    setTelegramStatus(null);
    setShafaStatus(null);

    void (async () => {
      const [accountResult, telegramResult, shafaResult] =
        await Promise.allSettled([
          getAccountRequest(accountId),
          getTelegramAuthStatus(accountId),
          getShafaAuthStatus(accountId),
        ]);

      if (isCancelled) {
        return;
      }

      if (accountResult.status === 'fulfilled') {
        setAccount(accountResult.value);
      } else {
        setAccount(null);
        setLoadError(
          formatApiError(
            accountResult.reason,
            'Не удалось загрузить информацию об аккаунте.',
          ),
        );
      }

      if (telegramResult.status === 'fulfilled') {
        setTelegramStatus(telegramResult.value);
      }

      if (shafaResult.status === 'fulfilled') {
        setShafaStatus(shafaResult.value);
      }

      setIsLoading(false);
    })();

    return () => {
      isCancelled = true;
    };
  }, [accountId, isOpen]);

  if (!isOpen || !accountId) {
    return null;
  }

  const title = account?.name || fallbackAccount?.name || 'Аккаунт';
  const statusMeta = account
    ? getAccountStatusMeta(account.status)
    : {
        statusLabel: fallbackAccount?.statusLabel || 'загрузка',
        statusTone: fallbackAccount?.statusTone || 'neutral',
      };
  const isStarted = statusMeta.statusTone === 'success';
  const statusCopy = isStarted ? 'АКТИВЕН' : 'ОСТАНОВЛЕН';
  const statusDescription = isStarted ? 'Рабочий сценарий' : 'Ожидает запуска';
  const accountExtra = isRecord(account?.extra) ? account.extra : {};
  const shafaEmail = extractAccountExtraText(
    accountExtra,
    ['email', 'shafa_email', 'shafaEmail', 'login_email'],
    isLikelyEmail,
  );
  const shafaPhone = extractAccountExtraText(accountExtra, [
    'shafa_phone',
    'shafaPhone',
    'phone_shafa',
    'phone',
  ]);
  const telegramPhone =
    telegramStatus?.phone_number?.trim() ||
    account?.phone?.trim() ||
    fallbackAccount?.phone?.trim() ||
    '';
  const shafaEmailValue = shafaStatus?.email?.trim() || shafaEmail;
  const shafaPhoneValue = shafaStatus?.phone?.trim() || shafaPhone;
  const primaryChannelTemplate = account
    ? getPrimaryChannelTemplate(account.channel_templates)
    : null;
  const accountChannels = account
    ? mapLinksToTelegramChannels(
        account.id,
        primaryChannelTemplate?.links.length
          ? primaryChannelTemplate.links
          : account.channel_links,
        primaryChannelTemplate,
      )
    : (fallbackAccount?.telegramChannels ?? []);
  const templateCount =
    account?.channel_templates.length ??
    fallbackAccount?.channelTemplates?.length ??
    0;
  const timerValue = account
    ? formatTimerLabel(account.timer_minutes)
    : formatAccountTextValue(fallbackAccount?.timer);
  const errorsValue = String(account?.errors ?? fallbackAccount?.errors ?? '0');
  const errorCount = Number.parseInt(errorsValue, 10) || 0;
  const lastRunValue = formatDashboardRunTimestamp(account?.last_run ?? null);
  const createdAtValue = formatAccountDateTime(account?.created_at);
  const updatedAtValue = formatAccountDateTime(account?.updated_at);
  const shouldShowInlineLoadingState =
    isLoading && !account && !fallbackAccount;
  const statusBadgeClassName = isStarted
    ? 'border-success/20 bg-success/12 text-success'
    : 'border-border/20 bg-foreground/70 text-text-muted';
  const infoTileClassName =
    'rounded-2xl border border-border/25 bg-secondary/75 p-5';
  const detailLabelClassName =
    'text-[11px] font-semibold uppercase tracking-widest text-text-muted/75';
  const detailSectionIconClassName =
    'flex h-11 w-11 items-center justify-center rounded-2xl border border-info/15 bg-info/10 text-info';
  const valueToneClassNames: Record<StatusTone, string> = {
    success: 'text-success',
    warning: 'text-warning',
    info: 'text-info',
    danger: 'text-error',
    neutral: 'text-text',
  };
  const renderIdentitySection = (isMobile = false) => (
    <div
      className={cx(
        'flex flex-col gap-5 bg-secondary/75 p-5',
        !isMobile && 'h-full',
      )}
    >
      <div className="space-y-4">
        <div className="space-y-3">
          <h2 className="max-w-[12ch] text-3xl font-semibold tracking-tight text-text md:text-[2.35rem] md:leading-[1.05]">
            {title}
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={cx(
                'inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]',
                statusBadgeClassName,
              )}
            >
              {statusCopy}
            </span>
          </div>
        </div>

        <p className="text-pretty leading-5.5 text-text-muted">
          {statusDescription}. В панели оставлены только рабочие параметры,
          активность и конфигурация каналов аккаунта.
        </p>
      </div>

      <div className="mt-auto space-y-4">
        <div className="rounded-3xl bg-secondary/75 border-border/12.5 border p-5 shadow-[0_20px_45px_rgba(15,23,42,0.12)]">
          <p className={detailLabelClassName}>Таймер запуска</p>
          <strong className="mt-3 block text-3xl font-semibold tracking-tight text-text">
            {timerValue}
          </strong>
          <p
            className={cx(
              'mt-3 text-sm font-medium',
              account?.last_run ? 'text-info' : 'text-text-muted',
            )}
          >
            {account?.last_run
              ? `Последний запуск ${lastRunValue}`
              : 'Запусков пока не было'}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-2xl border-border/12.5 border bg-secondary/75 p-5 shadow-[0_20px_45px_rgba(15,23,42,0.09)]">
            <p className={detailLabelClassName}>Каналы</p>
            <strong className="mt-3 block text-2xl font-semibold tracking-tight text-text">
              {accountChannels.length}
            </strong>
          </div>
          <div className="rounded-2xl border-border/12.5 border bg-secondary/75 p-5 shadow-[0_20px_45px_rgba(15,23,42,0.09)]">
            <p className={detailLabelClassName}>Ошибки</p>
            <strong
              className={cx(
                'mt-3 block text-2xl font-semibold tracking-tight',
                errorCount > 0 ? 'text-error' : 'text-text',
              )}
            >
              {errorsValue}
            </strong>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 p-4 backdrop-blur-sm md:p-8"
      role="dialog"
      onClick={onClose}
    >
      <div
        className="flex max-h-[calc(100vh-32px)] w-full max-w-295 overflow-hidden rounded-[34px] border border-border/15 bg-foreground shadow-[0_32px_90px_rgba(15,23,42,0.24)]"
        onClick={(event) => event.stopPropagation()}
      >
        <aside className="hidden w-[320px] shrink-0 border-r border-border/25 md:flex lg:w-90">
          {renderIdentitySection()}
        </aside>

        <div className="flex min-h-0 flex-1 flex-col bg-foreground">
          <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-border/25 bg-foreground/75 p-5 backdrop-blur">
            <div className="flex min-w-0 items-center gap-3">
              <h3 className="text-2xl font-semibold tracking-tight text-text">
                Детали аккаунта
              </h3>
              {isLoading ? (
                <span className="inline-flex shrink-0 items-center rounded-full border border-border/20 bg-secondary/70 px-3 py-1 text-xs font-medium text-text-muted">
                  Обновляем данные…
                </span>
              ) : null}
            </div>

            <button
              aria-label="Закрыть просмотр аккаунта"
              className={getButtonClassName({
                size: 'icon-sm',
                variant: 'solid',
                tone: 'info',
                className: 'rounded-xl',
              })}
              type="button"
              onClick={onClose}
            >
              <X className="h-5 w-5" />
            </button>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-6 pt-5 md:px-8 md:pb-8">
            <div className="mb-8 md:hidden">{renderIdentitySection(true)}</div>

            <div className="space-y-8 md:space-y-10">
              {loadError ? (
                <div className="rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
                  {loadError}
                </div>
              ) : null}

              {shouldShowInlineLoadingState ? (
                <div className="rounded-2xl border border-border/15 bg-secondary/60 px-4 py-3 text-sm text-text-muted">
                  Загружаем данные аккаунта...
                </div>
              ) : null}

              <section className="space-y-5">
                <div className="flex items-center gap-3">
                  <div className={detailSectionIconClassName}>
                    <User className="h-5 w-5" />
                  </div>
                  <h4 className="text-xl font-semibold tracking-tight text-text">
                    Профиль аккаунта
                  </h4>
                </div>

                <div className="grid gap-4 xl:grid-cols-2">
                  <div className={infoTileClassName}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1 min-w-0">
                        <p className={detailLabelClassName}>Телефон Telegram</p>
                        <strong className="block text-lg leading-7 text-text">
                          {formatAccountTextValue(telegramPhone)}
                        </strong>
                      </div>
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-info/10 bg-info/5">
                        <Phone className="h-5 w-5" />
                      </div>
                    </div>
                  </div>

                  <div className={infoTileClassName}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1 min-w-0">
                        <p className={detailLabelClassName}>Shafa email</p>
                        <strong className="block text-lg leading-7 text-text">
                          {formatAccountTextValue(shafaEmailValue)}
                        </strong>
                      </div>
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-info/15 bg-info/10 text-info">
                        <Mail className="h-5 w-5" />
                      </div>
                    </div>
                  </div>

                  <div className={infoTileClassName}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1 min-w-0">
                        <p className={detailLabelClassName}>Телефон Shafa</p>
                        <strong className="block text-lg leading-7 text-text">
                          {formatAccountTextValue(shafaPhoneValue)}
                        </strong>
                      </div>
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-info/15 bg-info/10 text-info">
                        <Phone className="h-5 w-5" />
                      </div>
                    </div>
                  </div>

                  <div className={infoTileClassName}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-1 min-w-0">
                        <p className={detailLabelClassName}>Шаблоны каналов</p>
                        <strong className="block text-lg leading-7 text-text">
                          {templateCount > 0
                            ? `${templateCount} шаблонов`
                            : 'Не найдены'}
                        </strong>
                      </div>
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-info/15 bg-info/10 text-info">
                        <Link2 className="h-5 w-5" />
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <section className="space-y-5">
                <div className="flex items-center gap-3">
                  <div className={detailSectionIconClassName}>
                    <Clock3 className="h-5 w-5" />
                  </div>
                  <h4 className="text-xl font-semibold tracking-tight text-text">
                    Тайминг и активность
                  </h4>
                </div>

                <div className="rounded-[30px] border border-border/25 bg-secondary/55 p-5">
                  <div className="space-y-1">
                    {[
                      {
                        label: 'Статус аккаунта',
                        value: statusCopy,
                        tone: statusMeta.statusTone,
                      },
                      {
                        label: 'Таймер запуска',
                        value: timerValue,
                        tone: 'neutral' as const,
                      },
                      {
                        label: 'Последний запуск',
                        value: lastRunValue,
                        tone: account?.last_run
                          ? ('info' as const)
                          : ('neutral' as const),
                      },
                      {
                        label: 'Создан',
                        value: createdAtValue,
                        tone: 'neutral' as const,
                      },
                      {
                        label: 'Обновлён',
                        value: updatedAtValue,
                        tone: 'neutral' as const,
                      },
                    ].map((item, index, items) => (
                      <div key={item.label}>
                        <div className="flex flex-col gap-2 py-4 sm:flex-row sm:items-center sm:justify-between">
                          <span className="text-sm font-medium text-text-muted">
                            {item.label}
                          </span>
                          <strong
                            className={cx(
                              'text-base font-semibold',
                              valueToneClassNames[item.tone],
                            )}
                          >
                            {item.value}
                          </strong>
                        </div>
                        {index < items.length - 1 ? (
                          <div className="h-px w-full bg-border/25" />
                        ) : null}
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="space-y-5">
                <div className="flex items-center gap-3">
                  <div className={detailSectionIconClassName}>
                    <Link2 className="h-5 w-5" />
                  </div>
                  <h4 className="text-xl font-semibold tracking-tight text-text">
                    Telegram-каналы
                  </h4>
                </div>

                <div className="rounded-[30px] border border-border/25 bg-secondary/55 p-5">
                  <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className={detailLabelClassName}>Количество каналов</p>
                      <strong className="mt-3 block text-2xl font-semibold tracking-tight text-text">
                        {accountChannels.length}
                      </strong>
                    </div>
                  </div>

                  {accountChannels.length > 0 ? (
                    <div className="space-y-2.5">
                      {accountChannels.map((channel) => (
                        <TelegramChannelCard
                          key={channel.id}
                          channel={channel}
                          compact
                        />
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm leading-6 text-text-muted">
                      Каналы ещё не настроены.
                    </p>
                  )}
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function AccountTemplatesNotice() {
  return (
    <div className="rounded-[22px] border border-dashed border-border/25 bg-secondary/45 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-info">
          <Link2 className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <strong className="block text-text">Telegram-каналы</strong>
          <p className="leading-6 text-text-muted">
            После создания аккаунта каналы настраиваются через API
            `channel-templates` и синхронизируются с рабочим runtime-списком
            аккаунта.
          </p>
        </div>
      </div>
    </div>
  );
}

function CreateAccountAccessNotice() {
  return (
    <div className="rounded-[22px] border border-border/20 bg-secondary/55 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-info">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <strong className="block text-text">
            Shafa и Telegram авторизация
          </strong>
          <p className="leading-6 text-text-muted">
            После создания аккаунта здесь появятся рабочие сценарии импорта
            Shafa-сессии и пошагового входа в Telegram.
          </p>
        </div>
      </div>
    </div>
  );
}

interface AuthInputFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  icon?: ReactNode;
  type?: 'text' | 'tel' | 'password';
  placeholder?: string;
  disabled?: boolean;
}

function AuthInputField({
  label,
  value,
  onChange,
  icon,
  type = 'text',
  placeholder,
  disabled = false,
}: AuthInputFieldProps) {
  return (
    <label className="flex flex-col gap-2.5">
      <span className={fieldLabelClassName}>
        {icon}
        {label}
      </span>
      <input
        className={`${accountControlClassName} ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
        disabled={disabled}
        placeholder={placeholder}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

interface AccountAuthPanelProps {
  account: AccountRow;
  accounts: AccountRow[];
  onReloadAccounts: () => Promise<void>;
}

function AccountAuthPanel({
  account,
  accounts,
  onReloadAccounts,
}: AccountAuthPanelProps) {
  const [telegramStatus, setTelegramStatus] =
    useState<ApiTelegramAuthStatus | null>(null);
  const [shafaStatus, setShafaStatus] = useState<ApiShafaAuthStatus | null>(
    null,
  );
  const [isStatusLoading, setIsStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState('');

  const loadStatuses = async () => {
    setIsStatusLoading(true);
    setStatusError('');

    const [telegramResult, shafaResult] = await Promise.allSettled([
      getTelegramAuthStatus(account.id),
      getShafaAuthStatus(account.id),
    ]);

    const nextErrors: string[] = [];

    if (telegramResult.status === 'fulfilled') {
      setTelegramStatus(telegramResult.value);
    } else {
      nextErrors.push(
        formatApiError(
          telegramResult.reason,
          'Не удалось загрузить статус Telegram.',
        ),
      );
    }

    if (shafaResult.status === 'fulfilled') {
      setShafaStatus(shafaResult.value);
    } else {
      nextErrors.push(
        formatApiError(
          shafaResult.reason,
          'Не удалось загрузить статус Shafa.',
        ),
      );
    }

    setStatusError(joinUniqueMessages(nextErrors));
    setIsStatusLoading(false);
  };

  useEffect(() => {
    void loadStatuses();
  }, [account.id]);

  return (
    <div className="space-y-6">
      {statusError ? (
        <div className="rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          {statusError}
        </div>
      ) : null}

      <ShafaSessionCard
        accountId={account.id}
        isStatusLoading={isStatusLoading}
        status={shafaStatus}
        onRefreshStatuses={loadStatuses}
        onReloadAccounts={onReloadAccounts}
      />

      <TelegramAuthCard
        accountId={account.id}
        accounts={accounts}
        isStatusLoading={isStatusLoading}
        status={telegramStatus}
        onRefreshStatuses={loadStatuses}
        onReloadAccounts={onReloadAccounts}
      />
    </div>
  );
}

interface ShafaSessionCardProps {
  accountId: string;
  status: ApiShafaAuthStatus | null;
  isStatusLoading: boolean;
  onRefreshStatuses: () => Promise<void>;
  onReloadAccounts: () => Promise<void>;
}

function ShafaSessionCard({
  accountId,
  status,
  isStatusLoading,
  onRefreshStatuses,
  onReloadAccounts,
}: ShafaSessionCardProps) {
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isBrowserLoginPending, setIsBrowserLoginPending] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const statusMeta = getShafaStatusMeta(status);
  const isConnected = Boolean(status?.connected);

  useEffect(() => {
    setFeedback('');
    setError('');
    setIsBrowserLoginPending(false);
  }, [accountId]);

  useEffect(() => {
    if (!isBrowserLoginPending) {
      return;
    }

    if (status?.connected) {
      setIsBrowserLoginPending(false);
      setFeedback('Shafa cookies сохранены. Аккаунт подключён.');
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void onRefreshStatuses();
    }, 2500);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [isBrowserLoginPending, onRefreshStatuses, status?.connected]);

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    setIsSubmitting(true);
    setError('');
    setFeedback('');

    try {
      const nextValue = await file.text();
      const payload = parseShafaImportInput(nextValue);
      const nextStatus = await saveShafaStorageState(accountId, payload);
      setFeedback(`Импортирован ${file.name}. ${nextStatus.message}`);
      await Promise.all([onRefreshStatuses(), onReloadAccounts()]);
    } catch (nextError) {
      setError(
        formatApiError(
          nextError,
          `Не удалось импортировать cookies из файла ${file.name}.`,
        ),
      );
    } finally {
      setIsSubmitting(false);
      event.target.value = '';
    }
  };

  const handleBrowserLogin = async () => {
    setIsSubmitting(true);
    setError('');
    setFeedback('');

    try {
      const nextStatus = await startShafaBrowserLogin(accountId);
      setFeedback(nextStatus.message);
      setIsBrowserLoginPending(true);
      await onRefreshStatuses();
    } catch (nextError) {
      setError(
        formatApiError(
          nextError,
          'Не удалось запустить Shafa login flow через браузер.',
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLogout = async () => {
    setIsSubmitting(true);
    setError('');
    setFeedback('');
    setIsBrowserLoginPending(false);

    try {
      const nextStatus = await logoutShafa(accountId);
      setFeedback(nextStatus.message);
      await Promise.all([onRefreshStatuses(), onReloadAccounts()]);
    } catch (nextError) {
      setError(formatApiError(nextError, 'Не удалось выйти из Shafa.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const isAuthActionDisabled = isSubmitting || isStatusLoading;

  return (
    <div className="rounded-[22px] border border-border/20 bg-secondary/55 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-info">
              <ShieldCheck className="h-6 w-6" />
            </div>

            <div className="space-y-1">
              <p className={cardTitleClassName}>Доступ к аккаунту Shafa</p>
              <div className="flex flex-wrap gap-2">
                <StatusPill tone={statusMeta.tone}>
                  {statusMeta.label}
                </StatusPill>
                <StatusPill
                  tone={status && status.cookies_count > 0 ? 'info' : 'neutral'}
                >
                  cookies: {status?.cookies_count ?? 0}
                </StatusPill>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-4">
          {isConnected ? (
            <button
              className="inline-flex items-center gap-2 self-center px-1 text-sm text-error/75 transition-colors hover:text-error cursor-pointer font-medium disabled:cursor-not-allowed disabled:text-error/45"
              disabled={isAuthActionDisabled}
              type="button"
              onClick={() => void handleLogout()}
            >
              {isSubmitting ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : null}
              Выйти
            </button>
          ) : (
            <ActionButton
              disabled={isAuthActionDisabled}
              icon={
                isSubmitting ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <LogIn className="h-4 w-4" />
                )
              }
              tone="info"
              variant="solid"
              onClick={() => void handleBrowserLogin()}
            >
              Войти через браузер
            </ActionButton>
          )}
          <input
            ref={fileInputRef}
            accept=".json,application/json"
            className="hidden"
            type="file"
            onChange={(event) => void handleFileChange(event)}
          />
          <ActionButton
            disabled={isSubmitting}
            icon={<FileJson className="h-4 w-4" />}
            onClick={() => fileInputRef.current?.click()}
          >
            Загрузить JSON
          </ActionButton>
        </div>
      </div>
      {error ? (
        <p className="mt-3 text-sm leading-6 text-error">{error}</p>
      ) : null}
      {feedback ? (
        <p className="mt-3 text-sm leading-6 text-text-muted">{feedback}</p>
      ) : null}
    </div>
  );
}

interface TelegramAuthCardProps {
  accountId: string;
  accounts: AccountRow[];
  status: ApiTelegramAuthStatus | null;
  isStatusLoading: boolean;
  onRefreshStatuses: () => Promise<void>;
  onReloadAccounts: () => Promise<void>;
}

function TelegramAuthCard({
  accountId,
  accounts,
  status,
  isStatusLoading,
  onRefreshStatuses,
  onReloadAccounts,
}: TelegramAuthCardProps) {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef<HTMLDivElement | null>(null);
  const stepMeta = getTelegramStepMeta(status);
  const isConnected = Boolean(status?.connected);
  const connectedPhoneLabel = status?.phone_number?.trim() || 'Номер не найден';
  const sessionSourceAccounts = [...accounts]
    .filter((account) => account.id !== accountId)
    .sort((leftAccount, rightAccount) => {
      const leftHasSession = Boolean(leftAccount.telegramSessionExists);
      const rightHasSession = Boolean(rightAccount.telegramSessionExists);

      if (leftHasSession !== rightHasSession) {
        return rightHasSession ? 1 : -1;
      }

      return leftAccount.name.localeCompare(rightAccount.name, 'ru', {
        sensitivity: 'base',
      });
    });
  const hasSessionSources = sessionSourceAccounts.length > 0;
  const hasCopyableSessionSource = sessionSourceAccounts.some((account) =>
    Boolean(account.telegramSessionExists),
  );
  const sessionImportLabel = !hasSessionSources
    ? 'Нет других аккаунтов'
    : hasCopyableSessionSource
      ? 'Импортировать из аккаунта'
      : 'Выбрать аккаунт';

  useEffect(() => {
    setPhone(status?.phone_number ?? '');
    setCode('');
    setPassword('');
    setFeedback('');
    setError('');
    setIsAccountMenuOpen(false);
  }, [accountId]);

  useEffect(() => {
    if (status?.phone_number) {
      setPhone(status.phone_number);
    }
  }, [status?.phone_number]);

  useEffect(() => {
    if (!isAccountMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (
        accountMenuRef.current &&
        event.target instanceof Node &&
        !accountMenuRef.current.contains(event.target)
      ) {
        setIsAccountMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsAccountMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAccountMenuOpen]);

  const runTelegramAction = async (
    action: () => Promise<ApiTelegramAuthStatus>,
    fallbackMessage: string,
  ) => {
    setIsSubmitting(true);
    setError('');
    setFeedback('');

    try {
      const nextStatus = await action();

      setFeedback(nextStatus.message);
      if (nextStatus.phone_number) {
        setPhone(nextStatus.phone_number);
      }
      if (nextStatus.current_step !== 'WAIT_CODE') {
        setCode('');
      }
      if (nextStatus.current_step !== 'WAIT_PASSWORD') {
        setPassword('');
      }

      await Promise.all([onRefreshStatuses(), onReloadAccounts()]);
    } catch (nextError) {
      setError(formatApiError(nextError, fallbackMessage));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSessionImport = async (sourceAccountId: string) => {
    setIsSubmitting(true);
    setIsAccountMenuOpen(false);
    setError('');
    setFeedback('');

    try {
      const nextStatus = await copyTelegramSession(accountId, {
        source_account_id: sourceAccountId,
      });

      setFeedback(nextStatus.message);
      if (nextStatus.phone_number) {
        setPhone(nextStatus.phone_number);
      }
      setCode('');
      setPassword('');

      await Promise.all([onRefreshStatuses(), onReloadAccounts()]);
    } catch (nextError) {
      setError(
        formatApiError(
          nextError,
          'Не удалось импортировать Telegram session из другого аккаунта.',
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const showCodeField = status?.current_step === 'WAIT_CODE';
  const showPasswordField = status?.current_step === 'WAIT_PASSWORD';
  const isPhoneDisabled =
    isSubmitting ||
    isStatusLoading ||
    !phone.trim() ||
    !status?.has_api_credentials ||
    isConnected;
  const isCodeDisabled =
    isSubmitting || isStatusLoading || !code.trim() || !showCodeField;
  const isPasswordDisabled =
    isSubmitting || isStatusLoading || !password.trim() || !showPasswordField;
  const isLogoutDisabled = isSubmitting || isStatusLoading || !isConnected;
  const isAccountMenuDisabled =
    isSubmitting || isStatusLoading || (!isConnected && !hasSessionSources);

  return (
    <div className="rounded-[22px] border border-border/20 bg-secondary/55 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-info">
              <LogIn className="h-6 w-6" />
            </div>

            <div className="space-y-1">
              <p className={cardTitleClassName}>Telegram авторизация</p>
              <div className="flex flex-wrap gap-2">
                <StatusPill tone={stepMeta.tone}>{stepMeta.label}</StatusPill>
              </div>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isConnected ? null : (
            <div className="relative" ref={accountMenuRef}>
              <ActionButton
                aria-expanded={isAccountMenuOpen}
                aria-haspopup="menu"
                disabled={isAccountMenuDisabled}
                icon={
                  isSubmitting ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )
                }
                size="sm"
                onClick={() =>
                  setIsAccountMenuOpen((currentValue) => !currentValue)
                }
              >
                {sessionImportLabel}
              </ActionButton>

              {isAccountMenuOpen ? (
                <div className="absolute top-full right-0 z-10 mt-2 w-80 max-w-[calc(100vw-3rem)] rounded-2xl border border-border/20 bg-foreground p-2 shadow-[0_18px_40px_rgba(15,23,42,0.14)]">
                  <p className="px-3 py-2 text-xs font-medium tracking-wide text-text-muted uppercase">
                    Выберите аккаунт-источник
                  </p>
                  <div className="flex max-h-72 flex-col gap-1 overflow-y-auto">
                    {sessionSourceAccounts.map((sourceAccount) => {
                      const hasTelegramSession = Boolean(
                        sourceAccount.telegramSessionExists,
                      );
                      const sourcePhoneLabel =
                        sourceAccount.phone?.trim() || 'Телефон не указан';

                      return (
                        <button
                          key={sourceAccount.id}
                          className={getButtonClassName({
                            size: 'row',
                            variant: 'ghost',
                            fullWidth: true,
                            align: 'left',
                            className: hasTelegramSession
                              ? 'justify-between'
                              : 'justify-between text-text-muted/70',
                          })}
                          disabled={!hasTelegramSession || isSubmitting}
                          type="button"
                          onClick={() =>
                            void handleSessionImport(sourceAccount.id)
                          }
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">
                              {sourceAccount.name}
                            </span>
                            <span className="block truncate text-xs text-text-muted">
                              {sourcePhoneLabel}
                            </span>
                          </span>
                          <StatusPill
                            tone={hasTelegramSession ? 'success' : 'neutral'}
                          >
                            {hasTelegramSession
                              ? 'Есть session'
                              : 'Нет session'}
                          </StatusPill>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {isConnected ? (
            <div className="relative" ref={accountMenuRef}>
              <div className="flex h-10 items-center gap-3 rounded-xl border border-border/50 bg-secondary px-3 font-medium">
                <button
                  aria-expanded={isAccountMenuOpen}
                  aria-haspopup="menu"
                  className="inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-l-xl border-r border-border/50 pr-3 text-sm font-medium text-text-muted/75 transition-colors duration-200 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={isAccountMenuDisabled}
                  type="button"
                  onClick={() =>
                    setIsAccountMenuOpen((currentValue) => !currentValue)
                  }
                >
                  {isSubmitting ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <ChevronDown
                      className={`h-4 w-4 transition-transform duration-200 ${isAccountMenuOpen ? 'rotate-180 text-text' : ''}`}
                    />
                  )}
                </button>
                {connectedPhoneLabel}
              </div>

              {isAccountMenuOpen ? (
                <button
                  className={getButtonClassName({
                    tone: 'danger',
                    size: 'row',
                    fullWidth: true,
                    align: 'left',
                    className:
                      'absolute top-full hover:bg-secondary right-0 z-10 mt-2 bg-foreground shadow-[0_18px_40px_rgba(15,23,42,0.14)]',
                  })}
                  disabled={isLogoutDisabled}
                  type="button"
                  onClick={() => {
                    setIsAccountMenuOpen(false);
                    void runTelegramAction(
                      () => logoutTelegram(accountId),
                      'Не удалось выйти из Telegram.',
                    );
                  }}
                >
                  {isSubmitting ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <LogOut className="h-4 w-4" />
                  )}
                  Выйти из аккаунта
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {isConnected ? null : (
        <>
          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <AuthInputField
              label="Телефон Telegram"
              value={phone}
              type="tel"
              placeholder="+380501112233"
              icon={<Phone className="h-4 w-4 text-info/75" />}
              disabled={isSubmitting}
              onChange={setPhone}
            />
            <button
              className={getButtonClassName({
                tone: 'info',
                variant: 'solid',
              })}
              disabled={isPhoneDisabled}
              type="button"
              onClick={() =>
                void runTelegramAction(
                  () =>
                    requestTelegramCode(accountId, {
                      phone: phone.trim(),
                    }),
                  'Не удалось запросить код Telegram.',
                )
              }
            >
              {isSubmitting ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Phone className="h-4 w-4" />
              )}
              {showCodeField ? 'Запросить новый код' : 'Запросить код'}
            </button>
          </div>

          {showCodeField ? (
            <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
              <AuthInputField
                label="Код из Telegram"
                value={code}
                placeholder="Введи код подтверждения"
                icon={<LogIn className="h-4 w-4 text-info/80" />}
                disabled={isSubmitting}
                onChange={setCode}
              />
              <button
                className={getButtonClassName({
                  tone: 'info',
                  variant: 'solid',
                })}
                disabled={isCodeDisabled}
                type="button"
                onClick={() =>
                  void runTelegramAction(
                    () =>
                      submitTelegramCode(accountId, {
                        code: code.trim(),
                      }),
                    'Не удалось подтвердить Telegram код.',
                  )
                }
              >
                {isSubmitting ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                Подтвердить код
              </button>
            </div>
          ) : null}

          {showPasswordField ? (
            <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
              <AuthInputField
                label="Telegram 2FA пароль"
                value={password}
                type="password"
                placeholder="Введи пароль двухфакторной защиты"
                icon={<LockKeyhole className="h-4 w-4 text-info/80" />}
                disabled={isSubmitting}
                onChange={setPassword}
              />
              <button
                className={getButtonClassName({
                  tone: 'info',
                  variant: 'solid',
                })}
                disabled={isPasswordDisabled}
                type="button"
                onClick={() =>
                  void runTelegramAction(
                    () =>
                      submitTelegramPassword(accountId, {
                        password,
                      }),
                    'Не удалось отправить Telegram 2FA пароль.',
                  )
                }
              >
                {isSubmitting ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                Завершить вход
              </button>
            </div>
          ) : null}
        </>
      )}

      {!status?.has_api_credentials ? (
        <p className="mt-3 text-sm leading-6 text-text-muted">
          Telegram API ID и API hash должны быть заданы на backend через `.env`
          или env variables.
        </p>
      ) : null}

      {error ? (
        <p className="mt-3 text-sm leading-6 text-error">{error}</p>
      ) : null}
      {feedback ? (
        <p className="mt-3 text-sm leading-6 text-text-muted">{feedback}</p>
      ) : null}
    </div>
  );
}

interface AccountDetailsDialogProps {
  account: AccountRow | null;
  accounts: AccountRow[];
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onSyncAccountChannels: (
    accountId: string,
    channelLinks: string[],
  ) => Promise<void>;
  onUpdateAccount: (accountId: string, draft: AccountDraft) => Promise<void>;
  onReloadAccounts: () => Promise<void>;
}

function AccountDetailsDialog({
  account,
  accounts,
  isOpen,
  isSubmitting,
  onClose,
  onSyncAccountChannels,
  onUpdateAccount,
  onReloadAccounts,
}: AccountDetailsDialogProps) {
  const [draft, setDraft] = useState<AccountDraft>(accountDraftInitialState);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (!isOpen || !account) {
      setDraft(accountDraftInitialState);
      setSubmitError('');
      return;
    }

    setDraft(getAccountDraftFromRow(account));
    setSubmitError('');
  }, [account, isOpen]);

  if (!isOpen || !account) {
    return null;
  }

  const isSubmitDisabled = !isAccountDraftValid(draft) || isSubmitting;

  return (
    <AccountDialogShell
      closeLabel="Закрыть настройки аккаунта"
      isOpen={isOpen}
      onClose={onClose}
      statusBadge={
        <div className="flex flex-wrap gap-2">
          <StatusPill tone={account.statusTone}>
            {account.statusLabel}
          </StatusPill>
          <StatusPill tone={account.shafaSessionExists ? 'success' : 'neutral'}>
            Shafa
          </StatusPill>
          <StatusPill
            tone={account.telegramSessionExists ? 'success' : 'neutral'}
          >
            Telegram
          </StatusPill>
        </div>
      }
      title={account.name}
    >
      <div className="space-y-6 pt-6">
        <AccountFormFields
          values={draft}
          onFieldChange={(field, value) =>
            setDraft((currentDraft) => ({
              ...currentDraft,
              [field]: value,
            }))
          }
        />

        <AccountAuthPanel
          account={account}
          accounts={accounts}
          onReloadAccounts={onReloadAccounts}
        />

        <TelegramChannelsPanel
          account={account}
          isSubmittingAccount={isSubmitting}
          onSyncAccountChannels={onSyncAccountChannels}
        />

        {submitError ? (
          <p className="text-sm text-error">{submitError}</p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          <ActionButton
            icon={<X className="h-4 w-4" />}
            size="md"
            onClick={onClose}
          >
            Отмена
          </ActionButton>
          <ActionButton
            disabled={isSubmitDisabled}
            icon={<Save className="h-4 w-4" />}
            tone="info"
            variant="solid"
            onClick={async () => {
              setSubmitError('');

              try {
                await onUpdateAccount(account.id, draft);
                onClose();
              } catch (error) {
                setSubmitError(
                  formatApiError(
                    error,
                    'Не удалось сохранить изменения аккаунта.',
                  ),
                );
              }
            }}
          >
            Сохранить
          </ActionButton>
        </div>
      </div>
    </AccountDialogShell>
  );
}

interface CreateAccountDialogProps {
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onCreateAccount: (draft: AccountDraft) => Promise<void>;
}

function CreateAccountDialog({
  isOpen,
  isSubmitting,
  onClose,
  onCreateAccount,
}: CreateAccountDialogProps) {
  const [draft, setDraft] = useState<AccountDraft>(accountDraftInitialState);
  const [submitError, setSubmitError] = useState('');
  const isSubmitDisabled = !isAccountDraftValid(draft) || isSubmitting;

  useEffect(() => {
    if (isOpen) {
      return;
    }

    setDraft(accountDraftInitialState);
    setSubmitError('');
  }, [isOpen]);

  return (
    <AccountDialogShell
      closeLabel="Закрыть форму добавления аккаунта"
      isOpen={isOpen}
      onClose={onClose}
      title="Новый аккаунт"
    >
      <div className="space-y-6 pt-6">
        <div className="space-y-1">
          <p className="leading-6 text-text-muted">
            Заполни базовые параметры аккаунта. Telegram-каналы можно будет
            добавить сразу после сохранения через меню `...`.
          </p>
        </div>

        <AccountFormFields
          values={draft}
          onFieldChange={(field, value) =>
            setDraft((currentDraft) => ({
              ...currentDraft,
              [field]: value,
            }))
          }
        />

        <CreateAccountAccessNotice />

        <AccountTemplatesNotice />

        {submitError ? (
          <p className="text-sm text-error">{submitError}</p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          <ActionButton
            icon={<X className="h-4 w-4" />}
            size="md"
            onClick={onClose}
          >
            Отмена
          </ActionButton>
          <ActionButton
            disabled={isSubmitDisabled}
            icon={<Save className="h-4 w-4" />}
            tone="info"
            variant="solid"
            onClick={async () => {
              if (isSubmitDisabled) {
                return;
              }

              setSubmitError('');

              try {
                await onCreateAccount(draft);
                onClose();
              } catch (error) {
                setSubmitError(
                  formatApiError(error, 'Не удалось создать аккаунт.'),
                );
              }
            }}
          >
            Создать аккаунт
          </ActionButton>
        </div>
      </div>
    </AccountDialogShell>
  );
}

interface DeleteAccountsDialogProps {
  accounts: AccountRow[];
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  onRemoveAccount: (accountId: string) => void;
}

function DeleteAccountsDialog({
  accounts,
  isOpen,
  isSubmitting,
  onClose,
  onConfirm,
  onRemoveAccount,
}: DeleteAccountsDialogProps) {
  const [submitError, setSubmitError] = useState('');
  const isSingleAccount = accounts.length === 1;
  const accountLabel = formatAccountCount(accounts.length);
  const accountSignature = accounts
    .map((account) => `${account.id}:${account.name}`)
    .join('|');
  const dialogTitle = isSingleAccount
    ? 'Удаление аккаунта'
    : 'Удаление аккаунтов';

  useEffect(() => {
    if (!isOpen) {
      setSubmitError('');
      return;
    }

    setSubmitError('');
  }, [isOpen, accountSignature]);

  if (!isOpen || accounts.length === 0) {
    return null;
  }

  return (
    <AccountDialogShell
      closeLabel="Закрыть подтверждение удаления"
      isOpen={isOpen}
      onClose={onClose}
      title={dialogTitle}
    >
      <div className="space-y-6 pt-6">
        <div className="rounded-[22px] border border-error/25 bg-error/8 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-error/12 text-error">
              <TriangleAlert className="h-5 w-5" />
            </div>
            <div className="space-y-1.5">
              <strong className="block text-text">Действие необратимо</strong>
              <p className="leading-6 text-text-muted">
                Будут удалены настройки, сессии, локальная база, логи и другие
                файлы выбранного аккаунта из каталога `accounts`. Автоматически
                восстановить их не получится.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <p className="leading-6 text-text-muted">
            {isSingleAccount
              ? 'Вы уверены, что хотите удалить этот аккаунт?'
              : `Вы уверены, что хотите удалить выбранные ${accountLabel}?`}
          </p>
          <div className="flex flex-wrap items-start gap-3">
            <span className="pt-1 text-sm font-semibold text-text">
              Будут удалены:
            </span>
            <div className="flex flex-wrap gap-2.5">
              {accounts.map((account) =>
                isSingleAccount ? (
                  <span
                    key={account.id}
                    className="inline-flex items-center rounded-xl border border-error/25 bg-secondary px-3 py-1 text-sm font-medium text-text"
                  >
                    {account.name}
                  </span>
                ) : (
                  <button
                    key={account.id}
                    className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-error/25 bg-secondary px-3 py-1 text-sm font-medium text-text transition hover:border-error/40 hover:bg-error/8 disabled:cursor-not-allowed disabled:opacity-55"
                    disabled={isSubmitting}
                    type="button"
                    onClick={() => onRemoveAccount(account.id)}
                  >
                    <span>{account.name}</span>
                    <X className="stroke-3 text-error h-3.5 w-3.5" />
                  </button>
                ),
              )}
            </div>
          </div>
        </div>

        {submitError ? (
          <p className="text-sm text-error">{submitError}</p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          <ActionButton
            icon={<X className="h-4 w-4" />}
            size="md"
            onClick={onClose}
          >
            Отмена
          </ActionButton>
          <ActionButton
            disabled={isSubmitting}
            icon={<Trash2 className="h-4 w-4" />}
            tone="danger"
            variant="solid"
            onClick={async () => {
              if (isSubmitting) {
                return;
              }

              setSubmitError('');

              try {
                await onConfirm();
              } catch (error) {
                setSubmitError(
                  formatApiError(
                    error,
                    'Не удалось удалить выбранные аккаунты.',
                  ),
                );
              }
            }}
          >
            {isSingleAccount ? 'Удалить аккаунт' : `Удалить ${accountLabel}`}
          </ActionButton>
        </div>
      </div>
    </AccountDialogShell>
  );
}

interface TelegramChannelsPanelProps {
  account: AccountRow;
  isSubmittingAccount: boolean;
  onSyncAccountChannels: (
    accountId: string,
    channelLinks: string[],
  ) => Promise<void>;
}

interface TelegramChannelComposerProps {
  draft: TelegramChannelDraft;
  isSubmitting?: boolean;
  deleteLabel?: string;
  submitLabel: string;
  title: string;
  onCancel: () => void;
  onDelete?: () => void;
  onDraftChange: (
    field: keyof TelegramChannelDraft,
    value: TelegramChannelDraft[keyof TelegramChannelDraft],
  ) => void;
  onSubmit: () => void;
}

function TelegramChannelsPanel({
  account,
  isSubmittingAccount,
  onSyncAccountChannels,
}: TelegramChannelsPanelProps) {
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [composerDraft, setComposerDraft] = useState<TelegramChannelDraft>(
    telegramDraftInitialState,
  );
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<TelegramChannelDraft>(
    telegramDraftInitialState,
  );
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const accountChannelTemplates = account.channelTemplates ?? [];
  const activeTemplate = getPrimaryChannelTemplate(accountChannelTemplates);
  const activeTemplateName = activeTemplate?.name ?? defaultChannelTemplateName;
  const channels = account.telegramChannels;
  const channelHandles = channels.map((channel) => channel.handle);
  const hasAdditionalTemplates = accountChannelTemplates.length > 1;
  const isActionDisabled = isSubmitting || isSubmittingAccount;

  useEffect(() => {
    setIsComposerOpen(false);
    setComposerDraft(telegramDraftInitialState);
    setEditingChannelId(null);
    setEditingDraft(telegramDraftInitialState);
    setFeedback('');
    setError('');
  }, [account.id]);

  const startEditing = (channel: TelegramChannel) => {
    setEditingChannelId(channel.id);
    setEditingDraft({
      handle: channel.handle,
    });
  };

  const resetEditing = () => {
    setEditingChannelId(null);
    setEditingDraft(telegramDraftInitialState);
  };

  const persistChannels = async (
    nextLinks: string[],
    successMessage: string,
  ) => {
    const normalizedLinks = normalizeTelegramLinks(nextLinks);

    setIsSubmitting(true);
    setError('');
    setFeedback('');

    try {
      if (activeTemplate) {
        if (normalizedLinks.length === 0) {
          await deleteChannelTemplateRequest(account.id, activeTemplate.name);
        } else {
          await updateChannelTemplateRequest(account.id, activeTemplate.name, {
            links: normalizedLinks,
          });
        }
      } else if (normalizedLinks.length > 0) {
        await createChannelTemplateRequest(account.id, {
          name: activeTemplateName,
          links: normalizedLinks,
        });
      }

      await onSyncAccountChannels(account.id, normalizedLinks);
      setFeedback(successMessage);
      return true;
    } catch (nextError) {
      setError(
        formatApiError(
          nextError,
          'Не удалось синхронизировать Telegram-каналы через API.',
        ),
      );
      return false;
    } finally {
      setIsSubmitting(false);
    }
  };

  const submitNewChannel = async () => {
    const normalizedHandle = normalizeTelegramHandle(composerDraft.handle);

    if (!normalizedHandle) {
      return;
    }

    const saved = await persistChannels(
      [...channelHandles, normalizedHandle],
      'Канал добавлен и синхронизирован с аккаунтом.',
    );

    if (!saved) {
      return;
    }

    setComposerDraft(telegramDraftInitialState);
    setIsComposerOpen(false);
  };

  const submitEditedChannel = async () => {
    if (!editingChannelId) {
      return;
    }

    const normalizedHandle = normalizeTelegramHandle(editingDraft.handle);

    if (!normalizedHandle) {
      return;
    }

    const targetIndex = channels.findIndex(
      (channel) => channel.id === editingChannelId,
    );

    if (targetIndex < 0) {
      return;
    }

    const nextLinks = [...channelHandles];
    nextLinks[targetIndex] = normalizedHandle;

    const saved = await persistChannels(
      nextLinks,
      'Канал обновлён и синхронизирован с аккаунтом.',
    );

    if (!saved) {
      return;
    }

    resetEditing();
  };

  const deleteChannel = async (channelId: string) => {
    const nextLinks = channels
      .filter((channel) => channel.id !== channelId)
      .map((channel) => channel.handle);

    await persistChannels(
      nextLinks,
      nextLinks.length === 0
        ? 'Все каналы удалены из аккаунта.'
        : 'Канал удалён и синхронизирован с аккаунтом.',
    );
  };

  return (
    <section className="space-y-4 border-t border-border/20 pt-2">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h3 className={sectionTitleClassName}>Telegram-каналы</h3>

        <ActionButton
          disabled={isActionDisabled}
          icon={<Plus className="h-3.5 w-3.5 text-text" />}
          size="sm"
          tone="success"
          onClick={() => setIsComposerOpen((current) => !current)}
        >
          {isComposerOpen ? 'Скрыть' : 'Добавить'}
        </ActionButton>
      </div>

      {hasAdditionalTemplates ? (
        <div className="rounded-2xl border border-warning/15 bg-warning/8 px-4 py-3 text-sm text-text">
          UI редактирует шаблон `{activeTemplateName}`. Остальные шаблоны этого
          аккаунта пока доступны только через API.
        </div>
      ) : null}

      {!activeTemplate && channels.length > 0 ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/65 px-4 py-3 text-sm text-text-muted">
          Для этого аккаунта уже есть рабочие `channel_links`. При первом
          сохранении UI создаст шаблон `{defaultChannelTemplateName}`.
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          {error}
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/70 px-4 py-3 text-sm text-text">
          {feedback}
        </div>
      ) : null}

      <div className="space-y-4">
        {isComposerOpen ? (
          <div className="rounded-[22px] border border-border/25 bg-secondary/60 p-4">
            <TelegramChannelComposer
              draft={composerDraft}
              isSubmitting={isActionDisabled}
              submitLabel="Сохранить канал"
              title="Новый Telegram-канал"
              onCancel={() => {
                setComposerDraft(telegramDraftInitialState);
                setIsComposerOpen(false);
              }}
              onDraftChange={(field, value) =>
                setComposerDraft((current) => ({ ...current, [field]: value }))
              }
              onSubmit={() => void submitNewChannel()}
            />
          </div>
        ) : null}

        {channels.length === 0 ? (
          <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
            <strong className="block text-text">Пока нет каналов</strong>
            <p className="mt-2 leading-6 text-text-muted">
              Открой форму выше и добавь первый Telegram-канал. Ссылка будет
              проверена через Telegram API и сохранена в runtime аккаунта.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {channels.map((channel) => {
              const isEditing = editingChannelId === channel.id;

              if (isEditing) {
                return (
                  <div
                    key={channel.id}
                    className="rounded-[22px] border border-border/25 bg-secondary/70 p-4"
                  >
                    <TelegramChannelComposer
                      draft={editingDraft}
                      deleteLabel="Удалить"
                      isSubmitting={isActionDisabled}
                      submitLabel="Обновить"
                      title={`${channel.title}`}
                      onCancel={resetEditing}
                      onDelete={() => void deleteChannel(channel.id)}
                      onDraftChange={(field, value) =>
                        setEditingDraft((current) => ({
                          ...current,
                          [field]: value,
                        }))
                      }
                      onSubmit={() => void submitEditedChannel()}
                    />
                  </div>
                );
              }

              return (
                <TelegramChannelCard
                  key={channel.id}
                  action={
                    <div className="flex items-center gap-2">
                      <button
                        className={getButtonClassName({
                          tone: 'warning',
                          size: 'icon-sm',
                        })}
                        disabled={isActionDisabled}
                        type="button"
                        onClick={() => startEditing(channel)}
                      >
                        <PencilLine className="text-text h-4 w-4" />
                      </button>
                    </div>
                  }
                  channel={channel}
                />
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}

function TelegramChannelComposer({
  draft,
  deleteLabel,
  isSubmitting = false,
  submitLabel,
  title,
  onCancel,
  onDelete,
  onDraftChange,
  onSubmit,
}: TelegramChannelComposerProps) {
  const isSubmitDisabled =
    !normalizeTelegramHandle(draft.handle) || isSubmitting;

  return (
    <div className="space-y-4">
      <div>
        <h1 className={cardTitleClassName}>{title}</h1>
        <p className="mt-2 leading-6 text-text-muted">
          Можно вставить `t.me/...`, `https://t.me/...` или просто `@handle`.
        </p>
      </div>

      <label className="flex flex-col gap-2">
        <span className={fieldLabelClassName}>Ссылка</span>
        <input
          className={accountControlClassName}
          placeholder="t.me/example_channel"
          type="text"
          value={draft.handle}
          onChange={(event) => onDraftChange('handle', event.target.value)}
        />
      </label>

      <div className="flex justify-end text-sm gap-2">
        {onDelete ? (
          <ActionButton
            disabled={isSubmitting}
            icon={<Trash2 className="h-4 w-4" />}
            size="sm"
            tone="danger"
            onClick={onDelete}
          >
            {deleteLabel ?? 'Удалить'}
          </ActionButton>
        ) : null}
        <ActionButton
          disabled={isSubmitting}
          icon={<X className="h-4 w-4" />}
          size="sm"
          onClick={onCancel}
        >
          Отмена
        </ActionButton>
        <ActionButton
          disabled={isSubmitDisabled}
          icon={<Check className="h-4 w-4" />}
          size="sm"
          tone="success"
          onClick={onSubmit}
        >
          {submitLabel}
        </ActionButton>
      </div>
    </div>
  );
}

interface LogsPageProps {
  accounts: AccountRow[];
  accountsError: string;
  currentPage: number;
  isAccountsLoading: boolean;
  itemsPerPage: TablePageSize;
  onCurrentPageChange: (page: number) => void;
  onItemsPerPageChange: (value: TablePageSize) => void;
  onReloadAccounts: () => Promise<void>;
}

function LogsPage({
  accounts,
  accountsError,
  currentPage,
  isAccountsLoading,
  itemsPerPage,
  onCurrentPageChange,
  onItemsPerPageChange,
  onReloadAccounts,
}: LogsPageProps) {
  const [selectedLogAccountId, setSelectedLogAccountId] =
    useState(allLogAccountsValue);
  const [selectedLogLevel, setSelectedLogLevel] =
    useState<string>(allLogLevelsValue);
  const [logEntries, setLogEntries] = useState<AccountLogEntry[]>([]);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState('');
  const hasInitializedLogFilters = useRef(false);
  const accountSignature = accounts
    .map((account) => `${account.id}:${account.name}`)
    .join('|');
  const logTotalPages = Math.max(1, Math.ceil(logEntries.length / itemsPerPage));
  const paginatedLogEntries = logEntries.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage,
  );
  const visibleLogRangeStart =
    paginatedLogEntries.length === 0
      ? 0
      : (currentPage - 1) * itemsPerPage + 1;
  const visibleLogRangeEnd =
    (currentPage - 1) * itemsPerPage + paginatedLogEntries.length;

  useEffect(() => {
    if (
      selectedLogAccountId === allLogAccountsValue ||
      accounts.some((account) => account.id === selectedLogAccountId)
    ) {
      return;
    }

    setSelectedLogAccountId(allLogAccountsValue);
  }, [accounts, selectedLogAccountId]);

  useEffect(() => {
    if (isAccountsLoading || accounts.length === 0) {
      setIsLogsLoading(false);
      setLogEntries([]);
      setLogsError('');
      return;
    }

    let isCancelled = false;
    const activeAccounts =
      selectedLogAccountId === allLogAccountsValue
        ? accounts
        : accounts.filter((account) => account.id === selectedLogAccountId);
    const requestLimit =
      selectedLogAccountId === allLogAccountsValue
        ? Math.max(80, itemsPerPage * 4)
        : Math.max(160, itemsPerPage * 4);

    async function loadLogs() {
      setIsLogsLoading(true);
      setLogsError('');

      const results = await Promise.allSettled(
        activeAccounts.map(async (account) => {
          const payload = await listAccountLogs(account.id, requestLimit, {
            level:
              selectedLogLevel === allLogLevelsValue
                ? undefined
                : selectedLogLevel,
          });

          return payload.map((entry) =>
            mapApiAccountLogEntryToEntry(entry, account.name),
          );
        }),
      );

      if (isCancelled) {
        return;
      }

      const nextEntries = results.flatMap((result) =>
        result.status === 'fulfilled' ? result.value : [],
      );
      const failures = results.flatMap((result, index) =>
        result.status === 'rejected'
          ? [
              {
                accountName:
                  activeAccounts[index]?.name ??
                  activeAccounts[index]?.id ??
                  'unknown',
                error: result.reason,
              },
            ]
          : [],
      );

      setLogEntries(mergeAndSortAccountLogEntries(nextEntries));
      setLogsError(
        resolveAccountLogError(failures, 'Не удалось загрузить логи из API.'),
      );
      setIsLogsLoading(false);
    }

    void loadLogs();

    return () => {
      isCancelled = true;
    };
  }, [
    accountSignature,
    accounts,
    isAccountsLoading,
    itemsPerPage,
    selectedLogAccountId,
    selectedLogLevel,
  ]);

  useEffect(() => {
    if (isAccountsLoading || accounts.length === 0) {
      return;
    }

    const activeAccounts =
      selectedLogAccountId === allLogAccountsValue
        ? accounts
        : accounts.filter((account) => account.id === selectedLogAccountId);
    const sockets = activeAccounts.map((account) => {
      const socket = new WebSocket(buildAccountLogsWebSocketUrl(account.id));

      socket.onmessage = (event) => {
        let payload: ApiAccountLogEntryRead;

        try {
          payload = JSON.parse(event.data) as ApiAccountLogEntryRead;
        } catch {
          return;
        }

        const nextEntry = mapApiAccountLogEntryToEntry(payload, account.name);

        if (
          selectedLogLevel !== allLogLevelsValue &&
          nextEntry.level !== selectedLogLevel
        ) {
          return;
        }

        setLogEntries((currentEntries) =>
          mergeAndSortAccountLogEntries([...currentEntries, nextEntry]),
        );
      };

      return socket;
    });

    return () => {
      sockets.forEach((socket) => {
        if (
          socket.readyState === WebSocket.OPEN ||
          socket.readyState === WebSocket.CONNECTING
        ) {
          socket.close();
        }
      });
    };
  }, [
    accountSignature,
    accounts,
    isAccountsLoading,
    selectedLogAccountId,
    selectedLogLevel,
  ]);

  useEffect(() => {
    if (!hasInitializedLogFilters.current) {
      hasInitializedLogFilters.current = true;
      return;
    }

    onCurrentPageChange(1);
  }, [onCurrentPageChange, selectedLogAccountId, selectedLogLevel]);

  useEffect(() => {
    if (currentPage <= logTotalPages) {
      return;
    }

    onCurrentPageChange(logTotalPages);
  }, [currentPage, logTotalPages, onCurrentPageChange]);

  return (
    <div className="space-y-4">
      <PageHeader title="Логи" />

      <div className="flex flex-col gap-6">
        <Panel
          title="Лента событий"
          actions={
            <div className="flex flex-wrap items-center gap-4">
              <div className="relative">
                <select
                  aria-label="Фильтр аккаунта для логов"
                  className={logFilterSelectClassName}
                  value={selectedLogAccountId}
                  onChange={(event) =>
                    setSelectedLogAccountId(event.target.value)
                  }
                >
                  <option value={allLogAccountsValue}>Все аккаунты</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.name}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-text-muted" />
              </div>

              <div className="relative">
                <select
                  aria-label="Фильтр уровня логов"
                  className={logFilterSelectClassName}
                  value={selectedLogLevel}
                  onChange={(event) => setSelectedLogLevel(event.target.value)}
                >
                  {logLevelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-text-muted" />
              </div>
            </div>
          }
        >
          <div className="flex flex-col gap-3">
            {accountsError && accounts.length === 0 ? (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
                <span>{accountsError}</span>
                <button
                  className={getButtonClassName({
                    tone: 'danger',
                    size: 'sm',
                  })}
                  disabled={isAccountsLoading}
                  type="button"
                  onClick={() => void onReloadAccounts()}
                >
                  Повторить
                </button>
              </div>
            ) : null}

            {logsError ? (
              <div className="rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
                {logsError}
              </div>
            ) : null}

            {isAccountsLoading ? (
              <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
                <strong className="block text-text">Загружаем аккаунты</strong>
                <p className="mt-2 leading-6 text-text-muted">
                  Нужен список аккаунтов, чтобы собрать ленту логов.
                </p>
              </div>
            ) : null}

            {!isAccountsLoading && accounts.length === 0 && !accountsError ? (
              <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
                <strong className="block text-text">Аккаунтов пока нет</strong>
                <p className="mt-2 leading-6 text-text-muted">
                  После создания аккаунтов здесь появится общая лента событий.
                </p>
              </div>
            ) : null}

            {!isAccountsLoading &&
            accounts.length > 0 &&
            logEntries.length === 0 &&
            !logsError ? (
              <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/50 p-5 text-center">
                <strong className="block text-text">
                  {isLogsLoading ? 'Загружаем логи' : 'Логи пока пусты'}
                </strong>
                <p className="mt-2 leading-6 text-text-muted">
                  {isLogsLoading
                    ? 'Получаем последние записи из runtime API.'
                    : 'Для выбранного фильтра пока нет записей.'}
                </p>
              </div>
            ) : null}

            {logEntries.length > 0 ? (
              <div className="overflow-hidden rounded-2xl border border-border/25 bg-secondary/75">
                <div
                  className={cx(
                    'hidden gap-4 border-b border-border/25 px-6 py-4 text-xs font-semibold uppercase tracking-widest text-text-muted/75 xl:grid',
                    logTableDesktopGridClassName,
                  )}
                >
                  <span>Дата и время</span>
                  <span>Аккаунт</span>
                  <span>Событие</span>
                  <span>Уровень</span>
                </div>

                <div className="divide-y divide-border/25">
                  {paginatedLogEntries.map((entry) => (
                    <article
                      key={entry.id}
                      className={cx(
                        'grid gap-5 px-5 py-5 xl:items-center xl:gap-4 xl:px-6',
                        logTableDesktopGridClassName,
                      )}
                    >
                      <div className="space-y-1">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Дата и время
                        </span>
                        <span className="font-medium text-sm tracking-tight text-text-muted">
                          {formatAccountLogTimestamp(entry.timestamp)}
                        </span>
                      </div>

                      <div className="min-w-0 space-y-2">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Аккаунт
                        </span>
                        <div className="flex items-center gap-3">
                          <p
                            className={cx(
                              cardTitleClassName,
                              'min-w-0 truncate',
                            )}
                          >
                            {entry.accountName}
                          </p>
                        </div>
                      </div>

                      <div className="min-w-0 space-y-2">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Событие
                        </span>
                        <div className="flex min-w-0 items-center gap-3">
                          <p className="min-w-0 text-sm leading-6 text-text-muted">
                            {entry.message}
                          </p>
                        </div>
                      </div>

                      <div className="space-y-2 xl:justify-self-start">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Уровень
                        </span>
                        <span
                          className={`inline-flex items-center justify-center rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-widest ${logLevelBadgeClassNames[entry.tone]}`}
                        >
                          {entry.level}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>

                <TablePaginationFooter
                  currentPage={currentPage}
                  itemsPerPage={itemsPerPage}
                  itemCountLabel="логов"
                  nextPageAriaLabel="Следующая страница логов"
                  previousPageAriaLabel="Предыдущая страница логов"
                  totalItems={logEntries.length}
                  totalPages={logTotalPages}
                  visibleRangeEnd={visibleLogRangeEnd}
                  visibleRangeStart={visibleLogRangeStart}
                  onItemsPerPageChange={(value) => {
                    onItemsPerPageChange(value);
                    onCurrentPageChange(1);
                  }}
                  onPageChange={onCurrentPageChange}
                />
              </div>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface SettingsPageProps {
  hasUnsavedChanges: boolean;
  onChangePreference: (
    field: keyof AppPreferences,
    value: string | number | boolean,
  ) => void;
  onNavigateToPage: (page: PageId) => void;
  onResetPreferences: () => void;
  onSavePreferences: () => void;
  onToggleTheme: () => void;
  preferences: AppPreferences;
  themeMode: ThemeMode;
}

function SettingsPage({
  hasUnsavedChanges,
  onChangePreference,
  onNavigateToPage,
  onResetPreferences,
  onSavePreferences,
  onToggleTheme,
  preferences,
  themeMode,
}: SettingsPageProps) {
  const [activeSection, setActiveSection] = useState<
    (typeof settingsSectionItems)[number]['id']
  >(settingsSectionItems[0].id);
  const selectedDateTimeFormat =
    dateTimeFormatOptions.find(
      (option) => option.value === preferences.dateTimeFormat,
    ) ?? dateTimeFormatOptions[0];

  useEffect(() => {
    const sections = settingsSectionItems
      .map((item) => document.getElementById(`settings-${item.id}`))
      .filter(
        (section): section is HTMLElement => section instanceof HTMLElement,
      );

    if (sections.length === 0) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visibleEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (left, right) => right.intersectionRatio - left.intersectionRatio,
          )[0];

        if (!visibleEntry) {
          return;
        }

        const matchedSection = settingsSectionItems.find(
          (item) => visibleEntry.target.id === `settings-${item.id}`,
        );

        if (matchedSection) {
          setActiveSection(matchedSection.id);
        }
      },
      {
        rootMargin: '-80px 0px -55% 0px',
        threshold: [0.2, 0.45, 0.7],
      },
    );

    sections.forEach((section) => observer.observe(section));

    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <div className={settingsPageClassName}>
      <div className="grid min-h-screen xl:grid-cols-[280px_minmax(0,1fr)]">
        <AppSidebar
          activePage="settings"
          onNavigate={onNavigateToPage}
          onToggleTheme={onToggleTheme}
          themeMode={themeMode}
        />

        <main className="min-w-0">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border-soft bg-foreground px-6">
            <nav className="flex min-w-0 items-center gap-1 overflow-x-auto">
              {settingsSectionItems.map(({ id, icon: Icon, label }) => {
                const isActive = activeSection === id;

                return (
                  <a
                    key={id}
                    className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-[14px] font-medium transition-colors duration-150 ${
                      isActive
                        ? 'border-info text-info'
                        : 'border-transparent text-text-faint hover:text-text'
                    }`}
                    href={`#settings-${id}`}
                    onClick={() => setActiveSection(id)}
                  >
                    <Icon className="h-4.25 w-4.25 shrink-0" />
                    <span>{label}</span>
                  </a>
                );
              })}
            </nav>

            <button
              className={getButtonClassName({
                tone: 'info',
                variant: 'solid',
                size: 'sm',
              })}
              disabled={!hasUnsavedChanges}
              type="button"
              onClick={onSavePreferences}
            >
              <Save className="h-4 w-4" />
              Сохранить
            </button>
          </header>

          <div className="mx-auto flex max-w-265 flex-col px-10 py-9">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <button
                  aria-label="Вернуться назад"
                  className={getButtonClassName({
                    size: 'icon-sm',
                    variant: 'soft',
                    className:
                      'border-border bg-foreground/75 text-text hover:bg-foreground hover:text-text',
                  })}
                  type="button"
                  onClick={() => onNavigateToPage('dashboard')}
                >
                  <ChevronLeft className="h-5 stroke-2 w-5" />
                </button>
                <nav className="flex items-center gap-2 text-[15px]">
                  <button
                    className="cursor-pointer text-text-faint transition-colors duration-150 hover:text-text"
                    type="button"
                    onClick={() => onNavigateToPage('dashboard')}
                  >
                    Приложение
                  </button>
                  <ChevronRight className="h-4 w-4 text-text-faint/70" />
                  <span className="font-medium text-text">Настройки</span>
                </nav>
              </div>

              <div className="grid gap-6">
                <section
                  id="settings-interface"
                  className={`${settingsPanelClassName} scroll-mt-20`}
                >
                  <SettingsSectionHeader
                    icon={<SlidersHorizontal className="h-4.5 w-4.5" />}
                    title="Время и часовой пояс"
                  />

                  <div className="grid gap-5 lg:grid-cols-2">
                    <SettingsSummaryCard
                      icon={<Clock3 className="h-5 w-5" />}
                      label="ТЕКУЩИЙ ФОРМАТ ВРЕМЕНИ"
                      value={selectedDateTimeFormat.preview}
                    />
                    <SettingsSelectField
                      label="ФОРМАТ ДАТЫ И ВРЕМЕНИ"
                      labelTooltip="Как отображать дату и время в логах, карточках и таблицах."
                      options={dateTimeFormatOptions.map((option) => ({
                        label: option.label,
                        value: option.value,
                      }))}
                      value={preferences.dateTimeFormat}
                      onChange={(value) =>
                        onChangePreference('dateTimeFormat', value)
                      }
                    />
                  </div>
                </section>

                <section
                  id="settings-http-retry"
                  className={`${settingsPanelClassName} scroll-mt-20`}
                >
                  <SettingsSectionHeader
                    icon={<RefreshCw className="h-4.5 w-4.5" />}
                    title="Повторы HTTP"
                  />

                  <div className="grid gap-5 md:grid-cols-2">
                    <SettingsNumberField
                      label="КОЛИЧЕСТВО ПОВТОРОВ HTTP"
                      labelTooltip="Максимальное количество повторных попыток для неудачных сетевых запросов."
                      maximum={5}
                      minimum={0}
                      step={1}
                      value={preferences.httpRetries}
                      onChange={(value) =>
                        onChangePreference('httpRetries', value)
                      }
                    />
                    <SettingsNumberField
                      label="БАЗОВАЯ ЗАДЕРЖКА ПОВТОРА"
                      labelTooltip="Базовая задержка перед первой повторной попыткой."
                      maximum={30}
                      minimum={0.1}
                      step={0.1}
                      suffix="сек"
                      value={preferences.httpRetryDelaySeconds}
                      onChange={(value) =>
                        onChangePreference('httpRetryDelaySeconds', value)
                      }
                    />
                  </div>

                  <div className="mt-6 grid gap-4 md:grid-cols-2">
                    <SettingsToggleCard
                      checked={preferences.httpRetryJitterEnabled}
                      description="Добавлять случайное отклонение к задержке(jitter), чтобы не создавать синхронные пики."
                      icon={
                        <RefreshCw className="h-4.5 w-4.5 text-text-faint" />
                      }
                      label="Отклонение задержки"
                      onToggle={() =>
                        onChangePreference(
                          'httpRetryJitterEnabled',
                          !preferences.httpRetryJitterEnabled,
                        )
                      }
                    />
                    <SettingsToggleCard
                      checked={preferences.persistRawJson}
                      description="Сохранять полный JSON payload для отладки и разбора ошибок."
                      icon={
                        <FileJson className="h-4.5 w-4.5 text-text-faint" />
                      }
                      label="Сохранять исходный JSON"
                      onToggle={() =>
                        onChangePreference(
                          'persistRawJson',
                          !preferences.persistRawJson,
                        )
                      }
                    />
                  </div>
                </section>

                <section
                  id="settings-working-paths"
                  className={`${settingsPanelClassName} scroll-mt-20`}
                >
                  <SettingsSectionHeader
                    icon={<FolderOpen className="h-4.5 w-4.5" />}
                    title="Рабочие пути"
                  />

                  <div className="grid gap-6">
                    <SettingsTextAreaField
                      label="ПАПКА АККАУНТОВ"
                      labelTooltip="Папка, в которой хранятся зашифрованные учётные данные аккаунтов."
                      value={preferences.accountsDirectory}
                      onChange={(value) =>
                        onChangePreference('accountsDirectory', value)
                      }
                    />
                    <SettingsTextAreaField
                      label="ПАПКА ЛОГОВ"
                      labelTooltip="Путь для логов сессий, runtime-логов и отчётов об ошибках."
                      value={preferences.logsDirectory}
                      onChange={(value) =>
                        onChangePreference('logsDirectory', value)
                      }
                    />
                  </div>
                </section>

                <div className="flex justify-center">
                  <button
                    className="text-sm text-error/75 hover:text-error cursor-pointer"
                    type="button"
                    onClick={onResetPreferences}
                  >
                    Сбросить все настройки
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

interface SettingsFieldShellProps {
  children: ReactNode;
  description?: string;
  label: string;
  labelTooltip?: string;
}

function SettingsFieldShell({
  children,
  description,
  label,
  labelTooltip,
}: SettingsFieldShellProps) {
  return (
    <label className="flex flex-col gap-2.5">
      <span className="flex items-center gap-1.5">
        <span className={settingsLabelClassName}>{label}</span>
        {labelTooltip ? (
          <span
            aria-label={labelTooltip}
            className="group relative inline-flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded-full text-text-faint transition-colors duration-150 outline-none hover:text-info focus:text-info"
            tabIndex={0}
          >
            <Info className="h-3.5 w-3.5" strokeWidth={2.4} />
            <span
              className="pointer-events-none absolute top-[calc(100%+8px)] left-0 z-20 hidden w-64 rounded-xl border border-border/20 bg-foreground px-3 py-2 text-[12px] leading-4 text-text-muted shadow-[0_14px_30px_rgba(15,23,42,0.14)] group-hover:block group-focus:block"
              role="tooltip"
            >
              {labelTooltip}
            </span>
          </span>
        ) : null}
      </span>
      {children}
      {description ? (
        <span className={settingsDescriptionClassName}>{description}</span>
      ) : null}
    </label>
  );
}

interface SettingsSectionHeaderProps {
  icon: ReactNode;
  title: string;
}

function SettingsSectionHeader({ icon, title }: SettingsSectionHeaderProps) {
  return (
    <div className="mb-5 flex items-center gap-3 text-info">
      <span className="flex h-5 w-5 items-center justify-center">{icon}</span>
      <h2 className="text-[17px] font-medium text-text">{title}</h2>
    </div>
  );
}

interface SettingsSummaryCardProps {
  icon: ReactNode;
  label: string;
  value: string;
}

function SettingsSummaryCard({ icon, label, value }: SettingsSummaryCardProps) {
  return (
    <div
      className={`${settingsSubtleCardClassName} h-fit flex items-center gap-4`}
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/25 bg-foreground text-info shadow-[0_1px_2px_rgba(15,23,42,0.06)]">
        {icon}
      </span>
      <div className="flex flex-col justify-center">
        <p className={settingsLabelClassName}>{label}</p>
        <p className="text-[15px] font-semibold text-text">{value}</p>
      </div>
    </div>
  );
}

interface SettingsSelectFieldProps {
  description?: string;
  label: string;
  labelTooltip?: string;
  options: ReadonlyArray<{
    label: string;
    value: string;
  }>;
  value: string;
  onChange: (value: string) => void;
}

function SettingsSelectField({
  description,
  label,
  labelTooltip,
  options,
  value,
  onChange,
}: SettingsSelectFieldProps) {
  return (
    <SettingsFieldShell
      description={description}
      label={label}
      labelTooltip={labelTooltip}
    >
      <div className="relative">
        <select
          className={`${settingsFieldClassName} appearance-none pr-11`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-text-faint" />
      </div>
    </SettingsFieldShell>
  );
}

interface SettingsNumberFieldProps {
  description?: string;
  label: string;
  labelTooltip?: string;
  maximum: number;
  minimum: number;
  step: number;
  suffix?: string;
  value: number;
  onChange: (value: number) => void;
}

function SettingsNumberField({
  description,
  label,
  labelTooltip,
  maximum,
  minimum,
  step,
  suffix,
  value,
  onChange,
}: SettingsNumberFieldProps) {
  return (
    <SettingsFieldShell
      description={description}
      label={label}
      labelTooltip={labelTooltip}
    >
      <div className="relative">
        <input
          className={`number-input-no-spin ${settingsFieldClassName} ${suffix ? 'pr-16' : ''}`}
          inputMode="decimal"
          max={maximum}
          min={minimum}
          step={step}
          type="number"
          value={String(value)}
          onChange={(event) => {
            const nextValue = event.target.value.trim();
            if (!nextValue) {
              return;
            }

            const parsedValue =
              step < 1
                ? Number.parseFloat(nextValue)
                : Number.parseInt(nextValue, 10);

            if (!Number.isFinite(parsedValue)) {
              return;
            }

            const normalizedValue =
              step < 1
                ? parseFloatSetting(parsedValue, value, minimum, maximum)
                : parseIntegerSetting(parsedValue, value, minimum, maximum);
            onChange(normalizedValue);
          }}
        />
        {suffix ? (
          <span className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-[15px] font-normal text-text-faint">
            {suffix}
          </span>
        ) : null}
      </div>
    </SettingsFieldShell>
  );
}

interface SettingsTextAreaFieldProps {
  description?: string;
  label: string;
  labelTooltip?: string;
  value: string;
  onChange: (value: string) => void;
}

function SettingsTextAreaField({
  description,
  label,
  labelTooltip,
  value,
  onChange,
}: SettingsTextAreaFieldProps) {
  return (
    <SettingsFieldShell
      description={description}
      label={label}
      labelTooltip={labelTooltip}
    >
      <div className="relative">
        <input
          className={`${settingsTextAreaClassName} pr-12`}
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          aria-label={getBrowseLabel(label)}
          className="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-text-faint transition-colors duration-150 hover:bg-secondary hover:text-info"
          type="button"
        >
          <FolderOpen className="h-4 w-4" />
        </button>
      </div>
    </SettingsFieldShell>
  );
}

interface SettingsToggleCardProps {
  checked: boolean;
  description: string;
  icon?: ReactNode;
  label: string;
  onToggle: () => void;
}

function SettingsToggleCard({
  checked,
  description,
  icon,
  label,
  onToggle,
}: SettingsToggleCardProps) {
  return (
    <button
      aria-checked={checked}
      className={`${settingsToggleCardClassName} flex w-full cursor-pointer items-center justify-between gap-3.5 text-left focus:ring-2 focus:ring-info/10`}
      role="switch"
      type="button"
      onClick={onToggle}
    >
      <div className="flex items-center gap-3">
        {icon ? (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary">
            {icon}
          </span>
        ) : null}
        <div>
          <h3 className="text-[15px] font-semibold text-text">{label}</h3>
          <span
            className={`${settingsDescriptionClassName} block leading-[1.3]`}
          >
            {description}
          </span>
        </div>
      </div>
      <ToggleSwitch checked={checked} />
    </button>
  );
}

interface EditableFieldProps {
  icon?: ReactNode;
  onChange: (value: string) => void;
  label: string;
  value: string;
}

interface AccountFormFieldsProps {
  values: AccountDraft;
  onFieldChange: (field: AccountEditableField, value: string) => void;
}

function AccountFormFields({ values, onFieldChange }: AccountFormFieldsProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <TextInputField
        label="Имя аккаунта"
        value={values.name}
        icon={
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary/50">
            <User className="h-3.5 w-3.5 text-info/75" />
          </div>
        }
        onChange={(value) => onFieldChange('name', value)}
      />
      <MinutesTimePickerField
        label="Таймер"
        value={values.timer}
        icon={
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary/50">
            <Clock3 className="h-3.5 w-3.5 text-info/75" />
          </div>
        }
        onChange={(value) => onFieldChange('timer', value)}
      />
    </div>
  );
}

function TextInputField({ label, value, onChange, icon }: EditableFieldProps) {
  return (
    <label className="flex flex-col gap-3">
      <span className={fieldLabelClassName}>
        {icon}
        {label}
      </span>
      <div className="relative overflow-hidden rounded-xl border border-border/25 bg-secondary transition-all duration-200 focus-within:border-info/55 focus-within:ring-4 focus-within:ring-info/10">
        <input
          className="h-12 w-full bg-transparent px-4 text-[17px] text-text outline-none placeholder:text-text-muted/45"
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    </label>
  );
}

function MinutesTimePickerField({
  label,
  value,
  onChange,
  icon,
}: EditableFieldProps) {
  const [inputValue, setInputValue] = useState(() => {
    const parsedValue = extractTimerMinutes(value);
    return parsedValue === null ? '' : String(parsedValue);
  });
  const [isOpen, setIsOpen] = useState(false);
  const fieldRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const parsedValue = extractTimerMinutes(value);
    const normalizedValue = parsedValue === null ? '' : String(parsedValue);

    setInputValue((currentValue) =>
      currentValue === normalizedValue ? currentValue : normalizedValue,
    );
  }, [value]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!fieldRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const parsedMinutes = extractTimerMinutes(inputValue);
  const hasValue = inputValue.trim().length > 0;
  const hasError = hasValue && !isTimerValueValid(inputValue);
  const helperText = hasError
    ? `Введите значение от ${minimumTimerMinutes} до ${maximumTimerMinutes}`
    : null;
  const timerUnitOffset = `${Math.max(inputValue.length, 1)}ch`;

  const setMinutes = (minutes: number) => {
    const nextMinutes = clampTimerMinutes(minutes);
    setInputValue(String(nextMinutes));
    onChange(formatTimerLabel(nextMinutes));
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.target.value.replace(/[^\d]/g, '').slice(0, 4);
    setInputValue(nextValue);

    if (!nextValue) {
      onChange('');
      return;
    }

    onChange(formatTimerLabel(Number.parseInt(nextValue, 10)));
  };

  const handleStep = (delta: number) => {
    const baseValue =
      parsedMinutes === null
        ? delta > 0
          ? defaultTimerMinutes - 1
          : minimumTimerMinutes + 1
        : parsedMinutes;

    setMinutes(baseValue + delta);
    setIsOpen(true);
  };

  return (
    <div className="flex flex-col gap-3">
      <span className={fieldLabelClassName}>
        {icon}
        {label}
      </span>
      <div className="relative" ref={fieldRef}>
        <div
          className={cx(
            'relative overflow-hidden rounded-xl border bg-secondary transition-all duration-200',
            hasError
              ? 'border-error ring-2 ring-error/10'
              : isOpen
                ? 'border-info/55 ring-4 ring-info/10'
                : 'border-border/25',
          )}
        >
          <input
            ref={inputRef}
            className="h-12 w-full bg-transparent pr-18 pl-4 text-[17px] text-text outline-none placeholder:text-text-muted/45"
            inputMode="numeric"
            placeholder="Введите минуты"
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            onFocus={() => setIsOpen(true)}
          />
          {hasValue ? (
            <span
              className="pointer-events-none absolute top-1/2 -translate-y-1/2 text-sm font-semibold text-text-muted"
              style={{ left: `calc(1rem + ${timerUnitOffset} + 0.55rem)` }}
            >
              мин
            </span>
          ) : null}
        </div>

        <div className="mt-1 flex items-start justify-between gap-3 px-1">
          <p
            className={cx(
              'text-sm leading-6',
              hasError ? 'text-error' : 'text-text-muted',
            )}
          >
            {hasError ? (
              <span className="inline-flex items-center gap-1.5">
                <TriangleAlert className="h-4 w-4" />
                {helperText}
              </span>
            ) : (
              helperText
            )}
          </p>
        </div>

        {isOpen ? (
          <div className="absolute inset-x-0 top-[calc(100%+12px)] z-30 overflow-hidden rounded-[22px] border border-border/20 bg-foreground p-4 shadow-[0_24px_64px_rgba(15,23,42,0.14)]">
            <div className="rounded-2xl border border-border/15 bg-secondary/65 p-4">
              <div className="flex items-center justify-between gap-3">
                <button
                  className={getButtonClassName({
                    size: 'icon-md',
                    className:
                      'font-semibold text-text/75 text-xl hover:text-text',
                  })}
                  type="button"
                  onClick={() => handleStep(-1)}
                >
                  -
                </button>

                <div className="min-w-0 flex-1 text-center">
                  <div className="flex items-end justify-center gap-2">
                    <span
                      className={cx(
                        'text-4xl font-semibold tracking-tight',
                        hasError ? 'text-error' : 'text-info',
                      )}
                    >
                      {inputValue || '—'}
                    </span>
                    <span className="pb-1 text-sm font-semibold text-text-muted">
                      мин
                    </span>
                  </div>
                </div>

                <button
                  className={getButtonClassName({
                    size: 'icon-md',
                    className:
                      'font-semibold text-text/75 text-xl hover:text-text',
                  })}
                  type="button"
                  onClick={() => handleStep(1)}
                >
                  +
                </button>
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <button
                className={getButtonClassName({
                  size: 'sm',
                  className: 'min-w-0 flex-1',
                })}
                type="button"
                onClick={() => {
                  setMinutes(defaultTimerMinutes);
                  inputRef.current?.focus();
                }}
              >
                Сбросить
              </button>
              <button
                className={getButtonClassName({
                  tone: 'info',
                  variant: 'solid',
                  size: 'sm',
                  className: 'min-w-0 flex-1',
                })}
                disabled={!hasValue || hasError}
                type="button"
                onClick={() => setIsOpen(false)}
              >
                Готово
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default App;
