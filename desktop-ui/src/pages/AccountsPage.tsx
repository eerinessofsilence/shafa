import {
  getAccount as getAccountRequest,
  listAccountLogs,
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
import {
  accountControlClassName,
  accountDraftInitialState,
  accountTableHeaders,
  ActionButton,
  AccountBulkActionId,
  AccountDraft,
  AccountEditableField,
  AccountStatusBadge,
  AccountSortDirection,
  AccountSortField,
  BulkActionButton,
  clampTimerMinutes,
  defaultChannelTemplateName,
  defaultTimerMinutes,
  extractAccountExtraText,
  extractTimerMinutes,
  fieldLabelClassName,
  formatAccountCount,
  formatAccountDateTime,
  formatAccountTextValue,
  formatApiError,
  formatDashboardRunTimestamp,
  formatTimerLabel,
  getAccountDraftFromRow,
  getAccountSortValue,
  getAccountStatusMeta,
  getPrimaryChannelTemplate,
  getShafaStatusMeta,
  getTelegramStepMeta,
  isAccountDraftValid,
  isLikelyEmail,
  isRecord,
  isTimerValueValid,
  joinUniqueMessages,
  mapLinksToTelegramChannels,
  maximumTimerMinutes,
  minimumTimerMinutes,
  normalizeTelegramHandle,
  normalizeTelegramLinks,
  pageTitleClassName,
  parseShafaImportInput,
  sectionTitleClassName,
  SelectionCheckbox,
  TablePaginationFooter,
  TablePageSize,
  telegramDraftInitialState,
  TelegramChannelCard,
  TelegramChannelDraft,
  ToggleSwitch,
} from '../app/shared';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { StatusPill } from '../components/StatusPill';
import type {
  AccountRow,
  ApiAccountRead,
  ApiShafaAuthStatus,
  ApiTelegramAuthStatus,
  StatusTone,
  TelegramChannel,
} from '../types';
import { cardTitleClassName, cx, getButtonClassName } from '../ui';
import {
  Check,
  ChevronDown,
  Clock3,
  EllipsisVertical,
  FileJson,
  FolderOpen,
  Link2,
  LoaderCircle,
  LockKeyhole,
  LogIn,
  LogOut,
  Mail,
  PencilLine,
  Phone,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  Upload,
  User,
  X,
} from 'lucide-react';
import {
  type ChangeEvent,
  type ReactNode,
  useEffect,
  useRef,
  useState,
} from 'react';

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
          const accountIdsToDelete = deleteDialogAccounts.map(
            (account) => account.id,
          );
          if (accountIdsToDelete.length === 0) {
            return;
          }

          const message = await onBulkAction('delete', accountIdsToDelete);
          if (message) {
            setBulkFeedback(message);
          }

          const deletedIdSet = new Set(accountIdsToDelete);
          setSelectedAccountIds((currentSelection) =>
            currentSelection.filter(
              (accountId) => !deletedIdSet.has(accountId),
            ),
          );
          setDeleteTargetAccountId(null);
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
      className={cx('relative', isOpen && 'z-40')}
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
        <div className="absolute top-full right-0 z-50 pt-2">
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
                        <p className={detailLabelClassName}>Email Shafa</p>
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
            `channel-templates` и синхронизируются с рабочим списком аккаунта.
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
      setFeedback('Сессия Shafa сохранена. Аккаунт подключён.');
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
          `Не удалось импортировать cookie из файла ${file.name}.`,
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
          'Не удалось запустить вход в Shafa через браузер.',
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
                  cookie: {status?.cookies_count ?? 0}
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
      ? 'Импортировать сессию'
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
          'Не удалось импортировать Telegram-сессию из другого аккаунта.',
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
                            {hasTelegramSession ? 'Есть сессия' : 'Нет сессии'}
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
                className: 'h-[42px]',
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
                  className: 'h-[42px]',
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
                  className: 'h-[42px]',
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

interface ImportedChannelTemplate {
  links: string[];
  name: string;
}

function getTemplateLinksValue(
  value: Record<string, unknown>,
): unknown[] | null {
  if (Array.isArray(value.links)) {
    return value.links;
  }

  if (Array.isArray(value.channel_links)) {
    return value.channel_links;
  }

  return null;
}

function isTemplatePayloadRecord(
  value: unknown,
): value is Record<string, unknown> {
  return isRecord(value) && getTemplateLinksValue(value) !== null;
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

function parseImportedTemplateEntry(
  value: unknown,
  options?: {
    fallbackName?: string;
    requireName?: boolean;
  },
): ImportedChannelTemplate {
  const { fallbackName = defaultChannelTemplateName, requireName = false } =
    options ?? {};
  const explicitName =
    isRecord(value) && typeof value.name === 'string' ? value.name.trim() : '';

  if (Array.isArray(value)) {
    const links = normalizeTelegramLinks(
      value.map((item) => String(item ?? '').trim()).filter(Boolean),
    );

    if (links.length === 0) {
      throw new Error(
        'JSON шаблона должен содержать хотя бы одну ссылку Telegram.',
      );
    }

    return {
      links,
      name: fallbackName,
    };
  }

  if (!isRecord(value)) {
    throw new Error(
      'Ожидается массив шаблонов, объект шаблона или массив ссылок Telegram.',
    );
  }

  if (!getTemplateLinksValue(value)) {
    const nestedTemplateEntries = Object.entries(value).filter(
      (entry): entry is [string, Record<string, unknown>] =>
        isTemplatePayloadRecord(entry[1]),
    );

    if (nestedTemplateEntries.length === 1) {
      const [nestedName, nestedPayload] = nestedTemplateEntries[0];

      return parseImportedTemplateEntry(
        {
          ...nestedPayload,
          name:
            typeof nestedPayload.name === 'string' && nestedPayload.name.trim()
              ? nestedPayload.name
              : nestedName,
        },
        {
          fallbackName: nestedName,
          requireName: true,
        },
      );
    }
  }

  const resolvedName = explicitName || fallbackName;

  if (requireName && !explicitName) {
    throw new Error('У каждого шаблона в JSON должно быть поле `name`.');
  }

  const rawLinks = getTemplateLinksValue(value);

  if (!rawLinks) {
    throw new Error(
      'У шаблона в JSON должно быть поле `links` со списком ссылок.',
    );
  }

  const links = normalizeTelegramLinks(
    rawLinks.map((item) => String(item ?? '').trim()).filter(Boolean),
  );

  if (links.length === 0) {
    throw new Error(
      `Шаблон \`${resolvedName}\` должен содержать хотя бы одну ссылку Telegram.`,
    );
  }

  return {
    links,
    name: resolvedName,
  };
}

function parseTelegramChannelTemplatesImport(
  value: string,
  fallbackName = defaultChannelTemplateName,
): ImportedChannelTemplate[] {
  const parsed = JSON.parse(value) as unknown;

  if (
    Array.isArray(parsed) &&
    parsed.every((item) => typeof item === 'string' || typeof item === 'number')
  ) {
    return [parseImportedTemplateEntry(parsed, { fallbackName })];
  }

  if (Array.isArray(parsed)) {
    const importedTemplates = parsed.map((item) =>
      parseImportedTemplateEntry(item, { requireName: true }),
    );

    if (importedTemplates.length === 0) {
      throw new Error('JSON не содержит шаблонов для импорта.');
    }

    return [
      ...new Map(importedTemplates.map((item) => [item.name, item])).values(),
    ];
  }

  if (isRecord(parsed)) {
    const templateList = Array.isArray(parsed.templates)
      ? parsed.templates
      : Array.isArray(parsed.channel_templates)
        ? parsed.channel_templates
        : null;

    if (templateList) {
      const importedTemplates = templateList.map((item) =>
        parseImportedTemplateEntry(item, { requireName: true }),
      );

      if (importedTemplates.length === 0) {
        throw new Error('JSON не содержит шаблонов для импорта.');
      }

      return [
        ...new Map(importedTemplates.map((item) => [item.name, item])).values(),
      ];
    }

    if (!getTemplateLinksValue(parsed)) {
      const namedTemplateEntries = Object.entries(parsed).filter(
        (entry): entry is [string, Record<string, unknown>] =>
          isTemplatePayloadRecord(entry[1]),
      );

      if (namedTemplateEntries.length > 0) {
        const importedTemplates = namedTemplateEntries.map(
          ([templateName, templatePayload]) =>
            parseImportedTemplateEntry(
              {
                ...templatePayload,
                name:
                  typeof templatePayload.name === 'string' &&
                  templatePayload.name.trim()
                    ? templatePayload.name
                    : templateName,
              },
              {
                fallbackName: templateName,
                requireName: true,
              },
            ),
        );

        return [
          ...new Map(
            importedTemplates.map((item) => [item.name, item]),
          ).values(),
        ];
      }
    }

    return [parseImportedTemplateEntry(parsed, { fallbackName })];
  }

  throw new Error(
    'Ожидается JSON шаблона Telegram-каналов, массив шаблонов или массив ссылок.',
  );
}

function formatTelegramChannelSyncError(error: unknown, fallback: string) {
  const message = formatApiError(error, fallback);

  if (
    message.includes('Сессия Telegram не найдена для аккаунта') &&
    message.includes('Сначала подключи Telegram')
  ) {
    return 'Сначала подключите Telegram для этого аккаунта в блоке «Telegram авторизация», а потом повторите сохранение или импорт каналов.';
  }

  if (
    message.includes('Сессия Telegram для аккаунта') &&
    message.includes('не авторизована')
  ) {
    return 'Telegram для этого аккаунта уже сохранён, но сессия больше не авторизована. Переподключите Telegram и повторите попытку.';
  }

  if (message.includes('Telegram API-данные не настроены для аккаунта')) {
    return 'На сервере не настроены Telegram API ID и API hash, поэтому проверить каналы сейчас нельзя.';
  }

  return message;
}

function TelegramChannelsPanel({
  account,
  isSubmittingAccount,
  onSyncAccountChannels,
}: TelegramChannelsPanelProps) {
  const templatesInputRef = useRef<HTMLInputElement | null>(null);
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
  const existingTemplateNames = new Set(
    accountChannelTemplates.map((template) => template.name),
  );
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
        formatTelegramChannelSyncError(
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

  const importTemplateFile = async (file: File) => {
    setIsSubmitting(true);
    setError('');
    setFeedback('');

    try {
      const importedTemplates = parseTelegramChannelTemplatesImport(
        await file.text(),
        activeTemplateName,
      );

      for (const template of importedTemplates) {
        if (existingTemplateNames.has(template.name)) {
          await updateChannelTemplateRequest(account.id, template.name, {
            links: template.links,
          });
        } else {
          await createChannelTemplateRequest(account.id, {
            links: template.links,
            name: template.name,
          });
        }
      }

      const importedTemplateByName = new Map(
        importedTemplates.map((template) => [template.name, template.links]),
      );
      const runtimeLinks =
        importedTemplateByName.get(activeTemplateName) ??
        importedTemplateByName.get(defaultChannelTemplateName) ??
        activeTemplate?.links ??
        importedTemplates[0]?.links ??
        channelHandles;

      await onSyncAccountChannels(account.id, runtimeLinks);
      setIsComposerOpen(false);
      resetEditing();
      setFeedback(
        importedTemplates.length === 1
          ? `JSON \`${file.name}\` импортирован. Шаблон синхронизирован с аккаунтом.`
          : `JSON \`${file.name}\` импортирован. Добавлено или обновлено шаблонов: ${importedTemplates.length}.`,
      );
    } catch (nextError) {
      setError(
        formatTelegramChannelSyncError(
          nextError,
          `Не удалось импортировать шаблоны Telegram-каналов из файла ${file.name}.`,
        ),
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTemplateFileChange = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    try {
      await importTemplateFile(file);
    } finally {
      event.target.value = '';
    }
  };

  return (
    <section className="space-y-4 border-t border-border/20 pt-2">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h3 className={sectionTitleClassName}>Telegram-каналы</h3>

        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={templatesInputRef}
            accept=".json,application/json"
            className="hidden"
            type="file"
            onChange={(event) => void handleTemplateFileChange(event)}
          />
          <ActionButton
            disabled={isActionDisabled}
            icon={<FileJson className="h-4 w-4" />}
            size="sm"
            onClick={() => templatesInputRef.current?.click()}
          >
            Загрузить JSON
          </ActionButton>
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
      </div>

      {hasAdditionalTemplates ? (
        <div className="rounded-2xl border border-warning/15 bg-warning/8 px-4 py-3 text-sm text-text">
          Интерфейс редактирует шаблон `{activeTemplateName}`. Остальные шаблоны
          этого аккаунта пока доступны только через API.
        </div>
      ) : null}

      {!activeTemplate && channels.length > 0 ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/65 px-4 py-3 text-sm text-text-muted">
          Для этого аккаунта уже есть рабочие `channel_links`. При первом
          сохранении интерфейс создаст шаблон `{defaultChannelTemplateName}`.
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
              проверена через Telegram API и сохранена в аккаунте.
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

export default AccountsPage;
