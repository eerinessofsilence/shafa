import type { MetricAccent } from '../types';

interface MetricCardProps {
  label: string;
  value: string;
  accent: MetricAccent;
}

const accentClasses: Record<MetricAccent, { bar: string; value: string }> = {
  teal: { bar: 'bg-success/75', value: 'text-success' },
  amber: { bar: 'bg-warning/75', value: 'text-warning' },
  blue: { bar: 'bg-info/75', value: 'text-info' },
  rose: { bar: 'bg-error/75', value: 'text-error' },
};

export function MetricCard({ label, value, accent }: MetricCardProps) {
  const accentClass = accentClasses[accent];

  return (
    <article className="relative flex  flex-col gap-2 overflow-hidden rounded-xl border border-border/25 bg-secondary/50 p-2.5 pt-4.5">
      <div
        className={[
          'absolute inset-x-0 top-0 h-2 opacity-70',
          accentClass.bar,
        ].join(' ')}
      />
      <span className="font-medium">{label}</span>
      <strong
        className={`leading-none text-3xl tracking-tighter ${accentClass.value}`}
      >
        {value}
      </strong>
    </article>
  );
}
