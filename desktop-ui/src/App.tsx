import { useEffect, useState } from 'react';

import { AppSidebar } from './components/AppSidebar';
import { settingToggles } from './data/mockData';
import { useAccountsState } from './features/accounts/hooks/useAccountsState';
import { AccountsPage } from './pages/AccountsPage';
import { DashboardPage } from './pages/DashboardPage';
import { SettingsPage } from './pages/SettingsPage';
import { StatsPage } from './pages/StatsPage';
import type { PageId, SettingToggle } from './types';

function App() {
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [parsingToggles, setParsingToggles] =
    useState<SettingToggle[]>(settingToggles);
  const accountsState = useAccountsState();
  const { loadAccounts } = accountsState;

  useEffect(() => {
    if (activePage !== 'accounts') {
      return;
    }

    void loadAccounts();
  }, [activePage, loadAccounts]);

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
        <AppSidebar activePage={activePage} onNavigate={setActivePage} />

        <main className="flex min-w-0 flex-col gap-3.5">
          <section className="min-h-0 overflow-auto px-5 py-15">
            {activePage === 'dashboard' && <DashboardPage />}
            {activePage === 'accounts' && (
              <AccountsPage
                accounts={accountsState.accounts}
                isLoading={accountsState.isAccountsLoading}
                isMutationPending={accountsState.isAccountMutationPending}
                loadError={accountsState.accountsError}
                onBulkAction={accountsState.onBulkAction}
                onCreateAccount={accountsState.onCreateAccount}
                onReload={accountsState.loadAccounts}
                onSyncAccountChannels={accountsState.onSyncAccountChannels}
                onUpdateAccount={accountsState.onUpdateAccount}
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

export default App;
