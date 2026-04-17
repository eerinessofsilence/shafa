import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Ellipsis,
  FolderOpen,
  Plus,
  Trash2,
  X,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import type { AccountRow, StatusTone } from '../types';
import { AccountDetailsDialog, CreateAccountDialog } from '../features/accounts/components/AccountDialogs';
import {
  accountPageSizeOptions,
  accountTableHeaders,
} from '../features/accounts/constants';
import type {
  AccountBulkActionId,
  AccountDraft,
  AccountSortDirection,
  AccountSortField,
} from '../features/accounts/types';
import {
  formatApiError,
  getAccountSortValue,
} from '../features/accounts/utils';

type BulkActionTone = 'primary' | 'neutral' | 'danger';

const accountStatusBadgeClassNames: Record<StatusTone, string> = {
  success: 'bg-success/15 text-success',
  warning: 'bg-info/15 text-info',
  info: 'bg-info/15 text-info',
  danger: 'bg-error/15 text-error',
  neutral: 'bg-secondary text-text-muted',
};

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
  onSyncAccountChannels: (
    accountId: string,
    channelLinks: string[],
  ) => Promise<void>;
  onUpdateAccount: (accountId: string, draft: AccountDraft) => Promise<void>;
}

export function AccountsPage({
  accounts,
  isLoading,
  isMutationPending,
  loadError,
  onBulkAction,
  onCreateAccount,
  onReload,
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
  const sortedAccounts = [...accounts].sort((leftAccount, rightAccount) => {
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
  });
  const totalPages = Math.max(1, Math.ceil(sortedAccounts.length / itemsPerPage));
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
        return { field, direction: 'desc' };
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

  return (
    <div className="space-y-4">
      <PageHeader title="Аккаунты" />

      {loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          <span>{loadError}</span>
          <button
            className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-error/20 bg-error/10 px-3 py-2 text-error transition hover:bg-error/15 disabled:cursor-not-allowed disabled:opacity-50"
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
                  disabled={selectedAccountIds.length === 0 || isMutationPending}
                  icon={
                    shouldShowCloseAction ? (
                      <X className="h-4 w-4" />
                    ) : (
                      <FolderOpen className="h-4 w-4" />
                    )
                  }
                  tone={shouldShowCloseAction ? 'danger' : 'primary'}
                  onClick={() =>
                    void runBulkAction(shouldShowCloseAction ? 'close' : 'open')
                  }
                >
                  {shouldShowCloseAction ? 'Остановить' : 'Открыть'}
                </BulkActionButton>
                <button
                  aria-label="Удалить отмеченные аккаунты"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-error/15 bg-error/8 text-error transition-all duration-200 hover:border-error/30 hover:bg-error/12 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-error/15 disabled:hover:bg-error/8"
                  disabled={selectedAccountIds.length === 0 || isMutationPending}
                  type="button"
                  onClick={() => void runBulkAction('delete')}
                >
                  <Trash2 className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Открыть настройки аккаунта"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl border border-border/15 bg-secondary/95 text-text transition-all duration-200 hover:border-border/35 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-border/15 disabled:hover:bg-secondary/95"
                  disabled={!detailsAccount || isMutationPending}
                  type="button"
                  onClick={() => setIsDetailsDialogOpen(true)}
                >
                  <Ellipsis className="h-4.5 w-4.5" />
                </button>
                <button
                  aria-label="Добавить аккаунт"
                  className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-xl bg-info text-white transition-all duration-200 hover:bg-info/90 active:scale-[0.98]"
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
          <div className="overflow-hidden rounded-2xl bg-secondary/50">
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
                        className="border-b border-border/20 px-4 pb-2 text-left text-xs font-medium uppercase tracking-wide text-text-muted"
                      >
                        <button
                          className={`inline-flex cursor-pointer items-center gap-1.5 uppercase transition-colors duration-200 ${
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
                      const browserEnabled = account.browser === 'Да';
                      const hasErrors = Number(account.errors) > 0;

                      return (
                        <tr
                          key={account.id}
                          className="group cursor-pointer text-sm"
                          onClick={() => setSelectedAccountIds([account.id])}
                        >
                          <td
                            className={`${rowCellClassName} w-16 rounded-l-2xl`}
                            onClick={(event) => event.stopPropagation()}
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
                            <div className="flex items-center gap-3 text-md font-medium text-text">
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
    </div>
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
      className={`inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl px-3.5 text-sm font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-45 ${
        disabled
          ? disabledBulkActionButtonClassNames[tone]
          : bulkActionButtonClassNames[tone]
      } ${className ?? ''}`}
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {icon}
      {children}
    </button>
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
