import { request } from './client';
import type {
  ApiAccountCreate,
  ApiAccountRead,
  ApiAccountUpdate,
} from '../types';

export async function listAccounts(): Promise<ApiAccountRead[]> {
  return request<ApiAccountRead[]>('/accounts');
}

export async function createAccount(
  payload: ApiAccountCreate,
): Promise<ApiAccountRead> {
  return request<ApiAccountRead>('/accounts', {
    body: JSON.stringify(payload),
    method: 'POST',
  });
}

export async function updateAccount(
  accountId: string,
  payload: ApiAccountUpdate,
): Promise<ApiAccountRead> {
  return request<ApiAccountRead>(`/accounts/${accountId}`, {
    body: JSON.stringify(payload),
    method: 'PATCH',
  });
}

export async function startAccount(
  accountId: string,
): Promise<ApiAccountRead> {
  return request<ApiAccountRead>(`/accounts/${accountId}/start`, {
    method: 'POST',
  });
}

export async function stopAccount(accountId: string): Promise<ApiAccountRead> {
  return request<ApiAccountRead>(`/accounts/${accountId}/stop`, {
    method: 'POST',
  });
}

export async function deleteAccount(
  accountId: string,
): Promise<{ detail: string }> {
  return request<{ detail: string }>(`/accounts/${accountId}`, {
    method: 'DELETE',
  });
}
