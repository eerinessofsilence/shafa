import { Link2, Save, ShieldCheck, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { StatusPill } from '../../../components/StatusPill';
import type { AccountRow } from '../../../types';
import { accountDraftInitialState } from '../constants';
import type { AccountDraft } from '../types';
import {
  formatApiError,
  getAccountDraftFromRow,
  isAccountDraftValid,
} from '../utils';
import { AccountAuthPanel } from './AccountAuthPanel';
import { AccountFormFields } from './AccountFormFields';
import { TelegramChannelsPanel } from './TelegramChannelsPanel';

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

interface AccountDetailsDialogProps {
  account: AccountRow | null;
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

export function AccountDetailsDialog({
  account,
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
            <Save className="h-4 w-4" />
            Сохранить
          </button>
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

export function CreateAccountDialog({
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
            <Save className="h-4 w-4" />
            Создать аккаунт
          </button>
        </div>
      </div>
    </AccountDialogShell>
  );
}
