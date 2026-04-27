import {
  createAccount as createAccountRequest,
  deleteAccount as deleteAccountRequest,
  listAccounts,
  startAccount as startAccountRequest,
  stopAccount as stopAccountRequest,
  updateAccount as updateAccountRequest,
} from './api/accounts';
import {
  AccountBulkActionId,
  AccountDraft,
  AppPreferences,
  AppSidebar,
  TablePageSize,
  ThemeMode,
  accountsPaginationStorageKey,
  createAccountCreatePayload,
  createAccountUpdatePayload,
  createDefaultAppPreferences,
  formatAccountCount,
  formatApiError,
  getInitialActivePage,
  joinUniqueMessages,
  loadStoredAppPreferences,
  loadStoredTablePagination,
  loadStoredThemeMode,
  logsPaginationStorageKey,
  mapApiAccountToRow,
  normalizeTelegramLinks,
  settingsPageClassName,
  settingsStorageKey,
  themeStorageKey,
} from './app/shared';
import AccountsPage from './pages/AccountsPage';
import DashboardPage from './pages/DashboardPage';
import LogsPage from './pages/LogsPage';
import SettingsPage from './pages/SettingsPage';
import type { AccountRow, PageId } from './types';
import { useCallback, useEffect, useState } from 'react';

function App() {
  const [activePage, setActivePage] = useState<PageId>(getInitialActivePage);
  const [themeMode, setThemeMode] = useState<ThemeMode>(() =>
    loadStoredThemeMode(),
  );
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [isAccountsLoading, setIsAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState('');
  const [isAccountMutationPending, setIsAccountMutationPending] =
    useState(false);
  const [appPreferences, setAppPreferences] = useState<AppPreferences>(() =>
    loadStoredAppPreferences(),
  );
  const [settingsDraft, setSettingsDraft] = useState<AppPreferences>(() =>
    loadStoredAppPreferences(),
  );
  const [selectedAccountId, setSelectedAccountId] = useState('');
  const [accountsPagination, setAccountsPagination] = useState(() =>
    loadStoredTablePagination(accountsPaginationStorageKey),
  );
  const [logsPagination, setLogsPagination] = useState(() =>
    loadStoredTablePagination(logsPaginationStorageKey),
  );

  useEffect(() => {
    if (
      selectedAccountId &&
      !accounts.some((account) => account.id === selectedAccountId)
    ) {
      setSelectedAccountId('');
    }
  }, [accounts, selectedAccountId]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        settingsStorageKey,
        JSON.stringify(appPreferences),
      );
    } catch {
      return;
    }
  }, [appPreferences]);

  useEffect(() => {
    setSettingsDraft(appPreferences);
  }, [appPreferences]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        accountsPaginationStorageKey,
        JSON.stringify(accountsPagination),
      );
    } catch {
      return;
    }
  }, [accountsPagination]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        logsPaginationStorageKey,
        JSON.stringify(logsPagination),
      );
    } catch {
      return;
    }
  }, [logsPagination]);

  const handleAccountsCurrentPageChange = useCallback((page: number) => {
    setAccountsPagination((currentPagination) =>
      currentPagination.currentPage === page
        ? currentPagination
        : {
            ...currentPagination,
            currentPage: page,
          },
    );
  }, []);

  const handleAccountsItemsPerPageChange = useCallback(
    (value: TablePageSize) => {
      setAccountsPagination((currentPagination) =>
        currentPagination.itemsPerPage === value
          ? currentPagination
          : {
              ...currentPagination,
              itemsPerPage: value,
            },
      );
    },
    [],
  );

  const handleLogsCurrentPageChange = useCallback((page: number) => {
    setLogsPagination((currentPagination) =>
      currentPagination.currentPage === page
        ? currentPagination
        : {
            ...currentPagination,
            currentPage: page,
          },
    );
  }, []);

  const handleLogsItemsPerPageChange = useCallback((value: TablePageSize) => {
    setLogsPagination((currentPagination) =>
      currentPagination.itemsPerPage === value
        ? currentPagination
        : {
            ...currentPagination,
            itemsPerPage: value,
          },
    );
  }, []);

  useEffect(() => {
    const rootElement = document.documentElement;
    rootElement.dataset.theme = themeMode;

    try {
      window.localStorage.setItem(themeStorageKey, themeMode);
    } catch {
      return;
    }
  }, [themeMode]);

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
    const intervalId = window.setInterval(
      () => void loadAccounts(),
      appPreferences.autoRefreshSeconds * 1000,
    );

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activePage, appPreferences.autoRefreshSeconds]);

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

  const handleUpdatePreference = (
    field: keyof AppPreferences,
    value: string | number | boolean,
  ) => {
    setSettingsDraft(
      (currentPreferences) =>
        ({
          ...currentPreferences,
          [field]: value,
        }) as AppPreferences,
    );
  };

  const handleSavePreferences = () => {
    setAppPreferences(settingsDraft);
  };

  const handleResetPreferences = () => {
    const nextDefaults = createDefaultAppPreferences();
    setAppPreferences(nextDefaults);
    setSettingsDraft(nextDefaults);
  };

  const handleToggleTheme = () => {
    setThemeMode((currentTheme) =>
      currentTheme === 'dark' ? 'light' : 'dark',
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
      const failedResults = results.filter(
        (result): result is PromiseRejectedResult =>
          result.status === 'rejected',
      );
      const failureCount = results.length - successCount;
      const failureMessage = joinUniqueMessages(
        failedResults.map((result) =>
          formatApiError(
            result.reason,
            'Не удалось выполнить действие над аккаунтом.',
          ),
        ),
      );

      await loadAccounts();

      if (action === 'open' && successCount > 0 && accountIds[0]) {
        setSelectedAccountId(accountIds[0]);
      }

      if (successCount === 0) {
        return (
          failureMessage ||
          `Не удалось выполнить действие для ${formatAccountCount(failureCount)}.`
        );
      }

      const actionVerb =
        action === 'open'
          ? 'Открыто'
          : action === 'close'
            ? 'Остановлено'
            : 'Удалено';
      const successMessage = `${actionVerb} ${formatAccountCount(successCount)}.`;

      return failureCount > 0
        ? joinUniqueMessages([
            `${successMessage} Ошибок: ${failureCount}.`,
            failureMessage,
          ])
        : successMessage;
    } finally {
      setIsAccountMutationPending(false);
    }
  };

  if (activePage === 'settings') {
    const hasUnsavedChanges =
      JSON.stringify(settingsDraft) !== JSON.stringify(appPreferences);

    return (
      <SettingsPage
        hasUnsavedChanges={hasUnsavedChanges}
        onChangePreference={handleUpdatePreference}
        onNavigateToPage={setActivePage}
        onResetPreferences={handleResetPreferences}
        onSavePreferences={handleSavePreferences}
        onToggleTheme={handleToggleTheme}
        preferences={settingsDraft}
        themeMode={themeMode}
      />
    );
  }

  return (
    <div className={settingsPageClassName}>
      <div className="grid min-h-screen xl:grid-cols-[280px_minmax(0,1fr)]">
        <AppSidebar
          activePage={activePage}
          onNavigate={setActivePage}
          onToggleTheme={handleToggleTheme}
          themeMode={themeMode}
        />

        <main className="min-w-0 bg-background">
          <section className="min-h-screen overflow-auto">
            <div className="mx-auto max-w-265 px-7.5 py-10">
              {activePage === 'dashboard' && <DashboardPage />}
              {activePage === 'accounts' && (
                <AccountsPage
                  accounts={accounts}
                  currentPage={accountsPagination.currentPage}
                  isLoading={isAccountsLoading}
                  isMutationPending={isAccountMutationPending}
                  itemsPerPage={accountsPagination.itemsPerPage}
                  loadError={accountsError}
                  onBulkAction={handleBulkAccountAction}
                  onCreateAccount={handleCreateAccount}
                  onCurrentPageChange={handleAccountsCurrentPageChange}
                  onItemsPerPageChange={handleAccountsItemsPerPageChange}
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
                  currentPage={logsPagination.currentPage}
                  isAccountsLoading={isAccountsLoading}
                  itemsPerPage={logsPagination.itemsPerPage}
                  onCurrentPageChange={handleLogsCurrentPageChange}
                  onItemsPerPageChange={handleLogsItemsPerPageChange}
                  onReloadAccounts={loadAccounts}
                />
              )}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

export default App;
