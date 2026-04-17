import { Check, PencilLine, Plus, Trash2, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import {
  createChannelTemplate as createChannelTemplateRequest,
  deleteChannelTemplate as deleteChannelTemplateRequest,
  updateChannelTemplate as updateChannelTemplateRequest,
} from '../../../api/channelTemplates';
import type { AccountRow, TelegramChannel } from '../../../types';
import {
  accountControlClassName,
  defaultChannelTemplateName,
  telegramDraftInitialState,
} from '../constants';
import type { TelegramChannelDraft } from '../types';
import {
  formatApiError,
  formatChannelBadge,
  getPrimaryChannelTemplate,
  normalizeTelegramHandle,
  normalizeTelegramLinks,
} from '../utils';

interface TelegramChannelsPanelProps {
  account: AccountRow;
  isSubmittingAccount: boolean;
  onSyncAccountChannels: (
    accountId: string,
    channelLinks: string[],
  ) => Promise<void>;
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

export function TelegramChannelsPanel({
  account,
  isSubmittingAccount,
  onSyncAccountChannels,
}: TelegramChannelsPanelProps) {
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
        formatApiError(
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

  return (
    <section className="space-y-4 border-t border-border/20 pt-2">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-[22px] font-semibold text-text">Telegram-каналы</h3>

        <button
          className="border inline-flex items-center gap-2 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-3 py-1"
          disabled={isActionDisabled}
          type="button"
          onClick={() => setIsComposerOpen((current) => !current)}
        >
          <Plus className="text-text w-3 h-3" />
          {isComposerOpen ? 'Скрыть' : 'Добавить'}
        </button>
      </div>

      {hasAdditionalTemplates ? (
        <div className="rounded-2xl border border-warning/15 bg-warning/8 px-4 py-3 text-sm text-text">
          UI редактирует шаблон `{activeTemplateName}`. Остальные шаблоны этого
          аккаунта пока доступны только через API.
        </div>
      ) : null}

      {!activeTemplate && channels.length > 0 ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/65 px-4 py-3 text-sm text-text-muted">
          Для этого аккаунта уже есть рабочие `channel_links`. При первом
          сохранении UI создаст шаблон `{defaultChannelTemplateName}`.
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
              проверена через Telegram API и сохранена в runtime аккаунта.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3">
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
                      title={channel.title}
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
                <article
                  key={channel.id}
                  className="rounded-xl border border-border/25 bg-secondary/50 p-2.5 shadow-[0_18px_48px_rgba(15,23,42,0.04)]"
                >
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <img src="/tg_logo.png" className="h-10 w-10" />
                          <div>
                            <h1 className="font-medium text-text">
                              {channel.title}
                            </h1>
                            <span className="text-sm text-text-muted">
                              {formatChannelBadge(channel.handle)}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          className="border inline-flex items-center rounded-xl border-border/50 bg-warning/6.25 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/12.5 hover:border-border/75 p-2.5 disabled:cursor-not-allowed disabled:opacity-50"
                          disabled={isActionDisabled}
                          type="button"
                          onClick={() => startEditing(channel)}
                        >
                          <PencilLine className="text-text h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </article>
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
        <h1 className="font-medium text-text">{title}</h1>
        <p className="mt-2 leading-6 text-text-muted">
          Можно вставить `t.me/...`, `https://t.me/...` или просто `@handle`.
        </p>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-sm font-medium text-text">Ссылка</span>
        <input
          className={accountControlClassName}
          placeholder="t.me/example_channel"
          type="text"
          value={draft.handle}
          onChange={(event) => onDraftChange('handle', event.target.value)}
        />
      </label>

      <div className="flex flex-wrap justify-between gap-2 text-sm">
        {onDelete ? (
          <button
            className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-error/25 bg-error/8 px-3 py-2 text-error transition hover:border-error/45 hover:bg-error/12 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-error/25 disabled:hover:bg-error/8"
            disabled={isSubmitting}
            type="button"
            onClick={onDelete}
          >
            <Trash2 className="h-4 w-4" />
            {deleteLabel ?? 'Удалить'}
          </button>
        ) : null}
        <button
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border/40 bg-secondary/75 px-3 py-2 text-text transition hover:border-border/70 hover:bg-secondary"
          disabled={isSubmitting}
          type="button"
          onClick={onCancel}
        >
          <X className="h-4 w-4" />
          Отмена
        </button>
        <button
          className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-success/30 bg-success/12.5 px-3 py-2 text-text transition hover:border-success/45 hover:bg-success/20 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-success/30 disabled:hover:bg-success/12.5"
          disabled={isSubmitDisabled}
          type="button"
          onClick={onSubmit}
        >
          <Check className="h-4 w-4" />
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
