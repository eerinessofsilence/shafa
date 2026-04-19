import {
  buildAccountLogsWebSocketUrl,
  createAccount as createAccountRequest,
  deleteAccount as deleteAccountRequest,
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
import { navItems, settingToggles } from './data/mockData';
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
  Metric,
  PageId,
  SettingToggle,
  StatusItem,
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
  Ellipsis,
  FileJson,
  FolderOpen,
  LayoutGrid,
  Link2,
  LoaderCircle,
  LockKeyhole,
  LogIn,
  LogOut,
  PencilLine,
  Phone,
  Plus,
  Power,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  Star,
  Trash2,
  Upload,
  TriangleAlert,
  User,
  Users,
  X,
  Send,
} from 'lucide-react';
import {
  type ChangeEvent,
  type ComponentPropsWithoutRef,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react';

const timerOptions = Array.from(
  { length: 60 },
  (_, index) => `${index + 1} мин`,
);
const accountControlClassName =
  'h-12 w-full rounded-xl border border-border/25 bg-secondary px-3 text-text outline-none transition focus:border-info/50 focus:ring-2 focus:ring-info/25';
const accountTextareaClassName =
  'min-h-36 w-full rounded-xl border border-border/25 bg-secondary px-3 py-3 text-text outline-none transition focus:border-info/50 focus:ring-2 focus:ring-info/25';
const accountSelectButtonClassName =
  'flex h-12 w-full cursor-pointer items-center justify-between gap-4 rounded-xl border border-border/25 bg-secondary px-3 text-left text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/25';
const telegramDraftInitialState = {
  handle: '',
};
const surfaceCardClassName =
  'rounded-[18px] border border-border/25 bg-secondary/50 p-4';
const navItemIcons: Record<PageId, ReactNode> = {
  dashboard: <LayoutGrid className="h-5 w-5" />,
  accounts: <Users className="h-5 w-5" />,
  parsing: <Power className="h-5 w-5" />,
  logs: <BarChart3 className="h-5 w-5" />,
  settings: <Settings className="h-5 w-5" />,
};

type TelegramChannelDraft = Pick<TelegramChannel, 'handle'>;
type ActionTone = ButtonTone;
type AccountEditableField = 'name' | 'path' | 'timer';
type AccountDraft = Pick<AccountRow, AccountEditableField>;
type AccountSortField = 'name' | 'timer' | 'channels' | 'status' | 'errors';
type AccountSortDirection = 'asc' | 'desc';
type AccountBulkActionId = 'open' | 'close' | 'delete';

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
const defaultAccountProjectPath =
  window.desktopShell?.cwd?.trim() ||
  '/Users/eeri/coding/python/projects/scripts/shafa';
const defaultChannelTemplateName = 'default';
const accountDraftInitialState: AccountDraft = {
  name: '',
  path: defaultAccountProjectPath,
  timer: timerOptions[4] ?? '5 мин',
};
const accountPageSizeOptions = [5, 10, 20, 50] as const;
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
  'h-12 min-w-[220px] appearance-none rounded-xl border border-border/25 bg-secondary/80 px-4 pr-11 text-sm font-medium text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/20';
const logToolbarButtonClassName = getButtonClassName();
const logLevelBadgeClassNames: Record<StatusTone, string> = {
  success: 'border-success/35 bg-success/10 text-success',
  warning: 'border-warning/40 bg-warning/10 text-warning',
  info: 'border-info/35 bg-info/10 text-info',
  danger: 'border-error/35 bg-error/10 text-error',
  neutral: 'border-border/20 bg-foreground/70 text-text-muted',
};
const logEventIconClassNames: Record<StatusTone, string> = {
  success: 'border-success/18 bg-success/10 text-success',
  warning: 'border-warning/20 bg-warning/10 text-warning',
  info: 'border-info/18 bg-info/10 text-info',
  danger: 'border-error/18 bg-error/10 text-error',
  neutral: 'border-border/18 bg-foreground/90 text-text-muted',
};
const accountLogTimestampFormatter = new Intl.DateTimeFormat('en-US', {
  day: '2-digit',
  hour: 'numeric',
  hour12: true,
  minute: '2-digit',
  month: 'short',
  year: 'numeric',
});
const dashboardDayLabelFormatter = new Intl.DateTimeFormat('ru-RU', {
  weekday: 'short',
});
const dashboardRunTimestampFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  month: 'short',
});

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

function parseTimerLabel(value: string) {
  const parsedValue = Number.parseInt(value, 10);

  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return 5;
  }

  return parsedValue;
}

function formatDashboardDayLabel(value: string) {
  const normalizedValue = value.trim();

  if (!normalizedValue) {
    return '—';
  }

  const parsedValue = new Date(`${normalizedValue}T00:00:00`);

  if (Number.isNaN(parsedValue.getTime())) {
    return normalizedValue;
  }

  const formattedValue = dashboardDayLabelFormatter
    .format(parsedValue)
    .replace('.', '');

  return formattedValue.charAt(0).toUpperCase() + formattedValue.slice(1);
}

function formatDashboardRunTimestamp(value: string | null) {
  if (!value) {
    return 'Запусков пока не было';
  }

  const parsedValue = new Date(value);

  if (Number.isNaN(parsedValue.getTime())) {
    return 'Запусков пока не было';
  }

  return dashboardRunTimestampFormatter.format(parsedValue);
}

function createEmptyDashboardSeries(): ChartPoint[] {
  const today = new Date();

  return Array.from({ length: 7 }, (_, index) => {
    const pointDate = new Date(today);
    pointDate.setDate(today.getDate() - (6 - index));
    const pointDateLabel = [
      pointDate.getFullYear(),
      String(pointDate.getMonth() + 1).padStart(2, '0'),
      String(pointDate.getDate()).padStart(2, '0'),
    ].join('-');

    return {
      label: formatDashboardDayLabel(pointDateLabel),
      items: 0,
      errors: 0,
    };
  });
}

function createDashboardMetrics(summary: ApiDashboardSummary | null): Metric[] {
  return [
    {
      label: 'Всего аккаунтов',
      value: summary ? String(summary.total_accounts) : '—',
      accent: 'teal',
    },
    {
      label: 'Активные сейчас',
      value: summary ? String(summary.active_accounts) : '—',
      accent: 'amber',
    },
    {
      label: 'Товаров за 7 дней',
      value: summary ? String(summary.item_successes_last_7_days) : '—',
      accent: 'blue',
    },
    {
      label: 'Ошибок за 7 дней',
      value: summary ? String(summary.error_events_last_7_days) : '—',
      accent: 'rose',
    },
  ];
}

function createDashboardSeries(
  summary: ApiDashboardSummary | null,
): ChartPoint[] {
  if (!summary || summary.series.length === 0) {
    return createEmptyDashboardSeries();
  }

  return summary.series.map((point) => ({
    label: formatDashboardDayLabel(point.date),
    items: point.items,
    errors: point.errors,
  }));
}

function createDashboardStatus(
  summary: ApiDashboardSummary | null,
): StatusItem[] {
  if (!summary) {
    return [
      {
        label: 'Готовность',
        value: 'Подключаем текущую сводку по аккаунтам и сессиям.',
        badge: 'Sync',
        tone: 'info',
      },
      {
        label: 'Последний запуск',
        value: 'Получаем историю запусков из API.',
        badge: 'Wait',
        tone: 'neutral',
      },
      {
        label: 'Фокус по ошибкам',
        value: 'Проверяем последние error-события и накопленные ошибки.',
        badge: 'Scan',
        tone: 'neutral',
      },
    ];
  }

  const readyTone: StatusTone =
    summary.total_accounts > 0 &&
    summary.ready_accounts === summary.total_accounts
      ? 'success'
      : summary.ready_accounts > 0
        ? 'warning'
        : 'neutral';
  const latestRunTone: StatusTone = summary.latest_run_at ? 'info' : 'neutral';
  const attentionTone: StatusTone =
    summary.top_error_account_name && summary.top_error_account_errors > 0
      ? 'danger'
      : summary.attention_accounts > 0
        ? 'warning'
        : 'success';

  return [
    {
      label: 'Готовы к запуску',
      value:
        summary.total_accounts > 0
          ? `${summary.ready_accounts} из ${summary.total_accounts} аккаунтов готовы по сессиям и API.`
          : 'Аккаунтов пока нет, поэтому готовность ещё не считается.',
      badge: summary.total_accounts > 0 ? 'Ready' : 'Empty',
      tone: readyTone,
    },
    {
      label: 'Последний запуск',
      value: summary.latest_run_account_name
        ? `${summary.latest_run_account_name} · ${formatDashboardRunTimestamp(summary.latest_run_at)}`
        : 'Запусков пока не было.',
      badge: summary.latest_run_at ? 'Recent' : 'Idle',
      tone: latestRunTone,
    },
    {
      label: 'Фокус по ошибкам',
      value:
        summary.top_error_account_name && summary.top_error_account_errors > 0
          ? `${summary.top_error_account_name}: ${summary.top_error_account_errors} накопленных ошибок.`
          : summary.attention_accounts > 0
            ? `${summary.attention_accounts} аккаунтов ещё требуют внимания по настройке или состоянию.`
            : 'Критичных сигналов сейчас нет.',
      badge:
        summary.top_error_account_name && summary.top_error_account_errors > 0
          ? 'Risk'
          : summary.attention_accounts > 0
            ? 'Watch'
            : 'Clear',
      tone: attentionTone,
    },
  ];
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
    path: draft.path.trim() || defaultAccountProjectPath,
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

function getAccountInitials(name: string) {
  const segments = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);

  if (segments.length === 0) {
    return '??';
  }

  return segments.map((segment) => segment.charAt(0).toUpperCase()).join('');
}

function AccountLogEventIcon({ tone }: { tone: StatusTone }) {
  switch (tone) {
    case 'success':
      return <LogIn className="h-4 w-4" />;
    case 'warning':
      return <LockKeyhole className="h-4 w-4" />;
    case 'danger':
      return <TriangleAlert className="h-4 w-4" />;
    case 'info':
      return <ShieldCheck className="h-4 w-4" />;
    default:
      return <FileJson className="h-4 w-4" />;
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

function createEntityId(prefix: string) {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? `${prefix}-${crypto.randomUUID()}`
    : `${prefix}-${Date.now()}-${Math.round(Math.random() * 1000)}`;
}

function deriveAccountBranch(path: string) {
  const pathSegments = path
    .trim()
    .replace(/\/+$/, '')
    .split('/')
    .filter(Boolean);
  const lastPathSegment = pathSegments[pathSegments.length - 1];

  return lastPathSegment || 'main';
}

function createAccountFromDraft(draft: AccountDraft): AccountRow {
  return {
    id: createEntityId('account'),
    name: draft.name.trim(),
    phone: '',
    path: draft.path.trim() || defaultAccountProjectPath,
    branch: deriveAccountBranch(draft.path),
    timer: draft.timer,
    errors: '0',
    statusLabel: 'stopped',
    statusTone: 'neutral',
    shafaSessionExists: false,
    telegramSessionExists: false,
    telegramChannels: [],
    channelTemplates: [],
  };
}

function getAccountDraftFromRow(account: AccountRow): AccountDraft {
  return {
    name: account.name,
    path: account.path,
    timer: account.timer,
  };
}

function isAccountDraftValid(draft: AccountDraft) {
  return Boolean(draft.name.trim());
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
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [isAccountsLoading, setIsAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState('');
  const [isAccountMutationPending, setIsAccountMutationPending] =
    useState(false);
  const [parsingToggles, setParsingToggles] =
    useState<SettingToggle[]>(settingToggles);
  const [selectedAccountId, setSelectedAccountId] = useState('');

  useEffect(() => {
    if (
      selectedAccountId &&
      !accounts.some((account) => account.id === selectedAccountId)
    ) {
      setSelectedAccountId('');
    }
  }, [accounts, selectedAccountId]);

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
  }, [activePage]);

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

  const handleToggleParsingOption = (label: string) => {
    setParsingToggles((currentToggles) =>
      currentToggles.map((toggle) =>
        toggle.label === label
          ? { ...toggle, enabled: !toggle.enabled }
          : toggle,
      ),
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

  return (
    <div className="min-h-screen font-sans antialiased">
      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="bg-foreground min-h-screen w-full p-5">
          <div className="space-y-4 sticky top-7.5">
            <h1 className="font-semibold text-text tracking-tight text-3xl">
              Shafa Control
            </h1>

            <nav className="flex flex-col gap-2.5">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-left transition-all duration-200 ${
                    activePage === item.id
                      ? 'border border-info/50 bg-secondary text-text'
                      : 'border border-transparent bg-secondary/50 text-text/75 hover:border-border/25 hover:bg-secondary/75'
                  }`}
                  onClick={() => setActivePage(item.id)}
                >
                  <span
                    className={`flex h-10 w-10 items-center justify-center rounded-xl transition-colors duration-200 ${
                      activePage === item.id
                        ? 'bg-info/15 text-info'
                        : 'bg-secondary text-text/65'
                    }`}
                  >
                    {navItemIcons[item.id]}
                  </span>
                  <span className="text-lg font-medium">{item.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        <main className="flex min-w-0 flex-col gap-3.5">
          <section className="min-h-0 overflow-auto px-5 py-15">
            {activePage === 'dashboard' && <DashboardPage />}
            {activePage === 'accounts' && (
              <AccountsPage
                accounts={accounts}
                isLoading={isAccountsLoading}
                isMutationPending={isAccountMutationPending}
                loadError={accountsError}
                onBulkAction={handleBulkAccountAction}
                onCreateAccount={handleCreateAccount}
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
                isAccountsLoading={isAccountsLoading}
                onReloadAccounts={loadAccounts}
              />
            )}
            {activePage === 'settings' && (
              <SettingsPage
                toggles={parsingToggles}
                onToggleOption={handleToggleParsingOption}
              />
            )}
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

interface ToggleSwitchProps {
  checked: boolean;
}

function ToggleSwitch({ checked }: ToggleSwitchProps) {
  return (
    <span
      aria-hidden="true"
      className={`relative inline-flex h-6 w-12 shrink-0 rounded-full border transition-all duration-200 ${
        checked
          ? 'border-success/25 bg-success/20 shadow-[inset_0_0_0_1px_rgba(34,197,94,0.06)]'
          : 'border-border/25 bg-foreground/35'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-4.5 w-4.5 rounded-full shadow-[0_8px_20px_rgba(15,23,42,0.16)] transition-transform duration-200 ${
          checked ? 'translate-x-6 bg-success' : 'bg-white'
        }`}
      />
    </span>
  );
}

const accountIconClassNames: Record<StatusTone, string> = {
  success: 'bg-success/12 text-success',
  warning: 'bg-info/12 text-info',
  info: 'bg-info/12 text-info',
  danger: 'bg-error/12 text-error',
  neutral: 'bg-info/12 text-info',
};

const accountStatusBadgeClassNames: Record<StatusTone, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-info/15 text-info',
  info: 'bg-info/15 text-info',
  danger: 'bg-error/15 text-error',
  neutral: 'bg-secondary text-text-muted',
};

function AccountRowIcon({ tone }: { tone: StatusTone }) {
  const icon =
    tone === 'danger' ? (
      <TriangleAlert className="h-4 w-4" />
    ) : tone === 'success' ? (
      <Star className="h-4 w-4 fill-current" />
    ) : (
      <User className="h-4 w-4" />
    );

  return (
    <span
      className={`flex h-9 w-9 items-center justify-center rounded-xl ${accountIconClassNames[tone]}`}
    >
      {icon}
    </span>
  );
}

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
      className={`flex h-6 w-6 cursor-pointer items-center justify-center rounded-md border transition-all duration-200 ${
        isActive
          ? 'border-info bg-info text-white shadow-[0_10px_20px_rgba(37,99,235,0.18)]'
          : 'border-border/20 bg-secondary/90 text-transparent hover:border-info/35 hover:bg-secondary'
      }`}
      role="checkbox"
      type="button"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
    >
      {checked ? (
        <Check className="h-3.5 w-3.5" />
      ) : indeterminate ? (
        <span className="h-0.5 w-2.5 rounded-full bg-current" />
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

function DashboardPage() {
  const [summary, setSummary] = useState<ApiDashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const dashboardMetrics = createDashboardMetrics(summary);
  const dashboardSeries = createDashboardSeries(summary);
  const dashboardStatus = createDashboardStatus(summary);
  const shouldShowEmptyAccounts =
    Boolean(summary) && (summary?.total_accounts ?? 0) === 0 && !isLoading;

  const loadDashboard = async () => {
    setIsLoading(true);
    setLoadError('');

    try {
      setSummary(await getDashboardSummary());
    } catch (error) {
      setLoadError(
        formatApiError(error, 'Не удалось загрузить сводку дэшборда из API.'),
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Dashboard"
        actions={
          <ActionButton
            disabled={isLoading}
            icon={
              <RefreshCw
                className={`h-4 w-4 text-text ${isLoading ? 'animate-spin' : ''}`}
              />
            }
            size="sm"
            tone="info"
            onClick={() => void loadDashboard()}
          >
            Обновить
          </ActionButton>
        }
      />

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
            onClick={() => void loadDashboard()}
          >
            Повторить
          </button>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-4">
        <Panel
          title="Главная статистика"
          subtitle="Последние 7 дней по реальным runtime-логам аккаунтов"
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
            <LineChart data={dashboardSeries} height={260} />
          )}
        </Panel>
      </div>
    </div>
  );
}

interface AccountsPageProps {
  accounts: AccountRow[];
  isLoading: boolean;
  isMutationPending: boolean;
  loadError: string;
  onBulkAction: (
    action: AccountBulkActionId,
    accountIds: string[],
  ) => Promise<string>;
  onCreateAccount: (draft: AccountDraft) => Promise<void>;
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
  isLoading,
  isMutationPending,
  loadError,
  onBulkAction,
  onCreateAccount,
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
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [itemsPerPage, setItemsPerPage] = useState<
    (typeof accountPageSizeOptions)[number]
  >(accountPageSizeOptions[0]);
  const [currentPage, setCurrentPage] = useState(1);
  const detailsAccount =
    selectedAccountIds.length === 1
      ? (accounts.find((account) => account.id === selectedAccountIds[0]) ??
        null)
      : null;
  const selectedAccounts = accounts.filter((account) =>
    selectedAccountIds.includes(account.id),
  );
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

  useEffect(() => {
    if (currentPage <= totalPages) {
      return;
    }

    setCurrentPage(totalPages);
  }, [currentPage, totalPages]);

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
    if (!detailsAccount && isDetailsDialogOpen) {
      setIsDetailsDialogOpen(false);
    }
  }, [detailsAccount, isDetailsDialogOpen]);

  useEffect(() => {
    if (isDeleteDialogOpen && selectedAccounts.length === 0) {
      setIsDeleteDialogOpen(false);
    }
  }, [isDeleteDialogOpen, selectedAccounts.length]);

  return (
    <div className="space-y-4">
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

      <div className="flex flex-col gap-5">
        <Panel
          title="Каталог аккаунтов"
          actions={
            <div className="flex items-center justify-between gap-4 rounded-[20px] border border-border/10 bg-secondary/95 p-1.5">
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
                  onClick={() => setIsDeleteDialogOpen(true)}
                >
                  <Trash2 className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Открыть настройки аккаунта"
                  className={getButtonClassName({ size: 'icon-sm' })}
                  disabled={!detailsAccount || isMutationPending}
                  type="button"
                  onClick={() => setIsDetailsDialogOpen(true)}
                >
                  <Ellipsis className="h-4.5 w-4.5" />
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
          <div className="overflow-hidden bg-secondary/50 rounded-2xl">
            <div className="overflow-x-auto px-5 py-3">
              <table className="w-full border-separate [border-spacing:0_10px]">
                <thead>
                  <tr>
                    <th className="border-b border-border/20 px-4 pb-2 text-left">
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
                        className="px-4 pb-2 text-left border-b border-border/20 text-xs font-medium uppercase tracking-wide text-text-muted"
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
                  </tr>
                </thead>
                <tbody>
                  {isLoading && accounts.length === 0 ? (
                    <tr>
                      <td colSpan={accountTableHeaders.length + 1}>
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
                      <td colSpan={accountTableHeaders.length + 1}>
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
                          onClick={() => onSelectAccount(account.id)}
                        >
                          <td
                            className={`${rowCellClassName} w-16 rounded-l-2xl`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onSelectAccount(account.id);
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
                            <span className="inline-flex min-w-8 items-center justify-center rounded-full bg-info/12 px-2.5 py-1 text-sm font-semibold text-info">
                              {account.telegramChannels.length}
                            </span>
                          </td>
                          <td className={rowCellClassName}>
                            <AccountStatusBadge tone={account.statusTone}>
                              {account.statusLabel}
                            </AccountStatusBadge>
                          </td>
                          <td className={`${rowCellClassName} rounded-r-2xl`}>
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
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between gap-4 border-t border-border/10 px-5 py-4">
              <p className="text-sm text-text-muted">
                Показано{' '}
                {visibleRangeStart === 0
                  ? 0
                  : `${visibleRangeStart}-${visibleRangeEnd}`}{' '}
                из {accounts.length} аккаунтов
              </p>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-muted">На странице</span>
                  <div className="relative">
                    <select
                      aria-label="Количество аккаунтов на странице"
                      className="h-10 appearance-none rounded-xl border border-border/20 bg-secondary/75 px-3.5 pr-9 text-sm font-medium text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/20"
                      value={String(itemsPerPage)}
                      onChange={(event) => {
                        setItemsPerPage(
                          Number(
                            event.target.value,
                          ) as (typeof accountPageSizeOptions)[number],
                        );
                        setCurrentPage(1);
                      }}
                    >
                      {accountPageSizeOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-text-muted" />
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    aria-label="Предыдущая страница"
                    className={getButtonClassName({
                      size: 'icon-sm',
                      className: 'text-text-muted hover:text-text',
                    })}
                    disabled={currentPage === 1}
                    type="button"
                    onClick={() =>
                      setCurrentPage((currentValue) =>
                        Math.max(1, currentValue - 1),
                      )
                    }
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <span className="inline-flex h-10 min-w-10 items-center justify-center rounded-xl bg-info px-3.5 text-sm font-semibold text-white">
                    {currentPage}
                  </span>
                  <button
                    aria-label="Следующая страница"
                    className={getButtonClassName({
                      size: 'icon-sm',
                      className: 'text-text-muted hover:text-text',
                    })}
                    disabled={currentPage === totalPages}
                    type="button"
                    onClick={() =>
                      setCurrentPage((currentValue) =>
                        Math.min(totalPages, currentValue + 1),
                      )
                    }
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </div>

      <AccountDetailsDialog
        account={detailsAccount}
        accounts={accounts}
        isOpen={isDetailsDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => setIsDetailsDialogOpen(false)}
        onReloadAccounts={onReload}
        onSyncAccountChannels={onSyncAccountChannels}
        onUpdateAccount={onUpdateAccount}
      />
      <CreateAccountDialog
        isOpen={isCreateDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => setIsCreateDialogOpen(false)}
        onCreateAccount={onCreateAccount}
      />
      <DeleteAccountsDialog
        accounts={selectedAccounts}
        isOpen={isDeleteDialogOpen}
        isSubmitting={isMutationPending}
        onClose={() => setIsDeleteDialogOpen(false)}
        onConfirm={async () => {
          await runBulkAction('delete');
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
        <div className="flex flex-col gap-4 border-b border-border/10 pb-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <h3 className={pageTitleClassName}>{title}</h3>
              {statusBadge}
            </div>
          </div>

          <button
            aria-label={closeLabel}
            className={getButtonClassName({ size: 'icon-sm' })}
            type="button"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {children}
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

interface AuthTextareaFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  icon?: ReactNode;
  placeholder?: string;
  disabled?: boolean;
}

function AuthTextareaField({
  label,
  value,
  onChange,
  icon,
  placeholder,
  disabled = false,
}: AuthTextareaFieldProps) {
  return (
    <label className="flex flex-col gap-2.5">
      <span className={fieldLabelClassName}>
        {icon}
        {label}
      </span>
      <textarea
        className={`${accountTextareaClassName} ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
        disabled={disabled}
        placeholder={placeholder}
        spellCheck={false}
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

    setStatusError(nextErrors.join(' '));
    setIsStatusLoading(false);
  };

  useEffect(() => {
    void loadStatuses();
  }, [account.id]);

  return (
    <div className="space-y-4">
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

        <div className="flex flex-wrap gap-2">
          <ActionButton
            disabled={isAuthActionDisabled}
            icon={
              isSubmitting ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : isConnected ? (
                <LogOut className="h-4 w-4" />
              ) : (
                <LogIn className="h-4 w-4" />
              )
            }
            tone={isConnected ? 'neutral' : 'info'}
            variant={isConnected ? 'soft' : 'solid'}
            onClick={() =>
              void (isConnected ? handleLogout() : handleBrowserLogin())
            }
          >
            {isConnected ? 'Выйти' : 'Войти через браузер'}
          </ActionButton>
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
              icon={<Phone className="h-4 w-4 text-info/80" />}
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
            size="sm"
            className="h-12"
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
            size="sm"
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
            size="sm"
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
                <article
                  key={channel.id}
                  className={`rounded-xl border border-border/25 p-2.5 bg-secondary/50 shadow-[0_18px_48px_rgba(15,23,42,0.04)]`}
                >
                  <div className="flex flex-col gap-4">
                    <div className="flex gap-4 items-center justify-between">
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <img src="/tg_logo.png" className="h-10 w-10" />
                          <div>
                            <h1 className={cardTitleClassName}>
                              {channel.title}
                            </h1>
                            <span className="text-sm text-text-muted">
                              {formatChannelBadge(channel.handle)}
                            </span>
                          </div>
                        </div>
                      </div>
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
                    </div>
                  </div>
                </article>
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
  isAccountsLoading: boolean;
  onReloadAccounts: () => Promise<void>;
}

function LogsPage({
  accounts,
  accountsError,
  isAccountsLoading,
  onReloadAccounts,
}: LogsPageProps) {
  const [selectedLogAccountId, setSelectedLogAccountId] =
    useState(allLogAccountsValue);
  const [selectedLogLevel, setSelectedLogLevel] =
    useState<string>(allLogLevelsValue);
  const [logEntries, setLogEntries] = useState<AccountLogEntry[]>([]);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState('');
  const [logsReloadToken, setLogsReloadToken] = useState(0);
  const accountSignature = accounts
    .map((account) => `${account.id}:${account.name}`)
    .join('|');

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
      selectedLogAccountId === allLogAccountsValue ? 40 : 120;

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
    logsReloadToken,
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

  return (
    <div className="space-y-4">
      <PageHeader title="Логи" />

      <div className="flex flex-col gap-5">
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
              <div className="overflow-hidden rounded-[26px] border border-border/25 bg-secondary/75">
                <div className="hidden grid-cols-[minmax(168px,1fr)_minmax(220px,1fr)_minmax(0,2.1fr)_120px] gap-6 border-b border-border/25 px-6 py-4 text-xs font-semibold uppercase tracking-widest text-text-muted/75 xl:grid">
                  <span>Дата и время</span>
                  <span>Аккаунт</span>
                  <span>Событие</span>
                  <span>Уровень</span>
                </div>

                <div className="divide-y divide-border/10">
                  {logEntries.map((entry) => (
                    <article
                      key={entry.id}
                      className="grid gap-5 px-5 py-5 xl:grid-cols-[minmax(168px,1fr)_minmax(220px,1fr)_minmax(0,2.1fr)_120px] xl:items-center xl:px-6"
                    >
                      <div className="space-y-1">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Дата и время
                        </span>
                        <span className="font-medium tracking-tight text-text-muted/75">
                          {formatAccountLogTimestamp(entry.timestamp)}
                        </span>
                      </div>

                      <div className="space-y-2">
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

                      <div className="space-y-2">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Событие
                        </span>
                        <div className="flex items-center gap-3">
                          <span
                            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${logEventIconClassNames[entry.tone]}`}
                          >
                            <AccountLogEventIcon tone={entry.tone} />
                          </span>
                          <p className="text-sm leading-6 text-text-muted">
                            {entry.message}
                          </p>
                        </div>
                      </div>

                      <div className="space-y-2 xl:justify-self-start">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Уровень
                        </span>
                        <span
                          className={`inline-flex items-center justify-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${logLevelBadgeClassNames[entry.tone]}`}
                        >
                          {entry.level}
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface SettingsPageProps {
  toggles: SettingToggle[];
  onToggleOption: (label: string) => void;
}

function SettingsPage({ toggles, onToggleOption }: SettingsPageProps) {
  return (
    <div className="space-y-4">
      <PageHeader title="Настройки" />

      <div className="grid gap-4">
        <Panel title="Общие параметры">
          <div className="grid grid-cols-2 gap-3">
            {toggles.map((toggle) => (
              <button
                key={toggle.label}
                aria-checked={toggle.enabled}
                className={`${surfaceCardClassName} flex w-full cursor-pointer items-center justify-between gap-3.5 text-left transition-all duration-200 hover:border-border/50 hover:bg-secondary/75 focus:border-info/50 focus:ring-2 focus:ring-info/25`}
                role="switch"
                type="button"
                onClick={() => onToggleOption(toggle.label)}
              >
                <div>
                  <h1 className={cardTitleClassName}>{toggle.label}</h1>
                  <span className="leading-6 text-text-muted">
                    {toggle.copy}
                  </span>
                </div>
                <ToggleSwitch checked={toggle.enabled} />
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
}

interface EditableFieldProps extends FieldProps {
  icon?: ReactNode;
  onChange: (value: string) => void;
}

interface SelectFieldProps extends EditableFieldProps {
  options: string[];
}

interface AccountFormFieldsProps {
  values: AccountDraft;
  onFieldChange: (field: AccountEditableField, value: string) => void;
}

function Field({ label, value }: FieldProps) {
  return (
    <div className={`${surfaceCardClassName} min-h-24`}>
      <span className="text-text-muted">{label}</span>
      <strong className="mt-2.5 block text-[18px] leading-7 text-text">
        {value}
      </strong>
    </div>
  );
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
      <SelectField
        label="Таймер"
        value={values.timer}
        options={timerOptions}
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
      <input
        className={accountControlClassName}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  icon,
}: SelectFieldProps) {
  const [isOpen, setIsOpen] = useState(false);
  const fieldRef = useRef<HTMLDivElement | null>(null);

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

  return (
    <div className="flex flex-col gap-3">
      <span className={fieldLabelClassName}>
        {icon}
        {label}
      </span>
      <div className="relative" ref={fieldRef}>
        <button
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          className={accountSelectButtonClassName}
          type="button"
          onClick={() => setIsOpen((current) => !current)}
        >
          <span className="truncate text-text">{value}</span>

          <ChevronDown
            className={`h-4 w-4 shrink-0 text-text/75 transition-transform duration-200 ${
              isOpen ? 'rotate-180' : ''
            }`}
          />
        </button>

        {isOpen ? (
          <div className="absolute inset-x-0 bottom-[calc(100%+10px)] z-30 overflow-hidden rounded-xl border border-border/25 bg-secondary p-1.5 shadow-[0_24px_64px_rgba(15,23,42,0.1)]">
            <div
              className={`${
                options.length > 8 ? 'max-h-80 overflow-y-auto pr-1' : ''
              }`}
              role="listbox"
            >
              {options.map((option, index) => {
                const isSelected = option === value;

                return (
                  <button
                    key={option}
                    aria-selected={isSelected}
                    className={getButtonClassName({
                      size: 'row',
                      variant: 'ghost',
                      fullWidth: true,
                      align: 'left',
                      className: cx(
                        'justify-between px-4',
                        isSelected ? 'bg-foreground' : 'hover:bg-foreground/50',
                        index < options.length - 1 && 'mb-1',
                      ),
                    })}
                    role="option"
                    type="button"
                    onClick={() => {
                      onChange(option);
                      setIsOpen(false);
                    }}
                  >
                    <span className="truncate text-[17px] text-text">
                      {option}
                    </span>

                    {isSelected ? (
                      <Check className="h-4 w-4 shrink-0 text-text/75" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default App;
