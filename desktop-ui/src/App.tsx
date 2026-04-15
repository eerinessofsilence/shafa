import { LineChart } from './components/LineChart';
import { MetricCard } from './components/MetricCard';
import { PageHeader } from './components/PageHeader';
import { Panel } from './components/Panel';
import { StatusPill } from './components/StatusPill';
import {
  accountRows,
  dashboardAlerts,
  dashboardMetrics,
  dashboardSeries,
  logRecords,
  navItems,
  parserQueue,
  parserResults,
  parserToggles,
  settingsGroups,
  statsMetrics,
  statsSeries,
  systemStatus,
} from './data/mockData';
import type {
  AccountRow,
  PageId,
  ParserToggle,
  TelegramChannel,
  TelegramPhotoSource,
} from './types';
import {
  CalendarRange,
  Check,
  ChevronDown,
  Clock3,
  Download,
  Eye,
  Filter,
  FolderOpen,
  Link2,
  PencilLine,
  Play,
  Plus,
  Power,
  RefreshCw,
  Save,
  Square,
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
  'flex h-12 w-full items-center justify-between gap-4 rounded-xl border border-border/25 bg-secondary px-3 text-left text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/25';
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

type TelegramChannelDraft = Pick<
  TelegramChannel,
  'title' | 'handle' | 'photoSource'
>;
type ActionTone = keyof typeof actionButtonClassNames;

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
    id:
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `telegram-${Date.now()}`,
    title: draft.title.trim() || formatChannelTitle(normalizedHandle),
    handle: normalizedHandle,
    photoSource: draft.photoSource,
  };
}

function App() {
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [accounts, setAccounts] = useState<AccountRow[]>(accountRows);
  const [parsingToggles, setParsingToggles] =
    useState<ParserToggle[]>(parserToggles);
  const [selectedAccountId, setSelectedAccountId] = useState(accountRows[0].id);
  const selectedAccount =
    accounts.find((account) => account.id === selectedAccountId) ?? accounts[0];

  const handleAccountFieldChange = (
    accountId: string,
    field: 'path' | 'browser' | 'timer',
    value: string,
  ) => {
    setAccounts((currentAccounts) =>
      currentAccounts.map((account) =>
        account.id === accountId ? { ...account, [field]: value } : account,
      ),
    );
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

  return (
    <div className="min-h-screen font-sans antialiased">
      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="bg-foreground min-h-screen w-full p-7.5">
          <div className="space-y-4 sticky top-7.5">
            <h1 className="font-semibold text-text tracking-tight text-3xl">
              Shafa Control
            </h1>

            <nav className="flex flex-col gap-2.5">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`flex flex-col gap-1 w-full items-start rounded-xl py-2 px-4 transition-all duration-200 ${
                    activePage === item.id
                      ? 'border text-text border-border/75 bg-secondary'
                      : 'border border-transparent text-text/75 bg-secondary/50 hover:bg-secondary/75  hover:border-border/50'
                  }`}
                  onClick={() => setActivePage(item.id)}
                >
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
                onSelectAccount={setSelectedAccountId}
                onUpdateAccountField={handleAccountFieldChange}
                onAddTelegramChannel={handleAddTelegramChannel}
                onUpdateTelegramChannel={handleUpdateTelegramChannel}
              />
            )}
            {activePage === 'parsing' && (
              <ParsingPage
                parserToggles={parsingToggles}
                onToggleParserOption={handleToggleParsingOption}
              />
            )}
            {activePage === 'stats' && <StatsPage />}
            {activePage === 'settings' && <SettingsPage />}
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

      <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
        <Panel
          title="Последние сигналы"
          subtitle="Что требует внимания команды"
        >
          <div className="flex flex-col gap-3">
            {dashboardAlerts.map((alert) => (
              <div
                key={alert.title}
                className="flex gap-2 bg-secondary/50 border border-border/25 p-3 rounded-[18px]"
              >
                <div>
                  <h1 className="text-text font-medium text-lg">
                    {alert.title}
                  </h1>
                  <p className="mt-3 whitespace-pre-line leading-6">
                    {alert.copy}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Ключевые аккаунты"
          subtitle="Шаблонное распределение нагрузки"
        >
          <div className="flex flex-col">
            {accountRows.slice(0, 4).map((account) => (
              <button
                key={account.id}
                type="button"
                className="flex w-full items-center justify-between gap-3.5 border-b border-[rgba(140,172,201,0.16)] py-3.5 text-left last:border-b-0"
              >
                <div>
                  <strong className="block">{account.name}</strong>
                  <span className="text-text-muted">{account.branch}</span>
                </div>
                <StatusPill tone={account.statusTone}>
                  {account.statusLabel}
                </StatusPill>
              </button>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

interface AccountsPageProps {
  accounts: AccountRow[];
  selectedAccount: AccountRow;
  selectedAccountId: string;
  onSelectAccount: (accountId: string) => void;
  onUpdateAccountField: (
    accountId: string,
    field: 'path' | 'browser' | 'timer',
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
  onSelectAccount,
  onUpdateAccountField,
  onAddTelegramChannel,
  onUpdateTelegramChannel,
}: AccountsPageProps) {
  return (
    <div className="space-y-4">
      <PageHeader title="Аккаунты" />

      <div className="flex flex-col gap-5">
        <Panel
          title="Каталог аккаунтов"
          actions={
            <>
              <button
                className="border inline-flex items-center gap-2 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-3 py-1"
                type="button"
              >
                <Plus className="text-text w-3 h-3" />
                Добавить
              </button>
              <button
                className="border inline-flex items-center gap-2 active:scale-[0.975] rounded-xl border-border/50  hover:bg-info/25 cursor-pointer duration-200 transition-all hover:border-border/75 bg-info/12.5 px-3 py-1"
                type="button"
              >
                <Power className="text-text w-3 h-3" />
                Запустить
              </button>
              <button
                className="border inline-flex items-center gap-2 active:scale-[0.975] rounded-xl border-border/50  hover:bg-error/25 cursor-pointer duration-200 transition-all hover:border-border/75 bg-error/12.5 px-3 py-1"
                type="button"
              >
                <X className="text-text w-3 h-3" />
                Удалить
              </button>
            </>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-230 border-collapse">
              <thead>
                <tr>
                  {[
                    'Имя',
                    'Проект',
                    'Браузер',
                    'Таймер',
                    'Каналы',
                    'Статус',
                    'Ошибки',
                  ].map((header) => (
                    <th
                      key={header}
                      className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5 text-left text-xs uppercase tracking-[0.08em]"
                    >
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => (
                  <tr
                    key={account.id}
                    className={`cursor-pointer transition duration-150 hover:bg-[rgba(94,166,255,0.08)]${
                      selectedAccountId === account.id &&
                      'bg-[rgba(94,166,255,0.08)]'
                    }`}
                    onClick={() => onSelectAccount(account.id)}
                  >
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      <strong>{account.name}</strong>
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5 text-[#8c9db4]">
                      {account.path}
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      {account.browser}
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      {account.timer}
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      <span className="inline-flex min-w-8 items-center justify-center rounded-full border border-border/25 bg-secondary/70 px-2.5 py-1 text-sm text-text">
                        {account.telegramChannels.length}
                      </span>
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      <StatusPill tone={account.statusTone}>
                        {account.statusLabel}
                      </StatusPill>
                    </td>
                    <td className="border-b border-[rgba(140,172,201,0.16)] px-3 py-3.5">
                      {account.errors}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title={selectedAccount.name}
          actions={
            <StatusPill tone={selectedAccount.statusTone}>
              {selectedAccount.statusLabel}
            </StatusPill>
          }
        >
          <div className="space-y-6">
            <div className="grid gap-3 md:grid-cols-3">
              <TextInputField
                label="Корень проекта"
                value={selectedAccount.path}
                icon={
                  <div className="bg-secondary/50 rounded-md w-7 h-7 flex items-center justify-center">
                    <FolderOpen className="h-3.5 w-3.5 text-warning/75" />
                  </div>
                }
                onChange={(value) =>
                  onUpdateAccountField(selectedAccount.id, 'path', value)
                }
              />
              <SelectField
                label="Браузер"
                value={selectedAccount.browser}
                options={browserOptions}
                icon={
                  <div className="bg-secondary/50 rounded-md w-7 h-7 flex items-center justify-center">
                    <Eye className="h-3.5 w-3.5 text-success/75" />
                  </div>
                }
                onChange={(value) =>
                  onUpdateAccountField(selectedAccount.id, 'browser', value)
                }
              />
              <SelectField
                label="Таймер"
                value={selectedAccount.timer}
                options={timerOptions}
                icon={
                  <div className="bg-secondary/50 rounded-md w-7 h-7 flex items-center justify-center">
                    <Clock3 className="h-3.5 w-3.5 text-info/75" />
                  </div>
                }
                onChange={(value) =>
                  onUpdateAccountField(selectedAccount.id, 'timer', value)
                }
              />
            </div>

            <TelegramChannelsPanel
              accountId={selectedAccount.id}
              channels={selectedAccount.telegramChannels}
              onAddChannel={onAddTelegramChannel}
              onUpdateChannel={onUpdateTelegramChannel}
            />
          </div>
        </Panel>
      </div>
    </div>
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
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary text-info shadow-[0_12px_30px_rgba(94,166,255,0.12)]">
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
          className="inline-flex items-center gap-2 rounded-xl border border-border/40 bg-secondary/75 px-3 py-2 text-text transition hover:border-border/70 hover:bg-secondary"
          type="button"
          onClick={onCancel}
        >
          <X className="h-4 w-4" />
          Отмена
        </button>
        <button
          className="inline-flex items-center gap-2 rounded-xl border border-success/30 bg-success/12.5 px-3 py-2 text-text transition hover:border-success/45 hover:bg-success/20 disabled:cursor-not-allowed disabled:opacity-50"
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

interface ParsingPageProps {
  parserToggles: ParserToggle[];
  onToggleParserOption: (label: string) => void;
}

function ParsingPage({
  parserToggles,
  onToggleParserOption,
}: ParsingPageProps) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Парсинг"
        actions={
          <>
            <ActionButton
              icon={<Square className="h-4 w-4 text-text" />}
              tone="danger"
            >
              Остановить
            </ActionButton>
            <ActionButton
              icon={<Play className="h-4 w-4 text-text" />}
              tone="info"
            >
              Стартовать
            </ActionButton>
          </>
        }
      />

      <Panel title="Параметры запуска" subtitle="Базовая форма настройки">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Категория" value="Женская одежда" />
          <Field label="Страниц" value="12" />
          <Field label="Задержка" value="2.5 сек" />
          <Field label="Прокси" value="proxy-batch-3.txt" />
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3">
          {parserToggles.map((toggle) => (
            <button
              key={toggle.label}
              aria-checked={toggle.enabled}
              className={`${surfaceCardClassName} flex w-full items-center justify-between gap-3.5 text-left transition-all duration-200 hover:border-border/50 hover:bg-secondary/75 focus:border-info/50 focus:ring-2 focus:ring-info/25`}
              role="switch"
              type="button"
              onClick={() => onToggleParserOption(toggle.label)}
            >
              <div>
                <h1 className="font-medium text-text text-lg">
                  {toggle.label}
                </h1>
                <span className="leading-6 text-text-muted">{toggle.copy}</span>
              </div>
              <ToggleSwitch checked={toggle.enabled} />
            </button>
          ))}
        </div>
      </Panel>

      <Panel
        title="Результаты"
        subtitle="Пример того, как может выглядеть вывод парсинга"
      >
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {parserResults.map((result) => (
            <div key={result.id} className={surfaceCardClassName}>
              <div className="mb-3.5 aspect-[1.2] rounded-2xl bg-[linear-gradient(135deg,rgba(94,166,255,0.25),rgba(69,214,195,0.08)),linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0))]" />
              <strong className="block text-[1.05rem]">{result.title}</strong>
              <span className="mt-2 block text-success">{result.price}</span>
              <p className="mt-3 leading-7 text-text-muted">{result.meta}</p>
            </div>
          ))}
        </div>
      </Panel>
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
          title="События и отклонения"
          subtitle="Mock-аналитика по качеству потока"
        >
          <div className="flex flex-col gap-3">
            <div className={surfaceCardClassName}>
              <strong className="block text-[1.05rem]">
                Средняя скорость выросла на 18%
              </strong>
              <p className="mt-3 leading-7 text-text-muted">
                Пиковая нагрузка сместилась в окно 11:00-13:00.
              </p>
            </div>
            <div className={surfaceCardClassName}>
              <strong className="block text-[1.05rem]">
                Ошибки остались в пределах нормы
              </strong>
              <p className="mt-3 leading-7 text-text-muted">
                В шаблоне зафиксировано 3 технических сбоя на 412 публикаций.
              </p>
            </div>
            <div className={surfaceCardClassName}>
              <strong className="block">Нужен drill-down по аккаунтам</strong>
              <p className="mt-3 leading-7 text-text-muted">
                Следующий этап: отдельный разрез по веткам, каналам и причинам
                фейлов.
              </p>
            </div>
          </div>
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

function SettingsPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Настройки"
        actions={
          <>
            <ActionButton
              compact
              icon={<RefreshCw className="h-4 w-4 text-text" />}
              tone="neutral"
            >
              Обновить
            </ActionButton>
            <ActionButton
              compact
              icon={<Save className="h-4 w-4 text-text" />}
              tone="success"
            >
              Сохранить
            </ActionButton>
          </>
        }
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {settingsGroups.map((group) => (
          <Panel
            key={group.title}
            title={group.title}
            subtitle={group.subtitle}
          >
            <div className="grid gap-3 md:grid-cols-2">
              {group.fields.map((field) => (
                <Field
                  key={field.label}
                  label={field.label}
                  value={field.value}
                />
              ))}
            </div>
          </Panel>
        ))}
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
                    className={`flex w-full items-center justify-between gap-4 rounded-xl px-4 py-2 text-left transition-colors duration-200 ${
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
