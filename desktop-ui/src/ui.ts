export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

export const pageTitleClassName =
  'text-[28px] font-semibold tracking-tight text-[#191c1e]';
export const sectionTitleClassName =
  'text-[17px] font-medium text-[#191c1e]';
export const cardTitleClassName =
  'text-[15px] font-semibold text-[#191c1e]';
export const fieldLabelClassName =
  'flex items-center gap-2 text-[13px] font-medium text-[#434654]';

export type ButtonTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';
export type ButtonVariant = 'soft' | 'solid' | 'ghost';
export type ButtonSize = 'sm' | 'md' | 'icon-sm' | 'icon-md' | 'row';

const buttonBaseClassName =
  'inline-flex shrink-0 cursor-pointer items-center justify-center rounded-[8px] border text-sm font-medium transition-all duration-200 outline-none active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50';

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
      'border-[#cfd5e1] bg-white text-[#191c1e] hover:border-[#b9c3d3] hover:bg-[#fafbfc]',
    info: 'border-[#c6d8ff] bg-[#f4f7ff] text-[#0c56d0] hover:border-[#9ebeff] hover:bg-[#eaf1ff]',
    success:
      'border-[#b9e5c9] bg-[#edf8f1] text-[#1f7a42] hover:border-[#94d3ac] hover:bg-[#e3f4ea]',
    warning:
      'border-[#ead7aa] bg-[#fdf7ea] text-[#966f15] hover:border-[#ddc685] hover:bg-[#fbf1d7]',
    danger:
      'border-[#f1c2ba] bg-[#fff1ee] text-[#b93823] hover:border-[#e8a79a] hover:bg-[#ffe7e1]',
  },
  solid: {
    neutral:
      'border-[#cfd5e1] bg-white text-[#191c1e] hover:border-[#b9c3d3] hover:bg-[#f7f8fa]',
    info: 'border-[#0c56d0] bg-[#0c56d0] text-white hover:border-[#094ab1] hover:bg-[#094ab1]',
    success:
      'border-[#18a058] bg-[#18a058] text-white hover:border-[#14854a] hover:bg-[#14854a]',
    warning:
      'border-[#d5a13e] bg-[#d5a13e] text-white hover:border-[#bb8c2f] hover:bg-[#bb8c2f]',
    danger:
      'border-[#d1331b] bg-[#d1331b] text-white hover:border-[#b02c17] hover:bg-[#b02c17]',
  },
  ghost: {
    neutral:
      'border-transparent bg-transparent text-[#191c1e] hover:border-[#d8dde7] hover:bg-white',
    info: 'border-transparent bg-transparent text-[#0c56d0] hover:border-[#c6d8ff] hover:bg-[#f4f7ff]',
    success:
      'border-transparent bg-transparent text-[#18a058] hover:border-[#b9e5c9] hover:bg-[#edf8f1]',
    warning:
      'border-transparent bg-transparent text-[#966f15] hover:border-[#ead7aa] hover:bg-[#fdf7ea]',
    danger:
      'border-transparent bg-transparent text-[#d1331b] hover:border-[#f1c2ba] hover:bg-[#fff1ee]',
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
