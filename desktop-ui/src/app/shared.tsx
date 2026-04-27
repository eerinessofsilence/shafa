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
} from '../api/accounts';
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
} from '../api/auth';
import {
  createChannelTemplate as createChannelTemplateRequest,
  deleteChannelTemplate as deleteChannelTemplateRequest,
  updateChannelTemplate as updateChannelTemplateRequest,
} from '../api/channelTemplates';
import { getDashboardSummary } from '../api/dashboard';
import { LineChart } from '../components/LineChart';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { StatusPill } from '../components/StatusPill';
import { navItems } from '../data/mockData';
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
} from '../types';
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
} from '../ui';
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
  useCallback,
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
const defaultAccountsDirectory = joinDisplayPath(
  defaultAccountProjectPath,
  'accounts',
);
const defaultLogsDirectory = joinDisplayPath(
  defaultAccountProjectPath,
  'runtime/logs',
);
const defaultChannelTemplateName = 'default';
const accountDraftInitialState: AccountDraft = {
  name: '',
  path: defaultAccountProjectPath,
  timer: `${defaultTimerMinutes} мин`,
};
const accountPageSizeOptions = [5, 10, 20, 50] as const;
const tablePaginationSelectClassName =
  'h-9 min-w-[4.75rem] appearance-none rounded-[8px] border border-border bg-foreground px-3 pr-8 text-[13px] font-medium text-text outline-none transition hover:border-border-strong hover:bg-secondary focus:border-info/30 focus:ring-2 focus:ring-info/12';
const tablePaginationButtonClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-border bg-foreground text-[13px] font-medium tabular-nums text-text-muted outline-none transition hover:border-border-strong hover:bg-secondary hover:text-text focus:border-info/30 focus:ring-2 focus:ring-info/12 disabled:pointer-events-none disabled:opacity-50';
const tablePaginationIconButtonClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-border bg-foreground text-text-muted outline-none transition hover:border-border-strong hover:bg-secondary hover:text-text focus:border-info/30 focus:ring-2 focus:ring-info/12 disabled:pointer-events-none disabled:opacity-50';
const tablePaginationCurrentPageClassName =
  'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] border border-info/25 bg-info/10 text-[13px] font-semibold tabular-nums text-info shadow-[0_1px_0_rgba(255,255,255,0.03)]';
const tablePaginationJumpTriggerClassName = tablePaginationButtonClassName;
const tablePaginationJumpPopoverClassName =
  'absolute bottom-[calc(100%+8px)] left-1/2 z-20 flex w-36 -translate-x-1/2 flex-col gap-1.5 rounded-[8px] border border-border bg-foreground p-2 shadow-[0_18px_40px_rgba(15,23,42,0.14)]';
const tablePaginationJumpInputClassName =
  'number-input-no-spin h-8 w-full rounded-[8px] border border-border bg-foreground px-2.5 text-[13px] font-medium text-text outline-none transition hover:border-border-strong focus:border-info/42 focus:ring-2 focus:ring-info/16';
const allLogAccountsValue = '__all_accounts__';
const allLogLevelsValue = 'ALL';
const logLevelOptions = [
  { label: 'Все уровни', value: allLogLevelsValue },
  { label: 'Успех', value: 'SUCCESS' },
  { label: 'Только ошибки', value: 'ERROR' },
  { label: 'Предупреждения', value: 'WARNING' },
  { label: 'Инфо', value: 'INFO' },
  { label: 'Отладка', value: 'DEBUG' },
] as const;
const logFilterSelectClassName =
  'h-[42px] w-full min-w-0 sm:min-w-[220px] appearance-none rounded-[8px] border border-border bg-foreground px-4 pr-11 text-[15px] font-normal text-text outline-none transition hover:border-border-strong focus:border-info focus:ring-2 focus:ring-info/10';
const logTableDesktopGridClassName =
  'xl:grid-cols-[minmax(180px,1.05fr)_minmax(128px,0.68fr)_minmax(108px,0.55fr)_minmax(0,2.65fr)]';
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
const accountsPaginationStorageKey = 'shafa.desktop.accounts-pagination.v1';
const logsPaginationStorageKey = 'shafa.desktop.logs-pagination.v1';
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
type AccountLogVisualPriority = 'muted' | 'default' | 'strong';
interface TablePaginationState {
  currentPage: number;
  itemsPerPage: TablePageSize;
}

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
  visualPriority: AccountLogVisualPriority;
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

function isTablePageSize(value: unknown): value is TablePageSize {
  return accountPageSizeOptions.some((option) => option === value);
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

function loadStoredTablePagination(storageKey: string): TablePaginationState {
  const defaultState: TablePaginationState = {
    currentPage: 1,
    itemsPerPage: accountPageSizeOptions[0],
  };

  if (typeof window === 'undefined') {
    return defaultState;
  }

  try {
    const rawValue = window.sessionStorage.getItem(storageKey);

    if (!rawValue) {
      return defaultState;
    }

    const parsedValue = JSON.parse(rawValue) as Record<string, unknown>;

    return {
      currentPage: parseIntegerSetting(parsedValue.currentPage, 1, 1, 9999),
      itemsPerPage: isTablePageSize(parsedValue.itemsPerPage)
        ? parsedValue.itemsPerPage
        : defaultState.itemsPerPage,
    };
  } catch {
    return defaultState;
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
        {visibleRangeStart === 0
          ? 0
          : `${visibleRangeStart}-${visibleRangeEnd}`}{' '}
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
                onItemsPerPageChange(
                  Number(event.target.value) as TablePageSize,
                )
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

const mutedAccountLogMessagePrefixes = [
  'бренды обновлены',
  'размеры обновлены',
  'размер:',
  'каталог:',
  'цена рассчитана',
  'фото скачаны',
  'временные фото удалены',
  'ссылки telegram-каналов экспортированы',
  'telegram api-данные сохранены',
  'код telegram запрошен',
  'отправляю код telegram',
  'отправляю пароль 2fa telegram',
  'сессия telegram удалена',
  'сохраняю сессию shafa',
  'сессия shafa сохранена',
  'окно входа shafa открыто',
  'номер телефона получен из telegram-сессии',
] as const;

const strongAccountLogMessagePrefixes = [
  'товар создан успешно',
  'размер отклонён api',
  'процесс запущен',
  'процесс остановлен',
  'процесс завершился с ошибкой',
  'статус аккаунта:',
  'остановка запрошена',
  'аккаунт создан',
  'настройки аккаунта обновлены',
  'аккаунт удалён',
  'не удалось',
  'сбой',
] as const;

function getAccountLogVisualPriority(
  level: string,
  message: string,
): AccountLogVisualPriority {
  const normalizedLevel = level.toUpperCase();
  const normalizedMessage = message.trim().toLowerCase();

  if (
    normalizedLevel === 'ERROR' ||
    normalizedLevel === 'CRITICAL' ||
    normalizedLevel === 'WARNING' ||
    normalizedLevel === 'SUCCESS' ||
    normalizedLevel === 'OK'
  ) {
    return 'strong';
  }

  if (
    strongAccountLogMessagePrefixes.some((prefix) =>
      normalizedMessage.startsWith(prefix),
    )
  ) {
    return 'strong';
  }

  if (
    mutedAccountLogMessagePrefixes.some((prefix) =>
      normalizedMessage.startsWith(prefix),
    )
  ) {
    return 'muted';
  }

  return 'default';
}

function getAccountLogLevelBadgeClassName(entry: AccountLogEntry) {
  return logLevelBadgeClassNames[entry.tone];
}

function getAccountLogEventSurfaceClassName(entry: AccountLogEntry) {
  if (entry.visualPriority === 'muted') {
    return 'rounded-[14px] border border-border/25 bg-secondary/75 px-4 py-3';
  }

  if (entry.visualPriority === 'default') {
    return 'rounded-[14px] border border-border/50 bg-secondary px-4 py-3';
  }

  switch (entry.tone) {
    case 'success':
      return 'rounded-[14px] border border-success/25 bg-success/5 px-4 py-3';
    case 'warning':
      return 'rounded-[14px] border border-warning/10 bg-warning/5 px-4 py-3';
    case 'danger':
      return 'rounded-[14px] border border-error/10 bg-error/5 px-4 py-3';
    case 'info':
      return 'rounded-[14px] border border-border/25 bg-secondary/75 px-4 py-3';
    default:
      return 'rounded-[14px] border border-border/25 bg-secondary/75 px-4 py-3';
  }
}

function getAccountLogMessageClassName(entry: AccountLogEntry) {
  switch (entry.visualPriority) {
    case 'muted':
      return 'text-sm leading-6 text-text-muted/78';
    case 'strong':
      return 'text-sm font-medium leading-6 text-text';
    default:
      return 'text-sm leading-6 text-text-muted';
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
    visualPriority: getAccountLogVisualPriority(normalizedLevel, entry.message),
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
  return (
    Boolean(draft.name.trim()) &&
    Boolean(draft.path.trim()) &&
    isTimerValueValid(draft.timer)
  );
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
          src="./tg_logo.png"
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

export {
  accountsPaginationStorageKey,
  accountControlClassName,
  accountDraftInitialState,
  accountTableHeaders,
  ActionButton,
  AccountStatusBadge,
  allLogAccountsValue,
  allLogLevelsValue,
  AppSidebar,
  BulkActionButton,
  clampTimerMinutes,
  createAccountCreatePayload,
  createAccountUpdatePayload,
  createDashboardMetrics,
  createDashboardSeries,
  createDefaultAppPreferences,
  createDefaultDashboardCustomRange,
  DashboardRangePicker,
  dateTimeFormatOptions,
  defaultChannelTemplateName,
  defaultTimerMinutes,
  extractAccountExtraText,
  extractTimerMinutes,
  fieldLabelClassName,
  formatAccountCount,
  formatAccountDateTime,
  formatAccountLogTimestamp,
  formatAccountTextValue,
  formatApiError,
  formatDashboardRunTimestamp,
  formatTimerLabel,
  getAccountDraftFromRow,
  getAccountLogEventSurfaceClassName,
  getAccountLogLevelBadgeClassName,
  getAccountLogMessageClassName,
  getAccountSortValue,
  getAccountStatusMeta,
  getBrowseLabel,
  getInitialActivePage,
  getPrimaryChannelTemplate,
  getShafaStatusMeta,
  getTelegramStepMeta,
  isAccountDraftValid,
  isLikelyEmail,
  isRecord,
  isTimerValueValid,
  joinUniqueMessages,
  loadStoredAppPreferences,
  loadStoredTablePagination,
  loadStoredThemeMode,
  logFilterSelectClassName,
  logLevelOptions,
  logsPaginationStorageKey,
  logTableDesktopGridClassName,
  mapApiAccountLogEntryToEntry,
  mapApiAccountToRow,
  mapLinksToTelegramChannels,
  maximumTimerMinutes,
  mergeAndSortAccountLogEntries,
  minimumTimerMinutes,
  normalizeTelegramHandle,
  normalizeTelegramLinks,
  pageTitleClassName,
  parseFloatSetting,
  parseIntegerSetting,
  parseShafaImportInput,
  productName,
  resolveAccountLogError,
  sectionTitleClassName,
  SelectionCheckbox,
  settingsDescriptionClassName,
  settingsFieldClassName,
  settingsLabelClassName,
  settingsPageClassName,
  settingsPanelClassName,
  settingsSectionItems,
  settingsStorageKey,
  settingsSubtleCardClassName,
  settingsTextAreaClassName,
  settingsToggleCardClassName,
  TablePaginationFooter,
  telegramDraftInitialState,
  themeStorageKey,
  ToggleSwitch,
  TelegramChannelCard,
};

export type {
  AccountBulkActionId,
  AccountDraft,
  AccountEditableField,
  AccountLogEntry,
  AccountSortDirection,
  AccountSortField,
  AppPreferences,
  TablePageSize,
  TablePaginationState,
  TelegramChannelDraft,
  ThemeMode,
};
