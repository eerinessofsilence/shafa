import { LineChart } from './components/LineChart';
import { MetricCard } from './components/MetricCard';
import { PageHeader } from './components/PageHeader';
import { Panel } from './components/Panel';
import { StatusPill } from './components/StatusPill';
import {
  accountRows,
  dashboardMetrics,
  dashboardSeries,
  logRecords,
  navItems,
  settingToggles,
  statsMetrics,
  statsSeries,
  systemStatus,
} from './data/mockData';
import type {
  AccountRow,
  PageId,
  SettingToggle,
  StatusTone,
  TelegramChannel,
  TelegramPhotoSource,
} from './types';
import {
  BarChart3,
  CalendarRange,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  Ellipsis,
  Eye,
  Filter,
  FolderOpen,
  LayoutGrid,
  Link2,
  PencilLine,
  Plus,
  Power,
  Save,
  Settings,
  Star,
  Trash2,
  TriangleAlert,
  User,
  Users,
  X,
} from 'lucide-react';
import { type ReactNode, useEffect, useRef, useState } from 'react';

const browserOptions = ['Да', 'Нет'];
const timerOptions = Array.from(
  { length: 60 },
  (_, index) => `${index + 1} мин`,
);
const accountControlClassName =
  'h-12 w-full rounded-xl border border-border/25 bg-secondary px-3 text-text outline-none transition focus:border-info/50 focus:ring-2 focus:ring-info/25';
const accountSelectButtonClassName =
  'flex h-12 w-full cursor-pointer items-center justify-between gap-4 rounded-xl border border-border/25 bg-secondary px-3 text-left text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/25';
const telegramDraftInitialState = {
  title: '',
  handle: '',
  photoSource: 'Сообщение' as TelegramPhotoSource,
};
const telegramPhotoSourceOptions: TelegramPhotoSource[] = [
  'Сообщение',
  'Комментарии',
  'Два в одном',
];
const actionButtonClassNames = {
  success:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-4 py-2',
  info: 'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-info/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-info/25 hover:border-border/75 px-4 py-2',
  warning:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-warning/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/25 hover:border-border/75 px-4 py-2',
  danger:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-error/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-error/25 hover:border-border/75 px-4 py-2',
  neutral:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-secondary/80 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-secondary hover:border-border/75 px-4 py-2',
} as const;
const compactActionButtonClassNames = {
  success:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-3 py-1',
  info: 'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-info/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-info/25 hover:border-border/75 px-3 py-1',
  warning:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-warning/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/25 hover:border-border/75 px-3 py-1',
  danger:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-error/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-error/25 hover:border-border/75 px-3 py-1',
  neutral:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-secondary/80 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-secondary hover:border-border/75 px-3 py-1',
} as const;
const surfaceCardClassName =
  'rounded-[18px] border border-border/25 bg-secondary/50 p-4';
const navItemIcons: Record<PageId, ReactNode> = {
  dashboard: <LayoutGrid className="h-5 w-5" />,
  accounts: <Users className="h-5 w-5" />,
  parsing: <Power className="h-5 w-5" />,
  stats: <BarChart3 className="h-5 w-5" />,
  settings: <Settings className="h-5 w-5" />,
};

type TelegramChannelDraft = Pick<
  TelegramChannel,
  'title' | 'handle' | 'photoSource'
>;
type ActionTone = keyof typeof actionButtonClassNames;
type AccountEditableField = 'name' | 'path' | 'browser' | 'timer';
type AccountDraft = Pick<AccountRow, AccountEditableField>;
type AccountSortField =
  | 'name'
  | 'browser'
  | 'timer'
  | 'channels'
  | 'status'
  | 'errors';
type AccountSortDirection = 'asc' | 'desc';
type AccountBulkActionId = 'open' | 'close' | 'delete';

const accountTableHeaders: Array<{
  id: AccountSortField;
  label: string;
}> = [
  { id: 'name', label: 'Имя' },
  { id: 'browser', label: 'Браузер' },
  { id: 'timer', label: 'Таймер' },
  { id: 'channels', label: 'Каналы' },
  { id: 'status', label: 'Статус' },
  { id: 'errors', label: 'Ошибки' },
];
const accountDraftInitialState: AccountDraft = {
  name: '',
  path: '',
  browser: browserOptions[1] ?? 'Нет',
  timer: timerOptions[4] ?? '5 мин',
};
const accountPageSizeOptions = [5, 10, 20, 50] as const;

function getAccountSortValue(account: AccountRow, field: AccountSortField) {
  switch (field) {
    case 'name':
      return account.name;
    case 'browser':
      return account.browser;
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

function createTelegramChannel(draft: TelegramChannelDraft): TelegramChannel {
  const normalizedHandle = normalizeTelegramHandle(draft.handle);

  return {
    id: createEntityId('telegram'),
    title: draft.title.trim() || formatChannelTitle(normalizedHandle),
    handle: normalizedHandle,
    photoSource: draft.photoSource,
  };
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
    path: draft.path.trim(),
    branch: deriveAccountBranch(draft.path),
    browser: draft.browser,
    timer: draft.timer,
    errors: '0',
    statusLabel: 'stopped',
    statusTone: 'neutral',
    telegramChannels: [],
  };
}

function isAccountDraftValid(draft: AccountDraft) {
  return Boolean(draft.name.trim() && draft.path.trim());
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
  const [accounts, setAccounts] = useState<AccountRow[]>(accountRows);
  const [parsingToggles, setParsingToggles] =
    useState<SettingToggle[]>(settingToggles);
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const selectedAccount =
    accounts.find((account) => account.id === selectedAccountId) ?? null;

  useEffect(() => {
    if (
      selectedAccountId &&
      !accounts.some((account) => account.id === selectedAccountId)
    ) {
      setSelectedAccountId('');
    }
  }, [accounts, selectedAccountId]);

  const handleAccountFieldChange = (
    accountId: string,
    field: AccountEditableField,
    value: string,
  ) => {
    setAccounts((currentAccounts) =>
      currentAccounts.map((account) =>
        account.id === accountId ? { ...account, [field]: value } : account,
      ),
    );
  };

  const handleCreateAccount = (draft: AccountDraft) => {
    const nextAccount = createAccountFromDraft(draft);

    setAccounts((currentAccounts) => [...currentAccounts, nextAccount]);
    setSelectedAccountId(nextAccount.id);
  };

  const handleAddTelegramChannel = (
    accountId: string,
    draft: TelegramChannelDraft,
  ) => {
    const normalizedHandle = normalizeTelegramHandle(draft.handle);

    if (!normalizedHandle) {
      return;
    }

    setAccounts((currentAccounts) =>
      currentAccounts.map((account) =>
        account.id === accountId
          ? {
              ...account,
              telegramChannels: [
                ...account.telegramChannels,
                createTelegramChannel({ ...draft, handle: normalizedHandle }),
              ],
            }
          : account,
      ),
    );
  };

  const handleUpdateTelegramChannel = (
    accountId: string,
    channelId: string,
    draft: TelegramChannelDraft,
  ) => {
    const normalizedHandle = normalizeTelegramHandle(draft.handle);

    if (!normalizedHandle) {
      return;
    }

    setAccounts((currentAccounts) =>
      currentAccounts.map((account) =>
        account.id === accountId
          ? {
              ...account,
              telegramChannels: account.telegramChannels.map((channel) =>
                channel.id === channelId
                  ? {
                      ...channel,
                      title:
                        draft.title.trim() ||
                        formatChannelTitle(normalizedHandle),
                      handle: normalizedHandle,
                      photoSource: draft.photoSource,
                    }
                  : channel,
              ),
            }
          : account,
      ),
    );
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

  const handleBulkAccountAction = (
    action: AccountBulkActionId,
    accountIds: string[],
  ) => {
    if (accountIds.length === 0) {
      return '';
    }

    const selectedIdSet = new Set(accountIds);
    const selectedAccounts = accounts.filter((account) =>
      selectedIdSet.has(account.id),
    );
    const selectedCount = selectedAccounts.length;
    const firstSelectedAccount = selectedAccounts[0];

    switch (action) {
      case 'open':
        setAccounts((currentAccounts) =>
          currentAccounts.map((account) =>
            selectedIdSet.has(account.id)
              ? {
                  ...account,
                  browser: 'Да',
                  statusLabel: 'running',
                  statusTone: 'success',
                }
              : account,
          ),
        );
        if (firstSelectedAccount) {
          setSelectedAccountId(firstSelectedAccount.id);
        }
        return selectedCount === 1 && firstSelectedAccount
          ? `Открыт аккаунт ${firstSelectedAccount.name}.`
          : `Открыто ${formatAccountCount(selectedCount)}.`;
      case 'close':
        setAccounts((currentAccounts) =>
          currentAccounts.map((account) =>
            selectedIdSet.has(account.id)
              ? {
                  ...account,
                  browser: 'Нет',
                  statusLabel: 'stopped',
                  statusTone: 'neutral',
                }
              : account,
          ),
        );
        return `Остановлено ${formatAccountCount(selectedCount)}.`;
      case 'delete':
        setAccounts((currentAccounts) =>
          currentAccounts.filter((account) => !selectedIdSet.has(account.id)),
        );
        return `Удалено ${formatAccountCount(selectedCount)}.`;
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
                selectedAccount={selectedAccount}
                selectedAccountId={selectedAccountId}
                onBulkAction={handleBulkAccountAction}
                onCreateAccount={handleCreateAccount}
                onSelectAccount={setSelectedAccountId}
                onUpdateAccountField={handleAccountFieldChange}
                onAddTelegramChannel={handleAddTelegramChannel}
                onUpdateTelegramChannel={handleUpdateTelegramChannel}
              />
            )}
            {activePage === 'stats' && <StatsPage />}
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

interface ActionButtonProps {
  children: ReactNode;
  icon?: ReactNode;
  tone?: ActionTone;
  compact?: boolean;
  onClick?: () => void;
}

function ActionButton({
  children,
  icon,
  tone = 'neutral',
  compact = false,
  onClick,
}: ActionButtonProps) {
  return (
    <button
      className={
        compact
          ? compactActionButtonClassNames[tone]
          : actionButtonClassNames[tone]
      }
      type="button"
      onClick={onClick}
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

type BulkActionTone = 'primary' | 'neutral' | 'danger';

const bulkActionButtonClassNames: Record<BulkActionTone, string> = {
  primary: 'bg-info text-white hover:bg-info/90',
  neutral: 'bg-transparent text-text hover:bg-secondary hover:text-text',
  danger: 'bg-transparent text-error hover:bg-error/8 hover:text-error',
};

const disabledBulkActionButtonClassNames: Record<BulkActionTone, string> = {
  primary: 'bg-info text-white',
  neutral: 'bg-transparent text-text',
  danger: 'bg-transparent text-error',
};

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
      className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl px-3.5 text-sm font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${disabled ? disabledBulkActionButtonClassNames[tone] : bulkActionButtonClassNames[tone]} ${className ?? ''}`}
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
  return (
    <div className="space-y-4">
      <PageHeader
        title="Dashboard"
        actions={
          <>
            <button
              className="border inline-flex items-center gap-3 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-4 py-2"
              type="button"
            >
              <Download className="text-text w-4 h-4" />
              Экспорт отчета
            </button>
            <button
              className="border inline-flex items-center gap-3 active:scale-[0.975] rounded-xl border-border/50  hover:bg-info/25 cursor-pointer duration-200 transition-all hover:border-border/75 bg-info/12.5 px-4 py-2"
              type="button"
            >
              <Plus className="text-text w-4 h-4" />
              Создать запуск
            </button>
          </>
        }
      />

      <div className="grid gap-3 grid-cols-4">
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-4">
        <Panel title="Активность за смену">
          <LineChart data={dashboardSeries} height={260} />
        </Panel>

        <Panel
          title="Состояние системы"
          subtitle="Сводка по окружению и очередям"
        >
          <div className="grid grid-cols-3 gap-2">
            {systemStatus.map((item) => (
              <div
                className="border-border/25 space-y-2 border bg-secondary/50 rounded-xl p-3"
                key={item.label}
              >
                <div className="flex items-center justify-between">
                  <span className="text-text font-medium">{item.label}</span>
                  <StatusPill tone={item.tone}>{item.badge}</StatusPill>
                </div>
                <p className="leading-6">{item.value}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface AccountsPageProps {
  accounts: AccountRow[];
  selectedAccount: AccountRow | null;
  selectedAccountId: string;
  onBulkAction: (action: AccountBulkActionId, accountIds: string[]) => string;
  onCreateAccount: (draft: AccountDraft) => void;
  onSelectAccount: (accountId: string) => void;
  onUpdateAccountField: (
    accountId: string,
    field: AccountEditableField,
    value: string,
  ) => void;
  onAddTelegramChannel: (
    accountId: string,
    draft: TelegramChannelDraft,
  ) => void;
  onUpdateTelegramChannel: (
    accountId: string,
    channelId: string,
    draft: TelegramChannelDraft,
  ) => void;
}

function AccountsPage({
  accounts,
  selectedAccount,
  selectedAccountId,
  onBulkAction,
  onCreateAccount,
  onSelectAccount,
  onUpdateAccountField,
  onAddTelegramChannel,
  onUpdateTelegramChannel,
}: AccountsPageProps) {
  const [sortState, setSortState] = useState<{
    field: AccountSortField;
    direction: AccountSortDirection;
  } | null>(null);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [bulkFeedback, setBulkFeedback] = useState('');
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
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

  const runBulkAction = (action: AccountBulkActionId) => {
    if (selectedAccountIds.length === 0) {
      return;
    }

    const message = onBulkAction(action, selectedAccountIds);

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

  return (
    <div className="space-y-4">
      <PageHeader title="Аккаунты" />

      <div className="flex flex-col gap-5">
        <Panel
          title="Каталог аккаунтов"
          actions={
            <div className="flex items-center justify-between gap-4 rounded-[20px] border border-border/10 bg-secondary/95 p-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <BulkActionButton
                  disabled={selectedAccountIds.length === 0}
                  icon={
                    shouldShowCloseAction ? (
                      <X className="h-4 w-4" />
                    ) : (
                      <FolderOpen className="h-4 w-4" />
                    )
                  }
                  tone={shouldShowCloseAction ? 'danger' : 'primary'}
                  onClick={() =>
                    runBulkAction(shouldShowCloseAction ? 'close' : 'open')
                  }
                >
                  {shouldShowCloseAction ? 'Остановить' : 'Открыть'}
                </BulkActionButton>
                <button
                  aria-label="Удалить отмеченные аккаунты"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-error/15 bg-error/8 text-error transition-all duration-200 hover:border-error/30 hover:bg-error/12 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-error/15 disabled:hover:bg-error/8"
                  disabled={selectedAccountIds.length === 0}
                  type="button"
                  onClick={() => runBulkAction('delete')}
                >
                  <Trash2 className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Открыть настройки аккаунта"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-border/15 bg-secondary/95 text-text transition-all duration-200 hover:border-border/35 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-border/15 disabled:hover:bg-secondary/95"
                  disabled={!detailsAccount}
                  type="button"
                  onClick={() => setIsDetailsDialogOpen(true)}
                >
                  <Ellipsis className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Добавить аккаунт"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl bg-info text-white transition-all duration-200 hover:bg-info/90 active:scale-[0.98]"
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
                  {sortedAccounts.length === 0 ? (
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
                      const browserEnabled = account.browser === 'Да';
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
                          <td
                            className={`${rowCellClassName} font-medium text-md text-text`}
                          >
                            <div className="flex items-center font-medium text-text gap-3">
                              {account.name}
                            </div>
                          </td>
                          <td className={rowCellClassName}>
                            <span
                              className={`font-medium ${
                                browserEnabled ? 'text-info' : 'text-text-muted'
                              }`}
                            >
                              {account.browser}
                            </span>
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
                      className="h-9 appearance-none rounded-xl border border-border/15 bg-secondary/70 px-3 pr-9 text-sm font-medium text-text outline-none transition focus:border-info/40 focus:ring-2 focus:ring-info/20"
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
                    className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl border border-border/15 bg-secondary/70 text-text-muted transition-colors duration-200 hover:text-text disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:text-text-muted"
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
                  <span className="inline-flex h-9 min-w-9 items-center justify-center rounded-xl bg-info px-3 text-sm font-semibold text-white">
                    {currentPage}
                  </span>
                  <button
                    aria-label="Следующая страница"
                    className="inline-flex h-9 w-9 cursor-pointer items-center justify-center rounded-xl border border-border/15 bg-secondary/70 text-text-muted transition-colors duration-200 hover:text-text disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:text-text-muted"
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
        isOpen={isDetailsDialogOpen}
        onAddTelegramChannel={onAddTelegramChannel}
        onClose={() => setIsDetailsDialogOpen(false)}
        onUpdateAccountField={onUpdateAccountField}
        onUpdateTelegramChannel={onUpdateTelegramChannel}
      />
      <CreateAccountDialog
        isOpen={isCreateDialogOpen}
        onClose={() => setIsCreateDialogOpen(false)}
        onCreateAccount={onCreateAccount}
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
        className="max-h-[calc(100vh-64px)] w-full max-w-330 overflow-y-auto rounded-[30px] border border-border/20 bg-foreground p-6 shadow-[0_30px_90px_rgba(15,23,42,0.2)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-col gap-4 border-b border-border/10 pb-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="text-3xl font-semibold tracking-tight text-text">
                {title}
              </h3>
              {statusBadge}
            </div>
          </div>

          <button
            aria-label={closeLabel}
            className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-border/15 bg-secondary text-text transition-all duration-200 hover:border-border/35 hover:bg-secondary/80"
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

interface AccountDetailsDialogProps {
  account: AccountRow | null;
  isOpen: boolean;
  onClose: () => void;
  onUpdateAccountField: (
    accountId: string,
    field: AccountEditableField,
    value: string,
  ) => void;
  onAddTelegramChannel: (
    accountId: string,
    draft: TelegramChannelDraft,
  ) => void;
  onUpdateTelegramChannel: (
    accountId: string,
    channelId: string,
    draft: TelegramChannelDraft,
  ) => void;
}

function AccountDetailsDialog({
  account,
  isOpen,
  onClose,
  onUpdateAccountField,
  onAddTelegramChannel,
  onUpdateTelegramChannel,
}: AccountDetailsDialogProps) {
  if (!isOpen || !account) {
    return null;
  }

  return (
    <AccountDialogShell
      closeLabel="Закрыть настройки аккаунта"
      isOpen={isOpen}
      onClose={onClose}
      statusBadge={
        <StatusPill tone={account.statusTone}>{account.statusLabel}</StatusPill>
      }
      title={account.name}
    >
      <div className="space-y-6 pt-6">
        <AccountFormFields
          values={account}
          onFieldChange={(field, value) =>
            onUpdateAccountField(account.id, field, value)
          }
        />

        <TelegramChannelsPanel
          accountId={account.id}
          channels={account.telegramChannels}
          onAddChannel={onAddTelegramChannel}
          onUpdateChannel={onUpdateTelegramChannel}
        />
      </div>
    </AccountDialogShell>
  );
}

interface CreateAccountDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateAccount: (draft: AccountDraft) => void;
}

function CreateAccountDialog({
  isOpen,
  onClose,
  onCreateAccount,
}: CreateAccountDialogProps) {
  const [draft, setDraft] = useState<AccountDraft>(accountDraftInitialState);
  const isSubmitDisabled = !isAccountDraftValid(draft);

  useEffect(() => {
    if (isOpen) {
      return;
    }

    setDraft(accountDraftInitialState);
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

        <div className="rounded-[22px] border border-dashed border-border/25 bg-secondary/45 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-info">
              <Link2 className="h-5 w-5" />
            </div>
            <div className="space-y-1">
              <strong className="block text-text">Telegram-каналы</strong>
              <p className="leading-6 text-text-muted">
                После создания аккаунта открой меню `...`, чтобы добавить каналы
                и настроить источник фото.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <button
            className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border/40 bg-secondary/75 px-3 py-2 text-text transition hover:border-border/70 hover:bg-secondary"
            type="button"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
            Отмена
          </button>
          <button
            className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-info px-4 py-2 text-white transition hover:bg-info/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-info"
            disabled={isSubmitDisabled}
            type="button"
            onClick={() => {
              if (isSubmitDisabled) {
                return;
              }

              onCreateAccount(draft);
              onClose();
            }}
          >
            <Save className="h-4 w-4" />
            Создать аккаунт
          </button>
        </div>
      </div>
    </AccountDialogShell>
  );
}

interface TelegramChannelsPanelProps {
  accountId: string;
  channels: TelegramChannel[];
  onAddChannel: (accountId: string, draft: TelegramChannelDraft) => void;
  onUpdateChannel: (
    accountId: string,
    channelId: string,
    draft: TelegramChannelDraft,
  ) => void;
}

interface TelegramChannelComposerProps {
  draft: TelegramChannelDraft;
  submitLabel: string;
  title: string;
  onCancel: () => void;
  onDraftChange: (
    field: keyof TelegramChannelDraft,
    value: TelegramChannelDraft[keyof TelegramChannelDraft],
  ) => void;
  onSubmit: () => void;
}

function TelegramChannelsPanel({
  accountId,
  channels,
  onAddChannel,
  onUpdateChannel,
}: TelegramChannelsPanelProps) {
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [composerDraft, setComposerDraft] = useState<TelegramChannelDraft>(
    telegramDraftInitialState,
  );
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<TelegramChannelDraft>(
    telegramDraftInitialState,
  );

  useEffect(() => {
    setIsComposerOpen(false);
    setComposerDraft(telegramDraftInitialState);
    setEditingChannelId(null);
    setEditingDraft(telegramDraftInitialState);
  }, [accountId]);

  const startEditing = (channel: TelegramChannel) => {
    setEditingChannelId(channel.id);
    setEditingDraft({
      title: channel.title,
      handle: channel.handle,
      photoSource: channel.photoSource,
    });
  };

  const resetEditing = () => {
    setEditingChannelId(null);
    setEditingDraft(telegramDraftInitialState);
  };

  const submitNewChannel = () => {
    if (!normalizeTelegramHandle(composerDraft.handle)) {
      return;
    }

    onAddChannel(accountId, composerDraft);
    setComposerDraft(telegramDraftInitialState);
    setIsComposerOpen(false);
  };

  const submitEditedChannel = () => {
    if (!editingChannelId || !normalizeTelegramHandle(editingDraft.handle)) {
      return;
    }

    onUpdateChannel(accountId, editingChannelId, editingDraft);
    resetEditing();
  };

  return (
    <section className="space-y-4 border-t border-border/20 pt-2">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <h3 className="text-[22px] font-semibold text-text">
            Telegram-каналы
          </h3>
          <p className="text-text-muted">
            Управление каналами внутри карточки аккаунта
          </p>
        </div>

        <button
          className="border inline-flex items-center gap-2 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-3 py-1"
          type="button"
          onClick={() => setIsComposerOpen((current) => !current)}
        >
          <Plus className="text-text w-3 h-3" />
          {isComposerOpen ? 'Скрыть' : 'Добавить'}
        </button>
      </div>

      <div className="space-y-4">
        {isComposerOpen ? (
          <div className="rounded-[22px] border border-border/25 bg-secondary/60 p-4">
            <TelegramChannelComposer
              draft={composerDraft}
              submitLabel="Сохранить канал"
              title="Новый Telegram-канал"
              onCancel={() => {
                setComposerDraft(telegramDraftInitialState);
                setIsComposerOpen(false);
              }}
              onDraftChange={(field, value) =>
                setComposerDraft((current) => ({ ...current, [field]: value }))
              }
              onSubmit={submitNewChannel}
            />
          </div>
        ) : null}

        {channels.length === 0 ? (
          <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
            <strong className="block text-text">Пока нет каналов</strong>
            <p className="mt-2 leading-6 text-text-muted">
              Открой форму выше и добавь первый Telegram-канал для этого
              аккаунта.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {channels.map((channel, index) => {
              const isEditing = editingChannelId === channel.id;

              if (isEditing) {
                return (
                  <div
                    key={channel.id}
                    className="rounded-[22px] border border-border/25 bg-secondary/70 p-4"
                  >
                    <TelegramChannelComposer
                      draft={editingDraft}
                      submitLabel="Обновить канал"
                      title={`Редактирование: ${channel.title}`}
                      onCancel={resetEditing}
                      onDraftChange={(field, value) =>
                        setEditingDraft((current) => ({
                          ...current,
                          [field]: value,
                        }))
                      }
                      onSubmit={submitEditedChannel}
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
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-info">
                            <Link2 className="h-5 w-5" />
                          </div>
                          <div>
                            <strong className="block text-[1.05rem] text-text">
                              {channel.title}
                            </strong>
                            <span className="text-sm text-text-muted">
                              {formatChannelBadge(channel.handle)}
                            </span>
                          </div>
                        </div>
                      </div>
                      <button
                        className="border inline-flex items-center rounded-xl border-border/50 bg-warning/6.25 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/12.5 hover:border-border/75 p-2.5"
                        type="button"
                        onClick={() => startEditing(channel)}
                      >
                        <PencilLine className="text-text h-4 w-4" />
                      </button>
                    </div>

                    {channel.photoSource ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs uppercase tracking-wide text-text-muted/75">
                          Фото брать из
                        </span>
                        <span className="inline-flex items-center rounded-full border border-info/25 bg-info/10 px-2 text-xs text-text-muted">
                          {channel.photoSource}
                        </span>
                      </div>
                    ) : null}
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
  submitLabel,
  title,
  onCancel,
  onDraftChange,
  onSubmit,
}: TelegramChannelComposerProps) {
  const isSubmitDisabled = !normalizeTelegramHandle(draft.handle);

  return (
    <div className="space-y-4">
      <div>
        <strong className="block text-[1.02rem] text-text">{title}</strong>
        <p className="mt-2 leading-6 text-text-muted">
          Можно вставить `t.me/...`, `https://t.me/...` или просто `@handle`.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-text">Название</span>
          <input
            className={accountControlClassName}
            placeholder="Например, Wardrobe Drop"
            type="text"
            value={draft.title}
            onChange={(event) => onDraftChange('title', event.target.value)}
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-text">Ссылка</span>
          <input
            className={accountControlClassName}
            placeholder="t.me/example_channel"
            type="text"
            value={draft.handle}
            onChange={(event) => onDraftChange('handle', event.target.value)}
          />
        </label>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium text-text">Откуда брать фото</span>
        <select
          className={accountControlClassName}
          value={draft.photoSource}
          onChange={(event) =>
            onDraftChange(
              'photoSource',
              event.target.value as TelegramPhotoSource,
            )
          }
        >
          {telegramPhotoSourceOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-wrap justify-end gap-2">
        <button
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border/40 bg-secondary/75 px-3 py-2 text-text transition hover:border-border/70 hover:bg-secondary"
          type="button"
          onClick={onCancel}
        >
          <X className="h-4 w-4" />
          Отмена
        </button>
        <button
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-success/30 bg-success/12.5 px-3 py-2 text-text transition hover:border-success/45 hover:bg-success/20 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-success/30 disabled:hover:bg-success/12.5"
          disabled={isSubmitDisabled}
          type="button"
          onClick={onSubmit}
        >
          <Check className="h-4 w-4" />
          {submitLabel}
        </button>
      </div>
    </div>
  );
}

function StatsPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Статистика"
        actions={
          <>
            <ActionButton
              compact
              icon={<CalendarRange className="h-4 w-4 text-text" />}
              tone="neutral"
            >
              7 дней
            </ActionButton>
            <ActionButton compact tone="info">
              30 дней
            </ActionButton>
          </>
        }
      />

      <div className="grid gap-3 grid-cols-4">
        {statsMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-5">
        <Panel
          title="График публикаций"
          subtitle="Серия items/errors для desktop-макета"
        >
          <LineChart data={statsSeries} height={320} />
        </Panel>

        <Panel
          title="Логи и события"
          subtitle="Поток ошибок и технических состояний теперь встроен в статистику"
          actions={
            <>
              <ActionButton
                compact
                icon={<Filter className="h-4 w-4 text-text" />}
                tone="neutral"
              >
                Все аккаунты
              </ActionButton>
              <ActionButton compact tone="warning">
                Только ошибки
              </ActionButton>
            </>
          }
        >
          <div className="flex flex-col gap-3">
            {logRecords.map((record) => (
              <div
                key={`${record.time}-${record.message}`}
                className={`${surfaceCardClassName} grid gap-4 xl:grid-cols-[170px_minmax(0,1fr)]`}
              >
                <div className="flex flex-col gap-2.5">
                  <span className="text-text-muted">{record.time}</span>
                  <div>
                    <StatusPill tone={record.tone}>{record.level}</StatusPill>
                  </div>
                </div>
                <div>
                  <strong className="block text-[1.05rem]">
                    {record.account}
                  </strong>
                  <p className="mt-3 leading-8 text-text-muted">
                    {record.message}
                  </p>
                </div>
              </div>
            ))}
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
                  <h1 className="font-medium text-text text-lg">
                    {toggle.label}
                  </h1>
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
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
      <TextInputField
        label="Корень проекта"
        value={values.path}
        icon={
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary/50">
            <FolderOpen className="h-3.5 w-3.5 text-warning/75" />
          </div>
        }
        onChange={(value) => onFieldChange('path', value)}
      />
      <SelectField
        label="Браузер"
        value={values.browser}
        options={browserOptions}
        icon={
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary/50">
            <Eye className="h-3.5 w-3.5 text-success/75" />
          </div>
        }
        onChange={(value) => onFieldChange('browser', value)}
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
      <span className="flex items-center gap-2 text-[16px] font-medium text-text">
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
      <span className="flex items-center gap-2 text-[16px] font-medium text-text">
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
                    className={`flex w-full cursor-pointer items-center justify-between gap-4 rounded-xl px-4 py-2 text-left transition-colors duration-200 ${
                      isSelected ? 'bg-foreground' : 'hover:bg-foreground/50'
                    } ${index < options.length - 1 ? 'mb-1' : ''}`}
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
