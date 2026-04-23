import {
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
import type { PageId } from '../types';
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
  SlidersHorizontal,
} from 'lucide-react';
import { type ReactNode, useEffect, useState } from 'react';

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
