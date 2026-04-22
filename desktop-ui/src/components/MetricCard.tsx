import type { MetricAccent, MetricBadgeTone, MetricKind } from '../types';
import {
  CircleAlert,
  Package2,
  Radio,
  Users,
  type LucideIcon,
} from 'lucide-react';

interface MetricCardProps {
  kind: MetricKind;
  label: string;
  value: string;
  unit?: string;
  badge?: string;
  badgeTone?: MetricBadgeTone;
  accent: MetricAccent;
}

const iconByKind: Record<MetricKind, LucideIcon> = {
  accounts: Users,
  active: Radio,
  items: Package2,
  errors: CircleAlert,
};

const accentClasses: Record<
  MetricAccent,
  {
    border: string;
    iconWrap: string;
    icon: string;
    glow: string;
  }
> = {
  teal: {
    border: 'border-success/12',
    iconWrap: 'bg-success/14',
    icon: 'text-success',
    glow: 'bg-[radial-gradient(circle_at_top_left,rgba(24,160,88,0.13),transparent_42%)]',
  },
  amber: {
    border: 'border-warning/14',
    iconWrap: 'bg-warning/16',
    icon: 'text-warning',
    glow: 'bg-[radial-gradient(circle_at_top_left,rgba(240,163,62,0.14),transparent_42%)]',
  },
  blue: {
    border: 'border-info/12',
    iconWrap: 'bg-info/14',
    icon: 'text-info',
    glow: 'bg-[radial-gradient(circle_at_top_left,rgba(12,86,208,0.13),transparent_42%)]',
  },
  rose: {
    border: 'border-error/12',
    iconWrap: 'bg-error/14',
    icon: 'text-error',
    glow: 'bg-[radial-gradient(circle_at_top_left,rgba(209,51,27,0.14),transparent_42%)]',
  },
};

const badgeClasses: Record<MetricBadgeTone, string> = {
  teal: 'bg-success/10 text-success',
  amber: 'bg-warning/12 text-warning',
  blue: 'bg-info/10 text-info',
  rose: 'bg-error/10 text-error',
  neutral: 'bg-secondary text-text-muted',
};

export function MetricCard({
  accent,
  badgeTone,
  kind,
  label,
  unit,
  value,
}: MetricCardProps) {
  const accentClass = accentClasses[accent];
  const Icon = iconByKind[kind];
  const resolvedBadgeTone = badgeTone ?? accent;

  return (
    <article
      className={[
        'group relative isolate flex flex-col overflow-hidden rounded-2xl border bg-foreground p-5 transition-transform duration-200 hover:-translate-y-0.5',
        accentClass.border,
      ].join(' ')}
    >
      <div className={`absolute inset-0 ${accentClass.glow}`} />

      <div className="space-y-3">
        <div className="relative flex items-center gap-3">
          <span
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${accentClass.iconWrap}`}
          >
            <Icon className={`h-5 w-5 ${accentClass.icon}`} strokeWidth={2.2} />
          </span>
          <p className="text-sm font-medium text-text-muted">{label}</p>
        </div>

        <div className="relative mt-auto">
          <div className="mt-3 flex items-end gap-2">
            <h1 className="text-3xl font-semibold tracking-tight text-text">
              {value}
            </h1>
            {unit && value !== '—' ? (
              <span className="mb-0.5 text-[15px] font-medium text-text-faint">
                {unit}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}
