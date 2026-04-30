import type {
  ApiChannelTemplateRead,
  ApiChannelTemplateCreate,
  ApiChannelTemplateSummary,
  ApiChannelTemplateUpdate,
  ApiResolvedTelegramChannel,
  ChannelTemplateType,
} from '../types';
import { request } from './client';

export async function listGlobalChannelTemplates(options?: {
  type?: ChannelTemplateType;
}): Promise<ApiChannelTemplateRead[]> {
  const params = new URLSearchParams();

  if (options?.type) {
    params.set('type', options.type);
  }

  return request<ApiChannelTemplateRead[]>(
    `/channel-templates${params.size ? `?${params.toString()}` : ''}`,
  );
}

export async function createGlobalChannelTemplate(
  payload: ApiChannelTemplateCreate,
): Promise<ApiChannelTemplateRead> {
  return request<ApiChannelTemplateRead>('/channel-templates', {
    body: JSON.stringify(payload),
    method: 'POST',
  });
}

export async function updateGlobalChannelTemplate(
  templateId: string,
  payload: ApiChannelTemplateUpdate,
): Promise<ApiChannelTemplateRead> {
  return request<ApiChannelTemplateRead>(
    `/channel-templates/${encodeURIComponent(templateId)}`,
    {
      body: JSON.stringify(payload),
      method: 'PUT',
    },
  );
}

export async function deleteGlobalChannelTemplate(
  templateId: string,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(
    `/channel-templates/${encodeURIComponent(templateId)}`,
    {
      method: 'DELETE',
    },
  );
}

export async function resolveGlobalChannelTemplateLinks(
  links: string[],
): Promise<ApiResolvedTelegramChannel[]> {
  return request<ApiResolvedTelegramChannel[]>('/channel-templates/resolve', {
    body: JSON.stringify({ links }),
    method: 'POST',
  });
}

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
