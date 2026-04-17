import type { ReactNode } from 'react';

const actionButtonClassNames = {
  success:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-4 py-2',
  info: 'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-info/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-info/25 hover:border-border/75 px-4 py-2',
  warning:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-warning/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/25 hover:border-border/75 px-4 py-2',
  danger:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-error/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-error/25 hover:border-border/75 px-4 py-2',
  neutral:
    'border inline-flex items-center gap-3 rounded-xl border-border/50 bg-secondary/80 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-secondary hover:border-border/75 px-4 py-2',
} as const;

const compactActionButtonClassNames = {
  success:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-3 py-1',
  info: 'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-info/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-info/25 hover:border-border/75 px-3 py-1',
  warning:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-warning/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-warning/25 hover:border-border/75 px-3 py-1',
  danger:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-error/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-error/25 hover:border-border/75 px-3 py-1',
  neutral:
    'border inline-flex items-center gap-2 rounded-xl border-border/50 bg-secondary/80 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-secondary hover:border-border/75 px-3 py-1',
} as const;

export type ActionTone = keyof typeof actionButtonClassNames;

interface ActionButtonProps {
  children: ReactNode;
  icon?: ReactNode;
  tone?: ActionTone;
  compact?: boolean;
  onClick?: () => void;
}

export function ActionButton({
  children,
  icon,
  tone = 'neutral',
  compact = false,
  onClick,
}: ActionButtonProps) {
  return (
    <button
      className={
        compact
          ? compactActionButtonClassNames[tone]
          : actionButtonClassNames[tone]
      }
      type="button"
      onClick={onClick}
    >
      {icon}
      {children}
    </button>
  );
}
