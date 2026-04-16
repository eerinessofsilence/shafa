import type { ReactNode } from 'react';

interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function Panel({ title, subtitle, actions, children }: PanelProps) {
  return (
    <section className="rounded-2xl space-y-3 flex flex-col justify-between border border-border/25 bg-foreground p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <h3 className="text-[22px] text-text font-semibold">{title}</h3>
          {subtitle ? <p className="text-text-muted">{subtitle}</p> : null}
        </div>
        {actions ? (
          <div className="flex gap-3 items-center">{actions}</div>
        ) : null}
      </div>
      {children}
    </section>
  );
}
