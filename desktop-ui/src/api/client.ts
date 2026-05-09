const runtimeApiBaseUrl =
  typeof window !== 'undefined'
    ? window.desktopShell?.apiBaseUrl?.replace(/\/+$/, '')
    : undefined;
const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '');
const apiBaseUrlSource = runtimeApiBaseUrl
  ? 'desktop'
  : configuredApiBaseUrl
    ? 'vite'
    : 'default';

export const apiBaseUrl =
  runtimeApiBaseUrl ||
  configuredApiBaseUrl ||
  'http://127.0.0.1:8000';

function buildUnavailableApiMessage() {
  if (apiBaseUrlSource === 'desktop') {
    return `API недоступно по адресу ${apiBaseUrl}. Проверь, что локальный backend запущен. В desktop-режиме адрес передаётся из Electron, а не через VITE_API_BASE_URL.`;
  }

  if (apiBaseUrlSource === 'vite') {
    return `API недоступно по адресу ${apiBaseUrl}. Проверь, что backend запущен и VITE_API_BASE_URL указан верно.`;
  }

  return `API недоступно по адресу ${apiBaseUrl}. Проверь, что backend запущен. Если UI открыт в браузере, при необходимости укажи VITE_API_BASE_URL.`;
}

export function buildApiUrl(path: string) {
  const normalizedPath = path.replace(/^\/+/, '');

  return new URL(normalizedPath, `${apiBaseUrl}/`).toString();
}

export function buildWebSocketUrl(path: string) {
  const url = new URL(buildApiUrl(path));
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';

  return url.toString();
}

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

export async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  const isFormDataBody = init?.body instanceof FormData;

  try {
    response = await fetch(buildApiUrl(path), {
      ...init,
      headers: {
        ...(isFormDataBody ? {} : { 'Content-Type': 'application/json' }),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiRequestError(buildUnavailableApiMessage(), 0);
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload?.detail) {
        message = payload.detail;
      }
    } catch {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }

    throw new ApiRequestError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
