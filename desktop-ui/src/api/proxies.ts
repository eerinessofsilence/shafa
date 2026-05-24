import { request } from './client';
import type {
  ApiProxyCreate,
  ApiProxyRead,
  ApiProxyUpdate,
} from '../types';

export async function listProxies(): Promise<ApiProxyRead[]> {
  return request<ApiProxyRead[]>('/proxies');
}

export async function createProxy(
  payload: ApiProxyCreate,
): Promise<ApiProxyRead> {
  return request<ApiProxyRead>('/proxies', {
    body: JSON.stringify(payload),
    method: 'POST',
  });
}

export async function updateProxy(
  proxyId: string,
  payload: ApiProxyUpdate,
): Promise<ApiProxyRead> {
  return request<ApiProxyRead>(`/proxies/${proxyId}`, {
    body: JSON.stringify(payload),
    method: 'PATCH',
  });
}

export async function deleteProxy(
  proxyId: string,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/proxies/${proxyId}`, {
    method: 'DELETE',
  });
}
