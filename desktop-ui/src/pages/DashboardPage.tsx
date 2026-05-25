import { getDashboardSummary } from '../api/dashboard';
import {
  DashboardRangePicker,
  createDashboardMetrics,
  createDashboardSeries,
  createDefaultDashboardCustomRange,
  formatApiError,
} from '../app/shared';
import { LineChart } from '../components/LineChart';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { Panel } from '../components/Panel';
import type { ApiDashboardSummary, DashboardRangePreset } from '../types';
import { getButtonClassName } from '../ui';
import { useEffect, useRef, useState } from 'react';

const DASHBOARD_AUTO_REFRESH_INTERVAL_MS = 30_000;

function DashboardPage() {
  const [summary, setSummary] = useState<ApiDashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const latestRequestIdRef = useRef(0);
  const backgroundRequestInFlightRef = useRef(false);
  const foregroundRequestCountRef = useRef(0);
  const defaultCustomRange = createDefaultDashboardCustomRange();
  const [dashboardRangePreset, setDashboardRangePreset] =
    useState<DashboardRangePreset>('all');
  const [customRangeDraft, setCustomRangeDraft] = useState(defaultCustomRange);
  const [appliedCustomRange, setAppliedCustomRange] =
    useState(defaultCustomRange);
  const dashboardMetrics = createDashboardMetrics(
    summary,
    dashboardRangePreset,
  );
  const dashboardSeries = createDashboardSeries(
    summary,
    dashboardRangePreset,
    appliedCustomRange,
  );
  const shouldShowEmptyAccounts =
    Boolean(summary) && (summary?.total_accounts ?? 0) === 0 && !isLoading;

  const loadDashboard = async (
    preset: DashboardRangePreset,
    customRange: { end: string; start: string },
    options: { silent?: boolean } = {},
  ) => {
    const isSilent = options.silent === true;
    if (isSilent) {
      if (
        backgroundRequestInFlightRef.current ||
        foregroundRequestCountRef.current > 0
      ) {
        return;
      }
      backgroundRequestInFlightRef.current = true;
    } else {
      foregroundRequestCountRef.current += 1;
      setIsLoading(true);
      setLoadError('');
    }
    const requestId = latestRequestIdRef.current + 1;
    latestRequestIdRef.current = requestId;

    try {
      const nextSummary = await getDashboardSummary({
          period: preset,
          dateFrom: preset === 'custom' ? customRange.start : undefined,
          dateTo: preset === 'custom' ? customRange.end : undefined,
      });
      if (requestId !== latestRequestIdRef.current) {
        return;
      }
      setSummary(nextSummary);
      setLoadError('');
    } catch (error) {
      if (requestId !== latestRequestIdRef.current) {
        return;
      }
      if (isSilent) {
        return;
      }
      setLoadError(
        formatApiError(error, 'Не удалось загрузить сводку дэшборда из API.'),
      );
    } finally {
      if (isSilent) {
        backgroundRequestInFlightRef.current = false;
        return;
      }
      foregroundRequestCountRef.current = Math.max(
        0,
        foregroundRequestCountRef.current - 1,
      );
      setIsLoading(foregroundRequestCountRef.current > 0);
    }
  };

  useEffect(() => {
    void loadDashboard(dashboardRangePreset, appliedCustomRange);
  }, [appliedCustomRange, dashboardRangePreset]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadDashboard(dashboardRangePreset, appliedCustomRange, {
        silent: true,
      });
    }, DASHBOARD_AUTO_REFRESH_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [appliedCustomRange, dashboardRangePreset]);

  const handleApplyCustomRange = () => {
    if (
      !customRangeDraft.start ||
      !customRangeDraft.end ||
      customRangeDraft.start > customRangeDraft.end
    ) {
      setLoadError('Укажи корректный диапазон дат для дэшборда.');
      return;
    }

    setAppliedCustomRange(customRangeDraft);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Обзор" />

      {loadError ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-error/15 bg-error/8 px-4 py-3 text-sm text-error">
          <span>{loadError}</span>
          <button
            className={getButtonClassName({
              tone: 'danger',
              size: 'sm',
            })}
            disabled={isLoading}
            type="button"
            onClick={() =>
              void loadDashboard(dashboardRangePreset, appliedCustomRange)
            }
          >
            Повторить
          </button>
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {dashboardMetrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </div>

      <div className="flex flex-col gap-6">
        <Panel
          title="Главная статистика"
          actions={
            <DashboardRangePicker
              customRange={customRangeDraft}
              isLoading={isLoading}
              preset={dashboardRangePreset}
              onApplyCustomRange={handleApplyCustomRange}
              onCustomRangeChange={(field, value) =>
                setCustomRangeDraft((previousValue) => ({
                  ...previousValue,
                  [field]: value,
                }))
              }
              onPresetChange={(preset) => setDashboardRangePreset(preset)}
            />
          }
        >
          {shouldShowEmptyAccounts ? (
            <div className="rounded-[22px] border border-dashed border-border/30 bg-secondary/40 p-6 text-center">
              <strong className="block text-text">Аккаунтов пока нет</strong>
              <p className="mt-2 leading-6 text-text-muted">
                После добавления аккаунтов здесь появится график публикаций и
                ошибок.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <LineChart data={dashboardSeries} height={260} />
              <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[15px] text-text-muted">
                <span className="inline-flex items-center gap-2">
                  <i className="h-2.5 w-2.5 rounded-full bg-[#45b99a]" />
                  Товары
                </span>
                <span className="inline-flex items-center gap-2">
                  <i className="h-2.5 w-2.5 rounded-full bg-[#ef6b7c]" />
                  Ошибки
                </span>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

export default DashboardPage;
