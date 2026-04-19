export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

export const pageTitleClassName =
  'text-3xl font-semibold tracking-tight text-text';
export const sectionTitleClassName =
  'text-2xl font-semibold tracking-tight text-text';
export const cardTitleClassName =
  'text-lg font-medium tracking-tight text-text';
export const fieldLabelClassName =
  'flex items-center gap-2 text-sm font-medium text-text';

export type ButtonTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type ButtonVariant = 'soft' | 'solid' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'icon-sm' | 'icon-md' | 'row';

const buttonBaseClassName =
  'inline-flex shrink-0 cursor-pointer items-center justify-center rounded-xl border text-sm font-medium transition-all duration-200 outline-none active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50';

const buttonSizeClassNames: Record<ButtonSize, string> = {
  sm: 'h-10 gap-2 px-3.5',
  md: 'h-12 gap-2.5 px-4',
  'icon-sm': 'h-10 w-10',
  'icon-md': 'h-12 w-12',
  row: 'h-10 gap-3 px-3',
};

const buttonVariantClassNames: Record<
  ButtonVariant,
  Record<ButtonTone, string>
> = {
  soft: {
    neutral:
      'border-border/40 bg-secondary/80 text-text hover:border-border/70 hover:bg-secondary',
    info: 'border-info/25 bg-info/12.5 text-text hover:border-info/45 hover:bg-info/20',
    success:
      'border-success/25 bg-success/12.5 text-text hover:border-success/45 hover:bg-success/20',
    warning:
      'border-warning/25 bg-warning/12.5 text-text hover:border-warning/45 hover:bg-warning/20',
    danger:
      'border-error/25 bg-error/8 text-error hover:border-error/45 hover:bg-error/12',
  },
  solid: {
    neutral:
      'border-border/50 bg-secondary text-text hover:border-border/70 hover:bg-secondary/90',
    info: 'border-info bg-info text-white hover:border-info/90 hover:bg-info/90',
    success:
      'border-success bg-success text-white hover:border-success/90 hover:bg-success/90',
    warning:
      'border-warning bg-warning text-text hover:border-warning/90 hover:bg-warning/90',
    danger:
      'border-error bg-error text-white hover:border-error/90 hover:bg-error/90',
  },
  ghost: {
    neutral:
      'border-transparent bg-transparent text-text hover:border-border/30 hover:bg-secondary/80',
    info: 'border-transparent bg-transparent text-info hover:border-info/25 hover:bg-info/10',
    success:
      'border-transparent bg-transparent text-success hover:border-success/25 hover:bg-success/10',
    warning:
      'border-transparent bg-transparent text-warning hover:border-warning/25 hover:bg-warning/10',
    danger:
      'border-transparent bg-transparent text-error hover:border-error/25 hover:bg-error/10',
  },
};

interface GetButtonClassNameOptions {
  tone?: ButtonTone;
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  align?: 'center' | 'left';
  className?: string;
}

export function getButtonClassName({
  tone = 'neutral',
  variant = 'soft',
  size = 'md',
  fullWidth = false,
  align = 'center',
  className,
}: GetButtonClassNameOptions = {}) {
  return cx(
    buttonBaseClassName,
    buttonSizeClassNames[size],
    buttonVariantClassNames[variant][tone],
    fullWidth && 'w-full',
    align === 'left' && 'justify-start text-left',
    className,
  );
}
