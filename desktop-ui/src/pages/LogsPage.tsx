import { buildAccountLogsWebSocketUrl, listAccountLogs } from '../api/accounts';
import {
  AccountLogEntry,
  allLogAccountsValue,
  allLogLevelsValue,
  formatAccountLogTimestamp,
  getAccountLogEventSurfaceClassName,
  getAccountLogLevelBadgeClassName,
  getAccountLogMessageClassName,
  logFilterSelectClassName,
  logLevelOptions,
  logTableDesktopGridClassName,
  mapApiAccountLogEntryToEntry,
  mergeAndSortAccountLogEntries,
  resolveAccountLogError,
  TablePaginationFooter,
  TablePageSize,
} from '../app/shared';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import type { AccountRow, ApiAccountLogEntryRead } from '../types';
import { cardTitleClassName, cx, getButtonClassName } from '../ui';
import { ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

interface LogsPageProps {
  accounts: AccountRow[];
  accountsError: string;
  currentPage: number;
  isAccountsLoading: boolean;
  itemsPerPage: TablePageSize;
  onCurrentPageChange: (page: number) => void;
  onItemsPerPageChange: (value: TablePageSize) => void;
  onReloadAccounts: () => Promise<void>;
}

function LogsPage({
  accounts,
  accountsError,
  currentPage,
  isAccountsLoading,
  itemsPerPage,
  onCurrentPageChange,
  onItemsPerPageChange,
  onReloadAccounts,
}: LogsPageProps) {
  const [selectedLogAccountId, setSelectedLogAccountId] =
    useState(allLogAccountsValue);
  const [selectedLogLevel, setSelectedLogLevel] =
    useState<string>(allLogLevelsValue);
  const [logEntries, setLogEntries] = useState<AccountLogEntry[]>([]);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState('');
  const hasInitializedLogFilters = useRef(false);
  const accountSignature = accounts
    .map((account) => `${account.id}:${account.name}`)
    .join('|');
  const logTotalPages = Math.max(
    1,
    Math.ceil(logEntries.length / itemsPerPage),
  );
  const paginatedLogEntries = logEntries.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage,
  );
  const visibleLogRangeStart =
    paginatedLogEntries.length === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const visibleLogRangeEnd =
    (currentPage - 1) * itemsPerPage + paginatedLogEntries.length;

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
    if (accounts.length === 0) {
      setIsLogsLoading(false);
      setLogEntries([]);
      setLogsError('');
      return;
    }

    if (isAccountsLoading) {
      return;
    }

    let isCancelled = false;
    const activeAccounts =
      selectedLogAccountId === allLogAccountsValue
        ? accounts
        : accounts.filter((account) => account.id === selectedLogAccountId);
    const requestLimit =
      selectedLogAccountId === allLogAccountsValue
        ? Math.max(80, itemsPerPage * 4)
        : Math.max(160, itemsPerPage * 4);

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
    itemsPerPage,
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

  useEffect(() => {
    if (!hasInitializedLogFilters.current) {
      hasInitializedLogFilters.current = true;
      return;
    }

    onCurrentPageChange(1);
  }, [onCurrentPageChange, selectedLogAccountId, selectedLogLevel]);

  useEffect(() => {
    if (currentPage <= logTotalPages) {
      return;
    }

    onCurrentPageChange(logTotalPages);
  }, [currentPage, logTotalPages, onCurrentPageChange]);

  return (
    <div className="space-y-4">
      <PageHeader title="Логи" />

      <div className="flex flex-col gap-6">
        <Panel
          title="Лента событий"
          actions={
            <div className="flex w-full flex-wrap items-center gap-4 sm:w-auto">
              <div className="relative w-full sm:w-auto">
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

              <div className="relative w-full sm:w-auto">
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

            {isAccountsLoading && accounts.length === 0 ? (
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
                    ? 'Получаем последние записи из API.'
                    : 'Для выбранного фильтра пока нет записей.'}
                </p>
              </div>
            ) : null}

            {logEntries.length > 0 ? (
              <div className="overflow-hidden rounded-2xl border border-border/25 bg-secondary/75">
                <div
                  className={cx(
                    'hidden gap-4 border-b border-border/25 px-6 py-4 text-xs font-semibold uppercase tracking-widest text-text-muted/75 xl:grid',
                    logTableDesktopGridClassName,
                  )}
                >
                  <span>Дата и время</span>
                  <span>Аккаунт</span>
                  <span>Уровень</span>
                  <span>Событие</span>
                </div>

                <div className="divide-y divide-border/25">
                  {paginatedLogEntries.map((entry) => (
                    <article
                      key={entry.id}
                      className={cx(
                        'grid gap-5 px-5 py-5 xl:items-center xl:gap-4 xl:px-6',
                        logTableDesktopGridClassName,
                      )}
                    >
                      <div className="space-y-1">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Дата и время
                        </span>
                        <span className="font-medium text-sm tracking-tight text-text-muted">
                          {formatAccountLogTimestamp(entry.timestamp)}
                        </span>
                      </div>

                      <div className="min-w-0 space-y-2">
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

                      <div className="space-y-2 xl:justify-self-start">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Уровень
                        </span>
                        <span
                          className={`inline-flex items-center justify-center rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-widest ${getAccountLogLevelBadgeClassName(entry)}`}
                        >
                          {entry.level}
                        </span>
                      </div>

                      <div className="min-w-0 space-y-2">
                        <span className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-muted/70 xl:hidden">
                          Событие
                        </span>
                        <div
                          className={cx(
                            'min-w-0',
                            getAccountLogEventSurfaceClassName(entry),
                          )}
                        >
                          <p
                            className={cx(
                              'min-w-0',
                              getAccountLogMessageClassName(entry),
                            )}
                          >
                            {entry.message}
                          </p>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>

                <TablePaginationFooter
                  currentPage={currentPage}
                  itemsPerPage={itemsPerPage}
                  itemCountLabel="логов"
                  nextPageAriaLabel="Следующая страница логов"
                  previousPageAriaLabel="Предыдущая страница логов"
                  totalItems={logEntries.length}
                  totalPages={logTotalPages}
                  visibleRangeEnd={visibleLogRangeEnd}
                  visibleRangeStart={visibleLogRangeStart}
                  onItemsPerPageChange={(value) => {
                    onItemsPerPageChange(value);
                    onCurrentPageChange(1);
                  }}
                  onPageChange={onCurrentPageChange}
                />
              </div>
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}

export default LogsPage;
