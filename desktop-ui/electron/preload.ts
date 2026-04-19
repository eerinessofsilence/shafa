import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("desktopShell", {
  apiBaseUrl: process.env.SHAFA_API_BASE_URL ?? "http://127.0.0.1:8000",
  platform: process.platform,
  electronVersion: process.versions.electron,
  chromeVersion: process.versions.chrome,
  cwd: process.cwd(),
});
