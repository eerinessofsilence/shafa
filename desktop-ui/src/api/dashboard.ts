import { request } from './client';
import type { ApiDashboardSummary, DashboardRangePreset } from '../types';

interface GetDashboardSummaryParams {
  period?: DashboardRangePreset;
  dateFrom?: string;
  dateTo?: string;
}

export async function getDashboardSummary({
  period = 'all',
  dateFrom,
  dateTo,
}: GetDashboardSummaryParams = {}): Promise<ApiDashboardSummary> {
  const searchParams = new URLSearchParams();

  searchParams.set('period', period);

  if (dateFrom) {
    searchParams.set('date_from', dateFrom);
  }
  if (dateTo) {
    searchParams.set('date_to', dateTo);
  }

  return request<ApiDashboardSummary>(
    `/dashboard/summary?${searchParams.toString()}`,
  );
}
