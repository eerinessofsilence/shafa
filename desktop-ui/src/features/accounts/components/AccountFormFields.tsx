import { Check, ChevronDown, Clock3, Eye, User } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  accountControlClassName,
  accountSelectButtonClassName,
  browserOptions,
  timerOptions,
} from '../constants';
import type { AccountDraft, AccountEditableField } from '../types';

interface FieldProps {
  label: string;
  value: string;
}

interface EditableFieldProps extends FieldProps {
  icon?: React.ReactNode;
  onChange: (value: string) => void;
}

interface SelectFieldProps extends EditableFieldProps {
  options: string[];
}

interface AccountFormFieldsProps {
  values: AccountDraft;
  onFieldChange: (field: AccountEditableField, value: string) => void;
}

export function AccountFormFields({
  values,
  onFieldChange,
}: AccountFormFieldsProps) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
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
      <SelectField
        label="Браузер"
        value={values.browser}
        options={browserOptions}
        icon={
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-secondary/50">
            <Eye className="h-3.5 w-3.5 text-success/75" />
          </div>
        }
        onChange={(value) => onFieldChange('browser', value)}
      />
      <SelectField
        label="Таймер"
        value={values.timer}
        options={timerOptions}
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
      <span className="flex items-center gap-2 text-[16px] font-medium text-text">
        {icon}
        {label}
      </span>
      <input
        className={accountControlClassName}
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  icon,
}: SelectFieldProps) {
  const [isOpen, setIsOpen] = useState(false);
  const fieldRef = useRef<HTMLDivElement | null>(null);

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

  return (
    <div className="flex flex-col gap-3">
      <span className="flex items-center gap-2 text-[16px] font-medium text-text">
        {icon}
        {label}
      </span>
      <div className="relative" ref={fieldRef}>
        <button
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          className={accountSelectButtonClassName}
          type="button"
          onClick={() => setIsOpen((current) => !current)}
        >
          <span className="truncate text-text">{value}</span>

          <ChevronDown
            className={`h-4 w-4 shrink-0 text-text/75 transition-transform duration-200 ${
              isOpen ? 'rotate-180' : ''
            }`}
          />
        </button>

        {isOpen ? (
          <div className="absolute inset-x-0 bottom-[calc(100%+10px)] z-30 overflow-hidden rounded-xl border border-border/25 bg-secondary p-1.5 shadow-[0_24px_64px_rgba(15,23,42,0.1)]">
            <div
              className={`${
                options.length > 8 ? 'max-h-80 overflow-y-auto pr-1' : ''
              }`}
              role="listbox"
            >
              {options.map((option, index) => {
                const isSelected = option === value;

                return (
                  <button
                    key={option}
                    aria-selected={isSelected}
                    className={`flex w-full cursor-pointer items-center justify-between gap-4 rounded-xl px-4 py-2 text-left transition-colors duration-200 ${
                      isSelected ? 'bg-foreground' : 'hover:bg-foreground/50'
                    } ${index < options.length - 1 ? 'mb-1' : ''}`}
                    role="option"
                    type="button"
                    onClick={() => {
                      onChange(option);
                      setIsOpen(false);
                    }}
                  >
                    <span className="truncate text-[17px] text-text">
                      {option}
                    </span>

                    {isSelected ? (
                      <Check className="h-4 w-4 shrink-0 text-text/75" />
                    ) : null}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
