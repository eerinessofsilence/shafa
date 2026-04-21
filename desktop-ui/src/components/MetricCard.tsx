import type { MetricAccent } from '../types';

interface MetricCardProps {
  label: string;
  value: string;
  accent: MetricAccent;
}

const accentClasses: Record<MetricAccent, { bar: string; value: string }> = {
  teal: { bar: 'bg-[#64d79c]', value: 'text-[#18a058]' },
  amber: { bar: 'bg-[#f3bf68]', value: 'text-[#d48806]' },
  blue: { bar: 'bg-[#86b2ff]', value: 'text-[#2d73ea]' },
  rose: { bar: 'bg-[#f28b97]', value: 'text-[#e0344a]' },
};

export function MetricCard({ label, value, accent }: MetricCardProps) {
  const accentClass = accentClasses[accent];

  return (
    <article className="relative flex flex-col gap-2 overflow-hidden rounded-[12px] border border-[#cfd5e1] bg-white px-3 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.02)]">
      <div
        className={[
          'absolute inset-x-0 top-0 h-1.5',
          accentClass.bar,
        ].join(' ')}
      />
      <span className="text-[14px] font-medium text-[#2f3440]">{label}</span>
      <strong
        className={`leading-none text-[32px] tracking-tight ${accentClass.value}`}
      >
        {value}
      </strong>
    </article>
  );
}
