import { Download, Plus } from 'lucide-react';

import { LineChart } from '../components/LineChart';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import { StatusPill } from '../components/StatusPill';
import {
  dashboardMetrics,
  dashboardSeries,
  systemStatus,
} from '../data/mockData';

export function DashboardPage() {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Dashboard"
        actions={
          <>
            <button
              className="border inline-flex items-center gap-3 rounded-xl border-border/50 bg-success/12.5 cursor-pointer duration-200 transition-all active:scale-[0.975] hover:bg-success/25 hover:border-border/75 px-4 py-2"
              type="button"
            >
              <Download className="text-text w-4 h-4" />
              Экспорт отчета
            </button>
            <button
              className="border inline-flex items-center gap-3 active:scale-[0.975] rounded-xl border-border/50 hover:bg-info/25 cursor-pointer duration-200 transition-all hover:border-border/75 bg-info/12.5 px-4 py-2"
              type="button"
            >
              <Plus className="text-text w-4 h-4" />
              Создать запуск
            </button>
          </>
        }
      />

      <div className="grid grid-cols-4 gap-3">
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-4">
        <Panel title="Активность за смену">
          <LineChart data={dashboardSeries} height={260} />
        </Panel>

        <Panel
          title="Состояние системы"
          subtitle="Сводка по окружению и очередям"
        >
          <div className="grid grid-cols-3 gap-2">
            {systemStatus.map((item) => (
              <div
                className="border-border/25 space-y-2 rounded-xl border bg-secondary/50 p-3"
                key={item.label}
              >
                <div className="flex items-center justify-between">
                  <span className="text-text font-medium">{item.label}</span>
                  <StatusPill tone={item.tone}>{item.badge}</StatusPill>
                </div>
                <p className="leading-6">{item.value}</p>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
