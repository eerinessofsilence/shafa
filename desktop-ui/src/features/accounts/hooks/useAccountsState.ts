import { useCallback, useState } from 'react';

import {
  createAccount as createAccountRequest,
  deleteAccount as deleteAccountRequest,
  listAccounts,
  startAccount as startAccountRequest,
  stopAccount as stopAccountRequest,
  updateAccount as updateAccountRequest,
} from '../../../api/accounts';
import type { AccountRow } from '../../../types';
import type { AccountBulkActionId, AccountDraft } from '../types';
import {
  createAccountCreatePayload,
  createAccountUpdatePayload,
  formatAccountCount,
  formatApiError,
  mapApiAccountToRow,
  normalizeTelegramLinks,
} from '../utils';

export function useAccountsState() {
  const [accounts, setAccounts] = useState<AccountRow[]>([]);
  const [isAccountsLoading, setIsAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState('');
  const [isAccountMutationPending, setIsAccountMutationPending] =
    useState(false);

  const loadAccounts = useCallback(async () => {
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
  }, []);

  const handleCreateAccount = useCallback(
    async (draft: AccountDraft) => {
      setIsAccountMutationPending(true);

      try {
        await createAccountRequest(createAccountCreatePayload(draft));
        await loadAccounts();
      } finally {
        setIsAccountMutationPending(false);
      }
    },
    [loadAccounts],
  );

  const handleSaveAccount = useCallback(
    async (accountId: string, draft: AccountDraft) => {
      setIsAccountMutationPending(true);

      try {
        await updateAccountRequest(accountId, createAccountUpdatePayload(draft));
        await loadAccounts();
      } finally {
        setIsAccountMutationPending(false);
      }
    },
    [loadAccounts],
  );

  const handleSyncAccountChannels = useCallback(
    async (accountId: string, channelLinks: string[]) => {
      setIsAccountMutationPending(true);

      try {
        await updateAccountRequest(accountId, {
          channel_links: normalizeTelegramLinks(channelLinks),
        });
        await loadAccounts();
      } finally {
        setIsAccountMutationPending(false);
      }
    },
    [loadAccounts],
  );

  const handleBulkAccountAction = useCallback(
    async (action: AccountBulkActionId, accountIds: string[]) => {
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
        const failureCount = results.length - successCount;

        await loadAccounts();

        if (successCount === 0) {
          return `Не удалось выполнить действие для ${formatAccountCount(failureCount)}.`;
        }

        const actionVerb =
          action === 'open'
            ? 'Открыто'
            : action === 'close'
              ? 'Остановлено'
              : 'Удалено';
        const successMessage = `${actionVerb} ${formatAccountCount(successCount)}.`;

        return failureCount > 0
          ? `${successMessage} Ошибок: ${failureCount}.`
          : successMessage;
      } finally {
        setIsAccountMutationPending(false);
      }
    },
    [loadAccounts],
  );

  return {
    accounts,
    accountsError,
    isAccountMutationPending,
    isAccountsLoading,
    loadAccounts,
    onBulkAction: handleBulkAccountAction,
    onCreateAccount: handleCreateAccount,
    onSyncAccountChannels: handleSyncAccountChannels,
    onUpdateAccount: handleSaveAccount,
  };
}
