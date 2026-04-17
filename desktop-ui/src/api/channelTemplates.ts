import { request } from './client';
import type {
  ApiChannelTemplateCreate,
  ApiChannelTemplateSummary,
  ApiChannelTemplateUpdate,
} from '../types';

export async function listChannelTemplates(
  accountId: string,
): Promise<ApiChannelTemplateSummary[]> {
  return request<ApiChannelTemplateSummary[]>(
    `/accounts/${accountId}/channel-templates`,
  );
}

export async function createChannelTemplate(
  accountId: string,
  payload: ApiChannelTemplateCreate,
): Promise<ApiChannelTemplateSummary> {
  return request<ApiChannelTemplateSummary>(
    `/accounts/${accountId}/channel-templates`,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
  );
}

export async function updateChannelTemplate(
  accountId: string,
  templateName: string,
  payload: ApiChannelTemplateUpdate,
): Promise<ApiChannelTemplateSummary> {
  return request<ApiChannelTemplateSummary>(
    `/accounts/${accountId}/channel-templates/${encodeURIComponent(templateName)}`,
    {
      body: JSON.stringify(payload),
      method: 'PUT',
    },
  );
}

export async function deleteChannelTemplate(
  accountId: string,
  templateName: string,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(
    `/accounts/${accountId}/channel-templates/${encodeURIComponent(templateName)}`,
    {
      method: 'DELETE',
    },
  );
}
