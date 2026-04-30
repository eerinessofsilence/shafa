import {
  createGlobalChannelTemplate,
  deleteGlobalChannelTemplate,
  listGlobalChannelTemplates,
  resolveGlobalChannelTemplateLinks,
  updateGlobalChannelTemplate,
} from '../api/channelTemplates';
import {
  ActionButton,
  accountControlClassName,
  fieldLabelClassName,
  formatAccountDateTime,
  formatApiError,
  mapLinksToTelegramChannels,
  SelectionCheckbox,
  TelegramChannelCard,
  normalizeTelegramLinks,
} from '../app/shared';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import type { ApiChannelTemplateRead, ChannelTemplateType } from '../types';
import { cardTitleClassName, cx, getButtonClassName } from '../ui';
import {
  Check,
  ChevronDown,
  EllipsisVertical,
  FilePlus2,
  Footprints,
  LoaderCircle,
  PencilLine,
  Plus,
  RefreshCw,
  Shirt,
  Trash2,
  X,
} from 'lucide-react';
import { type ReactNode, useEffect, useMemo, useState } from 'react';

type TemplateFilter = ChannelTemplateType | 'all';
type TemplateSortField = 'name' | 'type' | 'channels' | 'updated';
type TemplateSortDirection = 'asc' | 'desc';

interface TemplateDraft {
  links: string[];
  name: string;
  type: ChannelTemplateType;
}

const templateTypeOptions: Array<{
  label: string;
  shortLabel: string;
  value: ChannelTemplateType;
}> = [
  { label: 'Одежда', shortLabel: 'Одежда', value: 'clothes' },
  { label: 'Обувь', shortLabel: 'Обувь', value: 'shoes' },
];

const emptyTemplateDraft: TemplateDraft = {
  links: [],
  name: '',
  type: 'clothes',
};

const templateTableHeaders: Array<{
  id: TemplateSortField;
  label: string;
}> = [
  { id: 'name', label: 'Название' },
  { id: 'type', label: 'Тип' },
  { id: 'channels', label: 'Каналы' },
  { id: 'updated', label: 'Обновлён' },
];

function getTemplateTypeLabel(type: ChannelTemplateType) {
  return (
    templateTypeOptions.find((option) => option.value === type)?.label ??
    'Одежда'
  );
}

function getTemplateTypeIcon(type: ChannelTemplateType) {
  return type === 'shoes' ? (
    <Footprints className="h-4 w-4" />
  ) : (
    <Shirt className="h-4 w-4" />
  );
}

function getDraftFromTemplate(template: ApiChannelTemplateRead): TemplateDraft {
  return {
    links: template.links,
    name: template.name,
    type: template.type,
  };
}

function getTemplateSortValue(
  template: ApiChannelTemplateRead,
  field: TemplateSortField,
) {
  if (field === 'name') {
    return template.name;
  }

  if (field === 'type') {
    return getTemplateTypeLabel(template.type);
  }

  if (field === 'channels') {
    return template.links.length;
  }

  return Date.parse(template.updated_at) || 0;
}

function formatTelegramChannelHandle(link: string) {
  return link.replace(/^https:\/\/t\.me\//i, '@');
}

function formatTemplateChannelValidationError(error: unknown) {
  const message = formatApiError(
    error,
    'Канал не найден. Проверьте ссылку или @handle.',
  );

  if (message === 'Method Not Allowed') {
    return 'Backend ещё не обновлён для проверки каналов. Перезапустите backend и повторите добавление.';
  }

  if (message.includes('Канал не найден:')) {
    return message;
  }

  if (message.includes('подключите Telegram')) {
    return message;
  }

  return message;
}

function TemplatesPage() {
  const [templates, setTemplates] = useState<ApiChannelTemplateRead[]>([]);
  const [activeFilter, setActiveFilter] = useState<TemplateFilter>('all');
  const [sortState, setSortState] = useState<{
    field: TemplateSortField;
    direction: TemplateSortDirection;
  } | null>(null);
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutationPending, setIsMutationPending] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] =
    useState<ApiChannelTemplateRead | null>(null);
  const [deletingTemplate, setDeletingTemplate] =
    useState<ApiChannelTemplateRead | null>(null);

  const filteredTemplates = useMemo(
    () =>
      activeFilter === 'all'
        ? templates
        : templates.filter((template) => template.type === activeFilter),
    [activeFilter, templates],
  );
  const sortedTemplates = useMemo(
    () =>
      [...filteredTemplates].sort((leftTemplate, rightTemplate) => {
        if (!sortState) {
          return 0;
        }

        const leftValue = getTemplateSortValue(leftTemplate, sortState.field);
        const rightValue = getTemplateSortValue(
          rightTemplate,
          sortState.field,
        );
        const comparison =
          typeof leftValue === 'number' && typeof rightValue === 'number'
            ? leftValue - rightValue
            : String(leftValue).localeCompare(String(rightValue), 'ru', {
                sensitivity: 'base',
                numeric: true,
              });

        return sortState.direction === 'asc' ? comparison : -comparison;
      }),
    [filteredTemplates, sortState],
  );
  const visibleTemplateIds = sortedTemplates.map((template) => template.id);
  const selectedVisibleCount = selectedTemplateIds.filter((templateId) =>
    visibleTemplateIds.includes(templateId),
  ).length;
  const isAllVisibleSelected =
    visibleTemplateIds.length > 0 &&
    selectedVisibleCount === visibleTemplateIds.length;
  const isPartiallyVisibleSelected =
    selectedVisibleCount > 0 && !isAllVisibleSelected;
  const allTemplateIds = templates.map((template) => template.id);
  const allTemplateSignature = allTemplateIds.join('|');
  const templateCountByType = useMemo(
    () =>
      templateTypeOptions.reduce<Record<ChannelTemplateType, number>>(
        (accumulator, option) => ({
          ...accumulator,
          [option.value]: templates.filter(
            (template) => template.type === option.value,
          ).length,
        }),
        {
          clothes: 0,
          shoes: 0,
        },
      ),
    [templates],
  );

  const loadTemplates = async () => {
    setLoadError('');
    setIsLoading(true);

    try {
      setTemplates(await listGlobalChannelTemplates());
    } catch (error) {
      setLoadError(formatApiError(error, 'Не удалось загрузить шаблоны.'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadTemplates();
  }, []);

  useEffect(() => {
    const templateIdSet = new Set(allTemplateIds);

    setSelectedTemplateIds((currentSelection) => {
      const nextSelection = currentSelection.filter((templateId) =>
        templateIdSet.has(templateId),
      );

      return nextSelection.length === currentSelection.length
        ? currentSelection
        : nextSelection;
    });
  }, [allTemplateSignature]);

  useEffect(() => {
    if (!feedback) {
      return;
    }

    const timeoutId = window.setTimeout(() => setFeedback(''), 3200);
    return () => window.clearTimeout(timeoutId);
  }, [feedback]);

  const saveTemplate = async (
    draft: TemplateDraft,
    templateId?: string,
  ): Promise<boolean> => {
    const links = normalizeTelegramLinks(draft.links);

    if (!draft.name.trim() || links.length === 0 || isMutationPending) {
      return false;
    }

    setIsMutationPending(true);
    setFeedback('');

    try {
      if (templateId) {
        await updateGlobalChannelTemplate(templateId, {
          links,
          name: draft.name.trim(),
          type: draft.type,
        });
        setFeedback('Шаблон обновлён.');
      } else {
        await createGlobalChannelTemplate({
          links,
          name: draft.name.trim(),
          type: draft.type,
        });
        setFeedback('Шаблон создан.');
      }
      await loadTemplates();
      return true;
    } finally {
      setIsMutationPending(false);
    }
  };

  const handleSortHeaderClick = (field: TemplateSortField) => {
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

  const toggleTemplateSelection = (templateId: string) => {
    setSelectedTemplateIds((currentSelection) =>
      currentSelection.includes(templateId)
        ? currentSelection.filter((selectedId) => selectedId !== templateId)
        : [...currentSelection, templateId],
    );
  };

  const toggleAllVisibleTemplates = () => {
    const visibleIdSet = new Set(visibleTemplateIds);

    setSelectedTemplateIds((currentSelection) => {
      if (selectedVisibleCount > 0) {
        return currentSelection.filter(
          (selectedId) => !visibleIdSet.has(selectedId),
        );
      }

      const nextSelection = new Set([
        ...currentSelection,
        ...visibleTemplateIds,
      ]);

      return templates
        .map((template) => template.id)
        .filter((templateId) => nextSelection.has(templateId));
    });
  };

  const deleteTemplate = async () => {
    if (!deletingTemplate || isMutationPending) {
      return;
    }

    setIsMutationPending(true);
    setFeedback('');

    try {
      await deleteGlobalChannelTemplate(deletingTemplate.id);
      setDeletingTemplate(null);
      setSelectedTemplateIds((currentSelection) =>
        currentSelection.filter((templateId) => templateId !== deletingTemplate.id),
      );
      setFeedback('Шаблон удалён.');
      await loadTemplates();
    } finally {
      setIsMutationPending(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Шаблоны"
        actions={
          <>
            <ActionButton
              disabled={isLoading}
              icon={
                isLoading ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )
              }
              size="sm"
              onClick={() => void loadTemplates()}
            >
              Обновить
            </ActionButton>
            <ActionButton
              icon={<FilePlus2 className="h-4 w-4" />}
              size="sm"
              tone="info"
              variant="solid"
              onClick={() => setIsCreateDialogOpen(true)}
            >
              Добавить
            </ActionButton>
          </>
        }
      />

      {loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          <span>{loadError}</span>
          <button
            className={getButtonClassName({ tone: 'danger', size: 'sm' })}
            disabled={isLoading}
            type="button"
            onClick={() => void loadTemplates()}
          >
            Повторить
          </button>
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded-2xl border border-border/15 bg-secondary/70 px-4 py-3 text-sm text-text">
          {feedback}
        </div>
      ) : null}

      <Panel
        title="Каталог шаблонов"
        actions={
          <TemplateTypeFilter
            activeFilter={activeFilter}
            counts={templateCountByType}
            onChange={setActiveFilter}
          />
        }
      >
        <div className="overflow-hidden rounded-2xl border border-border/25 bg-secondary/50">
          <div className="overflow-x-auto px-5 py-3">
            <table className="w-full border-separate [border-spacing:0_10px]">
              <thead>
                <tr>
                  <th className="border-b border-border/25 px-4 pb-3 text-left">
                    <SelectionCheckbox
                      checked={isAllVisibleSelected}
                      indeterminate={isPartiallyVisibleSelected}
                      label="Выбрать все видимые шаблоны"
                      onToggle={toggleAllVisibleTemplates}
                    />
                  </th>
                  {templateTableHeaders.map((header) => (
                    <th
                      key={header.id}
                      aria-sort={
                        sortState?.field === header.id
                          ? sortState.direction === 'asc'
                            ? 'ascending'
                            : 'descending'
                          : 'none'
                      }
                      className="border-b border-border/25 px-4 pb-3 text-left text-xs font-medium uppercase tracking-wide text-text-muted"
                    >
                      <button
                        className={cx(
                          'inline-flex cursor-pointer items-center gap-1.5 uppercase transition-colors duration-200',
                          sortState?.field === header.id
                            ? 'text-info'
                            : 'hover:text-text',
                        )}
                        type="button"
                        onClick={() => handleSortHeaderClick(header.id)}
                      >
                        {header.label}
                        <ChevronDown
                          className={cx(
                            'h-4 w-4 transition-all duration-200',
                            sortState?.field === header.id
                              ? cx(
                                  'opacity-100',
                                  sortState.direction === 'asc' && 'rotate-180',
                                )
                              : 'opacity-35',
                          )}
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
                {isLoading && templates.length === 0 ? (
                  <tr>
                    <td colSpan={templateTableHeaders.length + 2}>
                      <TemplateEmptyState
                        title="Загружаем шаблоны"
                        text="Получаем список из API."
                      />
                    </td>
                  </tr>
                ) : sortedTemplates.length === 0 ? (
                  <tr>
                    <td colSpan={templateTableHeaders.length + 2}>
                      <TemplateEmptyState
                        title="Пока нет шаблонов"
                        text="Создай шаблон для одежды или обуви."
                      />
                    </td>
                  </tr>
                ) : (
                  sortedTemplates.map((template) => {
                    const isChecked = selectedTemplateIds.includes(template.id);

                    return (
                      <TemplateRow
                        key={template.id}
                        disabled={isMutationPending}
                        isChecked={isChecked}
                        template={template}
                        onDelete={setDeletingTemplate}
                        onEdit={setEditingTemplate}
                        onToggleSelection={toggleTemplateSelection}
                      />
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </Panel>

      <TemplateEditorDialog
        isOpen={isCreateDialogOpen}
        isSubmitting={isMutationPending}
        title="Новый шаблон"
        onClose={() => setIsCreateDialogOpen(false)}
        onSave={async (draft) => {
          try {
            const saved = await saveTemplate(draft);
            if (saved) {
              setIsCreateDialogOpen(false);
            }
          } catch (error) {
            throw error;
          }
        }}
      />
      <TemplateEditorDialog
        initialDraft={
          editingTemplate ? getDraftFromTemplate(editingTemplate) : undefined
        }
        isOpen={Boolean(editingTemplate)}
        isSubmitting={isMutationPending}
        title="Редактирование шаблона"
        onClose={() => setEditingTemplate(null)}
        onSave={async (draft) => {
          if (!editingTemplate) {
            return;
          }
          const saved = await saveTemplate(draft, editingTemplate.id);
          if (saved) {
            setEditingTemplate(null);
          }
        }}
      />
      <TemplateDeleteDialog
        isOpen={Boolean(deletingTemplate)}
        isSubmitting={isMutationPending}
        template={deletingTemplate}
        onClose={() => setDeletingTemplate(null)}
        onConfirm={deleteTemplate}
      />
    </div>
  );
}

interface TemplateTypeFilterProps {
  activeFilter: TemplateFilter;
  counts: Record<ChannelTemplateType, number>;
  onChange: (filter: TemplateFilter) => void;
}

function TemplateTypeFilter({
  activeFilter,
  counts,
  onChange,
}: TemplateTypeFilterProps) {
  const options: Array<{
    label: string;
    value: TemplateFilter;
  }> = [
    { label: 'Все', value: 'all' },
    ...templateTypeOptions.map((option) => ({
      label: `${option.shortLabel} ${counts[option.value]}`,
      value: option.value,
    })),
  ];

  return (
    <div className="flex rounded-[10px] border border-border bg-foreground p-1">
      {options.map((option) => (
        <button
          key={option.value}
          className={cx(
            'h-9 rounded-lg px-3 text-sm font-medium transition',
            activeFilter === option.value
              ? 'bg-info text-white'
              : 'text-text-muted hover:bg-secondary hover:text-text',
          )}
          type="button"
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

interface TemplateRowProps {
  disabled: boolean;
  isChecked: boolean;
  template: ApiChannelTemplateRead;
  onDelete: (template: ApiChannelTemplateRead) => void;
  onEdit: (template: ApiChannelTemplateRead) => void;
  onToggleSelection: (templateId: string) => void;
}

function TemplateRow({
  disabled,
  isChecked,
  template,
  onDelete,
  onEdit,
  onToggleSelection,
}: TemplateRowProps) {
  const rowSurfaceClassName = isChecked ? 'bg-info/8' : 'group-hover:bg-secondary/50';
  const rowCellClassName = `px-4 py-4 align-middle transition-colors duration-200 ${rowSurfaceClassName}`;

  return (
    <tr
      className="group cursor-pointer text-sm"
      onClick={() => onEdit(template)}
    >
      <td
        className={`${rowCellClassName} w-16 rounded-l-2xl`}
        onClick={(event) => {
          event.stopPropagation();
          onToggleSelection(template.id);
        }}
      >
        <SelectionCheckbox
          checked={isChecked}
          label={`Выбрать шаблон ${template.name}`}
          onToggle={() => onToggleSelection(template.id)}
        />
      </td>
      <td className={rowCellClassName}>
        <div className="font-medium text-text">{template.name}</div>
      </td>
      <td className={rowCellClassName}>
        <span className="inline-flex items-center gap-2 rounded-full border border-info/20 bg-info/8 px-3 py-1 text-xs font-semibold text-info">
          {getTemplateTypeIcon(template.type)}
          {getTemplateTypeLabel(template.type)}
        </span>
      </td>
      <td className={rowCellClassName}>
        <span className="inline-flex min-w-8 items-center justify-center rounded-full bg-info/5 p-1.5 text-sm font-semibold text-info">
          {template.links.length}
        </span>
      </td>
      <td className={rowCellClassName}>
        <span className="text-text-muted">
          {formatAccountDateTime(template.updated_at)}
        </span>
      </td>
      <td
        className={`${rowCellClassName} w-16 rounded-r-2xl`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex justify-end">
          <TemplateRowActionMenu
            disabled={disabled}
            template={template}
            onDelete={onDelete}
            onEdit={onEdit}
          />
        </div>
      </td>
    </tr>
  );
}

interface TemplateRowActionMenuProps {
  disabled: boolean;
  template: ApiChannelTemplateRead;
  onDelete: (template: ApiChannelTemplateRead) => void;
  onEdit: (template: ApiChannelTemplateRead) => void;
}

function TemplateRowActionMenu({
  disabled,
  template,
  onDelete,
  onEdit,
}: TemplateRowActionMenuProps) {
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
        aria-label={`Действия для шаблона ${template.name}`}
        className="inline-flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg border border-transparent bg-transparent text-text-muted transition-colors duration-200 hover:bg-foreground hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        disabled={disabled}
        type="button"
      >
        <EllipsisVertical className="h-4.5 w-4.5" />
      </button>

      {isOpen ? (
        <div className="absolute right-0 top-full z-50 pt-2">
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
                onEdit(template);
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
                onDelete(template);
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

interface TemplateEmptyStateProps {
  text: string;
  title: string;
}

function TemplateEmptyState({ text, title }: TemplateEmptyStateProps) {
  return (
    <div className="rounded-2xl border border-dashed border-border/20 bg-secondary/45 px-6 py-10 text-center">
      <strong className="block text-base text-text">{title}</strong>
      <p className="mt-2 text-sm leading-6 text-text-muted">{text}</p>
    </div>
  );
}

interface TemplateDialogShellProps {
  children: ReactNode;
  isOpen: boolean;
  onClose: () => void;
  title: string;
}

function TemplateDialogShell({
  children,
  isOpen,
  onClose,
  title,
}: TemplateDialogShellProps) {
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
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/55 px-5 backdrop-blur-sm"
      role="dialog"
      onClick={onClose}
    >
      <div
        className="max-h-[calc(100vh-64px)] w-full max-w-190 overflow-y-auto rounded-[28px] border border-border/20 bg-foreground p-5 shadow-[0_30px_90px_rgba(15,23,42,0.2)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 border-b border-border/25 pb-4">
          <h3 className="text-2xl font-semibold tracking-tight text-text">
            {title}
          </h3>
          <button
            aria-label="Закрыть"
            className={getButtonClassName({
              tone: 'info',
              variant: 'solid',
              size: 'icon-sm',
              className: 'rounded-xl',
            })}
            type="button"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

interface TemplateEditorDialogProps {
  initialDraft?: TemplateDraft;
  isOpen: boolean;
  isSubmitting: boolean;
  title: string;
  onClose: () => void;
  onSave: (draft: TemplateDraft) => Promise<void>;
}

function TemplateEditorDialog({
  initialDraft = emptyTemplateDraft,
  isOpen,
  isSubmitting,
  title,
  onClose,
  onSave,
}: TemplateEditorDialogProps) {
  const [draft, setDraft] = useState<TemplateDraft>(initialDraft);
  const [channelDraft, setChannelDraft] = useState('');
  const [editingChannelIndex, setEditingChannelIndex] = useState<number | null>(
    null,
  );
  const [editingChannelDraft, setEditingChannelDraft] = useState('');
  const [channelError, setChannelError] = useState('');
  const [isValidatingChannel, setIsValidatingChannel] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const links = normalizeTelegramLinks(draft.links);
  const channels = mapLinksToTelegramChannels(
    `template-${draft.name || 'new'}`,
    links,
    null,
  );
  const isSaveDisabled =
    isSubmitting || !draft.name.trim() || draft.links.length === 0;

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setDraft(initialDraft);
    setChannelDraft('');
    setEditingChannelIndex(null);
    setEditingChannelDraft('');
    setChannelError('');
    setIsValidatingChannel(false);
    setSubmitError('');
  }, [initialDraft, isOpen]);

  const setLinks = (nextLinks: string[]) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      links: normalizeTelegramLinks(nextLinks),
    }));
  };

  const validateChannelLink = async (value: string) => {
    const [normalizedLink] = normalizeTelegramLinks([value]);

    if (!normalizedLink) {
      setChannelError('Введите ссылку или @handle Telegram-канала.');
      return null;
    }

    setIsValidatingChannel(true);
    setChannelError('');

    try {
      await resolveGlobalChannelTemplateLinks([normalizedLink]);
      return normalizedLink;
    } catch (error) {
      setChannelError(formatTemplateChannelValidationError(error));
      return null;
    } finally {
      setIsValidatingChannel(false);
    }
  };

  const addChannel = async () => {
    const [normalizedLink] = normalizeTelegramLinks([channelDraft]);

    if (!normalizedLink) {
      setChannelError('Введите ссылку или @handle Telegram-канала.');
      return;
    }

    if (links.includes(normalizedLink)) {
      setChannelError(
        `Этот канал уже есть в шаблоне: ${formatTelegramChannelHandle(normalizedLink)}. Повторно добавлять его не нужно.`,
      );
      return;
    }

    const validatedLink = await validateChannelLink(normalizedLink);
    if (!validatedLink) {
      return;
    }

    setLinks([...links, validatedLink]);
    setChannelDraft('');
    setChannelError('');
  };

  const startEditingChannel = (index: number) => {
    setEditingChannelIndex(index);
    setEditingChannelDraft(links[index] ?? '');
  };

  const resetEditingChannel = () => {
    setEditingChannelIndex(null);
    setEditingChannelDraft('');
  };

  const saveEditedChannel = async () => {
    if (editingChannelIndex === null) {
      return;
    }

    const [normalizedLink] = normalizeTelegramLinks([editingChannelDraft]);

    if (!normalizedLink) {
      setChannelError('Введите ссылку или @handle Telegram-канала.');
      return;
    }

    const duplicateIndex = links.findIndex(
      (link, index) => link === normalizedLink && index !== editingChannelIndex,
    );
    if (duplicateIndex >= 0) {
      setChannelError(
        `Этот канал уже есть в шаблоне: ${formatTelegramChannelHandle(normalizedLink)}. Повторно добавлять его не нужно.`,
      );
      return;
    }

    if (links[editingChannelIndex] === normalizedLink) {
      resetEditingChannel();
      setChannelError('');
      return;
    }

    const validatedLink = await validateChannelLink(normalizedLink);
    if (!validatedLink) {
      return;
    }

    const nextLinks = [...links];
    nextLinks[editingChannelIndex] = validatedLink;
    setLinks(nextLinks);
    resetEditingChannel();
    setChannelError('');
  };

  const deleteEditingChannel = () => {
    if (editingChannelIndex === null) {
      return;
    }

    setLinks(links.filter((_, linkIndex) => linkIndex !== editingChannelIndex));
    resetEditingChannel();
    setChannelError('');
  };

  return (
    <TemplateDialogShell isOpen={isOpen} title={title} onClose={onClose}>
      <div className="space-y-5 pt-5">
        <div className="grid gap-4 md:grid-cols-[1fr_250px]">
          <label className="flex flex-col gap-2">
            <span className={fieldLabelClassName}>Название</span>
            <input
              className={accountControlClassName}
              placeholder="Основной дроп"
              type="text"
              value={draft.name}
              onChange={(event) =>
                setDraft((currentDraft) => ({
                  ...currentDraft,
                  name: event.target.value,
                }))
              }
            />
          </label>
          <div className="flex flex-col gap-2">
            <span className={fieldLabelClassName}>Тип</span>
            <TemplateTypeSegmentedControl
              value={draft.type}
              onChange={(value) =>
                setDraft((currentDraft) => ({
                  ...currentDraft,
                  type: value,
                }))
              }
            />
          </div>
        </div>

        <section className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h4 className={cardTitleClassName}>Telegram-каналы</h4>
              <p className="mt-1 text-sm leading-6 text-text-muted">
                Добавь ссылку или `@handle`, затем сохрани шаблон.
              </p>
            </div>
          </div>

          <div className="rounded-[22px] border border-border/25 bg-secondary/55 p-4">
            <div className="flex flex-col gap-3 sm:flex-row">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Новый Telegram-канал</span>
                <input
                  className={accountControlClassName}
                  placeholder="t.me/example_channel"
                  type="text"
                  value={channelDraft}
                  onChange={(event) => setChannelDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      void addChannel();
                    }
                  }}
                />
              </label>
              <ActionButton
                disabled={
                  isSubmitting ||
                  isValidatingChannel ||
                  normalizeTelegramLinks([channelDraft]).length === 0
                }
                icon={
                  isValidatingChannel ? (
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                  ) : (
                    <Plus className="h-4 w-4" />
                  )
                }
                className="h-10.5"
                size="sm"
                tone="success"
                onClick={() => void addChannel()}
              >
                Добавить
              </ActionButton>
            </div>
          </div>

          {channelError ? (
            <div className="rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
              {channelError}
            </div>
          ) : null}

          {channels.length === 0 ? (
            <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
              <strong className="block text-text">Пока нет каналов</strong>
              <p className="mt-2 leading-6 text-text-muted">
                Добавь первый Telegram-канал через поле выше.
              </p>
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {channels.map((channel, index) => {
                const isEditing = editingChannelIndex === index;

                if (isEditing) {
                  return (
                    <div
                      key={channel.id}
                      className="rounded-[22px] border border-border/25 bg-secondary/70 p-4"
                    >
                      <div className="space-y-4">
                        <label className="flex flex-col gap-2">
                          <span className={fieldLabelClassName}>Ссылка</span>
                          <input
                            className={accountControlClassName}
                            type="text"
                            value={editingChannelDraft}
                            onChange={(event) =>
                              setEditingChannelDraft(event.target.value)
                            }
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                void saveEditedChannel();
                              }
                            }}
                          />
                        </label>
                        <div className="flex justify-end gap-2">
                          <button
                            aria-label="Удалить канал"
                            className={getButtonClassName({
                              tone: 'danger',
                              size: 'icon-sm',
                            })}
                            disabled={isSubmitting}
                            type="button"
                            onClick={deleteEditingChannel}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                          <button
                            aria-label="Отменить редактирование канала"
                            className={getButtonClassName({
                              size: 'icon-sm',
                            })}
                            disabled={isSubmitting}
                            type="button"
                            onClick={resetEditingChannel}
                          >
                            <X className="h-4 w-4" />
                          </button>
                          <button
                            aria-label="Сохранить канал"
                            className={getButtonClassName({
                              tone: 'success',
                              size: 'icon-sm',
                            })}
                            disabled={
                              isSubmitting ||
                              isValidatingChannel ||
                              normalizeTelegramLinks([editingChannelDraft])
                                .length === 0
                            }
                            type="button"
                            onClick={() => void saveEditedChannel()}
                          >
                            {isValidatingChannel ? (
                              <LoaderCircle className="h-4 w-4 animate-spin" />
                            ) : (
                              <Check className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                }

                return (
                  <TelegramChannelCard
                    key={channel.id}
                    action={
                      <div className="flex items-center gap-2">
                        <button
                          aria-label={`Редактировать канал ${channel.title}`}
                          className={getButtonClassName({
                            tone: 'warning',
                            size: 'icon-sm',
                          })}
                          disabled={isSubmitting}
                          type="button"
                          onClick={() => startEditingChannel(index)}
                        >
                          <PencilLine className="h-4 w-4 text-text" />
                        </button>
                      </div>
                    }
                    channel={channel}
                  />
                );
              })}
            </div>
          )}
        </section>

        {submitError ? (
          <p className="text-sm text-error">{submitError}</p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          <ActionButton
            disabled={isSubmitting}
            icon={<X className="h-4 w-4" />}
            size="sm"
            onClick={onClose}
          >
            Отмена
          </ActionButton>
          <ActionButton
            disabled={isSaveDisabled}
            icon={
              isSubmitting ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )
            }
            size="sm"
            tone="success"
            variant="solid"
            onClick={async () => {
              setSubmitError('');

              try {
                await onSave(draft);
              } catch (error) {
                setSubmitError(
                  formatApiError(error, 'Не удалось сохранить шаблон.'),
                );
              }
            }}
          >
            Сохранить
          </ActionButton>
        </div>
      </div>
    </TemplateDialogShell>
  );
}

interface TemplateTypeSegmentedControlProps {
  value: ChannelTemplateType;
  onChange: (value: ChannelTemplateType) => void;
}

function TemplateTypeSegmentedControl({
  value,
  onChange,
}: TemplateTypeSegmentedControlProps) {
  return (
    <div className="grid h-10.5 grid-cols-2 rounded-[10px] border border-border bg-secondary p-1">
      {templateTypeOptions.map((option) => (
        <button
          key={option.value}
          aria-pressed={value === option.value}
          className={cx(
            'inline-flex min-w-0 cursor-pointer items-center justify-center gap-2 rounded-lg px-3 text-sm font-medium transition',
            value === option.value
              ? 'bg-info text-white shadow-[0_1px_2px_rgba(15,23,42,0.08)]'
              : 'text-text-muted hover:bg-foreground hover:text-text',
          )}
          type="button"
          onClick={() => onChange(option.value)}
        >
          {getTemplateTypeIcon(option.value)}
          <span>{option.shortLabel}</span>
        </button>
      ))}
    </div>
  );
}

interface TemplateDeleteDialogProps {
  isOpen: boolean;
  isSubmitting: boolean;
  template: ApiChannelTemplateRead | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}

function TemplateDeleteDialog({
  isOpen,
  isSubmitting,
  template,
  onClose,
  onConfirm,
}: TemplateDeleteDialogProps) {
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setSubmitError('');
    }
  }, [isOpen, template?.id]);

  if (!template) {
    return null;
  }

  return (
    <TemplateDialogShell
      isOpen={isOpen}
      title="Удаление шаблона"
      onClose={onClose}
    >
      <div className="space-y-5 pt-5">
        <div className="rounded-[22px] border border-error/25 bg-error/8 p-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-error/12 text-error">
              <Trash2 className="h-5 w-5" />
            </div>
            <div className="space-y-1.5">
              <strong className="block text-text">{template.name}</strong>
              <p className="leading-6 text-text-muted">
                Будут удалены тип шаблона и {template.links.length} каналов.
              </p>
            </div>
          </div>
        </div>

        {submitError ? (
          <p className="text-sm text-error">{submitError}</p>
        ) : null}

        <div className="flex flex-wrap justify-end gap-2">
          <ActionButton
            disabled={isSubmitting}
            icon={<X className="h-4 w-4" />}
            size="sm"
            onClick={onClose}
          >
            Отмена
          </ActionButton>
          <ActionButton
            disabled={isSubmitting}
            icon={<Trash2 className="h-4 w-4" />}
            size="sm"
            tone="danger"
            variant="solid"
            onClick={async () => {
              setSubmitError('');

              try {
                await onConfirm();
              } catch (error) {
                setSubmitError(
                  formatApiError(error, 'Не удалось удалить шаблон.'),
                );
              }
            }}
          >
            Удалить
          </ActionButton>
        </div>
      </div>
    </TemplateDialogShell>
  );
}

export default TemplatesPage;
