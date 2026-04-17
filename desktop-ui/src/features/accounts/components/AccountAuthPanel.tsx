import {
  ChevronDown,
  Check,
  FileJson,
  LoaderCircle,
  LockKeyhole,
  LogIn,
  LogOut,
  Phone,
  ShieldCheck,
} from 'lucide-react';
import type { ChangeEvent, ReactNode } from 'react';
import { useEffect, useRef, useState } from 'react';

import {
  getShafaAuthStatus,
  getTelegramAuthStatus,
  logoutShafa,
  logoutTelegram,
  requestTelegramCode,
  saveShafaStorageState,
  startShafaBrowserLogin,
  submitTelegramCode,
  submitTelegramPassword,
} from '../../../api/auth';
import { StatusPill } from '../../../components/StatusPill';
import type {
  AccountRow,
  ApiShafaAuthStatus,
  ApiTelegramAuthStatus,
} from '../../../types';
import { accountControlClassName } from '../constants';
import {
  formatApiError,
  getShafaStatusMeta,
  getTelegramStepMeta,
  parseShafaImportInput,
} from '../utils';

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
      <span className="flex items-center gap-2 text-sm font-medium text-text">
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
  onReloadAccounts: () => Promise<void>;
}

export function AccountAuthPanel({
  account,
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
      setFeedback(nextStatus.message);
      await Promise.all([onRefreshStatuses(), onReloadAccounts()]);
    } catch (nextError) {
      setError(
        formatApiError(
          nextError,
          'Не удалось импортировать storage state или cookies для Shafa.',
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
              <p className="font-medium text-text">Доступ к аккаунту Shafa</p>
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
          <button
            className={
              isConnected
                ? 'inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-border/40 bg-secondary/85 px-4 py-2 text-sm font-medium text-text transition hover:border-border/70 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border/40 disabled:hover:bg-secondary/85'
                : 'inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-info px-4 py-2 text-white transition hover:bg-info/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-info'
            }
            disabled={isAuthActionDisabled}
            type="button"
            onClick={() =>
              void (isConnected ? handleLogout() : handleBrowserLogin())
            }
          >
            {isSubmitting ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : isConnected ? (
              <LogOut className="h-4 w-4" />
            ) : (
              <LogIn className="h-4 w-4" />
            )}
            {isConnected ? 'Выйти' : 'Войти через браузер'}
          </button>
          <input
            ref={fileInputRef}
            accept=".json,application/json"
            className="hidden"
            type="file"
            onChange={(event) => void handleFileChange(event)}
          />
          <button
            className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-border/40 bg-secondary/85 px-4 py-2 text-sm font-medium text-text transition hover:border-border/70 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-border/40 disabled:hover:bg-secondary/85"
            disabled={isAuthActionDisabled}
            type="button"
            onClick={() => fileInputRef.current?.click()}
          >
            <FileJson className="h-4 w-4" />
            Импортировать JSON
          </button>
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
  status: ApiTelegramAuthStatus | null;
  isStatusLoading: boolean;
  onRefreshStatuses: () => Promise<void>;
  onReloadAccounts: () => Promise<void>;
}

function TelegramAuthCard({
  accountId,
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
    if (isConnected) {
      return;
    }

    setIsAccountMenuOpen(false);
  }, [isConnected]);

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
  const isAccountMenuDisabled = isSubmitting || isStatusLoading || !isConnected;

  return (
    <div className="rounded-[22px] border border-border/20 bg-secondary/55 p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-info">
              <LogIn className="h-6 w-6" />
            </div>

            <div className="space-y-1">
              <p className="font-medium text-text">Telegram авторизация</p>
              <div className="flex flex-wrap gap-2">
                <StatusPill tone={stepMeta.tone}>{stepMeta.label}</StatusPill>
                <StatusPill
                  tone={status?.has_api_credentials ? 'success' : 'warning'}
                >
                  {status?.has_api_credentials ? 'API настроен' : 'Нет API'}
                </StatusPill>
              </div>
            </div>
          </div>
        </div>
        {isConnected ? (
          <div className="relative" ref={accountMenuRef}>
            <div className="flex font-medium gap-3 items-center px-3 border border-border/50 bg-secondary h-9.5 rounded-xl">
              <button
                aria-expanded={isAccountMenuOpen}
                aria-haspopup="menu"
                className="inline-flex cursor-pointer items-center justify-center gap-2 border-r border-border/50 rounded-l-xl text-sm h-9.5 font-medium pr-3 hover:text-text-muted text-text-muted/75 disabled:cursor-not-allowed disabled:opacity-50"
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
                    className={`h-4 w-4 transition-transform duration-200 ${
                      isAccountMenuOpen ? 'rotate-180 text-text' : ''
                    }`}
                  />
                )}
              </button>
              {connectedPhoneLabel}
            </div>

            {isAccountMenuOpen ? (
              <div className="absolute top-full right-0 z-10 mt-2 rounded-2xl border border-border/20 bg-foreground p-2 shadow-[0_18px_40px_rgba(15,23,42,0.14)]">
                <button
                  className="inline-flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium text-text transition hover:bg-secondary/80 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
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
              </div>
            ) : null}
          </div>
        ) : null}
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
              className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-info px-4 py-2 text-white transition hover:bg-info/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-info"
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
                className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-info px-4 py-2 text-white transition hover:bg-info/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-info"
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
                className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-info px-4 py-2 text-white transition hover:bg-info/90 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-info"
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
