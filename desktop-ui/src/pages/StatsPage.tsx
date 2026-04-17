import { CalendarRange, Filter } from 'lucide-react';

import { ActionButton } from '../components/ActionButton';
import { LineChart } from '../components/LineChart';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { StatusPill } from '../components/StatusPill';
import { logRecords, statsMetrics, statsSeries } from '../data/mockData';
import { surfaceCardClassName } from '../lib/ui';

export function StatsPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Статистика"
        actions={
          <>
            <ActionButton
              compact
              icon={<CalendarRange className="h-4 w-4 text-text" />}
              tone="neutral"
            >
              7 дней
            </ActionButton>
            <ActionButton compact tone="info">
              30 дней
            </ActionButton>
          </>
        }
      />

      <div className="grid grid-cols-4 gap-3">
        {statsMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-5">
        <Panel
          title="График публикаций"
          subtitle="Серия items/errors для desktop-макета"
        >
          <LineChart data={statsSeries} height={320} />
        </Panel>

        <Panel
          title="Логи и события"
          subtitle="Поток ошибок и технических состояний теперь встроен в статистику"
          actions={
            <>
              <ActionButton
                compact
                icon={<Filter className="h-4 w-4 text-text" />}
                tone="neutral"
              >
                Все аккаунты
              </ActionButton>
              <ActionButton compact tone="warning">
                Только ошибки
              </ActionButton>
            </>
          }
        >
          <div className="flex flex-col gap-3">
            {logRecords.map((record) => (
              <div
                key={`${record.time}-${record.message}`}
                className={`${surfaceCardClassName} grid gap-4 xl:grid-cols-[170px_minmax(0,1fr)]`}
              >
                <div className="flex flex-col gap-2.5">
                  <span className="text-text-muted">{record.time}</span>
                  <div>
                    <StatusPill tone={record.tone}>{record.level}</StatusPill>
                  </div>
                </div>
                <div>
                  <strong className="block text-[1.05rem]">
                    {record.account}
                  </strong>
                  <p className="mt-3 leading-8 text-text-muted">
                    {record.message}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
