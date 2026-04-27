import { contextBridge } from "electron";

const API_BASE_URL_ARGUMENT = "--shafa-api-base-url=";

function resolveApiBaseUrl(): string {
  const apiBaseUrlArgument = process.argv.find((argument) =>
    argument.startsWith(API_BASE_URL_ARGUMENT),
  );

  if (apiBaseUrlArgument) {
    const encodedValue = apiBaseUrlArgument.slice(API_BASE_URL_ARGUMENT.length);
    try {
      return decodeURIComponent(encodedValue);
    } catch {
      return encodedValue;
    }
  }

  return process.env.SHAFA_API_BASE_URL ?? "http://127.0.0.1:8000";
}

contextBridge.exposeInMainWorld("desktopShell", {
  apiBaseUrl: resolveApiBaseUrl(),
  platform: process.platform,
  electronVersion: process.versions.electron,
  chromeVersion: process.versions.chrome,
  cwd: process.cwd(),
});
