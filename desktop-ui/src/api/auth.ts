import { request } from './client';
import type {
  ApiShafaAuthStatus,
  ApiShafaStorageStateRequest,
  ApiTelegramAuthStatus,
  ApiTelegramCodeRequest,
  ApiTelegramCredentialsRequest,
  ApiTelegramPasswordRequest,
  ApiTelegramPhoneRequest,
} from '../types';

export async function getTelegramAuthStatus(
  accountId: string,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(`/accounts/${accountId}/auth/telegram`);
}

export async function saveTelegramCredentials(
  accountId: string,
  payload: ApiTelegramCredentialsRequest,
): Promise<ApiTelegramAuthStatus> {
  return request<ApiTelegramAuthStatus>(
    `/accounts/${accountId}/auth/telegram/credentials`,
    {
      body: JSON.stringify(payload),
      method: 'POST',
    },
  );
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
