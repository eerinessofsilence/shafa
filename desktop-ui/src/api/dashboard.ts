import { request } from './client';
import type { ApiDashboardSummary } from '../types';

export async function getDashboardSummary(): Promise<ApiDashboardSummary> {
  return request<ApiDashboardSummary>('/dashboard/summary');
}
