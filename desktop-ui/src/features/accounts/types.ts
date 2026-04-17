import type { AccountRow, TelegramChannel } from '../../types';

export type TelegramChannelDraft = Pick<TelegramChannel, 'handle'>;
export type AccountEditableField = 'name' | 'path' | 'browser' | 'timer';
export type AccountDraft = Pick<AccountRow, AccountEditableField>;
export type AccountSortField =
  | 'name'
  | 'browser'
  | 'timer'
  | 'channels'
  | 'status'
  | 'errors';
export type AccountSortDirection = 'asc' | 'desc';
export type AccountBulkActionId = 'open' | 'close' | 'delete';
