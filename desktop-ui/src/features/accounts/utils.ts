import type {
  AccountRow,
  ApiAccountCreate,
  ApiAccountRead,
  ApiAccountUpdate,
  ApiChannelTemplateSummary,
  ApiShafaAuthStatus,
  ApiShafaStorageStateRequest,
  ApiTelegramAuthStatus,
  StatusTone,
  TelegramChannel,
} from '../../types';
import {
  defaultAccountProjectPath,
  defaultChannelTemplateName,
} from './constants';
import type { AccountDraft, AccountSortField } from './types';

export function formatTimerLabel(minutes: number) {
  return `${minutes} мин`;
}

export function parseTimerLabel(value: string) {
  const parsedValue = Number.parseInt(value, 10);

  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return 5;
  }

  return parsedValue;
}

export function getAccountStatusMeta(
  status: ApiAccountRead['status'],
): Pick<AccountRow, 'statusLabel' | 'statusTone'> {
  return status === 'started'
    ? { statusLabel: 'started', statusTone: 'success' }
    : { statusLabel: 'stopped', statusTone: 'neutral' };
}

export function getPrimaryChannelTemplate(
  templates: ApiChannelTemplateSummary[],
): ApiChannelTemplateSummary | null {
  return (
    templates.find(
      (template) => template.name === defaultChannelTemplateName,
    ) ??
    templates[0] ??
    null
  );
}

export function mapLinksToTelegramChannels(
  accountId: string,
  links: string[],
  template: ApiChannelTemplateSummary | null,
): TelegramChannel[] {
  const resolvedChannels = template?.resolved_channels ?? [];

  return links.map((link, index) => {
    const resolvedChannel = resolvedChannels[index];

    return {
      id: `${template?.id ?? accountId}-channel-${index}`,
      title: resolvedChannel?.title || formatChannelTitle(link),
      handle: link,
      channelId: resolvedChannel?.channel_id,
      alias: resolvedChannel?.alias,
    };
  });
}

export function mapApiAccountToRow(account: ApiAccountRead): AccountRow {
  const { statusLabel, statusTone } = getAccountStatusMeta(account.status);
  const primaryChannelTemplate = getPrimaryChannelTemplate(
    account.channel_templates,
  );
  const channelLinks = primaryChannelTemplate?.links.length
    ? primaryChannelTemplate.links
    : account.channel_links;

  return {
    id: account.id,
    name: account.name,
    path: account.path,
    branch: account.branch,
    browser: account.open_browser ? 'Да' : 'Нет',
    timer: formatTimerLabel(account.timer_minutes),
    errors: String(account.errors),
    statusLabel,
    statusTone,
    shafaSessionExists: account.shafa_session_exists,
    telegramSessionExists: account.telegram_session_exists,
    telegramChannels: mapLinksToTelegramChannels(
      account.id,
      channelLinks,
      primaryChannelTemplate,
    ),
    channelTemplates: account.channel_templates,
  };
}

export function createAccountCreatePayload(draft: AccountDraft): ApiAccountCreate {
  return {
    name: draft.name.trim(),
    phone: '',
    path: draft.path.trim() || defaultAccountProjectPath,
    open_browser: draft.browser === 'Да',
    timer_minutes: parseTimerLabel(draft.timer),
    channel_links: [],
  };
}

export function createAccountUpdatePayload(draft: AccountDraft): ApiAccountUpdate {
  return {
    name: draft.name.trim(),
    path: draft.path.trim(),
    open_browser: draft.browser === 'Да',
    timer_minutes: parseTimerLabel(draft.timer),
  };
}

export function formatApiError(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseShafaImportInput(
  value: string,
): ApiShafaStorageStateRequest {
  const parsed = JSON.parse(value) as unknown;

  if (Array.isArray(parsed)) {
    return { cookies: parsed };
  }

  if (isRecord(parsed)) {
    if (isRecord(parsed.storage_state)) {
      return { storage_state: parsed.storage_state };
    }

    if (Array.isArray(parsed.cookies)) {
      return { storage_state: parsed };
    }
  }

  throw new Error(
    'Ожидается JSON storage state Playwright или массив cookies для Shafa.',
  );
}

export function getTelegramStepMeta(status: ApiTelegramAuthStatus | null): {
  label: string;
  tone: StatusTone;
} {
  if (!status) {
    return { label: 'загрузка', tone: 'neutral' };
  }

  if (status.connected) {
    return { label: 'подключен', tone: 'success' };
  }

  switch (status.current_step) {
    case 'WAIT_CODE':
      return { label: 'ждёт код', tone: 'info' };
    case 'WAIT_PASSWORD':
      return { label: 'ждёт пароль', tone: 'warning' };
    case 'FAILED':
      return { label: 'ошибка', tone: 'danger' };
    case 'WAIT_PHONE':
      return { label: 'код запрошен', tone: 'info' };
    case 'INIT':
      return { label: 'не начат', tone: 'neutral' };
    case 'SUCCESS':
      return { label: 'подключен', tone: 'success' };
    default:
      return { label: status.current_step.toLowerCase(), tone: 'neutral' };
  }
}

export function getShafaStatusMeta(status: ApiShafaAuthStatus | null): {
  label: string;
  tone: StatusTone;
} {
  if (!status) {
    return { label: 'загрузка', tone: 'neutral' };
  }

  return status.connected
    ? { label: 'подключен', tone: 'success' }
    : { label: 'не подключен', tone: 'warning' };
}

export function getAccountSortValue(account: AccountRow, field: AccountSortField) {
  switch (field) {
    case 'name':
      return account.name;
    case 'browser':
      return account.browser;
    case 'timer':
      return Number.parseInt(account.timer, 10) || 0;
    case 'channels':
      return account.telegramChannels.length;
    case 'status':
      return account.statusLabel;
    case 'errors':
      return Number.parseInt(account.errors, 10) || 0;
  }
}

export function normalizeTelegramHandle(value: string) {
  const cleanedValue = value
    .trim()
    .replace(/^https?:\/\/(www\.)?/i, '')
    .replace(/^telegram\.me\//i, 't.me/')
    .replace(/^@/, 't.me/')
    .replace(/[?#].*$/, '')
    .replace(/\/+$/, '');

  if (!cleanedValue) {
    return '';
  }

  if (cleanedValue.startsWith('t.me/')) {
    return cleanedValue;
  }

  return `t.me/${cleanedValue.replace(/^\/+/, '')}`;
}

export function formatChannelTitle(handle: string) {
  const slug = normalizeTelegramHandle(handle)
    .replace(/^t\.me\//, '')
    .replace(/[_-]+/g, ' ')
    .trim();

  if (!slug) {
    return 'Новый канал';
  }

  return slug.replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}

export function formatChannelBadge(handle: string) {
  const normalizedHandle = normalizeTelegramHandle(handle);

  if (!normalizedHandle) {
    return '@new_channel';
  }

  return `@${normalizedHandle.replace(/^t\.me\//, '')}`;
}

export function normalizeTelegramLinks(links: string[]) {
  const uniqueLinks = new Set<string>();

  links.forEach((link) => {
    const normalizedHandle = normalizeTelegramHandle(link);

    if (normalizedHandle) {
      uniqueLinks.add(`https://${normalizedHandle}`);
    }
  });

  return [...uniqueLinks];
}

export function getAccountDraftFromRow(account: AccountRow): AccountDraft {
  return {
    name: account.name,
    path: account.path,
    browser: account.browser,
    timer: account.timer,
  };
}

export function isAccountDraftValid(draft: AccountDraft) {
  return Boolean(draft.name.trim());
}

export function formatAccountCount(count: number) {
  const lastDigit = count % 10;
  const lastTwoDigits = count % 100;

  if (lastDigit === 1 && lastTwoDigits !== 11) {
    return `${count} аккаунт`;
  }

  if (
    lastDigit >= 2 &&
    lastDigit <= 4 &&
    (lastTwoDigits < 12 || lastTwoDigits > 14)
  ) {
    return `${count} аккаунта`;
  }

  return `${count} аккаунтов`;
}
