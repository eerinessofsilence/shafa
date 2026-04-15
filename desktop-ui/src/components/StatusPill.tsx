import type { StatusTone } from '../types';
import type { ReactNode } from 'react';

interface StatusPillProps {
  tone?: StatusTone;
  children: ReactNode;
}

const toneClasses: Record<StatusTone, string> = {
  success: 'border-success text-success',
  warning: 'border-warning text-warning',
  info: 'border-info text-info',
  danger: 'border-error text-error',
  neutral: 'border-text-muted text-text-muted',
};

export function StatusPill({ tone = 'neutral', children }: StatusPillProps) {
  return (
    <p
      className={[
        'inline-flex items-center justify-center rounded-full border px-2 text-xs uppercase tracking-wider',
        toneClasses[tone],
      ].join(' ')}
    >
      {children}
    </p>
  );
}
