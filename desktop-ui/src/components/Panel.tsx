import { sectionTitleClassName } from '../ui';
import type { ReactNode } from 'react';

interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function Panel({ title, subtitle, actions, children }: PanelProps) {
  return (
    <section className="flex flex-col justify-between space-y-5 rounded-[12px] border border-[#cfd5e1] bg-white px-6 py-6 shadow-[0_1px_2px_rgba(15,23,42,0.02)]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <h3 className={sectionTitleClassName}>{title}</h3>
          {subtitle ? (
            <p className="text-[15px] leading-[1.45] text-[#737685]">
              {subtitle}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex gap-3 items-center">{actions}</div>
        ) : null}
      </div>
      {children}
    </section>
  );
}
