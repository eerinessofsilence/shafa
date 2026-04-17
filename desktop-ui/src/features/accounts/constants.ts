import type { AccountDraft, AccountSortField, TelegramChannelDraft } from './types';

export const browserOptions = ['Да', 'Нет'];
export const timerOptions = Array.from(
  { length: 60 },
  (_, index) => `${index + 1} мин`,
);

export const accountControlClassName =
  'h-12 w-full rounded-xl border border-border/25 bg-secondary px-3 text-text outline-none transition focus:border-info/50 focus:ring-2 focus:ring-info/25';
export const accountSelectButtonClassName =
  'flex h-12 w-full cursor-pointer items-center justify-between gap-4 rounded-xl border border-border/25 bg-secondary px-3 text-left text-text outline-none transition hover:border-border/50 focus:border-info/50 focus:ring-2 focus:ring-info/25';

export const telegramDraftInitialState: TelegramChannelDraft = {
  handle: '',
};

export const accountTableHeaders: Array<{
  id: AccountSortField;
  label: string;
}> = [
  { id: 'name', label: 'Имя' },
  { id: 'browser', label: 'Браузер' },
  { id: 'timer', label: 'Таймер' },
  { id: 'channels', label: 'Каналы' },
  { id: 'status', label: 'Статус' },
  { id: 'errors', label: 'Ошибки' },
];

export const defaultAccountProjectPath =
  window.desktopShell?.cwd?.trim() ||
  '/Users/eeri/coding/python/projects/scripts/shafa';
export const defaultChannelTemplateName = 'default';

export const accountDraftInitialState: AccountDraft = {
  name: '',
  path: defaultAccountProjectPath,
  browser: browserOptions[1] ?? 'Нет',
  timer: timerOptions[4] ?? '5 мин',
};

export const accountPageSizeOptions = [5, 10, 20, 50] as const;
