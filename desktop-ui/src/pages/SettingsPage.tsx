import {
  formatApiError,
  AppPreferences,
  AppSidebar,
  dateTimeFormatOptions,
  getBrowseLabel,
  parseFloatSetting,
  parseIntegerSetting,
  settingsDescriptionClassName,
  settingsFieldClassName,
  settingsLabelClassName,
  settingsPageClassName,
  settingsPanelClassName,
  settingsSectionItems,
  settingsSubtleCardClassName,
  settingsTextAreaClassName,
  settingsToggleCardClassName,
  ThemeMode,
  ToggleSwitch,
} from '../app/shared';
import type {
  ApiProxyCreate,
  ApiProxyRead,
  PageId,
} from '../types';
import { getButtonClassName } from '../ui';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileJson,
  FolderOpen,
  Info,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
} from 'lucide-react';
import {
  type ComponentPropsWithoutRef,
  type ReactNode,
  useEffect,
  useState,
} from 'react';

interface SettingsPageProps {
  hasUnsavedChanges: boolean;
  isProxyMutationPending: boolean;
  isProxiesLoading: boolean;
  onChangePreference: (
    field: keyof AppPreferences,
    value: string | number | boolean,
  ) => void;
  onCreateProxy: (payload: ApiProxyCreate) => Promise<void>;
  onDeleteProxy: (proxyId: string) => Promise<void>;
  onNavigateToPage: (page: PageId) => void;
  onResetPreferences: () => void;
  onSavePreferences: () => void;
  onToggleTheme: () => void;
  onUpdateProxy: (proxyId: string, payload: ApiProxyCreate) => Promise<void>;
  preferences: AppPreferences;
  proxies: ApiProxyRead[];
  proxiesError: string;
  themeMode: ThemeMode;
}

interface ProxyFormDraft {
  enabled: boolean;
  host: string;
  maxAccounts: number;
  name: string;
  notes: string;
  password: string;
  port: string;
  scheme: 'http' | 'https' | 'socks5';
  username: string;
}

function createEmptyProxyDraft(): ProxyFormDraft {
  return {
    enabled: true,
    host: '',
    maxAccounts: 3,
    name: '',
    notes: '',
    password: '',
    port: '',
    scheme: 'http',
    username: '',
  };
}

function SettingsPage({
  hasUnsavedChanges,
  isProxyMutationPending,
  isProxiesLoading,
  onChangePreference,
  onCreateProxy,
  onDeleteProxy,
  onNavigateToPage,
  onResetPreferences,
  onSavePreferences,
  onToggleTheme,
  onUpdateProxy,
  preferences,
  proxies,
  proxiesError,
  themeMode,
}: SettingsPageProps) {
  const [activeSection, setActiveSection] = useState<
    (typeof settingsSectionItems)[number]['id']
  >(settingsSectionItems[0].id);
  const [editingProxyId, setEditingProxyId] = useState('');
  const [proxyDraft, setProxyDraft] = useState<ProxyFormDraft>(
    createEmptyProxyDraft,
  );
  const [proxySubmitError, setProxySubmitError] = useState('');
  const selectedDateTimeFormat =
    dateTimeFormatOptions.find(
      (option) => option.value === preferences.dateTimeFormat,
    ) ?? dateTimeFormatOptions[0];

  const isProxyDraftValid =
    Boolean(proxyDraft.name.trim()) &&
    Boolean(proxyDraft.host.trim()) &&
    Number.parseInt(proxyDraft.port, 10) > 0 &&
    Number.parseInt(proxyDraft.port, 10) <= 65535 &&
    proxyDraft.maxAccounts >= 1;

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

  useEffect(() => {
    if (
      editingProxyId &&
      !proxies.some((proxy) => proxy.id === editingProxyId)
    ) {
      setEditingProxyId('');
      setProxyDraft(createEmptyProxyDraft());
      setProxySubmitError('');
    }
  }, [editingProxyId, proxies]);

  const handleProxyFieldChange = (
    field: keyof ProxyFormDraft,
    value: string | number | boolean,
  ) => {
    setProxyDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  };

  const resetProxyDraft = () => {
    setEditingProxyId('');
    setProxyDraft(createEmptyProxyDraft());
    setProxySubmitError('');
  };

  const submitProxyDraft = async () => {
    setProxySubmitError('');

    const payload: ApiProxyCreate = {
      name: proxyDraft.name.trim(),
      scheme: proxyDraft.scheme,
      host: proxyDraft.host.trim(),
      port: Number.parseInt(proxyDraft.port, 10),
      username: proxyDraft.username.trim(),
      password: proxyDraft.password,
      max_accounts: proxyDraft.maxAccounts,
      enabled: proxyDraft.enabled,
      notes: proxyDraft.notes.trim(),
    };

    try {
      if (editingProxyId) {
        await onUpdateProxy(editingProxyId, payload);
      } else {
        await onCreateProxy(payload);
      }
      resetProxyDraft();
    } catch (error) {
      setProxySubmitError(
        formatApiError(error, 'Не удалось сохранить настройки прокси.'),
      );
    }
  };

  const beginProxyEdit = (proxy: ApiProxyRead) => {
    setEditingProxyId(proxy.id);
    setProxyDraft({
      enabled: proxy.enabled,
      host: proxy.host,
      maxAccounts: proxy.max_accounts,
      name: proxy.name,
      notes: proxy.notes || '',
      password: proxy.password || '',
      port: String(proxy.port),
      scheme: proxy.scheme,
      username: proxy.username || '',
    });
    setProxySubmitError('');
  };

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
          <header className="sticky top-0 z-30 flex h-14 items-center gap-4 overflow-hidden border-b border-border-soft bg-foreground px-6">
            <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
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
                className: 'shrink-0',
              })}
              disabled={!hasUnsavedChanges}
              type="button"
              onClick={onSavePreferences}
            >
              <Save className="h-4 w-4" />
              Сохранить
            </button>
          </header>

          <div className="mx-auto flex w-full min-w-0 max-w-265 flex-col px-10 py-9">
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
                      description="Добавлять случайное отклонение к задержке (jitter), чтобы не создавать синхронные пики."
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
                      description="Сохранять полный JSON-ответ для отладки и разбора ошибок."
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
                  id="settings-proxies"
                  className={`${settingsPanelClassName} scroll-mt-20`}
                >
                  <SettingsSectionHeader
                    icon={<ShieldCheck className="h-4.5 w-4.5" />}
                    title="Прокси и маршруты"
                  />

                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
                    <div className="space-y-4">
                      <div className="grid gap-4 md:grid-cols-2">
                        <SettingsSummaryCard
                          icon={<ShieldCheck className="h-5 w-5" />}
                          label="АКТИВНЫЕ ПРОКСИ"
                          value={String(
                            proxies.filter((proxy) => proxy.enabled).length,
                          )}
                        />
                        <SettingsSummaryCard
                          icon={<RefreshCw className="h-5 w-5" />}
                          label="ВСЕГО ПРОКСИ"
                          value={String(proxies.length)}
                        />
                      </div>

                      {proxiesError ? (
                        <p className="rounded-[8px] border border-error/15 bg-error/6 px-4 py-3 text-sm text-error">
                          {proxiesError}
                        </p>
                      ) : null}

                      <div className="space-y-3">
                        {isProxiesLoading ? (
                          <div className={settingsSubtleCardClassName}>
                            <p className="text-sm text-text-muted">
                              Загружаю список прокси...
                            </p>
                          </div>
                        ) : null}

                        {!isProxiesLoading && proxies.length === 0 ? (
                          <div className={settingsSubtleCardClassName}>
                            <p className="text-sm text-text-muted">
                              Прокси ещё не добавлены. Создай первый профиль
                              справа, и он станет доступен в настройках
                              аккаунта.
                            </p>
                          </div>
                        ) : null}

                        {proxies.map((proxy) => {
                          const isEditing = editingProxyId === proxy.id;
                          return (
                            <div
                              key={proxy.id}
                              className="rounded-[10px] border border-border bg-foreground px-4 py-4"
                            >
                              <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="space-y-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <h3 className="text-[15px] font-semibold text-text">
                                      {proxy.name}
                                    </h3>
                                    <span className="rounded-full border border-border bg-secondary px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.04em] text-text-muted">
                                      {proxy.scheme}
                                    </span>
                                    <span className="rounded-full border border-border bg-secondary px-2.5 py-1 text-[11px] font-medium text-text-muted">
                                      {proxy.status}
                                    </span>
                                  </div>
                                  <p className="text-sm text-text-muted">
                                    {proxy.host}:{proxy.port}
                                  </p>
                                  <p className="text-[12px] text-text-muted">
                                    Аккаунтов: {proxy.assigned_accounts_count}/
                                    {proxy.max_accounts}
                                  </p>
                                </div>

                                <div className="flex gap-2">
                                  <button
                                    className={getButtonClassName({
                                      size: 'sm',
                                      variant: isEditing ? 'solid' : 'soft',
                                      tone: isEditing ? 'info' : 'neutral',
                                    })}
                                    type="button"
                                    onClick={() => beginProxyEdit(proxy)}
                                  >
                                    Изменить
                                  </button>
                                  <button
                                    className={getButtonClassName({
                                      size: 'sm',
                                      tone: 'danger',
                                      variant: 'soft',
                                    })}
                                    disabled={isProxyMutationPending}
                                    type="button"
                                    onClick={async () => {
                                      if (
                                        !window.confirm(
                                          `Удалить прокси "${proxy.name}"?`,
                                        )
                                      ) {
                                        return;
                                      }

                                      try {
                                        await onDeleteProxy(proxy.id);
                                        if (editingProxyId === proxy.id) {
                                          resetProxyDraft();
                                        }
                                      } catch (error) {
                                        setProxySubmitError(
                                          formatApiError(
                                            error,
                                            'Не удалось удалить прокси.',
                                          ),
                                        );
                                      }
                                    }}
                                  >
                                    <Trash2 className="h-4 w-4" />
                                    Удалить
                                  </button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="space-y-4 rounded-[12px] border border-border bg-secondary/40 p-4">
                      <div className="space-y-1">
                        <h3 className="text-[16px] font-semibold text-text">
                          {editingProxyId ? 'Редактирование прокси' : 'Новый прокси'}
                        </h3>
                        <p className="text-sm text-text-muted">
                          Прокси назначаются аккаунтам и затем автоматически
                          используются для Shafa и Telegram в пределах этого
                          аккаунта.
                        </p>
                      </div>

                      <div className="grid gap-4">
                        <SettingsTextField
                          label="НАЗВАНИЕ ПРОКСИ"
                          value={proxyDraft.name}
                          onChange={(value) =>
                            handleProxyFieldChange('name', value)
                          }
                        />
                        <div className="grid gap-4 md:grid-cols-2">
                          <SettingsSelectField
                            label="ТИП ПРОКСИ"
                            options={[
                              { label: 'HTTP', value: 'http' },
                              { label: 'HTTPS', value: 'https' },
                              { label: 'SOCKS5', value: 'socks5' },
                            ]}
                            value={proxyDraft.scheme}
                            onChange={(value) =>
                              handleProxyFieldChange(
                                'scheme',
                                value as ProxyFormDraft['scheme'],
                              )
                            }
                          />
                          <SettingsNumberField
                            label="ЛИМИТ АККАУНТОВ"
                            maximum={100}
                            minimum={1}
                            step={1}
                            value={proxyDraft.maxAccounts}
                            onChange={(value) =>
                              handleProxyFieldChange('maxAccounts', value)
                            }
                          />
                        </div>
                        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_140px]">
                          <SettingsTextField
                            label="HOST"
                            value={proxyDraft.host}
                            onChange={(value) =>
                              handleProxyFieldChange('host', value)
                            }
                          />
                          <SettingsTextField
                            inputMode="numeric"
                            label="PORT"
                            value={proxyDraft.port}
                            onChange={(value) =>
                              handleProxyFieldChange(
                                'port',
                                value.replace(/[^\d]/g, '').slice(0, 5),
                              )
                            }
                          />
                        </div>
                        <div className="grid gap-4 md:grid-cols-2">
                          <SettingsTextField
                            label="USERNAME"
                            value={proxyDraft.username}
                            onChange={(value) =>
                              handleProxyFieldChange('username', value)
                            }
                          />
                          <SettingsTextField
                            label="PASSWORD"
                            value={proxyDraft.password}
                            onChange={(value) =>
                              handleProxyFieldChange('password', value)
                            }
                          />
                        </div>
                        <SettingsTextField
                          label="ЗАМЕТКИ"
                          value={proxyDraft.notes}
                          onChange={(value) =>
                            handleProxyFieldChange('notes', value)
                          }
                        />
                        <SettingsToggleCard
                          checked={proxyDraft.enabled}
                          description="Отключённый прокси нельзя назначить новому аккаунту, и backend будет блокировать запуск уже связанных аккаунтов."
                          icon={
                            <ShieldCheck className="h-4.5 w-4.5 text-text-faint" />
                          }
                          label="Прокси активен"
                          onToggle={() =>
                            handleProxyFieldChange('enabled', !proxyDraft.enabled)
                          }
                        />
                      </div>

                      {proxySubmitError ? (
                        <p className="rounded-[8px] border border-error/15 bg-error/6 px-4 py-3 text-sm text-error">
                          {proxySubmitError}
                        </p>
                      ) : null}

                      <div className="flex flex-wrap justify-end gap-2">
                        {editingProxyId ? (
                          <button
                            className={getButtonClassName({
                              size: 'sm',
                              variant: 'soft',
                            })}
                            type="button"
                            onClick={resetProxyDraft}
                          >
                            Отмена
                          </button>
                        ) : null}
                        <button
                          className={getButtonClassName({
                            tone: 'info',
                            variant: 'solid',
                            size: 'sm',
                          })}
                          disabled={!isProxyDraftValid || isProxyMutationPending}
                          type="button"
                          onClick={() => void submitProxyDraft()}
                        >
                          <Save className="h-4 w-4" />
                          {editingProxyId ? 'Сохранить прокси' : 'Создать прокси'}
                        </button>
                      </div>
                    </div>
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
                      labelTooltip="Путь для логов сессий, служебных логов и отчётов об ошибках."
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

interface SettingsTextFieldProps {
  description?: string;
  inputMode?: ComponentPropsWithoutRef<'input'>['inputMode'];
  label: string;
  labelTooltip?: string;
  value: string;
  onChange: (value: string) => void;
}

function SettingsTextField({
  description,
  inputMode,
  label,
  labelTooltip,
  value,
  onChange,
}: SettingsTextFieldProps) {
  return (
    <SettingsFieldShell
      description={description}
      label={label}
      labelTooltip={labelTooltip}
    >
      <input
        className={settingsFieldClassName}
        inputMode={inputMode}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
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
          className="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 cursor-not-allowed items-center justify-center rounded-md text-text-faint/55"
          disabled
          title="Выбор папки из интерфейса пока недоступен"
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

export default SettingsPage;
