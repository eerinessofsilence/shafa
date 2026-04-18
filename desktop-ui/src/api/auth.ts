import { request } from './client';
import type {
  ApiShafaAuthStatus,
  ApiShafaStorageStateRequest,
  ApiTelegramAuthStatus,
  ApiTelegramCodeRequest,
  ApiTelegramPasswordRequest,
  ApiTelegramPhoneRequest,
} from '../types';

export async function getTelegramAuthStatus(
  accountId: string,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(`/accounts/${accountId}/auth/telegram`);
}

export async function requestTelegramCode(
  accountId: string,
  payload: ApiTelegramPhoneRequest,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(
    `/accounts/${accountId}/auth/telegram/request-code`,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
  );
}

export async function submitTelegramCode(
  accountId: string,
  payload: ApiTelegramCodeRequest,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(
    `/accounts/${accountId}/auth/telegram/submit-code`,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
  );
}

export async function submitTelegramPassword(
  accountId: string,
  payload: ApiTelegramPasswordRequest,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(
    `/accounts/${accountId}/auth/telegram/submit-password`,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
  );
}

export async function logoutTelegram(
  accountId: string,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(`/accounts/${accountId}/auth/telegram/logout`, {
    method: 'POST',
  });
}

export async function importTelegramSession(
  accountId: string,
  file: File,
): Promise<ApiTelegramAuthStatus> {
  const formData = new FormData();
  formData.append('file', file);

  return request<ApiTelegramAuthStatus>(
    `/accounts/${accountId}/auth/telegram/import-session`,
    {
      body: formData,
      method: 'POST',
    },
  );
}

export async function getShafaAuthStatus(
  accountId: string,
): Promise<ApiShafaAuthStatus> {
  return request<ApiShafaAuthStatus>(`/accounts/${accountId}/auth/shafa`);
}

export async function saveShafaStorageState(
  accountId: string,
  payload: ApiShafaStorageStateRequest,
): Promise<ApiShafaAuthStatus> {
  return request<ApiShafaAuthStatus>(`/accounts/${accountId}/auth/shafa/cookies`, {
    body: JSON.stringify(payload),
    method: 'POST',
  });
}

export async function startShafaBrowserLogin(
  accountId: string,
): Promise<ApiShafaAuthStatus> {
  return request<ApiShafaAuthStatus>(
    `/accounts/${accountId}/auth/shafa/browser-login`,
    {
      method: 'POST',
    },
  );
}

export async function logoutShafa(
  accountId: string,
): Promise<ApiShafaAuthStatus> {
  return request<ApiShafaAuthStatus>(`/accounts/${accountId}/auth/shafa/logout`, {
    method: 'POST',
  });
}
